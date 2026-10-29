"""AI summaries of historical FIR records: listing with coverage, per-record summaries, and batches."""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.user import User
from ...services import fir_summaries as fs
from ...services.audit import log_audit_event
from ...services.auth import get_current_user

router = APIRouter(prefix="/summaries", tags=["AI Case Summaries"])


def _matches(rec: dict, search, district, station, case_status, date_from, date_to) -> bool:
    if search:
        s = search.strip().lower()
        if not any(s in str(rec.get(k) or "").lower() for k in ("fir_number", "title", "station", "district")):
            return False
    if district and (rec.get("district") or "").lower() != district.lower():
        return False
    if station and station.lower() not in (rec.get("station") or "").lower():
        return False
    if case_status and (rec.get("case_status") or "UNREGISTERED") != case_status:
        return False
    d = rec.get("record_date")
    d = d.date() if isinstance(d, datetime) else d
    if date_from and (not d or d < date_from):
        return False
    if date_to and (not d or d > date_to):
        return False
    return True


@router.get("/records")
async def list_records(
    search: Optional[str] = None, district: Optional[str] = None, station: Optional[str] = None,
    case_status: Optional[str] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
    summary_status: Optional[str] = Query(None, description="COMPLETED, STALE, PENDING, FAILED or NEEDS_REVIEW"),
    language: str = "en",
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Authorised historical FIR records with each language's summary state, plus coverage counts."""
    if language not in fs.LANGUAGES:
        raise HTTPException(status_code=400, detail="Language must be en, te or hi.")
    records = await fs.list_records(db, current_user)
    rows = await fs.summary_rows(db, [r["record_key"] for r in records], status_only=True)
    items, coverage = [], {
        "total_records": len(records), "eligible": 0, "needs_ocr_or_review": 0,
        "by_language": {l: {"COMPLETED": 0, "STALE": 0, "PENDING": 0, "FAILED": 0} for l in fs.LANGUAGES},
    }
    for rec in records:
        state = fs.summary_state(rec, rows.get(rec["record_key"], {}))
        usable = rec["source_chars"] >= fs.MIN_SOURCE_CHARS
        coverage["eligible" if usable else "needs_ocr_or_review"] += 1
        for l in fs.LANGUAGES:
            if state[l] in coverage["by_language"][l]:
                coverage["by_language"][l][state[l]] += 1
        if not _matches(rec, search, district, station, case_status, date_from, date_to):
            continue
        if summary_status and state[language] != summary_status:
            continue
        items.append({**{k: v for k, v in rec.items() if k != "source_hash"},
                      "record_date": rec["record_date"].isoformat() if rec.get("record_date") else None,
                      "usable_text": usable, "summary_state": state})
    items.sort(key=lambda r: r["record_date"] or "", reverse=True)
    return {"items": items, "coverage": coverage, "languages": list(fs.LANGUAGES)}


@router.get("/records/{record_key}")
async def get_summary(record_key: str, language: str = "en",
                      db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The stored summary of one record in one language (generated on request, never implicitly)."""
    if language not in fs.LANGUAGES:
        raise HTTPException(status_code=400, detail="Language must be en, te or hi.")
    rec = await fs.authorized_record(db, current_user, record_key)
    row = (await fs.summary_rows(db, [record_key])).get(record_key, {}).get(language)
    out = fs.serialize_summary(row, rec)
    if out["status"] == "PENDING" and rec["source_chars"] < fs.MIN_SOURCE_CHARS:
        out = {"status": "NEEDS_REVIEW", "error": "No readable text is stored for this FIR record; run OCR again or review the document."}
    return {"record": {**{k: v for k, v in rec.items() if k != "source_hash"},
                       "record_date": rec["record_date"].isoformat() if rec.get("record_date") else None},
            **out}


class GenerateRequest(BaseModel):
    regenerate: bool = False


@router.post("/records/{record_key}/generate")
async def generate_summary(record_key: str, req: GenerateRequest, language: str = "en",
                           db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Summarise one record (all three languages from the same sources); up-to-date summaries are reused."""
    if language not in fs.LANGUAGES:
        raise HTTPException(status_code=400, detail="Language must be en, te or hi.")
    rec = await fs.authorized_record(db, current_user, record_key)
    outcome = await fs.generate_record(db, current_user, rec, force=req.regenerate)
    if outcome["status"] in ("COMPLETED",):
        await log_audit_event(db=db, actor_id=current_user.id, actor_username=current_user.username,
                              action_type="FIR_SUMMARY_GENERATED", object_type="FIR_RECORD", object_id=record_key,
                              after_state={"languages": list(fs.LANGUAGES), "regenerate": req.regenerate})
    if outcome["status"] == "QUOTA_EXHAUSTED":
        raise HTTPException(status_code=503, detail="The AI provider's quota is exhausted; existing summaries are still shown. Try again later.")
    if outcome["status"] == "FAILED":
        raise HTTPException(status_code=502, detail=f"The summary could not be generated: {outcome.get('error') or 'unknown error'}")
    row = (await fs.summary_rows(db, [record_key])).get(record_key, {}).get(language)
    return {"outcome": outcome["status"], "record_key": record_key, **fs.serialize_summary(row, rec)}


class BatchRequest(BaseModel):
    record_keys: Optional[List[str]] = None  # default: every authorised record that needs a summary
    include_stale: bool = True


@router.post("/batch")
async def start_batch(req: BatchRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Summarise many authorised records in the background; progress via GET /summaries/batch/{id}."""
    records = await fs.list_records(db, current_user)
    allowed = {r["record_key"]: r for r in records}
    if req.record_keys:
        unknown = [k for k in req.record_keys if k not in allowed]
        if unknown:
            raise HTTPException(status_code=404, detail=f"{len(unknown)} selected record(s) were not found or are not authorised.")
        keys = list(dict.fromkeys(req.record_keys))
    else:
        rows = await fs.summary_rows(db, list(allowed), status_only=True)
        keys = []
        for key, rec in allowed.items():
            state = fs.summary_state(rec, rows.get(key, {}))
            todo = {"PENDING", "FAILED"} | ({"STALE"} if req.include_stale else set())
            if any(state[l] in todo for l in fs.LANGUAGES) and rec["source_chars"] >= fs.MIN_SOURCE_CHARS:
                keys.append(key)
            elif rec["source_chars"] < fs.MIN_SOURCE_CHARS and not rows.get(key):
                keys.append(key)  # recorded as NEEDS_REVIEW, so coverage reflects it
    if not keys:
        return {"status": "NOTHING_TO_DO", "message": "Every authorised record already has an up-to-date summary.", "total": 0}
    job = await fs.start_batch(db, current_user, keys)
    return fs.serialize_batch(job)


@router.get("/batch/active")
async def active_batch(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = await fs.active_batch(db, current_user)
    return fs.serialize_batch(job) if job else {"status": "NONE"}


@router.get("/batch/{job_id}")
async def batch_status(job_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ...models.bulk import BulkJob
    job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id, BulkJob.file_type == "SUMMARY"))).scalar_one_or_none()
    if not job or (job.user_id != current_user.id and current_user.role != "STATE"):
        raise HTTPException(status_code=404, detail="Batch not found.")
    return fs.serialize_batch(job)


@router.post("/batch/{job_id}/cancel")
async def cancel_batch(job_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ...models.bulk import BulkJob
    job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id, BulkJob.file_type == "SUMMARY"))).scalar_one_or_none()
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Batch not found.")
    if job.status == "RUNNING":
        job.status = "CANCELLED"
        await db.commit()
    return fs.serialize_batch(job)
