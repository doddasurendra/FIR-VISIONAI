"""
Bulk ingestion of scanned FIRs: many PDFs / images, or ZIP archives of them, in one job.

Every file goes through the same pipeline as a single upload (documents.ingest_file_bytes): type
check by content, reuse of an identical file already processed (duplicate), resume of an unfinished
one, storage, audit, OCR -> extraction -> indexing. Files are processed one after another and each
file's outcome is recorded on the BulkJob, so the page can show per-file progress.

ZIP safety: entries are read in memory only (no paths are written from archive names), nested
archives and hidden/system entries are skipped, and the number of files, each file's size, the
total size and the compression ratio are limited (zip-bomb protection).
"""
import asyncio
import hashlib
import io
import json
import logging
import os
import zipfile
from datetime import datetime
from typing import Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy import select

logger = logging.getLogger(__name__)

SCAN_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_FILES = 200
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
PER_FILE_TIMEOUT_S = 15 * 60


def expand_uploads(uploads: List[Tuple[str, bytes]]) -> Tuple[List[Tuple[str, bytes]], List[Dict[str, str]]]:
    """(accepted [(name, bytes)], skipped [{name, reason}]). ZIPs are expanded; other types are skipped."""
    accepted: List[Tuple[str, bytes]] = []
    skipped: List[Dict[str, str]] = []
    total = 0

    def take(name: str, data: bytes):
        nonlocal total
        ext = os.path.splitext(name.lower())[1]
        if ext not in SCAN_EXTENSIONS:
            skipped.append({"name": name, "reason": f"Unsupported file type '{ext or 'none'}' (PDF, JPG, PNG, WEBP)."})
        elif not data:
            skipped.append({"name": name, "reason": "Empty file."})
        elif len(data) > MAX_FILE_BYTES:
            skipped.append({"name": name, "reason": "Larger than 50 MB."})
        elif len(accepted) >= MAX_FILES:
            skipped.append({"name": name, "reason": f"More than {MAX_FILES} files in one job."})
        elif total + len(data) > MAX_TOTAL_BYTES:
            skipped.append({"name": name, "reason": "The job would exceed 500 MB in total."})
        else:
            total += len(data)
            accepted.append((name, data))

    for name, data in uploads:
        if name.lower().endswith(".zip"):
            try:
                archive = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                skipped.append({"name": name, "reason": "Not a valid ZIP archive."})
                continue
            for info in archive.infolist():
                entry = info.filename.replace("\\", "/")
                base = entry.rsplit("/", 1)[-1]
                if info.is_dir() or not base or base.startswith(".") or "__MACOSX/" in entry:
                    continue
                if base.lower().endswith(".zip"):
                    skipped.append({"name": f"{name}/{entry}", "reason": "Nested ZIP archives are not opened."})
                    continue
                if info.file_size > MAX_FILE_BYTES or (info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO):
                    skipped.append({"name": f"{name}/{entry}", "reason": "Too large when uncompressed."})
                    continue
                take(f"{name}/{entry}", archive.read(info))
        else:
            take(name, data)
    return accepted, skipped


async def run_scan_job(job_id: str, items: List[Tuple[str, bytes]], user_id: str) -> None:
    """Process each file in turn through the upload pipeline and record its outcome on the job."""
    from ..api.v1.documents import _PROCESSING_JOBS, ingest_file_bytes
    from ..database import AsyncSessionLocal
    from ..models.bulk import BulkJob
    from ..models.user import User

    def display(name: str) -> str:
        return name.rsplit("/", 1)[-1]

    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one()
        state = json.loads(job.errors_json or "{}")
        files = state.get("files", [])
        seen_hashes: Dict[str, str] = {}
        for i, (name, data) in enumerate(items):
            entry = files[i]
            digest = hashlib.sha256(data).hexdigest()
            try:
                if digest in seen_hashes:
                    entry.update(status="DUPLICATE", detail=f"Same file as {seen_hashes[digest]} in this job; not processed twice.")
                else:
                    seen_hashes[digest] = display(name)
                    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
                    entry["status"] = "PROCESSING"
                    await _save(db, job, files)
                    result = await ingest_file_bytes(db, user, display(name), data)
                    entry["document_id"] = result.get("document_id")
                    if result.get("is_deduplicated"):
                        entry.update(status="DUPLICATE", detail="Identical to a document already processed; reused it.")
                    else:
                        entry.update(await _wait_for(result["job_id"], _PROCESSING_JOBS))
            except HTTPException as e:
                detail = e.detail if isinstance(e.detail, str) else (e.detail or {}).get("message", str(e.detail))
                entry.update(status="DUPLICATE" if e.status_code == 409 else "FAILED", detail=detail)
            except Exception as e:  # one bad file must not stop the job
                logger.exception(f"Bulk scan {job_id}: {name} failed")
                try:
                    await db.rollback()
                except Exception:
                    pass
                entry.update(status="FAILED", detail=f"{type(e).__name__}: {str(e)[:200]}")
            job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one()
            job.processed_records = i + 1
            job.success_count = sum(1 for f in files if f["status"] in ("COMPLETED", "NEEDS_REVIEW"))
            job.failure_count = sum(1 for f in files if f["status"] == "FAILED")
            await _save(db, job, files)
        job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one()
        job.status = "COMPLETED" if job.failure_count == 0 else "PARTIALLY_FAILED"  # status column is VARCHAR(20)
        await _save(db, job, files)


async def _wait_for(doc_job_id: str, jobs: dict) -> Dict[str, str]:
    deadline = asyncio.get_running_loop().time() + PER_FILE_TIMEOUT_S
    while asyncio.get_running_loop().time() < deadline:
        j = jobs.get(doc_job_id) or {}
        if j.get("stage") == "COMPLETED":
            if j.get("warning"):
                return {"status": "NEEDS_REVIEW", "detail": j["warning"]}
            return {"status": "COMPLETED", "detail": "Processed: text read, fields extracted, indexed."}
        if j.get("stage") == "FAILED":
            return {"status": "FAILED", "detail": j.get("error") or "Processing failed."}
        await asyncio.sleep(1.0)
    return {"status": "FAILED", "detail": "Processing did not finish in time; use Retry processing on the document."}


async def _save(db, job, files) -> None:
    try:
        skipped = json.loads(job.errors_json or "{}").get("skipped", [])  # kept from the upload request
    except (ValueError, AttributeError):
        skipped = []
    job.errors_json = json.dumps({"files": files, "skipped": skipped}, ensure_ascii=False)
    job.updated_at = datetime.utcnow()
    await db.commit()
