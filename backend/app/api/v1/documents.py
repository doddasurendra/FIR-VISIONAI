import os
import shutil
import json
import asyncio
import logging
import hashlib
import mimetypes
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse, Response
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, and_, func
from ...config import settings
from ...database import get_db, AsyncSessionLocal
from ...models.user import User
from ...models.document import Document, DocumentPage
from ...models.case import Case
from ...models.extraction import ExtractionConfig, ExtractionRun
from ...models.base import generate_uuid
from ...services.auth import get_current_user, enforce_data_scope
from ...services.pdf_pipeline import pdf_pipeline
from ...services.audit import log_audit_event
from ...services.storage import storage_service
from ...services.gemini import gemini_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Document Ingestion & Evidence Viewer"])

# ── In-process background job tracker ────────────────────────────────────────
# Keyed by job_id (UUID string). Safe: each job entry is per-upload, per-user.
# Stages: UPLOADED → OCR_PROCESSING → EXTRACTING → INDEXING → COMPLETED | FAILED
_PROCESSING_JOBS: Dict[str, Dict[str, Any]] = {}
_MAX_JOBS = 500  # evict oldest when full


def _job_create(job_id: str, document_id: str, filename: str, user_id: str) -> None:
    if len(_PROCESSING_JOBS) >= _MAX_JOBS:
        # Evict oldest 50 completed jobs
        done = [k for k, v in _PROCESSING_JOBS.items() if v["stage"] in ("COMPLETED", "FAILED")]
        for k in done[:50]:
            _PROCESSING_JOBS.pop(k, None)
    _PROCESSING_JOBS[job_id] = {
        "job_id": job_id,
        "document_id": document_id,
        "filename": filename,
        "user_id": user_id,
        "stage": "UPLOADED",
        "progress_pct": 5,
        "error": None,
        "extraction_payload": None,
        "run_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _persist_processing_failure(document_id: str, message: str) -> None:
    """
    Record a background failure on the document itself. The in-memory job disappears on restart;
    without this the document stayed PROCESSING forever and the officer could only re-upload.
    """
    try:
        async with AsyncSessionLocal() as s:
            doc = (await s.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
            if doc and doc.ingestion_status in ("PROCESSING", "PENDING"):
                doc.ingestion_status = "FAILED"
                doc.index_status = "FAILED"
                doc.error_message = message[:1000]
                await s.commit()
    except Exception as e:
        logger.error(f"Could not record processing failure for {document_id}: {e}")


def _job_update(job_id: str, stage: str, progress_pct: int, error: str | None = None) -> None:
    if job_id in _PROCESSING_JOBS:
        _PROCESSING_JOBS[job_id]["stage"] = stage
        _PROCESSING_JOBS[job_id]["progress_pct"] = progress_pct
        _PROCESSING_JOBS[job_id]["error"] = error
        _PROCESSING_JOBS[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()


async def _run_background_processing(
    job_id: str,
    document_id: str,
    local_path: str,
    original_filename: str,
    detected_mime: str,
    user_id: str,
    case_id: Optional[str],
    storage_type: str,
    stored_path: Optional[str] = None,
) -> None:
    """
    Background coroutine: OCR → Extraction → Indexing.
    Uses its OWN database session (not the upload request's session which is closed).
    Records real stage progress in _PROCESSING_JOBS. Never creates duplicate records.
    """
    async with AsyncSessionLocal() as db:
        try:
            # Stage 1: OCR / PDF parsing (already saved doc record — just update it)
            _job_update(job_id, "OCR_PROCESSING", 15)
            doc = None
            try:
                res = await db.execute(select(Document).where(Document.id == document_id))
                doc = res.scalar_one_or_none()
            except Exception:
                pass

            if not doc:
                _job_update(job_id, "FAILED", 0, "Document record not found for background processing.")
                return

            try:
                processed_doc = await pdf_pipeline.process_document(
                    file_path=local_path,
                    original_filename=original_filename,
                    mime_type=detected_mime,
                    user_id=user_id,
                    db=db,
                    case_id=case_id,
                    stored_path=stored_path,
                )
                document_id = processed_doc.id  # may be same or the deduplicated existing doc
            except Exception as ocr_err:
                logger.error(f"Background OCR/pipeline failed for job {job_id}: {ocr_err}")
                message = f"Document processing error: {str(ocr_err)[:200]}"
                try:
                    await db.rollback()
                except Exception:
                    pass
                # Saved before the job reports FAILED: a client that sees FAILED and retries at once must
                # find the document FAILED (retryable), not still PROCESSING
                await _persist_processing_failure(document_id, message + " Use 'Retry processing' to try again.")
                _job_update(job_id, "FAILED", 15, message)
                return

            _job_update(job_id, "EXTRACTING", 55)

            # Stage 2: Structured field extraction
            extraction_payload: dict = {}
            run = None
            try:
                from sqlalchemy import desc as sqla_desc
                from ...models.document import DocumentPage as DP
                from .extraction import _execute_extraction, DEFAULT_FIR_SCHEMA, DEFAULT_INSTRUCTIONS

                p_stmt = select(DP).where(DP.document_id == document_id).order_by(DP.physical_page_number.asc())
                p_res = await db.execute(p_stmt)
                pages = p_res.scalars().all()

                cfg_stmt = select(ExtractionConfig).where(ExtractionConfig.is_active == True).order_by(sqla_desc(ExtractionConfig.version))
                cfg_res = await db.execute(cfg_stmt)
                config = cfg_res.scalars().first()
                if not config:
                    config = ExtractionConfig(
                        id="cfg-default-fir",
                        name="FIR Standard Extraction",
                        version=1,
                        schema_json=json.dumps(DEFAULT_FIR_SCHEMA),
                        instructions=DEFAULT_INSTRUCTIONS,
                        sarvam_config_id=None,
                        is_active=True,
                    )
                    db.add(config)
                    await db.flush()

                extraction_payload = await _execute_extraction(processed_doc, pages, config, user_id)

                run = ExtractionRun(
                    id=generate_uuid(),
                    document_id=document_id,
                    config_id=config.id,
                    config_version=config.version,
                    status="COMPLETED",
                    raw_extracted_json=json.dumps(extraction_payload),
                    reviewed_extracted_json=json.dumps(extraction_payload),
                    case_id=case_id,
                    sarvam_job_id=extraction_payload.get("sarvam_job_id"),
                    created_by=user_id,
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)
                if extraction_payload.get("page_text_updated"):
                    from ...services.ingestion import reindex_after_recovered_text
                    await reindex_after_recovered_text(db, processed_doc, user_id)
            except Exception as ext_err:
                logger.warning(f"Background extraction failed for job {job_id}: {ext_err}")
                try:
                    await db.rollback()
                except Exception:
                    pass
                extraction_payload = {}

            # Chunking, embedding and index verification already ran inside process_document
            _job_update(job_id, "INDEXING", 90)

            # Mark complete — store extraction payload for the frontend to pick up
            flat_extracted: dict = {}
            if extraction_payload.get("structured_fields"):
                for f in extraction_payload["structured_fields"]:
                    k = f.get("key")
                    if k:
                        flat_extracted[k] = f.get("value")

            # Report the document's real outcome (e.g. text unreadable -> needs review), not just "done"
            try:
                final_doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
            except Exception:
                final_doc = None
            if final_doc is not None and (final_doc.index_status in ("NEEDS_REVIEW", "FAILED")
                                          or final_doc.ingestion_status in ("NEEDS_REVIEW", "FAILED")):
                _PROCESSING_JOBS[job_id]["warning"] = (final_doc.error_message or "The document's text could not be read reliably.") + \
                    " Review the extracted fields carefully, or use 'Retry processing'."
            _PROCESSING_JOBS[job_id]["document_status"] = final_doc.index_status if final_doc is not None else None
            _PROCESSING_JOBS[job_id]["stage"] = "COMPLETED"
            _PROCESSING_JOBS[job_id]["progress_pct"] = 100
            _PROCESSING_JOBS[job_id]["run_id"] = run.id if run else None
            _PROCESSING_JOBS[job_id]["extraction_payload"] = extraction_payload
            _PROCESSING_JOBS[job_id]["extracted_data"] = flat_extracted
            _PROCESSING_JOBS[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

            # Clean up Supabase temp cache file if applicable
            if storage_type == "SUPABASE" and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass

            logger.info(f"Background job {job_id} COMPLETED for document {document_id[:8]}")

        except Exception as fatal_err:
            logger.error(f"Fatal error in background job {job_id}: {fatal_err}", exc_info=True)
            try:
                await db.rollback()
            except Exception:
                pass
            await _persist_processing_failure(
                document_id, f"Unexpected processing error: {str(fatal_err)[:300]} Use 'Retry processing' to try again.")
            _job_update(job_id, "FAILED", 0, f"Unexpected error: {str(fatal_err)[:300]}")

# Supported MIME types mapped to file-header magic bytes (for backend content validation)
SUPPORTED_MIME_TYPES = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png":  [b"\x89PNG"],
    "image/webp": [b"RIFF"],
}
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _detect_mime_type(filename: str, file_bytes: bytes) -> str:
    """
    Detect MIME type using actual file magic bytes (do NOT trust filename alone).
    Returns detected MIME type string, or raises HTTPException for unsupported/unsafe files.
    """
    ext = os.path.splitext(filename.lower())[1]
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported formats: PDF, JPG, JPEG, PNG, WEBP."
        )

    header = file_bytes[:12]

    # PDF detection
    if header[:4] == b"%PDF":
        return "application/pdf"

    # JPEG detection
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    # PNG detection
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    # WebP detection (RIFF....WEBP)
    if header[:4] == b"RIFF" and len(file_bytes) > 12 and file_bytes[8:12] == b"WEBP":
        return "image/webp"

    raise HTTPException(
        status_code=400,
        detail=(
            f"The uploaded file '{filename}' has an unrecognized or unsafe content signature. "
            "Please upload a valid PDF, JPEG, PNG, or WEBP document."
        )
    )


@router.get("/storage-status")
async def get_storage_status(current_user: User = Depends(get_current_user)):
    """Return cloud storage status diagnostics."""
    return storage_service.get_status()


@router.get("/jobs/{job_id}/status")
async def get_processing_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Poll the status of a background document-processing job.
    Returns stage (UPLOADED/OCR_PROCESSING/EXTRACTING/INDEXING/COMPLETED/FAILED),
    progress percentage, and extracted data once completed.
    Only the user who initiated the job can view it.
    """
    job = _PROCESSING_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found. It may have expired.")
    if job["user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied: this job belongs to a different user.")

    response = {
        "job_id": job_id,
        "document_id": job["document_id"],
        "filename": job["filename"],
        "stage": job["stage"],
        "progress_pct": job["progress_pct"],
        "error": job["error"],
        "run_id": job.get("run_id"),
        "warning": job.get("warning"),
        "document_status": job.get("document_status"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }
    if job["stage"] == "COMPLETED":
        response["extraction_payload"] = job.get("extraction_payload") or {}
        response["extracted_data"] = job.get("extracted_data") or {}
    return response


def _flatten_fields(payload: dict) -> dict:
    return {f.get("key"): f.get("value") for f in (payload.get("structured_fields") or []) if f.get("key")}


async def _start_intake_processing(db: AsyncSession, doc: Document, user: User) -> str:
    """(Re)start OCR + extraction for an existing uploaded document; returns the new job id."""
    from ...services.ingestion import materialize_document_file
    path, is_temp = await materialize_document_file(doc)
    if not path:
        raise HTTPException(status_code=404, detail={
            "code": "ORIGINAL_FILE_MISSING",
            "message": "The original file is not in storage, so it cannot be processed again. Upload the file again."})
    doc.ingestion_status = "PROCESSING"
    doc.error_message = None
    doc.updated_at = datetime.utcnow()
    await db.commit()
    job_id = generate_uuid()
    _job_create(job_id, doc.id, doc.original_filename, user.id)
    asyncio.create_task(_run_background_processing(
        job_id=job_id, document_id=doc.id, local_path=path, original_filename=doc.original_filename,
        detected_mime=doc.mime_type or "application/pdf", user_id=user.id, case_id=doc.case_id,
        storage_type="SUPABASE" if is_temp else "LOCAL", stored_path=doc.stored_path,
    ))
    return job_id


@router.get("/{document_id}/intake-status")
async def get_intake_status(document_id: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """
    Processing state of an uploaded document, read from the database, so the intake page can
    recover after the in-memory job is gone (server restart or reload). Stages: PROCESSING,
    INTERRUPTED (stalled; retry), FAILED (retry), COMPLETED (with the latest extraction, if any).
    """
    from ...services.document_access import get_authorized_document
    from ...services.ingestion import effective_status
    doc = await get_authorized_document(db, current_user, document_id)
    state = effective_status(doc)
    base = {"document_id": doc.id, "filename": doc.original_filename, "index_status": doc.index_status}
    if state == "PROCESSING":
        return {**base, "stage": "PROCESSING", "error": None}
    if state == "STALLED":
        return {**base, "stage": "INTERRUPTED", "retryable": True,
                "error": "Processing was interrupted (for example by a server restart) before it finished. "
                         "Use 'Retry processing'; the file does not need to be uploaded again."}
    if state == "FAILED":
        return {**base, "stage": "FAILED", "retryable": True,
                "error": doc.error_message or "Processing failed. Use 'Retry processing'."}
    run = (await db.execute(select(ExtractionRun).where(ExtractionRun.document_id == doc.id, ExtractionRun.status == "COMPLETED")
                            .order_by(desc(ExtractionRun.created_at)))).scalars().first()
    payload = {}
    if run:
        try:
            payload = json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")
        except Exception:
            payload = {}
    warning = None
    if doc.index_status in ("NEEDS_REVIEW", "FAILED") or state == "NEEDS_REVIEW":
        warning = (doc.error_message or "The document's text could not be read reliably.") + \
            " Review the extracted fields carefully, or use 'Retry processing'."
    return {**base, "stage": "COMPLETED", "run_id": run.id if run else None, "warning": warning,
            "retryable": warning is not None, "extraction_payload": payload, "extracted_data": _flatten_fields(payload)}


@router.post("/{document_id}/intake-retry")
async def retry_intake_processing(document_id: str, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Process an uploaded FIR document again (OCR and extraction) without a new upload."""
    from ...services.document_access import STATEWIDE_CATEGORIES, get_authorized_document
    from ...services.ingestion import effective_status
    doc = await get_authorized_document(db, current_user, document_id)
    if (doc.doc_category or "").upper() in STATEWIDE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Reference documents are reprocessed from the Knowledge Base.")
    if effective_status(doc) == "PROCESSING":
        raise HTTPException(status_code=409, detail="This document is still being processed. Wait for it to finish.")
    job_id = await _start_intake_processing(db, doc, current_user)
    await log_audit_event(db=db, actor_id=current_user.id, actor_username=current_user.username,
                          action_type="DOCUMENT_REPROCESS_REQUESTED", object_type="DOCUMENT", object_id=doc.id,
                          after_state={"mode": "intake", "job_id": job_id})
    return {"job_id": job_id, "document_id": doc.id, "stage": "UPLOADED", "status": "PROCESSING"}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload FIR evidence document (PDF, JPEG, PNG, or WEBP).
    Returns immediately with a job_id after saving the file.
    OCR, extraction, and indexing run in the background — poll /jobs/{job_id}/status.
    """
    file_bytes = await file.read()
    return await ingest_file_bytes(db, current_user, file.filename, file_bytes, case_id)


async def ingest_file_bytes(db: AsyncSession, current_user: User, filename: str, file_bytes: bytes,
                            case_id: Optional[str] = None) -> dict:
    """
    The upload pipeline for one file (also used by bulk scanned-FIR ingestion): size and type checks,
    reuse of an identical already-processed file, resume of an unfinished one, storage, audit, and
    background OCR -> extraction -> indexing. Raises HTTPException for files that cannot be accepted.
    """
    # 1. Enforce size limit
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the maximum allowed size of 50 MB. Please reduce the file size."
        )

    # 2. Content-based MIME detection
    detected_mime = _detect_mime_type(filename, file_bytes)

    # 2b. Hash and deduplication check
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    dup_stmt = select(Document).where(
        Document.file_hash == file_hash,
        Document.ingestion_status == "COMPLETED"
    ).order_by(desc(Document.created_at))
    dup_res = await db.execute(dup_stmt)
    existing_doc = dup_res.scalars().first()

    if existing_doc:
        run_stmt = select(ExtractionRun).where(
            ExtractionRun.document_id == existing_doc.id,
            ExtractionRun.status == "COMPLETED"
        ).order_by(desc(ExtractionRun.created_at))
        run_res = await db.execute(run_stmt)
        existing_run = run_res.scalars().first()

        if existing_run:
            logger.info(f"Deduplication hit: Reusing existing extraction for {filename} (hash={file_hash[:12]})")
            if case_id and not existing_doc.case_id:
                existing_doc.case_id = case_id
                await db.commit()

            try:
                extraction_payload = json.loads(existing_run.reviewed_extracted_json or existing_run.raw_extracted_json or "{}")
            except Exception:
                extraction_payload = {}

            flat_extracted = {}
            if extraction_payload.get("structured_fields"):
                for f in extraction_payload["structured_fields"]:
                    k = f.get("key")
                    if k:
                        flat_extracted[k] = f.get("value")

            # Create a synthetic completed job entry for UI consistency
            job_id = generate_uuid()
            _job_create(job_id, existing_doc.id, filename, current_user.id)
            _PROCESSING_JOBS[job_id]["stage"] = "COMPLETED"
            _PROCESSING_JOBS[job_id]["progress_pct"] = 100
            _PROCESSING_JOBS[job_id]["run_id"] = existing_run.id
            _PROCESSING_JOBS[job_id]["extraction_payload"] = extraction_payload
            _PROCESSING_JOBS[job_id]["extracted_data"] = flat_extracted

            return {
                "job_id": job_id,
                "id": existing_doc.id,
                "document_id": existing_doc.id,
                "run_id": existing_run.id,
                "filename": existing_doc.original_filename,
                "mime_type": existing_doc.mime_type,
                "physical_page_count": existing_doc.physical_page_count,
                "is_image": (existing_doc.mime_type or "").startswith("image/"),
                "file_hash": existing_doc.file_hash,
                "status": "COMPLETED",
                "stage": "COMPLETED",
                "progress_pct": 100,
                "storage_type": "DEDUPLICATED_CACHE",
                "is_deduplicated": True,
                "extraction_payload": extraction_payload,
                "extracted_data": flat_extracted,
                "structured_fields": extraction_payload.get("structured_fields", []),
                "entities": extraction_payload.get("entities", []),
                "key_points": extraction_payload.get("key_points", []),
                "warnings": extraction_payload.get("warnings", []),
                "document_content": extraction_payload.get("document_content"),
                "pages_content": extraction_payload.get("pages_content", []),
                "document_metadata": extraction_payload.get("document_metadata", {}),
                "raw_text_summary": extraction_payload.get("raw_text_summary"),
                "provider": extraction_payload.get("provider"),
            }

    # 2c. The same file uploaded earlier but never finished (failed, or interrupted by a restart):
    # resume that record instead of creating a duplicate document
    from ...services.document_access import user_can_access_document
    from ...services.ingestion import effective_status
    unfinished = (await db.execute(
        select(Document).where(Document.file_hash == file_hash, Document.is_archived == False,  # noqa: E712
                               Document.ingestion_status.in_(("PROCESSING", "PENDING", "FAILED")))
        .order_by(desc(Document.created_at))
    )).scalars().first()
    if unfinished and await user_can_access_document(db, current_user, unfinished):
        if effective_status(unfinished) == "PROCESSING":
            raise HTTPException(status_code=409, detail={
                "code": "ALREADY_PROCESSING", "document_id": unfinished.id,
                "message": "This file is already being processed. Wait for it to finish; it does not need to be uploaded again."})
        if case_id and not unfinished.case_id:
            unfinished.case_id = case_id
        job_id = await _start_intake_processing(db, unfinished, current_user)
        logger.info(f"Upload of {filename} resumed unfinished document {unfinished.id[:8]} instead of duplicating it")
        return {
            "job_id": job_id, "id": unfinished.id, "document_id": unfinished.id, "filename": unfinished.original_filename,
            "mime_type": unfinished.mime_type, "file_hash": file_hash, "is_image": (unfinished.mime_type or "").startswith("image/"),
            "status": "PROCESSING", "stage": "UPLOADED", "progress_pct": 5, "resumed_existing": True,
            "message": "This file was uploaded before but not processed; processing it again on the same record.",
        }

    # 3. Store file via StorageService
    storage_meta = await storage_service.upload_file(
        file_bytes=file_bytes,
        filename=filename,
        content_type=detected_mime
    )

    # 4. Resolve local path for processing
    local_path = storage_meta["stored_path"]
    if storage_meta["storage_type"] == "SUPABASE":
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{storage_meta['file_hash'][:8]}_{filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    # 5. Create a stub Document record immediately (status=PROCESSING) so UI can reference it.
    # The record keeps the permanent storage key; the cloud cache copy is deleted after processing.
    doc_stub = Document(
        case_id=case_id,
        original_filename=filename,
        stored_path=storage_meta["stored_path"],
        file_hash=file_hash,
        mime_type=detected_mime,
        physical_page_count=0,
        ingestion_status="PROCESSING",
        created_by=current_user.id,
    )
    db.add(doc_stub)
    await db.commit()
    await db.refresh(doc_stub)

    # 6. Register background job
    job_id = generate_uuid()
    _job_create(job_id, doc_stub.id, filename, current_user.id)

    # 7. Audit the upload immediately
    try:
        await log_audit_event(
            db=db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="DOCUMENT_UPLOADED",
            object_type="DOCUMENT",
            object_id=doc_stub.id,
            after_state={
                "filename": filename,
                "mime_type": detected_mime,
                "hash": file_hash,
                "storage_type": storage_meta["storage_type"],
                "job_id": job_id,
            }
        )
    except Exception:
        pass

    # 8. Launch background processing (non-blocking — returns immediately after this)
    asyncio.create_task(
        _run_background_processing(
            job_id=job_id,
            document_id=doc_stub.id,
            local_path=local_path,
            original_filename=filename,
            detected_mime=detected_mime,
            user_id=current_user.id,
            case_id=case_id,
            storage_type=storage_meta["storage_type"],
            stored_path=storage_meta["stored_path"],
        )
    )

    # 9. Return immediately — frontend polls /documents/jobs/{job_id}/status
    return {
        "job_id": job_id,
        "id": doc_stub.id,
        "document_id": doc_stub.id,
        "filename": filename,
        "mime_type": detected_mime,
        "file_hash": file_hash,
        "is_image": detected_mime.startswith("image/"),
        "status": "PROCESSING",
        "stage": "UPLOADED",
        "progress_pct": 5,
        "storage_type": storage_meta["storage_type"],
        "message": "Document uploaded. Processing started in background. Poll /documents/jobs/{job_id}/status for progress.",
    }


@router.get("/{document_id}/extract")
async def extract_document_fields(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Extract structured FIR case fields on demand from an uploaded document's pages."""
    from ...services.document_access import get_authorized_document
    doc = await get_authorized_document(db, current_user, document_id)

    p_stmt = select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.physical_page_number.asc())
    p_res = await db.execute(p_stmt)
    pages = p_res.scalars().all()
    meaningful_lines = [
        p.raw_text for p in pages
        if p.raw_text and not (p.raw_text.startswith("[Physical Page") and "Official Evidence Record" in p.raw_text)
    ]
    full_text = "\n\n".join(meaningful_lines if meaningful_lines else [p.raw_text for p in pages if p.raw_text])
    extracted = gemini_service.extract_structured_case(full_text) if full_text.strip() else {}
    return {
        "document_id": doc.id,
        "filename": doc.original_filename,
        "extracted_data": extracted,
        "raw_text_length": len(full_text)
    }


@router.get("", include_in_schema=False)
@router.get("/")
async def list_documents(
    case_id: Optional[str] = None,
    category: Optional[str] = Query(None, description="Filter by doc_category (FIR, LEGAL_ACT, CIRCULAR, etc.)"),
    search: Optional[str] = None,
    search_content: bool = Query(False, description="Also search the extracted full text and return excerpts"),
    index_status: Optional[str] = Query(None, description="INDEXED, PARTIALLY_INDEXED, NEEDS_REVIEW, FAILED, NOT_INDEXED, STALLED"),
    source_type: Optional[str] = Query(None, description="OFFICIAL, SECONDARY, SYNTHETIC, UNVERIFIED"),
    legal_status: Optional[str] = Query(None, description="IN_FORCE, AMENDED, REPEALED, SUPERSEDED, HISTORICAL, UNKNOWN"),
    jurisdiction: Optional[str] = Query(None, description="e.g. Central, Andhra Pradesh, or a district name"),
    date_from: Optional[str] = Query(None, description="Effective/version date lower bound (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Effective/version date upper bound (YYYY-MM-DD)"),
    sort: str = Query("newest", description="newest, oldest, title, effective_date"),
    include_archived: bool = Query(False, description="Whether to include soft-deleted/archived documents"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List documents the user is authorised to see, with Knowledge Base filters, sorting and
    optional full-text content search (returns matching excerpts with page numbers).
    """
    from ...services.document_access import apply_document_scope
    from ...services.ingestion import STALE_PROCESSING_AFTER, effective_status

    stmt = apply_document_scope(select(Document), current_user)
    if case_id:
        stmt = stmt.where(Document.case_id == case_id)
    if category and category.upper() != "ALL":
        cat_upper = category.upper()
        if cat_upper in ("HISTORICAL_FIR", "FIR"):
            stmt = stmt.where(Document.doc_category.in_(["HISTORICAL_FIR", "FIR"]))
        else:
            stmt = stmt.where(Document.doc_category == cat_upper)
    if not include_archived:
        stmt = stmt.where(Document.is_archived == False)
    if source_type:
        stmt = stmt.where(Document.source_type == source_type.upper())
    if legal_status:
        stmt = stmt.where(Document.legal_status == legal_status.upper())
    if jurisdiction:
        stmt = stmt.where(or_(Document.jurisdiction.ilike(jurisdiction), Document.district.ilike(jurisdiction)))
    effective_date = func.coalesce(Document.commencement_date, Document.version_date, Document.publication_date)
    if date_from:
        stmt = stmt.where(effective_date >= date_from)
    if date_to:
        stmt = stmt.where(effective_date <= date_to)
    if index_status:
        wanted = index_status.upper()
        stale_before = datetime.utcnow() - STALE_PROCESSING_AFTER
        if wanted == "STALLED":
            stmt = stmt.where(Document.ingestion_status == "PROCESSING", Document.updated_at < stale_before)
        elif wanted == "NOT_INDEXED":
            stmt = stmt.where(or_(Document.index_status.is_(None), Document.index_status == "NOT_INDEXED"))
        else:
            stmt = stmt.where(Document.index_status == wanted)

    excerpts: Dict[str, Dict[str, Any]] = {}
    if search:
        pattern = f"%{search}%"
        meta_match = or_(
            Document.original_filename.ilike(pattern),
            Document.document_title.ilike(pattern),
            Document.source_department.ilike(pattern),
            Document.doc_category.ilike(pattern),
            Document.reference_number.ilike(pattern),
            Document.issuing_authority.ilike(pattern),
        )
        if search_content:
            # Full-text hits within the already-authorised, filtered document set
            from ...services.retrieval import keyword_search
            from ...services.rag_engine import best_excerpt
            from ...services.retrieval import query_terms
            allowed_ids = [r[0] for r in (await db.execute(stmt.with_only_columns(Document.id))).fetchall()]
            hits = await keyword_search(db, search, document_ids=allowed_ids, limit=100)
            terms = query_terms(search)
            for h in hits:
                if h["document_id"] not in excerpts:
                    excerpts[h["document_id"]] = {
                        "excerpt": best_excerpt(h["chunk_text"], terms, 240),
                        "physical_page_number": h["physical_page_number"],
                    }
            stmt = stmt.where(or_(meta_match, Document.id.in_(list(excerpts.keys()) or ["__none__"])))
        else:
            stmt = stmt.where(meta_match)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    order = {
        "oldest": Document.created_at.asc(),
        "title": func.lower(func.coalesce(Document.document_title, Document.original_filename)).asc(),
        "effective_date": effective_date.desc(),
    }.get(sort, desc(Document.created_at))
    docs = (await db.execute(stmt.order_by(order).offset(skip).limit(limit))).scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "documents": [
            {
                "id": d.id,
                "case_id": d.case_id,
                "original_filename": d.original_filename,
                "document_title": d.document_title or d.original_filename,
                "doc_category": d.doc_category or "FIR",
                "source_department": d.source_department,
                "version_date": d.version_date,
                "district": d.district or "Statewide",
                "station": d.station,
                "physical_page_count": d.physical_page_count,
                "mime_type": d.mime_type,
                "file_hash": d.file_hash,
                "is_verified_official": d.is_verified_official,
                "source_type": d.source_type or "UNVERIFIED",
                "record_kind": d.record_kind,
                "source_url": d.source_url,
                "issuing_authority": d.issuing_authority,
                "reference_number": d.reference_number,
                "jurisdiction": d.jurisdiction,
                "publication_date": d.publication_date,
                "commencement_date": d.commencement_date,
                "legal_status": d.legal_status,
                "is_archived": d.is_archived,
                "archive_reason": d.archive_reason,
                "archived_at": d.archived_at.isoformat() if d.archived_at else None,
                "replaced_by_id": d.replaced_by_id,
                "replaces_id": d.replaces_id,
                "replacement_reason": d.replacement_reason,
                "status": effective_status(d),
                "index_status": d.index_status or "NOT_INDEXED",
                "indexed_chunk_count": d.indexed_chunk_count or 0,
                "embedded_chunk_count": d.embedded_chunk_count or 0,
                "error_message": d.error_message,
                "match": excerpts.get(d.id),
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "created_by": d.created_by,
            }
            for d in docs
        ]
    }


@router.get("/kb-stats")
async def knowledge_base_stats(
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Document counts per category, index status and source type within the user's authorised scope."""
    from ...services.document_access import apply_document_scope

    def scoped(col):
        stmt = apply_document_scope(select(col, func.count(Document.id)), current_user)
        if not include_archived:
            stmt = stmt.where(Document.is_archived == False)  # noqa: E712
        return stmt.group_by(col)

    by_category = {(k or "FIR"): v for k, v in (await db.execute(scoped(Document.doc_category))).all()}
    by_index = {(k or "NOT_INDEXED"): v for k, v in (await db.execute(scoped(Document.index_status))).all()}
    by_source = {(k or "UNVERIFIED"): v for k, v in (await db.execute(scoped(Document.source_type))).all()}
    return {
        "total": sum(by_category.values()),
        "by_category": by_category,
        "by_index_status": by_index,
        "by_source_type": by_source,
    }


@router.get("/historical-firs")
async def list_historical_firs(
    search: Optional[str] = Query(None, description="Search FIR number, crime, district, station, offence"),
    district: Optional[str] = Query(None),
    station: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search and retrieve authorized Historical FIR records joined with case metadata.
    Enforces role-based jurisdictional scoping (STATION, DISTRICT, STATE).
    Used by AI FIR Assistance Chatbot, Case Management, and Evidence Intelligence.
    """
    stmt = (
        select(Document, Case)
        .outerjoin(Case, Document.case_id == Case.id)
        .where(
            Document.is_archived == False,
            or_(
                Document.doc_category.in_(["FIR", "HISTORICAL_FIR", "EVIDENCE"]),
                Document.case_id.isnot(None),
            )
        )
    )

    # Role-based jurisdictional filtering (shared rules with every other document route)
    from ...services.document_access import apply_document_scope
    stmt = apply_document_scope(stmt, current_user)

    if district:
        stmt = stmt.where(or_(Case.district == district, Document.district == district))
    if station:
        stmt = stmt.where(or_(Case.station == station, Document.station == station))

    if search:
        pat = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Case.fir_number.ilike(pat),
                Case.offence_nature.ilike(pat),
                Case.contraband_type.ilike(pat),
                Case.vehicle_details.ilike(pat),
                Document.original_filename.ilike(pat),
                Document.document_title.ilike(pat),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(desc(Case.registration_date), desc(Document.created_at)).offset(skip).limit(limit)
    res = await db.execute(stmt)
    rows = res.all()

    records = []
    for doc, case in rows:
        records.append({
            "document_id": doc.id,
            "id": doc.id,
            "original_filename": doc.original_filename,
            "document_title": doc.document_title or doc.original_filename,
            "mime_type": doc.mime_type,
            "physical_page_count": doc.physical_page_count or 1,
            "is_image": bool(doc.mime_type and doc.mime_type.startswith("image/")),
            "ingestion_status": doc.ingestion_status or "COMPLETED",
            "index_status": doc.index_status or "NOT_INDEXED",
            "record_kind": doc.record_kind,
            "file_hash": doc.file_hash,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "case_id": case.id if case else doc.case_id,
            "fir_number": case.fir_number if case else None,
            "year": case.year if case else None,
            "district": (case.district if case else None) or doc.district or "Unassigned",
            "station": (case.station if case else None) or doc.station or "Unassigned",
            "offence_nature": case.offence_nature if case else None,
            "contraband_type": case.contraband_type if case else None,
            "seized_quantity": case.seized_quantity if case else None,
            "seized_unit": case.seized_unit if case else None,
            "vehicle_details": case.vehicle_details if case else None,
            "case_status": case.status if case else None,
            "display_label": f"FIR {case.fir_number} ({case.district} - {case.station}) • {doc.original_filename}" if (case and case.fir_number) else f"{doc.original_filename} ({doc.district or 'General Evidence'})",
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": records
    }


KB_CATEGORIES = {"LEGAL_ACT", "CIRCULAR", "SEIZURE_REPORT", "INVESTIGATION_GUIDE", "REFERENCE", "HISTORICAL_FIR", "EVIDENCE"}
KB_EXTRA_EXTENSIONS = {".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       ".txt": "text/plain", ".md": "text/markdown"}


def _detect_kb_mime(filename: str, file_bytes: bytes) -> str:
    """Knowledge Base accepts DOCX and plain text in addition to PDF/images."""
    ext = os.path.splitext((filename or "").lower())[1]
    if ext == ".docx":
        if file_bytes[:2] != b"PK":
            raise HTTPException(status_code=400, detail="The .docx file is not a valid Word document.")
        return KB_EXTRA_EXTENSIONS[ext]
    if ext in (".txt", ".md"):
        try:
            file_bytes[:4096].decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Text files must be UTF-8 encoded.")
        return KB_EXTRA_EXTENSIONS[ext]
    return _detect_mime_type(filename, file_bytes)


def _can_manage_document(user: User, doc: Document) -> bool:
    """Statewide reference material may only be changed by DISTRICT or STATE users."""
    from ...services.document_access import STATEWIDE_CATEGORIES
    if (doc.doc_category or "").upper() in STATEWIDE_CATEGORIES:
        return user.role in ("DISTRICT", "STATE")
    return True


async def _run_kb_ingestion(document_id: str, local_path: str, user_id: str, trigger: str,
                            cleanup_path: Optional[str] = None) -> None:
    """Background ingestion with its own session; outcome is recorded on the document and job."""
    from ...services.ingestion import ingest_file
    async with AsyncSessionLocal() as bg_db:
        try:
            doc = (await bg_db.execute(select(Document).where(Document.id == document_id))).scalar_one()
            await ingest_file(bg_db, doc, local_path, trigger=trigger, user_id=user_id)
        except Exception as e:
            logger.error(f"Knowledge Base ingestion task failed for {document_id}: {e}", exc_info=True)
        finally:
            if cleanup_path and os.path.exists(cleanup_path):
                try:
                    os.remove(cleanup_path)
                except Exception:
                    pass


@router.post("/knowledge-base/upload")
async def upload_knowledge_base_document(
    file: UploadFile = File(...),
    document_title: str = Form(..., description="Official title of the document"),
    category: str = Form("LEGAL_ACT", description="LEGAL_ACT, CIRCULAR, SEIZURE_REPORT, INVESTIGATION_GUIDE, REFERENCE, HISTORICAL_FIR, EVIDENCE"),
    source_department: Optional[str] = Form(None),
    version_date: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    station: Optional[str] = Form(None),
    is_verified_official: bool = Form(False),
    source_type: Optional[str] = Form(None, description="OFFICIAL, SECONDARY, SYNTHETIC, UNVERIFIED"),
    record_kind: Optional[str] = Form(None, description="For FIR/evidence: ACTUAL, REDACTED, SYNTHETIC"),
    source_url: Optional[str] = Form(None),
    issuing_authority: Optional[str] = Form(None),
    reference_number: Optional[str] = Form(None, description="Act / order / notification / circular number"),
    jurisdiction: Optional[str] = Form(None),
    publication_date: Optional[str] = Form(None),
    commencement_date: Optional[str] = Form(None),
    legal_status: Optional[str] = Form(None, description="IN_FORCE, AMENDED, REPEALED, SUPERSEDED, HISTORICAL, UNKNOWN"),
    language: Optional[str] = Form(None),
    case_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a document to the Knowledge Base. Returns immediately with status PROCESSING; text
    extraction, chunking, embedding and index verification run in the background. Poll
    GET /documents/{id}/detail for the outcome. Identical files are reported as duplicates.
    """
    from ...services.document_access import STATEWIDE_CATEGORIES

    category = (category or "").upper()
    if category not in KB_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'.")
    # Column limits: PostgreSQL rejects longer values, so report them as input errors
    limits = {"document_title": (document_title, 255), "source_department": (source_department, 100),
              "issuing_authority": (issuing_authority, 255), "reference_number": (reference_number, 100),
              "jurisdiction": (jurisdiction, 100), "source_url": (source_url, 500),
              "district": (district, 50), "station": (station, 100), "language": (language, 20)}
    too_long = [f"{name} (max {n} characters)" for name, (value, n) in limits.items() if value and len(value) > n]
    if too_long:
        raise HTTPException(status_code=400, detail="Too long: " + ", ".join(too_long))
    if category in STATEWIDE_CATEGORIES and current_user.role not in ("DISTRICT", "STATE"):
        raise HTTPException(status_code=403, detail="Only district or state officers can add statewide reference documents.")

    source_type = (source_type or ("OFFICIAL" if is_verified_official else "UNVERIFIED")).upper()
    if source_type not in ("OFFICIAL", "SECONDARY", "SYNTHETIC", "UNVERIFIED"):
        raise HTTPException(status_code=400, detail=f"Unknown source type '{source_type}'.")
    if source_type == "OFFICIAL" and current_user.role != "STATE":
        raise HTTPException(status_code=403, detail="Only state-level officers can mark a document as an official source.")
    if source_type == "OFFICIAL" and not source_url:
        raise HTTPException(status_code=400, detail="Official documents need the official source URL.")

    # Station/district users can only file case material in their own jurisdiction
    if current_user.role == "STATION":
        district, station = current_user.district, current_user.station
    elif current_user.role == "DISTRICT" and category not in STATEWIDE_CATEGORIES:
        district = current_user.district
    if case_id:
        case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
        if not case or not enforce_data_scope(current_user, case.district, case.station):
            raise HTTPException(status_code=403, detail="Case not found or outside your jurisdiction.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds maximum size of 50 MB.")
    detected_mime = _detect_kb_mime(file.filename, file_bytes)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    duplicate = (await db.execute(
        select(Document).where(Document.file_hash == file_hash, Document.is_archived == False)  # noqa: E712
        .order_by(desc(Document.created_at))
    )).scalars().first()
    if duplicate:
        raise HTTPException(status_code=409, detail={
            "message": "This exact file is already in FIR VisionAI. It was not uploaded again.",
            "duplicate_document_id": duplicate.id,
            "duplicate_title": duplicate.document_title or duplicate.original_filename,
            "duplicate_category": duplicate.doc_category,
        })

    storage_meta = await storage_service.upload_file(file_bytes=file_bytes, filename=file.filename, content_type=detected_mime)
    local_path = storage_meta["stored_path"]
    cleanup_path = None
    if storage_meta["storage_type"] == "SUPABASE":
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = cleanup_path = os.path.join(temp_dir, f"{file_hash[:8]}_{file.filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    doc = Document(
        case_id=case_id,
        original_filename=file.filename,
        stored_path=storage_meta["stored_path"],
        file_hash=file_hash,
        mime_type=detected_mime,
        physical_page_count=0,
        ingestion_status="PROCESSING",
        index_status="NOT_INDEXED",
        created_by=current_user.id,
        document_title=document_title.strip(),
        doc_category=category,
        source_department=source_department,
        version_date=version_date,
        district=district,
        station=station,
        is_verified_official=source_type == "OFFICIAL",
        source_type=source_type,
        record_kind=(record_kind or "").upper() or None,
        source_url=source_url,
        issuing_authority=issuing_authority,
        reference_number=reference_number,
        jurisdiction=jurisdiction,
        publication_date=publication_date,
        commencement_date=commencement_date,
        legal_status=(legal_status or "").upper() or None,
        language=language,
        last_verified_at=datetime.utcnow() if source_type == "OFFICIAL" else None,
        is_archived=False,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="KB_DOCUMENT_UPLOADED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={"title": doc.document_title, "category": category, "source_type": source_type,
                     "hash": file_hash, "storage": storage_meta["storage_type"]},
    )

    asyncio.create_task(_run_kb_ingestion(doc.id, local_path, current_user.id, "UPLOAD", cleanup_path))

    return {
        "message": f"'{doc.document_title}' was uploaded. Text extraction and indexing are running.",
        "id": doc.id,
        "document_title": doc.document_title,
        "category": doc.doc_category,
        "source_type": source_type,
        "status": "PROCESSING",
        "index_status": "NOT_INDEXED",
    }


@router.post("/{document_id}/replace")
async def replace_document(
    document_id: str,
    file: UploadFile = File(...),
    reason: str = Form(..., description="Mandatory reason for document replacement"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Replace an existing document. Soft-archives the old document,
    records replacement reason, ingests replacement, re-indexes chunks,
    and invalidates stale RAG caches.
    """
    from ...services.document_access import get_authorized_document
    old_doc = await get_authorized_document(db, current_user, document_id)
    if not _can_manage_document(current_user, old_doc):
        raise HTTPException(status_code=403, detail="Only district or state officers can replace statewide reference documents.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Replacement file is empty.")

    detected_mime = _detect_mime_type(file.filename, file_bytes)
    import hashlib
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    storage_meta = await storage_service.upload_file(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=detected_mime
    )

    local_path = storage_meta["stored_path"]
    if storage_meta["storage_type"] == "SUPABASE":
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{file_hash[:8]}_{file.filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    # Process new document
    new_doc = await pdf_pipeline.process_document(
        file_path=local_path,
        original_filename=file.filename,
        mime_type=detected_mime,
        user_id=current_user.id,
        db=db,
        case_id=old_doc.case_id,
        stored_path=storage_meta["stored_path"],
    )

    # Inherit and link attributes
    new_doc.document_title = old_doc.document_title or file.filename
    new_doc.doc_category = old_doc.doc_category
    new_doc.source_department = old_doc.source_department
    new_doc.version_date = old_doc.version_date
    new_doc.district = old_doc.district
    new_doc.station = old_doc.station
    new_doc.is_verified_official = old_doc.is_verified_official
    new_doc.replaces_id = old_doc.id

    # Archive old document
    old_doc.is_archived = True
    old_doc.archived_at = datetime.utcnow()
    old_doc.archived_by = current_user.id
    old_doc.archive_reason = f"Replaced by '{file.filename}': {reason}"
    old_doc.replaced_by_id = new_doc.id

    await db.commit()

    # Invalidate stale RAG caches
    from ...services.rag_engine import rag_engine
    rag_engine.invalidate_cache(old_doc.id)
    rag_engine.invalidate_cache()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_REPLACED",
        object_type="DOCUMENT",
        object_id=old_doc.id,
        after_state={
            "new_document_id": new_doc.id,
            "filename": file.filename,
            "reason": reason
        }
    )

    return {
        "message": f"Document '{old_doc.original_filename}' successfully replaced with '{file.filename}'.",
        "new_document_id": new_doc.id,
        "old_document_id": old_doc.id,
        "filename": new_doc.original_filename,
        "pages": new_doc.physical_page_count,
        "replaces_id": old_doc.id,
        "cache_invalidated": True
    }


@router.delete("/{document_id}")
async def archive_document(
    document_id: str,
    reason: str = Query("Departmental record archival", description="Mandatory reason for archiving/deleting document"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Soft-delete / archive an authorized document."""
    from ...services.document_access import get_authorized_document
    doc = await get_authorized_document(db, current_user, document_id)
    if not _can_manage_document(current_user, doc):
        raise HTTPException(status_code=403, detail="Only district or state officers can archive statewide reference documents.")

    doc.is_archived = True
    doc.archived_at = datetime.utcnow()
    doc.archived_by = current_user.id
    doc.archive_reason = reason

    await db.commit()

    # Invalidate RAG cache
    from ...services.rag_engine import rag_engine
    rag_engine.invalidate_cache(document_id)
    rag_engine.invalidate_cache()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_ARCHIVED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={"reason": reason, "is_archived": True}
    )

    return {
        "message": f"Document '{doc.original_filename}' successfully archived and excluded from active searches.",
        "cache_invalidated": True
    }


@router.post("/{document_id}/restore")
async def restore_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Restore an archived document to active status."""
    from ...services.document_access import get_authorized_document
    doc = await get_authorized_document(db, current_user, document_id)
    if not _can_manage_document(current_user, doc):
        raise HTTPException(status_code=403, detail="Only district or state officers can restore statewide reference documents.")

    doc.is_archived = False
    doc.archived_at = None
    doc.archived_by = None
    doc.archive_reason = None

    await db.commit()

    # Invalidate RAG cache
    from ...services.rag_engine import rag_engine
    rag_engine.invalidate_cache(document_id)
    rag_engine.invalidate_cache()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_RESTORED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={"is_archived": False}
    )

    return {"message": f"Document '{doc.original_filename}' successfully restored to active records."}


@router.get("/{document_id}/pages")
async def get_document_pages(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ...services.document_access import get_authorized_document
    doc = await get_authorized_document(db, current_user, document_id)

    p_stmt = select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.physical_page_number.asc())
    p_res = await db.execute(p_stmt)
    pages = p_res.scalars().all()

    pages_list = []
    if pages:
        for p in pages:
            pages_list.append({
                "id": p.id,
                "physical_page_number": p.physical_page_number,
                "printed_page_number": p.printed_page_number,
                "ocr_applied": p.ocr_applied,
                "text_snippet": (p.raw_text or "")[:1000]
            })
    else:
        # Fallback 1: check DocumentChunk
        c_stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index.asc())
        c_res = await db.execute(c_stmt)
        chunks = c_res.scalars().all()
        if chunks:
            by_page: Dict[int, list] = {}
            for ch in chunks:
                p_num = ch.physical_page_number or 1
                by_page.setdefault(p_num, []).append(ch.chunk_text or "")
            for p_num, texts in sorted(by_page.items()):
                pages_list.append({
                    "id": f"chunk_p_{p_num}",
                    "physical_page_number": p_num,
                    "printed_page_number": p_num,
                    "ocr_applied": True,
                    "text_snippet": ("\n".join(texts))[:1000]
                })
        else:
            # Fallback 2: check ExtractionRun
            r_stmt = select(ExtractionRun).where(ExtractionRun.document_id == document_id).order_by(desc(ExtractionRun.created_at))
            r_res = await db.execute(r_stmt)
            run = r_res.scalars().first()
            if run:
                raw_payload = {}
                try:
                    raw_payload = json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")
                except Exception:
                    pass
                content = raw_payload.get("document_content") or raw_payload.get("raw_text_summary") or ""
                if content:
                    pages_list.append({
                        "id": f"run_{run.id}",
                        "physical_page_number": 1,
                        "printed_page_number": 1,
                        "ocr_applied": True,
                        "text_snippet": content[:1000]
                    })

    is_img = bool(doc.mime_type and doc.mime_type.startswith("image/")) or (doc.original_filename or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    return {
        "document_id": doc.id,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "physical_page_count": max(doc.physical_page_count or 1, len(pages_list) or 1),
        "is_image": is_img,
        "ingestion_status": doc.ingestion_status or "COMPLETED",
        "has_extracted_text": len(pages_list) > 0 and bool(pages_list[0].get("text_snippet")),
        "pages": pages_list
    }


import jwt
from fastapi.security import OAuth2PasswordBearer
from fastapi import Query

oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

async def get_user_from_header_or_param(
    header_token: Optional[str] = Depends(oauth2_optional),
    query_token: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = header_token or query_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Bearer token in header or 'token' query parameter required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials: invalid token claims",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please refresh session or log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or pending administrator approval.",
        )
    return user


@router.get("/{document_id}/view")
async def view_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_user_from_header_or_param)
):
    """Secure authenticated document serving endpoint for embedded PDF/image viewer."""
    from urllib.parse import quote
    from ...services.document_access import get_authorized_document
    from ...services.ingestion import materialize_document_file
    doc = await get_authorized_document(db, current_user, document_id)

    # Local file, evidence-folder copy, or the Supabase object (by its stored key, or the
    # evidence/{hash8}_{filename} key cloud uploads are saved under)
    path, is_temp = await materialize_document_file(doc)
    if not path:
        logger.warning(f"Original file missing for document {doc.id} ({doc.original_filename}); stored_path={doc.stored_path!r}")
        raise HTTPException(status_code=404, detail={
            "code": "ORIGINAL_FILE_MISSING",
            "message": f"The original file '{doc.original_filename}' is not in storage. Its extracted text is still available.",
        })
    fname = doc.original_filename or "document"
    mime = doc.mime_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f"inline; filename*=UTF-8''{quote(fname)}", "Cache-Control": "private, no-store"}
    if is_temp:
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        return Response(content=data, media_type=mime, headers=headers)
    return FileResponse(path=path, media_type=mime, headers=headers)


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_user_from_header_or_param)
):
    """Secure document download endpoint (original file, from local disk or Supabase Storage)."""
    from ...services.document_access import get_authorized_document
    from ...services.ingestion import materialize_document_file
    doc = await get_authorized_document(db, current_user, document_id)

    path, is_temp = await materialize_document_file(doc)
    if not path:
        raise HTTPException(status_code=404, detail="Document file not found on storage")
    mime = doc.mime_type or "application/octet-stream"
    if is_temp:
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        return Response(content=data, media_type=mime,
                        headers={"Content-Disposition": f"attachment; filename=\"{doc.original_filename}\""})
    return FileResponse(
        path=path,
        media_type=mime,
        filename=doc.original_filename,
        headers={"Content-Disposition": f"attachment; filename=\"{doc.original_filename}\""}
    )


@router.get("/{document_id}/detail")
async def get_document_detail(
    document_id: str,
    page_from: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Metadata, ingestion history, index state and extracted text (paged) for one document."""
    from ...models.document import DocumentChunk, IngestionJob
    from ...models.legal import LegalCorpus
    from ...services.document_access import get_authorized_document
    from ...services.ingestion import effective_status

    doc = await get_authorized_document(db, current_user, document_id)

    pages_total = (await db.execute(
        select(func.count()).where(DocumentPage.document_id == doc.id))).scalar() or 0
    pages_with_text = (await db.execute(select(func.count()).where(
        DocumentPage.document_id == doc.id, DocumentPage.raw_text.isnot(None),
        func.length(DocumentPage.raw_text) >= 20))).scalar() or 0
    chunk_count = (await db.execute(
        select(func.count()).where(DocumentChunk.document_id == doc.id))).scalar() or 0
    sections = [r[0] for r in (await db.execute(
        select(DocumentChunk.section_ref).where(DocumentChunk.document_id == doc.id, DocumentChunk.section_ref.isnot(None))
        .group_by(DocumentChunk.section_ref).order_by(func.min(DocumentChunk.chunk_index)).limit(1000)
    )).fetchall()]
    provisions = (await db.execute(
        select(func.count()).where(LegalCorpus.document_id == doc.id))).scalar() or 0
    jobs = (await db.execute(
        select(IngestionJob).where(IngestionJob.document_id == doc.id).order_by(desc(IngestionJob.created_at)).limit(10)
    )).scalars().all()
    pages = (await db.execute(
        select(DocumentPage).where(DocumentPage.document_id == doc.id,
                                   DocumentPage.physical_page_number >= page_from,
                                   DocumentPage.physical_page_number < page_from + page_size)
        .order_by(DocumentPage.physical_page_number)
    )).scalars().all()

    return {
        "id": doc.id,
        "document_title": doc.document_title or doc.original_filename,
        "original_filename": doc.original_filename,
        "doc_category": doc.doc_category,
        "mime_type": doc.mime_type,
        "file_hash": doc.file_hash,
        "case_id": doc.case_id,
        "district": doc.district,
        "station": doc.station,
        "source_type": doc.source_type or "UNVERIFIED",
        "record_kind": doc.record_kind,
        "source_url": doc.source_url,
        "issuing_authority": doc.issuing_authority or doc.source_department,
        "reference_number": doc.reference_number,
        "jurisdiction": doc.jurisdiction,
        "publication_date": doc.publication_date,
        "commencement_date": doc.commencement_date,
        "version_date": doc.version_date,
        "legal_status": doc.legal_status,
        "language": doc.language,
        "last_verified_at": doc.last_verified_at.isoformat() if doc.last_verified_at else None,
        "verification_note": doc.verification_note,
        "is_archived": doc.is_archived,
        "status": effective_status(doc),
        "index_status": doc.index_status or "NOT_INDEXED",
        "error_message": doc.error_message,
        "physical_page_count": doc.physical_page_count,
        "pages_total": pages_total,
        "pages_with_text": pages_with_text,
        "chunk_count": chunk_count,
        "embedded_chunk_count": doc.embedded_chunk_count or 0,
        "embedding_model": doc.embedding_model,
        "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
        "sections": sections,
        "legal_provisions": provisions,
        "can_manage": _can_manage_document(current_user, doc),
        "ingestion_jobs": [
            {
                "id": j.id, "status": j.status, "stage": j.stage, "trigger": j.trigger,
                "pages_total": j.pages_total, "pages_with_text": j.pages_with_text,
                "chunks_written": j.chunks_written, "chunks_embedded": j.chunks_embedded,
                "error_message": j.error_message,
                "warnings": json.loads(j.warnings_json) if j.warnings_json else [],
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in jobs
        ],
        "page_from": page_from,
        "page_size": page_size,
        "pages": [
            {
                "physical_page_number": p.physical_page_number,
                "text": p.raw_text or "",
                "ocr_applied": bool(p.ocr_applied),
                "is_unreadable": bool(p.is_unreadable) or not (p.raw_text or "").strip(),
            }
            for p in pages
        ],
    }


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    mode: str = Query("full", description="full = re-extract text from the original file; reindex = rebuild chunks/embeddings from stored text"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retry ingestion for a failed, stalled, partially indexed or needs-review document."""
    from ...services.document_access import get_authorized_document
    from ...services.ingestion import effective_status, materialize_document_file, reindex_from_pages

    doc = await get_authorized_document(db, current_user, document_id)
    if not _can_manage_document(current_user, doc):
        raise HTTPException(status_code=403, detail="Only district or state officers can reprocess statewide reference documents.")
    if effective_status(doc) == "PROCESSING":
        raise HTTPException(status_code=409, detail="This document is already being processed.")

    mode = mode.lower()
    if mode == "reindex":
        async def _bg_reindex(doc_id: str, user_id: str):
            async with AsyncSessionLocal() as bg_db:
                d = (await bg_db.execute(select(Document).where(Document.id == doc_id))).scalar_one()
                await reindex_from_pages(bg_db, d, trigger="RETRY", user_id=user_id)
        doc.ingestion_status = "PROCESSING"
        await db.commit()
        asyncio.create_task(_bg_reindex(doc.id, current_user.id))
    elif mode == "full":
        path, is_temp = await materialize_document_file(doc)
        if not path:
            raise HTTPException(status_code=404, detail="The original file is not available in storage, so text cannot be re-extracted. Try mode=reindex or re-upload the file.")
        doc.ingestion_status = "PROCESSING"
        await db.commit()
        asyncio.create_task(_run_kb_ingestion(doc.id, path, current_user.id, "RETRY", path if is_temp else None))
    else:
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'reindex'.")

    await log_audit_event(
        db=db, actor_id=current_user.id, actor_username=current_user.username,
        action_type="DOCUMENT_REPROCESS_REQUESTED", object_type="DOCUMENT", object_id=doc.id,
        after_state={"mode": mode},
    )
    return {"message": "Reprocessing started.", "id": doc.id, "status": "PROCESSING", "mode": mode}
