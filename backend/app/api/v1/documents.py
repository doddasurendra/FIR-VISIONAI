import os
import shutil
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
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
                )
                document_id = processed_doc.id  # may be same or the deduplicated existing doc
            except Exception as ocr_err:
                logger.error(f"Background OCR/pipeline failed for job {job_id}: {ocr_err}")
                _job_update(job_id, "FAILED", 15, f"Document processing error: {str(ocr_err)[:200]}")
                try:
                    await db.rollback()
                except Exception:
                    pass
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
                config = cfg_res.scalar_one_or_none()
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
            except Exception as ext_err:
                logger.warning(f"Background extraction failed for job {job_id}: {ext_err}")
                try:
                    await db.rollback()
                except Exception:
                    pass
                extraction_payload = {}

            _job_update(job_id, "INDEXING", 80)

            # Stage 3: Reindex chunks for RAG
            try:
                from ...services.pdf_pipeline import reindex_document
                await reindex_document(document_id, db)
            except Exception as ri_err:
                logger.warning(f"Background reindex failed for job {job_id}: {ri_err}")
                try:
                    await db.rollback()
                except Exception:
                    pass

            # Mark complete — store extraction payload for the frontend to pick up
            flat_extracted: dict = {}
            if extraction_payload.get("structured_fields"):
                for f in extraction_payload["structured_fields"]:
                    k = f.get("key")
                    if k:
                        flat_extracted[k] = f.get("value")

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
            _job_update(job_id, "FAILED", 0, f"Unexpected error: {str(fatal_err)[:300]}")
            try:
                await db.rollback()
            except Exception:
                pass

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
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }
    if job["stage"] == "COMPLETED":
        response["extraction_payload"] = job.get("extraction_payload") or {}
        response["extracted_data"] = job.get("extracted_data") or {}
    return response


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
    # 1. Read file bytes and enforce size limit
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the maximum allowed size of 50 MB. Please reduce the file size."
        )

    # 2. Content-based MIME detection
    detected_mime = _detect_mime_type(file.filename, file_bytes)

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
            logger.info(f"Deduplication hit: Reusing existing extraction for {file.filename} (hash={file_hash[:12]})")
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
            _job_create(job_id, existing_doc.id, file.filename, current_user.id)
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
            }

    # 3. Store file via StorageService
    storage_meta = await storage_service.upload_file(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=detected_mime
    )

    # 4. Resolve local path for processing
    local_path = storage_meta["stored_path"]
    if storage_meta["storage_type"] == "SUPABASE":
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{storage_meta['file_hash'][:8]}_{file.filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    # 5. Create a stub Document record immediately (status=PROCESSING) so UI can reference it
    doc_stub = Document(
        case_id=case_id,
        original_filename=file.filename,
        stored_path=local_path,
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
    _job_create(job_id, doc_stub.id, file.filename, current_user.id)

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
                "filename": file.filename,
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
            original_filename=file.filename,
            detected_mime=detected_mime,
            user_id=current_user.id,
            case_id=case_id,
            storage_type=storage_meta["storage_type"],
        )
    )

    # 9. Return immediately — frontend polls /documents/jobs/{job_id}/status
    return {
        "job_id": job_id,
        "id": doc_stub.id,
        "document_id": doc_stub.id,
        "filename": file.filename,
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
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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
    include_archived: bool = Query(False, description="Whether to include soft-deleted/archived documents"),
    skip: int = 0,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List documents with search, category filtering, and role-based jurisdictional scoping.
    Used by Knowledge Base and Case Document Management.
    """
    stmt = select(Document)
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
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Document.original_filename.ilike(pattern),
                Document.document_title.ilike(pattern),
                Document.source_department.ilike(pattern),
                Document.doc_category.ilike(pattern)
            )
        )

    # Jurisdiction filter for non-case documents: universal/statewide documents accessible to all roles
    statewide_districts = ["STATE", "ALL", "Statewide", "STATEWIDE", "All Districts"]
    if current_user.role == "DISTRICT":
        stmt = stmt.where(
            or_(
                Document.district == current_user.district,
                Document.district.is_(None),
                Document.district.in_(statewide_districts)
            )
        )
    elif current_user.role == "STATION":
        stmt = stmt.where(
            or_(
                and_(
                    Document.district == current_user.district,
                    or_(Document.station == current_user.station, Document.station.is_(None))
                ),
                Document.district.is_(None),
                Document.district.in_(statewide_districts)
            )
        )

    # Get total count
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(desc(Document.created_at)).offset(skip).limit(limit)
    res = await db.execute(stmt)
    docs = res.scalars().all()

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
                "source_department": d.source_department or "AP Prohibition & Excise",
                "version_date": d.version_date,
                "district": d.district or "Statewide",
                "station": d.station,
                "physical_page_count": d.physical_page_count,
                "mime_type": d.mime_type,
                "file_hash": d.file_hash,
                "is_verified_official": d.is_verified_official,
                "is_archived": d.is_archived,
                "archive_reason": d.archive_reason,
                "archived_at": d.archived_at.isoformat() if d.archived_at else None,
                "replaced_by_id": d.replaced_by_id,
                "replaces_id": d.replaces_id,
                "replacement_reason": d.replacement_reason,
                "status": d.ingestion_status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "created_by": d.created_by,
            }
            for d in docs
        ]
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

    # Role-based jurisdictional filtering
    if current_user.role == "STATION":
        stmt = stmt.where(
            or_(
                and_(
                    or_(Case.district == current_user.district, Document.district == current_user.district),
                    or_(Case.station == current_user.station, Document.station == current_user.station, Case.station.is_(None), Document.station.is_(None))
                ),
                and_(Case.district.is_(None), Document.district.is_(None))
            )
        )
    elif current_user.role == "DISTRICT":
        stmt = stmt.where(
            or_(
                Case.district == current_user.district,
                Document.district == current_user.district,
                and_(Case.district.is_(None), Document.district.is_(None))
            )
        )

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


@router.post("/knowledge-base/upload")
async def upload_knowledge_base_document(
    file: UploadFile = File(...),
    document_title: str = Form(..., description="Official title of the document"),
    category: str = Form("LEGAL_ACT", description="LEGAL_ACT, CIRCULAR, SEIZURE_REPORT, INVESTIGATION_GUIDE, REFERENCE, HISTORICAL_FIR, EVIDENCE"),
    source_department: Optional[str] = Form("AP Prohibition & Excise Department"),
    version_date: Optional[str] = Form(None),
    district: Optional[str] = Form(None),
    station: Optional[str] = Form(None),
    is_verified_official: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload official document to the departmental Knowledge Base.
    Parses text, indexes pages/chunks, and computes embeddings for Grounded RAG.
    """
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds maximum size of 50 MB.")

    detected_mime = _detect_mime_type(file.filename, file_bytes)
    import hashlib
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Store via StorageService
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

    # Ingest document and index pages/chunks
    doc = await pdf_pipeline.process_document(
        file_path=local_path,
        original_filename=file.filename,
        mime_type=detected_mime,
        user_id=current_user.id,
        db=db,
        case_id=None
    )

    # Populate Knowledge Base metadata
    doc.document_title = document_title
    doc.doc_category = category
    doc.source_department = source_department
    doc.version_date = version_date
    doc.district = district
    doc.station = station
    doc.is_verified_official = is_verified_official
    doc.is_archived = False

    await db.commit()
    await db.refresh(doc)

    # Invalidate general KB query cache
    from ...services.rag_engine import rag_engine
    rag_engine.invalidate_cache()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="KB_DOCUMENT_UPLOADED",
        object_type="DOCUMENT",
        object_id=doc.id,
        after_state={
            "title": document_title,
            "category": category,
            "source": source_department,
            "version_date": version_date,
            "hash": file_hash,
            "pages": doc.physical_page_count,
            "is_verified_official": is_verified_official
        }
    )

    return {
        "message": f"Knowledge Base document '{document_title}' uploaded and indexed successfully.",
        "id": doc.id,
        "document_title": doc.document_title,
        "category": doc.doc_category,
        "physical_page_count": doc.physical_page_count,
        "status": doc.ingestion_status
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
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    old_doc = res.scalar_one_or_none()
    if not old_doc:
        raise HTTPException(status_code=404, detail="Document not found")

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
        case_id=old_doc.case_id
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
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

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

    # 1. Direct local disk streaming if file exists locally
    if doc.stored_path and os.path.exists(doc.stored_path):
        mime = doc.mime_type or ("image/png" if (doc.original_filename or "").lower().endswith(".png") else "application/pdf")
        return FileResponse(
            path=doc.stored_path,
            media_type=mime,
            headers={"Content-Disposition": f"inline; filename={doc.original_filename}"}
        )

    # 2. Check evidence directories on disk
    evidence_dir = settings.EVIDENCE_DIR
    fname = doc.original_filename or "document"
    fhash = doc.file_hash or ""
    candidates = [
        os.path.join(evidence_dir, fname),
        os.path.join(evidence_dir, "cloud_cache", fname),
        os.path.join(evidence_dir, f"{fhash[:8]}_{fname}" if fhash else ""),
        os.path.join(evidence_dir, "cloud_cache", f"{fhash[:8]}_{fname}" if fhash else ""),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            mime = doc.mime_type or ("image/png" if fname.lower().endswith(".png") else "application/pdf")
            return FileResponse(
                path=c,
                media_type=mime,
                headers={"Content-Disposition": f"inline; filename={fname}"}
            )

    # 3. If stored in Supabase cloud, fetch binary bytes directly to prevent CORS/redirect failures
    if storage_service.is_cloud_configured() and doc.stored_path:
        try:
            file_bytes = await storage_service.get_file_bytes(doc.stored_path, storage_type="SUPABASE")
            if file_bytes:
                mime = doc.mime_type or ("image/png" if fname.lower().endswith(".png") else "application/pdf")
                return Response(
                    content=file_bytes,
                    media_type=mime,
                    headers={"Content-Disposition": f"inline; filename={fname}"}
                )
        except Exception as cloud_err:
            logger.warning(f"Could not retrieve document bytes from cloud: {cloud_err}")

    # 4. If neither found, 404 with clear message
    raise HTTPException(status_code=404, detail=f"Evidence file '{doc.original_filename}' is not available on storage.")


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_user_from_header_or_param)
):
    """Secure document download endpoint."""
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not os.path.exists(doc.stored_path):
        raise HTTPException(status_code=404, detail="Document file not found on storage")

    mime = doc.mime_type or "application/octet-stream"
    return FileResponse(
        path=doc.stored_path,
        media_type=mime,
        filename=doc.original_filename,
        headers={"Content-Disposition": f"attachment; filename=\"{doc.original_filename}\""}
    )
