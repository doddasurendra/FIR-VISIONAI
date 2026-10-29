import asyncio
import json
import os
import shutil
import hashlib
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ...config import settings
from ...database import get_db, AsyncSessionLocal
from ...models.user import User
from ...models.bulk import BulkJob
from ...services.auth import get_current_user
from ...services.bulk_ingestion import bulk_service
from ...services.bulk_scans import expand_uploads, run_scan_job
from ...services.audit import log_audit_event

router = APIRouter(prefix="/bulk", tags=["Bulk Historical Ingestion"])

async def run_bulk_job_background(job_id: str, file_path: str, user: User):
    async with AsyncSessionLocal() as db:
        await bulk_service.process_csv_or_json(job_id, file_path, user, db)

@router.post("/upload")
async def upload_bulk_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    fname = file.filename.lower()
    file_type = "CSV" if fname.endswith(".csv") else "JSON" if fname.endswith(".json") else None
    if not file_type:
        raise HTTPException(status_code=400, detail="Only CSV and JSON structured datasets are supported for bulk intake.")

    dest_path = os.path.join(settings.EVIDENCE_DIR, f"bulk_{int(os.times().elapsed)}_{file.filename}")
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Compute hash
    hasher = hashlib.sha256()
    with open(dest_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    file_hash = hasher.hexdigest()

    job = BulkJob(
        filename=file.filename,
        file_type=file_type,
        file_hash=file_hash,
        status="PENDING",
        user_id=current_user.id
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Run in background
    background_tasks.add_task(run_bulk_job_background, job.id, dest_path, current_user)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="BULK_INGESTION_STARTED",
        object_type="BULK_JOB",
        object_id=job.id,
        after_state={"filename": file.filename, "type": file_type, "hash": file_hash}
    )

    return job

@router.post("/upload-scans")
async def upload_scanned_firs(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk ingestion of scanned FIRs: several PDFs / images and/or ZIP archives of them in one job.
    Each file goes through the normal upload pipeline (OCR, extraction, indexing, duplicate detection);
    poll GET /bulk/jobs/{job_id} for per-file progress.
    """
    uploads = [(f.filename or "file", await f.read()) for f in files]
    items, skipped = expand_uploads(uploads)
    if not items:
        raise HTTPException(status_code=400, detail={"message": "No scanned FIR files (PDF, JPG, PNG, WEBP) were found.",
                                                     "skipped": skipped})
    names = [f.filename or "file" for f in files]
    job = BulkJob(
        filename=names[0] if len(names) == 1 else f"{len(names)} uploads ({', '.join(names[:3])}{'…' if len(names) > 3 else ''})"[:255],
        file_type="SCANNED_FIRS",
        file_hash=hashlib.sha256(b"".join(hashlib.sha256(d).digest() for _, d in items)).hexdigest(),
        status="PROCESSING",
        total_records=len(items),
        user_id=current_user.id,
        errors_json=json.dumps({"files": [{"name": n.rsplit("/", 1)[-1], "source": n, "status": "QUEUED"} for n, _ in items],
                                "skipped": skipped}, ensure_ascii=False),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await log_audit_event(db=db, actor_id=current_user.id, actor_username=current_user.username,
                          action_type="BULK_SCAN_INGESTION_STARTED", object_type="BULK_JOB", object_id=job.id,
                          after_state={"files": len(items), "skipped": len(skipped), "uploads": names[:20]})
    asyncio.create_task(run_scan_job(job.id, items, current_user.id))
    return _job_view(job)


def _job_view(job: BulkJob) -> dict:
    data = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    try:
        detail = json.loads(job.errors_json or "{}")
    except ValueError:
        detail = {}
    if isinstance(detail, dict) and "files" in detail:
        data["files"] = detail["files"]
        data["skipped"] = detail.get("skipped", [])
    return data


def _scope_jobs(stmt, user: User):
    # State officers see every job; others see the jobs they started
    return stmt if user.role == "STATE" else stmt.where(BulkJob.user_id == user.id)


@router.get("/jobs")
async def list_bulk_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = _scope_jobs(select(BulkJob).order_by(desc(BulkJob.created_at)).limit(20), current_user)
    res = await db.execute(stmt)
    return [_job_view(j) for j in res.scalars().all()]

@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = _scope_jobs(select(BulkJob).where(BulkJob.id == job_id), current_user)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_view(job)
