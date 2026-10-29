import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ...config import settings
from ...database import get_db
from ...models.user import User
from ...models.generation import GeneratedDocument, CaseSummary, DocumentApprovalHistory
from ...models.case import Case
from ...schemas.schemas import DocumentGenerateRequest, DocumentApprovalRequest
from ...services.auth import get_current_user
from ...services.auth import enforce_data_scope
from ...services.document_generator import document_generator, is_outdated
from ...services.gemini import gemini_service
from ...services.audit import log_audit_event
from ...services.legal_service import CaseAccessDenied

router = APIRouter(prefix="/generation", tags=["Case Diary & Chargesheet Generation"])


async def _authorized_case(case_id: str, user: User, db: AsyncSession) -> Case:
    case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not enforce_data_scope(user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied: this case is outside your jurisdiction.")
    return case


async def _authorized_doc(doc_id: str, user: User, db: AsyncSession) -> GeneratedDocument:
    doc = (await db.execute(select(GeneratedDocument).where(GeneratedDocument.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await _authorized_case(doc.case_id, user, db)
    return doc


def _doc_view(doc: GeneratedDocument) -> dict:
    view = {c.name: getattr(doc, c.name) for c in doc.__table__.columns}
    view["is_outdated"] = is_outdated(doc)
    return view


@router.post("/draft")
async def generate_draft_document(
    req: DocumentGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        doc = await document_generator.generate_draft(
            case_id=req.case_id,
            doc_type=req.doc_type,
            user=current_user,
            db=db,
            language=req.language or "en"
        )

        await log_audit_event(
            db=db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="DRAFT_DOCUMENT_GENERATED",
            object_type="GENERATED_DOCUMENT",
            object_id=doc.id,
            after_state={"title": doc.title, "type": doc.doc_type, "version": doc.version, "language": doc.language}
        )

        return _doc_view(doc)
    except CaseAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/case/{case_id}/documents")
async def list_case_generated_documents(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await _authorized_case(case_id, current_user, db)
    stmt = select(GeneratedDocument).where(GeneratedDocument.case_id == case_id).order_by(
        desc(GeneratedDocument.version), desc(GeneratedDocument.created_at))
    res = await db.execute(stmt)
    return [_doc_view(d) for d in res.scalars().all()]

@router.put("/{doc_id}")
async def update_draft_content(
    doc_id: str,
    content: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = await _authorized_doc(doc_id, current_user, db)

    doc.content = content
    doc.version += 1
    
    # Audit version history on draft edit
    edit_history = DocumentApprovalHistory(
        document_id=doc.id,
        version=doc.version,
        action="EDITED",
        officer_id=current_user.id,
        comments="Officer manual draft modification"
    )
    db.add(edit_history)
    await db.commit()
    await db.refresh(doc)
    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DRAFT_DOCUMENT_EDITED",
        object_type="GENERATED_DOCUMENT",
        object_id=doc.id,
        after_state={"type": doc.doc_type, "version": doc.version, "language": doc.language}
    )
    return _doc_view(doc)

@router.post("/{doc_id}/approve")
async def approve_document(
    doc_id: str,
    req: DocumentApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = await _authorized_doc(doc_id, current_user, db)

    doc.status = req.action
    doc.approved_by = current_user.id
    doc.approved_at = datetime.utcnow()

    history = DocumentApprovalHistory(
        document_id=doc.id,
        version=doc.version,
        action=req.action,
        officer_id=current_user.id,
        comments=req.comments
    )
    db.add(history)
    await db.commit()
    await db.refresh(doc)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_APPROVED",
        object_type="GENERATED_DOCUMENT",
        object_id=doc.id,
        after_state={"action": req.action, "version": doc.version}
    )

    return _doc_view(doc)

@router.get("/{doc_id}/export-pdf")
async def export_document_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = await _authorized_doc(doc_id, current_user, db)

    output_filename = f"{doc.doc_type}_{doc.id[:8]}_v{doc.version}.pdf"
    output_path = os.path.join(settings.EXPORTS_DIR, output_filename)

    document_generator.export_pdf(doc, output_path)

    return FileResponse(
        path=output_path,
        media_type="application/pdf",
        filename=output_filename
    )

@router.get("/{doc_id}/export-docx")
async def export_document_docx(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = await _authorized_doc(doc_id, current_user, db)

    output_filename = f"{doc.doc_type}_{doc.id[:8]}_v{doc.version}.docx"
    output_path = os.path.join(settings.EXPORTS_DIR, output_filename)

    document_generator.export_docx(doc, output_path)

    return FileResponse(
        path=output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=output_filename
    )

@router.get("/case/{case_id}/summary")
async def get_or_generate_summary(
    case_id: str,
    language: str = "en",
    regenerate: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Summary of a case, served by the historical FIR summary service: the case's FIR document if it
    has one, otherwise the case record. Jurisdiction is enforced; summaries are cited and versioned.
    """
    from ...services import fir_summaries as fs
    from ...services.auth import enforce_data_scope
    if language not in fs.LANGUAGES:
        raise HTTPException(status_code=400, detail="Language must be en, te or hi.")
    case = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one_or_none()
    if not case or not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=404, detail="Case not found")
    records = [r for r in await fs.list_records(db, current_user) if r["case_id"] == case_id]
    if not records:
        raise HTTPException(status_code=404, detail="Case not found")
    rec = next((r for r in records if r["record_type"] == "FIR_DOCUMENT"), records[0])
    row = (await fs.summary_rows(db, [rec["record_key"]])).get(rec["record_key"], {}).get(language)
    if regenerate or row is None or row.status != "COMPLETED" or row.source_hash != rec["source_hash"]:
        outcome = await fs.generate_record(db, current_user, rec, force=regenerate)
        if outcome["status"] in ("FAILED", "QUOTA_EXHAUSTED", "NEEDS_REVIEW") and not (row and row.status == "COMPLETED"):
            return {"summary": None, "language": language, "is_ai_generated": True,
                    "status": outcome["status"], "error": outcome.get("error"), "record_key": rec["record_key"]}
        row = (await fs.summary_rows(db, [rec["record_key"]])).get(rec["record_key"], {}).get(language)
    out = fs.serialize_summary(row, rec)
    overview = ((out.get("summary") or {}).get("overview") or {}).get("text")
    return {"summary": overview or out.get("summary_text"), "language": language, "is_ai_generated": True,
            "status": out["status"], "record_key": rec["record_key"], "details": out}
