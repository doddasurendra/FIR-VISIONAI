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
from ...services.document_generator import document_generator
from ...services.gemini import gemini_service
from ...services.audit import log_audit_event

router = APIRouter(prefix="/generation", tags=["Case Diary & Chargesheet Generation"])

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
            db=db
        )

        await log_audit_event(
            db=db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="DRAFT_DOCUMENT_GENERATED",
            object_type="GENERATED_DOCUMENT",
            object_id=doc.id,
            after_state={"title": doc.title, "type": doc.doc_type, "version": doc.version}
        )

        return doc
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/case/{case_id}/documents")
async def list_case_generated_documents(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(GeneratedDocument).where(GeneratedDocument.case_id == case_id).order_by(desc(GeneratedDocument.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.put("/{doc_id}")
async def update_draft_content(
    doc_id: str,
    content: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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
    return doc

@router.post("/{doc_id}/approve")
async def approve_document(
    doc_id: str,
    req: DocumentApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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

    return doc

@router.get("/{doc_id}/export-pdf")
async def export_document_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    output_filename = f"{doc.doc_type}_{doc.id[:8]}_v{doc.version}.pdf"
    output_path = os.path.join(settings.EXPORTS_DIR, output_filename)

    document_generator.export_pdf(doc, output_path)

    return FileResponse(
        path=output_path,
        media_type="application/pdf",
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
    # Check cache
    if not regenerate:
        c_stmt = select(CaseSummary).where(CaseSummary.case_id == case_id, CaseSummary.language == language)
        c_res = await db.execute(c_stmt)
        cached = c_res.scalar_one_or_none()
        if cached:
            return {"summary": cached.summary_text, "language": cached.language, "is_ai_generated": cached.is_ai_generated}

    # Fetch case
    case_stmt = select(Case).where(Case.id == case_id)
    case_res = await db.execute(case_stmt)
    case = case_res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Generate 3-5 sentence summary
    narrative_text = f"Case {case.fir_number}: {case.offence_nature}. Contraband: {case.contraband_type} ({case.seized_quantity} {case.seized_unit}). Vehicle: {case.vehicle_details}. {case.narrative or ''}"
    
    extracted = gemini_service.extract_structured_case(narrative_text, language_hint=language)
    summary_text = extracted.get("narrative_summary") or f"Case registered under {case.station} for {case.offence_nature}. Total {case.seized_quantity} {case.seized_unit} seized."

    new_summary = CaseSummary(
        case_id=case_id,
        summary_text=summary_text,
        language=language,
        is_ai_generated=True,
        version=1
    )
    db.add(new_summary)
    await db.commit()
    await db.refresh(new_summary)

    return {"summary": new_summary.summary_text, "language": new_summary.language, "is_ai_generated": True}
