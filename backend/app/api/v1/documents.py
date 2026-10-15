import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse, RedirectResponse
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
from ...services.storage import storage_service

router = APIRouter(prefix="/documents", tags=["Document Ingestion & PDF Viewer"])

@router.get("/storage-status")
async def get_storage_status(current_user: User = Depends(get_current_user)):
    """Return cloud storage status diagnostics."""
    return storage_service.get_status()

@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported for grounded page RAG.")

    # Check file size (limit to 50MB)
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds maximum allowed limit of 50MB.")

    # Store via StorageService adapter (Supabase private storage with local fallback)
    storage_meta = await storage_service.upload_file(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type="application/pdf"
    )

    # Local path for PDF text parsing & chunk extraction
    local_path = storage_meta["stored_path"]
    if storage_meta["storage_type"] == "SUPABASE":
        # Cache locally for parsing
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{storage_meta['file_hash'][:8]}_{file.filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    # Process through pipeline with graceful error capture
    try:
        doc = await pdf_pipeline.process_pdf(
            file_path=local_path,
            original_filename=file.filename,
            user_id=current_user.id,
            db=db,
            case_id=case_id
        )
    except Exception as e:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=400,
            detail=f"Unable to process or index PDF: {str(e)}. Please ensure the document is a valid, readable PDF."
        )

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_UPLOADED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={
            "filename": file.filename,
            "pages": doc.physical_page_count,
            "hash": doc.file_hash,
            "storage_type": storage_meta["storage_type"]
        }
    )

    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "physical_page_count": doc.physical_page_count,
        "file_hash": doc.file_hash,
        "status": doc.ingestion_status,
        "storage_type": storage_meta["storage_type"]
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
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # If Supabase cloud storage, attempt signed URL redirect
    if storage_service.is_cloud_configured():
        signed_url = await storage_service.create_signed_url(doc.stored_path)
        if signed_url:
            return RedirectResponse(url=signed_url)

    if not os.path.exists(doc.stored_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    return FileResponse(
        path=doc.stored_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={doc.original_filename}"}
    )
