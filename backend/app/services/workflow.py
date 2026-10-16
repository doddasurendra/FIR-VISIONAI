"""
Post-intake automated intelligence workflow orchestrator.
Runs classification → entity extraction → AI summary stages asynchronously.
All stages are idempotent and safe to retry.
"""
from __future__ import annotations
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def _upsert_workflow_stage(
    db: AsyncSession,
    case_id: str,
    stage: str,
    status: str,
    result_summary: str | None = None,
    error_message: str | None = None,
) -> None:
    """Insert or update a workflow execution record for a case stage."""
    # Late import to avoid circular imports at module load time
    from ..models.folder import WorkflowExecution
    from ..models.base import generate_uuid

    stmt = select(WorkflowExecution).where(
        WorkflowExecution.case_id == case_id,
        WorkflowExecution.stage == stage,
    )
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.status = status
        existing.result_summary = result_summary
        existing.error_message = error_message
        if status == "RUNNING" and not existing.started_at:
            existing.started_at = now
        if status in ("COMPLETED", "FAILED", "SKIPPED"):
            existing.completed_at = now
    else:
        wf = WorkflowExecution(
            id=generate_uuid(),
            case_id=case_id,
            stage=stage,
            status=status,
            started_at=now if status == "RUNNING" else None,
            completed_at=now if status in ("COMPLETED", "FAILED", "SKIPPED") else None,
            result_summary=result_summary,
            error_message=error_message,
        )
        db.add(wf)
    await db.commit()


async def _run_classification_stage(db: AsyncSession, case_id: str) -> None:
    """Classify case text and assign to best-matching FIR folder."""
    from ..models.case import Case
    from ..models.folder import FIRFolder, CaseFolderAssignment
    from ..models.document import DocumentChunk
    from ..models.base import generate_uuid
    try:
        from .classification import classify_case_text
    except ImportError:
        classify_case_text = None

    await _upsert_workflow_stage(db, case_id, "CLASSIFICATION", "RUNNING")
    try:
        # Load case
        case_res = await db.execute(select(Case).where(Case.id == case_id))
        case = case_res.scalar_one_or_none()
        if not case:
            await _upsert_workflow_stage(db, case_id, "CLASSIFICATION", "FAILED",
                                         error_message="Case not found")
            return

        # Gather document chunks for this case
        from ..models.document import Document
        doc_res = await db.execute(select(Document.id).where(Document.case_id == case_id))
        doc_ids = [row[0] for row in doc_res.all()]

        full_text_parts = []
        if doc_ids:
            chunk_res = await db.execute(
                select(DocumentChunk.chunk_text)
                .where(DocumentChunk.document_id.in_(doc_ids))
                .limit(200)
            )
            full_text_parts = [row[0] for row in chunk_res.all() if row[0]]

        full_text = " ".join(full_text_parts)
        if classify_case_text:
            result = classify_case_text(
                full_text=full_text,
                offence_nature=case.offence_nature,
                offence_category=case.offence_category,
            )
        else:
            from dataclasses import dataclass
            @dataclass
            class FallbackResult:
                folder_slug: str = "pending-classification"
                confidence: float = 0.0
                evidence_snippets: list[str] = ()
            result = FallbackResult()

        # Find or create the folder
        folder_res = await db.execute(
            select(FIRFolder).where(FIRFolder.slug == result.folder_slug)
        )
        folder = folder_res.scalar_one_or_none()
        if not folder:
            # Fallback to pending-classification folder
            folder_res = await db.execute(
                select(FIRFolder).where(FIRFolder.slug == "pending-classification")
            )
            folder = folder_res.scalar_one_or_none()

        if folder:
            # Remove existing AUTO assignments for this case
            existing_res = await db.execute(
                select(CaseFolderAssignment).where(
                    CaseFolderAssignment.case_id == case_id,
                    CaseFolderAssignment.assignment_source == "AUTO",
                )
            )
            for existing_assignment in existing_res.scalars().all():
                await db.delete(existing_assignment)

            # Create new assignment
            assignment = CaseFolderAssignment(
                id=generate_uuid(),
                case_id=case_id,
                folder_id=folder.id,
                is_primary=True,
                confidence_score=result.confidence,
                assignment_source="AUTO",
                notes=json.dumps(result.evidence_snippets[:2]) if getattr(result, "evidence_snippets", None) else None,
            )
            db.add(assignment)

        # Update case classification status
        case.classification_status = "CLASSIFIED" if result.confidence >= 0.25 else "PENDING"
        case.classification_confidence = result.confidence
        case.classification_source = "AUTO"

        await db.commit()
        await _upsert_workflow_stage(
            db, case_id, "CLASSIFICATION", "COMPLETED",
            result_summary=json.dumps({
                "folder_slug": result.folder_slug,
                "confidence": result.confidence,
            })
        )
        logger.info(f"Case {case_id} classified → {result.folder_slug} (conf={result.confidence})")

    except Exception as exc:
        logger.exception(f"Classification failed for case {case_id}: {exc}")
        await _upsert_workflow_stage(db, case_id, "CLASSIFICATION", "FAILED",
                                     error_message=str(exc))


async def trigger_post_intake_workflow(case_id: str, db: AsyncSession) -> None:
    """
    Entry point: trigger the automated post-intake intelligence workflow.
    Runs asynchronously in the background after a case is saved.
    Stages: CLASSIFICATION (entity extraction & AI summary are placeholders for future phases).
    """
    try:
        await _run_classification_stage(db, case_id)
    except Exception as exc:
        logger.exception(f"Workflow failed for case {case_id}: {exc}")
