import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...config import settings
from ...database import get_db
from ...models.user import User
from ...models.document import Document, DocumentPage
from ...models.case import Case
from ...services.auth import get_current_user, enforce_data_scope
from ...services.pdf_pipeline import pdf_pipeline
from ...services.audit import log_audit_event

router = APIRouter(prefix="/documents", tags=["Document Ingestion & PDF Viewer"])

@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported for grounded page RAG.")

    # Save to evidence dir
    safe_filename = f"{current_user.id[:8]}_{int(os.times().elapsed)}_{file.filename}"
    file_path = os.path.join(settings.EVIDENCE_DIR, safe_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Process through pipeline
    doc = await pdf_pipeline.process_pdf(
        file_path=file_path,
        original_filename=file.filename,
        user_id=current_user.id,
        db=db,
        case_id=case_id
    )

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_UPLOADED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={"filename": file.filename, "pages": doc.physical_page_count, "hash": doc.file_hash}
    )

    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "physical_page_count": doc.physical_page_count,
        "file_hash": doc.file_hash,
        "status": doc.ingestion_status
    }

@router.get("/")
async def list_documents(
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Document)
    if case_id:
        stmt = stmt.where(Document.case_id == case_id)
    res = await db.execute(stmt)
    docs = res.scalars().all()
    return docs

@router.get("/{document_id}/pages")
async def get_document_pages(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    p_stmt = select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.physical_page_number.asc())
    p_res = await db.execute(p_stmt)
    pages = p_res.scalars().all()

    return {
        "document_id": doc.id,
        "original_filename": doc.original_filename,
        "physical_page_count": doc.physical_page_count,
        "pages": [
            {
                "id": p.id,
                "physical_page_number": p.physical_page_number,
                "printed_page_number": p.printed_page_number,
                "ocr_applied": p.ocr_applied,
                "text_snippet": (p.raw_text or "")[:200]
            } for p in pages
        ]
    }

@router.get("/{document_id}/view")
async def view_document_pdf(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Secure authenticated document serving endpoint for embedded PDF viewer."""
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc or not os.path.exists(doc.stored_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    return FileResponse(
        path=doc.stored_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={doc.original_filename}"}
    )
