import os
import shutil
import hashlib
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ...config import settings
from ...database import get_db, AsyncSessionLocal
from ...models.user import User
from ...models.bulk import BulkJob
from ...services.auth import get_current_user
from ...services.bulk_ingestion import bulk_service
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

@router.get("/jobs")
async def list_bulk_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(BulkJob).order_by(desc(BulkJob.created_at)).limit(20)
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(BulkJob).where(BulkJob.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
