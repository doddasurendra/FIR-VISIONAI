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

router = APIRouter(prefix="/documents", tags=["Document Ingestion & Evidence Viewer"])

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


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload FIR evidence document (PDF, JPEG, PNG, or WEBP).
    - PDFs are parsed page-by-page and indexed in FTS5 with physical page numbers.
    - Images (JPG/PNG/WEBP) are decoded, EXIF-corrected, and OCR-extracted via Gemini Multimodal.
    All originals are stored unchanged via the StorageService adapter.
    """
    # 1. Read file bytes and enforce size limit
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the maximum allowed size of 50 MB. Please reduce the file size."
        )

    # 2. Content-based MIME detection (magic bytes — not filename or browser-provided type)
    detected_mime = _detect_mime_type(file.filename, file_bytes)

    # 3. Store via StorageService adapter (Supabase private storage with local fallback)
    storage_meta = await storage_service.upload_file(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=detected_mime
    )

    # 4. Resolve local path for text extraction and OCR parsing
    local_path = storage_meta["stored_path"]
    if storage_meta["storage_type"] == "SUPABASE":
        # Cache locally for parsing
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{storage_meta['file_hash'][:8]}_{file.filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    # 5. Route to PDF or Image processing pipeline
    try:
        doc = await pdf_pipeline.process_document(
            file_path=local_path,
            original_filename=file.filename,
            mime_type=detected_mime,
            user_id=current_user.id,
            db=db,
            case_id=case_id
        )
    except Exception as e:
        if os.path.exists(local_path) and storage_meta["storage_type"] == "SUPABASE":
            try:
                os.remove(local_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=400,
            detail=f"Unable to process document '{file.filename}': {str(e)}. "
                   f"Please ensure the file is a valid, readable PDF, JPEG, PNG, or WEBP."
        )

    # 6. Audit event
    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="DOCUMENT_UPLOADED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={
            "filename": file.filename,
            "mime_type": detected_mime,
            "pages": doc.physical_page_count,
            "hash": doc.file_hash,
            "storage_type": storage_meta["storage_type"]
        }
    )

    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "mime_type": detected_mime,
        "physical_page_count": doc.physical_page_count,
        "is_image": detected_mime.startswith("image/"),
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
        "mime_type": doc.mime_type,
        "physical_page_count": doc.physical_page_count,
        "is_image": doc.mime_type and doc.mime_type.startswith("image/"),
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
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Enforce jurisdiction data scoping if document belongs to a case
    if doc.case_id:
        case_stmt = select(Case).where(Case.id == doc.case_id)
        case_res = await db.execute(case_stmt)
        case = case_res.scalar_one_or_none()
        if case and not enforce_data_scope(current_user, case.district, case.station):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to view documents from this jurisdiction."
            )

    # If Supabase cloud storage, attempt signed URL redirect
    if storage_service.is_cloud_configured():
        signed_url = await storage_service.create_signed_url(doc.stored_path)
        if signed_url:
            return RedirectResponse(url=signed_url)

    if not os.path.exists(doc.stored_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    mime = doc.mime_type or "application/pdf"
    return FileResponse(
        path=doc.stored_path,
        media_type=mime,
        headers={"Content-Disposition": f"inline; filename={doc.original_filename}"}
    )
