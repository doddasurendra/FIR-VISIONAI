"""
Extraction quality check: flags case fields that contradict the FIR text they were extracted from.

For every case with an FIR document, the document's page text is read with the deterministic FIR
form parser and compared with the stored case: offence date, place, offence nature, legal sections,
contraband, vehicle, accused, and the station's district (station master list). Each problem is a
row of extraction_quality_flags; a re-run closes flags that no longer apply. Runs on demand
(POST /api/v1/extraction/quality-check, scripts/run_extraction_quality_check.py) and nightly when
EXTRACTION_QC_NIGHTLY is set.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case, CaseField
from ..models.document import Document, DocumentPage
from ..models.extraction import ExtractionQualityFlag
from .field_validation import CONTRABAND_NOT_APPLICABLE, canonical_contraband
from .fir_form_parser import normalise_registration, parse_fir_text
from .jurisdiction import station_master_district
from .text_processing import clean_extracted_text, is_placeholder_text

logger = logging.getLogger(__name__)

_STOP = {"the", "of", "and", "or", "a", "an", "in", "on", "at", "by", "to", "for", "with", "from", "near", "case",
         "offence", "illegal", "under", "sec", "section", "act", "fir", "police", "station", "district", "lost"}
_PLACEHOLDER_PLACE = re.compile(r"^[\s,]*(null|none|n/?a)?([\s,]+(null|none|n/?a))*[\s,]*$|^[\s,]+", re.I)


def _words(text: Optional[str]) -> set:
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in _STOP}


def _flag(code: str, field: str, message: str, stored=None, source=None, evidence=None, severity="ERROR") -> Dict:
    return {"check_code": code, "field_name": field, "message": message, "severity": severity,
            "stored_value": None if stored is None else str(stored)[:1000],
            "source_value": None if source is None else str(source)[:1000],
            "evidence": None if evidence is None else str(evidence)[:1000]}


async def fir_text_for_case(db: AsyncSession, case: Case) -> (Optional[str], Optional[str]):
    """(document id, cleaned page text) of the case's FIR document, or (None, None)."""
    docs = (await db.execute(select(Document).where(Document.case_id == case.id, Document.is_archived == False)  # noqa: E712
                             .order_by(Document.created_at))).scalars().all()
    for doc in sorted(docs, key=lambda d: d.doc_category != "FIR"):
        pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_id == doc.id)
                                  .order_by(DocumentPage.physical_page_number))).scalars().all()
        text = "\n\n".join(clean_extracted_text(p.raw_text or "") for p in pages
                           if not p.is_unreadable and not is_placeholder_text(p.raw_text or ""))
        if len(text.strip()) >= 100:
            return doc.id, text
    return None, None


def check_case_against_text(case: Case, fields: List[CaseField], text: str, master_district: Optional[str]) -> List[Dict]:
    """Every contradiction between a case and its FIR text (pure: no database access)."""
    p = parse_fir_text(text)
    low = text.lower()
    flags: List[Dict] = []
    by_name = {f.field_name: (f.human_override_value or f.normalized_value or f.original_value) for f in fields}

    # Date
    stored_date = case.offence_date or case.incident_date
    if p.offence_date:
        if not stored_date:
            flags.append(_flag("DATE_MISSING", "offence_date", f"The FIR gives the offence date {p.offence_date:%d.%m.%Y}, "
                               "but the case has none.", None, f"{p.offence_date:%Y-%m-%d}", p.evidence.get("offence_date")))
        elif stored_date.date() != p.offence_date.date():
            flags.append(_flag("DATE_MISMATCH", "offence_date", f"Case offence date {stored_date:%d.%m.%Y} differs from "
                               f"the FIR ({p.offence_date:%d.%m.%Y}).", f"{stored_date:%Y-%m-%d}",
                               f"{p.offence_date:%Y-%m-%d}", p.evidence.get("offence_date")))
    # Place
    stored_place = case.incident_place_raw or case.location_description
    if p.place:
        if not stored_place or _PLACEHOLDER_PLACE.match(stored_place) or "null" in stored_place.lower():
            flags.append(_flag("PLACE_MISSING", "incident_place_raw", f"The FIR gives the place '{p.place}', but the case "
                               "place is empty or a placeholder.", stored_place, p.place, p.evidence.get("place")))
        elif not (_words(stored_place) & _words(p.place + " " + (p.address or ""))):
            flags.append(_flag("PLACE_MISMATCH", "incident_place_raw", f"Case place '{stored_place}' does not match the "
                               f"FIR place '{p.place}'.", stored_place, p.place, p.evidence.get("place")))
    # Offence nature: its words must occur in the FIR text (or match the offences of the recorded sections)
    if case.offence_nature:
        offence_words = _words(case.offence_nature)
        label_words = _words(p.offence_label())
        if offence_words and not any(w in low for w in offence_words) and not (offence_words & label_words):
            flags.append(_flag("OFFENCE_NOT_IN_TEXT", "offence_nature", f"Offence '{case.offence_nature}' is not supported "
                               "by the FIR text" + (f" (the FIR sections describe: {p.offence_label()})." if p.offence_label() else "."),
                               case.offence_nature, p.offence_label(), p.evidence.get("sections")))
    # Sections recorded in the FIR must be on the case
    if p.sections:
        recorded = " ".join(str(by_name.get(k) or "") for k in ("law_sections", "reported_offences_acts", "sections"))
        recorded_nums = set(re.findall(r"\d{1,3}[A-Z]{0,2}", recorded.upper()))
        missing = [f"{a} {s}" for a, s in p.sections if re.sub(r"\(.*", "", s).upper() not in recorded_nums]
        if missing:
            flags.append(_flag("SECTIONS_MISSING", "law_sections", "Sections recorded in the FIR are missing from the case: "
                               + ", ".join(missing) + ".", recorded.strip() or None, ", ".join(p.section_labels()),
                               p.evidence.get("sections"), severity="WARN"))
    # Contraband
    contraband = (case.contraband_type or "").strip()
    if contraband and contraband != CONTRABAND_NOT_APPLICABLE and canonical_contraband(contraband) is None:
        flags.append(_flag("CONTRABAND_INVALID", "contraband_type", f"'{contraband}' is not a contraband type.",
                           contraband, p.contraband_raw, p.evidence.get("contraband")))
    elif p.contraband_type and canonical_contraband(contraband) != p.contraband_type:
        flags.append(_flag("CONTRABAND_MISMATCH", "contraband_type", f"The FIR records {p.seized_quantity:g} {p.seized_unit} "
                           f"{p.contraband_raw}; the case has '{contraband or 'none'}'.", contraband or None,
                           p.contraband_type, p.evidence.get("contraband")))
    elif not contraband:
        flags.append(_flag("CONTRABAND_MISSING", "contraband_type", "No contraband is recorded. Record the seized item, or "
                           f"'{CONTRABAND_NOT_APPLICABLE}' when nothing was seized.", None, None, None, severity="WARN"))
    # Vehicle
    reg = normalise_registration(text)
    stored_reg = normalise_registration(case.vehicle_details)
    if case.vehicle_details and not stored_reg and reg:
        flags.append(_flag("VEHICLE_INVALID", "vehicle_details", f"Vehicle '{case.vehicle_details}' has no registration "
                           f"number; the FIR names {reg}.", case.vehicle_details, reg, p.evidence.get("vehicle")))
    elif stored_reg and stored_reg not in re.sub(r"[\s-]", "", text.upper()):
        flags.append(_flag("VEHICLE_NOT_IN_TEXT", "vehicle_details", f"Vehicle {stored_reg} does not occur in the FIR text.",
                           case.vehicle_details, reg, None))
    # Officer: never a software role
    if case.seizing_officer_name and re.search(r"system|architect|engineer|developer|admin", case.seizing_officer_name, re.I):
        flags.append(_flag("OFFICER_INVALID", "seizing_officer_name", f"'{case.seizing_officer_name}' is an application "
                           "user, not an officer named in the FIR.", case.seizing_officer_name, p.officer, None))
    # District must match the station master list
    if master_district and (case.district or "").strip().lower() != master_district.strip().lower():
        flags.append(_flag("DISTRICT_STATION_MISMATCH", "district", f"Station '{case.station}' belongs to {master_district} "
                           f"district, but the case district is '{case.district}'.", case.district, master_district, None))
    return flags


async def check_case(db: AsyncSession, case: Case) -> List[Dict]:
    fields = (await db.execute(select(CaseField).where(CaseField.case_id == case.id))).scalars().all()
    master = await station_master_district(db, case.station)
    doc_id, text = await fir_text_for_case(db, case)
    if not text:
        flags = []
        if master and (case.district or "").strip().lower() != master.strip().lower():
            flags.append(_flag("DISTRICT_STATION_MISMATCH", "district", f"Station '{case.station}' belongs to {master} "
                               f"district, but the case district is '{case.district}'.", case.district, master, None))
        if not (case.contraband_type or "").strip():
            flags.append(_flag("CONTRABAND_MISSING", "contraband_type", "No contraband is recorded.", severity="WARN"))
        return flags
    out = check_case_against_text(case, fields, text, master)
    for f in out:
        f["document_id"] = doc_id
    return out


async def run_quality_check(db: AsyncSession, cases: List[Case], run_id: Optional[str] = None,
                            persist: bool = True) -> Dict:
    """Check the given cases; store new flags, close fixed ones. Returns a summary with every flag."""
    run_id = run_id or str(uuid.uuid4())
    results, total = [], 0
    for case in cases:
        flags = await check_case(db, case)
        total += len(flags)
        results.append({"case_id": case.id, "fir_number": case.fir_number, "flags": flags})
        if not persist:
            continue
        existing = (await db.execute(select(ExtractionQualityFlag).where(
            ExtractionQualityFlag.case_id == case.id, ExtractionQualityFlag.status == "OPEN"))).scalars().all()
        keep = {(f["check_code"], f["field_name"]) for f in flags}
        for row in existing:
            if (row.check_code, row.field_name) not in keep:
                row.status = "RESOLVED"
        open_keys = {(r.check_code, r.field_name): r for r in existing if (r.check_code, r.field_name) in keep}
        for f in flags:
            row = open_keys.get((f["check_code"], f["field_name"]))
            if row is None:
                db.add(ExtractionQualityFlag(id=str(uuid.uuid4()), case_id=case.id, run_id=run_id, status="OPEN", **f))
            else:
                for k, v in f.items():
                    setattr(row, k, v)
                row.run_id = run_id
    if persist:
        await db.commit()
    return {"run_id": run_id, "cases_checked": len(cases), "flags": total,
            "cases_with_flags": sum(1 for r in results if r["flags"]), "results": results}


async def _nightly_loop(hour: int) -> None:
    from ..database import AsyncSessionLocal
    from .audit import log_audit_event
    while True:
        now = datetime.now()
        nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            async with AsyncSessionLocal() as db:
                cases = (await db.execute(select(Case).where(Case.is_archived == False, Case.deleted_at.is_(None)))).scalars().all()  # noqa: E712
                summary = await run_quality_check(db, cases)
                await log_audit_event(db, actor_id="system", actor_username="system", action_type="EXTRACTION_QUALITY_CHECK",
                                      object_type="SYSTEM", object_id=summary["run_id"],
                                      after_state={k: summary[k] for k in ("cases_checked", "flags", "cases_with_flags")})
                logger.info(f"Nightly extraction quality check: {summary['flags']} flags on {summary['cases_with_flags']} cases")
        except Exception as e:
            logger.warning(f"Nightly extraction quality check failed: {type(e).__name__}: {e}")


def start_nightly(hour: int) -> asyncio.Task:
    return asyncio.create_task(_nightly_loop(hour))
