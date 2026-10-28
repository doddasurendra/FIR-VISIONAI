"""
AI summaries of historical FIR records, built on the existing records (no copied dataset).

A record is an active FIR document ("doc:<id>") or a registered case that has no FIR document
("case:<id>"). Its sources are the document's stored page text (OCR) plus the officer-entered case
fields and officer-approved field corrections. One model call produces English, Telugu and Hindi
from the same numbered sources; each language is stored as a row of fir_summaries with its
citations, version and a fingerprint of the sources, so a summary is reused until its source
changes. Records without usable text are marked NEEDS_REVIEW instead of being summarised.
"""
import asyncio
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import Case, CaseField
from ..models.document import Document, DocumentPage
from ..models.extraction import ExtractionRun
from ..models.generation import FIRSummary
from ..models.user import User
from .auth import apply_case_scope_filter, enforce_data_scope
from .document_access import apply_document_scope, user_can_access_document
from .text_processing import clean_extracted_text, split_text

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "te", "hi")
FIELD_KEYS = [
    "fir_number", "source_document", "incident_date", "incident_location", "complainant", "accused",
    "witnesses", "officers", "narrative", "alleged_offences", "seized_items", "legal_sections",
    "investigation_progress", "key_evidence", "missing_information", "ambiguities",
]
NOT_IN_SOURCE = "NOT_IN_SOURCE"
MIN_SOURCE_CHARS = 200      # less readable text than this is not summarised
MAX_SOURCE_CHARS = 30000    # cap on text sent to the model for one record
LOW_OCR_CONFIDENCE = 0.6

FIELD_LABELS = {
    "en": {
        "overview": "Overview", "fir_number": "FIR number", "source_document": "Source document",
        "incident_date": "Incident date", "incident_location": "Incident location", "complainant": "Complainant",
        "accused": "Accused", "witnesses": "Witnesses", "officers": "Officers", "narrative": "Incident narrative",
        "alleged_offences": "Alleged offences", "seized_items": "Seized items and quantities",
        "legal_sections": "Legal sections recorded", "investigation_progress": "Investigation progress",
        "key_evidence": "Key evidence", "missing_information": "Missing or unreadable information",
        "ambiguities": "Ambiguities and conflicting statements",
        "_na": "Not available in the source",
    },
    "te": {
        "overview": "సారాంశం", "fir_number": "ఎఫ్‌ఐఆర్ సంఖ్య", "source_document": "మూల పత్రం",
        "incident_date": "సంఘటన తేదీ", "incident_location": "సంఘటన స్థలం", "complainant": "ఫిర్యాదుదారు",
        "accused": "నిందితులు", "witnesses": "సాక్షులు", "officers": "అధికారులు", "narrative": "సంఘటన వివరణ",
        "alleged_offences": "ఆరోపిత నేరాలు", "seized_items": "స్వాధీనం చేసుకున్న వస్తువులు, పరిమాణాలు",
        "legal_sections": "నమోదైన చట్ట సెక్షన్లు", "investigation_progress": "దర్యాప్తు పురోగతి",
        "key_evidence": "ముఖ్యమైన సాక్ష్యాలు", "missing_information": "లేని లేదా చదవలేని సమాచారం",
        "ambiguities": "అస్పష్టతలు, పరస్పర విరుద్ధ ప్రకటనలు",
        "_na": "మూల పత్రంలో అందుబాటులో లేదు",
    },
    "hi": {
        "overview": "सारांश", "fir_number": "एफआईआर संख्या", "source_document": "स्रोत दस्तावेज़",
        "incident_date": "घटना की तारीख", "incident_location": "घटना स्थल", "complainant": "शिकायतकर्ता",
        "accused": "अभियुक्त", "witnesses": "गवाह", "officers": "अधिकारी", "narrative": "घटना का विवरण",
        "alleged_offences": "आरोपित अपराध", "seized_items": "जब्त वस्तुएँ और मात्रा",
        "legal_sections": "दर्ज कानूनी धाराएँ", "investigation_progress": "जाँच की प्रगति",
        "key_evidence": "मुख्य साक्ष्य", "missing_information": "अनुपलब्ध या अपठनीय जानकारी",
        "ambiguities": "अस्पष्टताएँ और विरोधाभासी कथन",
        "_na": "स्रोत में उपलब्ध नहीं",
    },
}


# ── Records ─────────────────────────────────────────────────────────────────

def _case_date(case: Optional[Case]):
    if not case:
        return None
    return case.incident_date or case.offence_date or case.registration_date


def _run_fir_number(run: Optional[ExtractionRun]) -> Optional[str]:
    if not run:
        return None
    for raw in (run.reviewed_extracted_json, run.raw_extracted_json):
        try:
            data = json.loads(raw or "{}")
        except Exception:
            continue
        for f in data.get("structured_fields", []) or []:
            if isinstance(f, dict) and f.get("key") == "fir_number" and str(f.get("value") or "").strip():
                return str(f["value"]).strip()[:100]
    return None


# FIR number read from an extraction run, by run id -> (run updated_at, FIR number). A run's JSON
# is large, so it is read once per version of the run rather than on every listing.
_RUN_FIR_CACHE: Dict[str, Tuple[Any, Optional[str]]] = {}


async def _run_fir_numbers(db: AsyncSession, document_ids: List[str]) -> Dict[str, Optional[str]]:
    """The extracted FIR number of each document's latest extraction run."""
    latest: Dict[str, Tuple[str, Any]] = {}
    for run_id, doc_id, updated in (await db.execute(
        select(ExtractionRun.id, ExtractionRun.document_id, ExtractionRun.updated_at)
        .where(ExtractionRun.document_id.in_(document_ids)).order_by(ExtractionRun.created_at)
    )).all():
        latest[doc_id] = (run_id, updated)  # latest run per document
    stale = [rid for rid, upd in latest.values() if _RUN_FIR_CACHE.get(rid, (None,))[0] != upd]
    if stale:
        for run in (await db.execute(select(ExtractionRun).where(ExtractionRun.id.in_(stale)))).scalars().all():
            _RUN_FIR_CACHE[run.id] = (run.updated_at, _run_fir_number(run))
    return {doc_id: _RUN_FIR_CACHE.get(rid, (None, None))[1] for doc_id, (rid, _) in latest.items()}


async def list_records(db: AsyncSession, user: User, only: Optional[str] = None) -> List[Dict]:
    """
    Every historical FIR record the user is authorised to see, with text availability and a source
    fingerprint. `only` (a record key) limits every query to that one record.
    """
    kind, _, rid = (only or "").partition(":")
    docs_stmt = select(Document).where(Document.doc_category == "FIR", Document.is_archived == False)  # noqa: E712
    if kind == "doc":
        docs_stmt = docs_stmt.where(Document.id == rid)
    elif kind == "case":
        docs_stmt = docs_stmt.where(Document.case_id == rid)  # an FIR document makes it a document record
    docs = (await db.execute(apply_document_scope(docs_stmt, user))).scalars().all()
    case_ids = {d.case_id for d in docs if d.case_id}
    cases_stmt = apply_case_scope_filter(select(Case).where(Case.is_archived == False, Case.deleted_at.is_(None)), user, Case)  # noqa: E712
    if kind == "case":
        cases_stmt = cases_stmt.where(Case.id == rid)
    scoped_cases = {} if kind == "doc" else {c.id: c for c in (await db.execute(cases_stmt)).scalars().all()}
    linked_cases = {c.id: c for c in (await db.execute(select(Case).where(Case.id.in_(case_ids)))).scalars().all()} if case_ids else {}

    doc_ids = [d.id for d in docs]
    page_stats = {}
    if doc_ids:
        rows = (await db.execute(
            select(DocumentPage.document_id, func.count(DocumentPage.id), func.max(DocumentPage.updated_at),
                   func.coalesce(func.sum(func.length(DocumentPage.raw_text)), 0))
            .where(DocumentPage.document_id.in_(doc_ids), func.coalesce(DocumentPage.is_unreadable, False) == False)  # noqa: E712
            .group_by(DocumentPage.document_id)
        )).all()
        page_stats = {r[0]: (r[1], r[2], int(r[3] or 0)) for r in rows}
    field_stamp = {}
    all_case_ids = list(case_ids | set(scoped_cases))
    if all_case_ids:
        rows = (await db.execute(
            select(CaseField.case_id, func.count(CaseField.id), func.max(CaseField.updated_at))
            .where(CaseField.case_id.in_(all_case_ids)).group_by(CaseField.case_id)
        )).all()
        field_stamp = {r[0]: (r[1], r[2]) for r in rows}
    run_firs = {}
    unlinked = [d.id for d in docs if not d.case_id]
    if unlinked:
        run_firs = await _run_fir_numbers(db, unlinked)

    records = []
    for d in docs:
        case = linked_cases.get(d.case_id)
        pages, page_updated, chars = page_stats.get(d.id, (0, None, 0))
        stamp = [d.id, pages, chars, str(page_updated), d.updated_at.isoformat() if d.updated_at else ""]
        if case:
            stamp += [case.updated_at.isoformat() if case.updated_at else "", str(field_stamp.get(case.id))]
        records.append({
            "record_key": f"doc:{d.id}", "record_type": "FIR_DOCUMENT", "document_id": d.id,
            "case_id": case.id if case else None,
            "fir_number": (case.fir_number if case else None) or run_firs.get(d.id) or d.reference_number,
            "title": d.document_title or d.original_filename,
            "district": (case.district if case else None) or d.district,
            "station": (case.station if case else None) or d.station,
            "case_status": case.status if case else None,
            "record_date": (_case_date(case) or d.created_at),
            "index_status": d.index_status,
            "source_chars": chars,
            "source_hash": hashlib.sha256(json.dumps(stamp, default=str).encode()).hexdigest(),
        })
    fir_case_ids = {d.case_id for d in docs if d.case_id}
    # Case records are summarised from their narrative and the other documents filed on them
    case_only = [cid for cid in scoped_cases if cid not in fir_case_ids]
    filed_chars = {}
    if case_only:
        rows = (await db.execute(
            select(Document.case_id, func.coalesce(func.sum(func.length(DocumentPage.raw_text)), 0))
            .join(DocumentPage, DocumentPage.document_id == Document.id)
            .where(Document.case_id.in_(case_only), Document.is_archived == False,  # noqa: E712
                   func.coalesce(DocumentPage.is_unreadable, False) == False)  # noqa: E712
            .group_by(Document.case_id)
        )).all()
        filed_chars = {r[0]: int(r[1] or 0) for r in rows}
    for case in scoped_cases.values():
        if case.id in fir_case_ids:
            continue
        # The registered record's structured fields (offence, place, dates, seizure, officer) are a
        # source too, so a case entered without a long narrative is still summarisable
        block = _case_block(case, [])
        chars = len((case.narrative or "").strip()) + filed_chars.get(case.id, 0) + (len(block["text"]) if block else 0)
        stamp = [case.id, case.updated_at.isoformat() if case.updated_at else "", str(field_stamp.get(case.id)), chars]
        records.append({
            "record_key": f"case:{case.id}", "record_type": "CASE_RECORD", "document_id": None, "case_id": case.id,
            "fir_number": case.fir_number, "title": f"Case {case.fir_number}",
            "district": case.district, "station": case.station, "case_status": case.status,
            "record_date": _case_date(case), "index_status": None, "source_chars": chars,
            "source_hash": hashlib.sha256(json.dumps(stamp, default=str).encode()).hexdigest(),
        })
    return records


async def summary_rows(db: AsyncSession, keys: List[str], status_only: bool = False) -> Dict[str, Dict[str, FIRSummary]]:
    """
    Stored summaries by record and language. status_only loads just what summary_state() needs,
    not the summary JSON and text (the bulk of the data when listing every record).
    """
    out: Dict[str, Dict[str, FIRSummary]] = {}
    for i in range(0, len(keys), 500):
        if status_only:
            # Plain objects, not partly loaded ORM rows that would break a later full read in this session
            for key, lang, status, source_hash in (await db.execute(
                select(FIRSummary.record_key, FIRSummary.language, FIRSummary.status, FIRSummary.source_hash)
                .where(FIRSummary.record_key.in_(keys[i:i + 500]))
            )).all():
                out.setdefault(key, {})[lang] = SimpleNamespace(record_key=key, language=lang, status=status,
                                                                source_hash=source_hash)
            continue
        for row in (await db.execute(select(FIRSummary).where(FIRSummary.record_key.in_(keys[i:i + 500])))).scalars().all():
            out.setdefault(row.record_key, {})[row.language] = row
    return out


def summary_state(record: Dict, rows: Dict[str, FIRSummary]) -> Dict[str, str]:
    """Per language: COMPLETED, STALE (source changed since), FAILED, NEEDS_REVIEW or PENDING."""
    state = {}
    for lang in LANGUAGES:
        row = rows.get(lang)
        if record["source_chars"] < MIN_SOURCE_CHARS and (not row or row.status != "COMPLETED"):
            state[lang] = "NEEDS_REVIEW"
        elif not row or row.status == "NEEDS_REVIEW":
            # A record flagged for missing text that now has readable text (e.g. after OCR was retried)
            state[lang] = "PENDING"
        elif row.status == "COMPLETED":
            state[lang] = "COMPLETED" if row.source_hash == record["source_hash"] else "STALE"
        else:
            state[lang] = row.status
    return state


async def authorized_record(db: AsyncSession, user: User, record_key: str) -> Dict:
    """The record for a key, after the same authorisation checks as the rest of the application."""
    kind, _, rid = record_key.partition(":")
    if kind == "doc":
        doc = (await db.execute(select(Document).where(Document.id == rid))).scalar_one_or_none()
        if not doc or doc.doc_category != "FIR" or doc.is_archived or not await user_can_access_document(db, user, doc):
            raise HTTPException(status_code=404, detail="FIR record not found.")
    elif kind == "case":
        case = (await db.execute(select(Case).where(Case.id == rid))).scalar_one_or_none()
        if not case or not enforce_data_scope(user, case.district, case.station):
            raise HTTPException(status_code=404, detail="FIR record not found.")
    else:
        raise HTTPException(status_code=400, detail="Unknown record key.")
    for rec in await list_records(db, user, only=record_key):
        if rec["record_key"] == record_key:
            return rec
    # e.g. a case that does have an FIR document: summarise it through that document
    raise HTTPException(status_code=404, detail="FIR record not found.")


# ── Sources ─────────────────────────────────────────────────────────────────

def _case_block(case: Case, fields: List[CaseField]) -> Optional[Dict]:
    lines = []
    for label, value in (
        ("FIR number", case.fir_number), ("Year", case.year), ("District", case.district), ("Station", case.station),
        ("Mandal", case.mandal), ("Village", case.village), ("Incident location", case.incident_place_raw or case.location_description),
        ("Offence date", case.offence_date), ("Incident date", case.incident_date), ("Registration date", case.registration_date),
        ("Offence / allegation", case.offence_nature), ("Contraband", case.contraband_type),
        ("Seized quantity", f"{case.seized_quantity} {case.seized_unit or ''}".strip() if case.seized_quantity else None),
        ("Vehicle", case.vehicle_details), ("Seizing / investigating officer",
         f"{case.seizing_officer_name or ''} {('(' + case.seizing_officer_rank + ')') if case.seizing_officer_rank else ''}".strip() or None),
        ("Witnesses", case.witnesses_summary), ("Case status", case.status),
    ):
        if value not in (None, "", 0):
            lines.append(f"{label}: {value.date().isoformat() if isinstance(value, datetime) else value}")
    approved = []
    for f in fields:
        value = f.human_override_value or (f.normalized_value if f.verification_status in ("VERIFIED", "OVERRIDDEN") else None)
        if value and f.field_name not in ("document_content",):
            approved.append(f"{f.field_name}: {str(value)[:300]}")
    if approved:
        lines.append("Officer-approved field values: " + "; ".join(approved))
    if not lines:
        return None
    return {"label": "Registered case record (officer-entered and officer-approved fields)", "text": "\n".join(lines),
            "document_id": None, "page": None}


async def build_sources(db: AsyncSession, record: Dict) -> Tuple[List[Dict], int]:
    """Numbered source passages for a record and the number of readable source-text characters."""
    sources: List[Dict] = []
    case = None
    if record["case_id"]:
        case = (await db.execute(select(Case).where(Case.id == record["case_id"]))).scalar_one_or_none()
    budget, text_chars = MAX_SOURCE_CHARS, 0

    def add_pages(doc, pages, label):
        nonlocal budget, text_chars
        for p in pages:
            if p.is_unreadable:
                continue
            text = clean_extracted_text(p.raw_text or "")
            if not text.strip():
                continue
            text_chars += len(text)
            for part in split_text(text, max_chars=1800, overlap=0):
                if budget <= 0:
                    return
                part = part[:budget]
                budget -= len(part)
                sources.append({
                    "label": label, "text": part, "document_id": doc.id, "page": p.physical_page_number,
                    "ocr": bool(p.ocr_applied),
                    "ocr_uncertain": bool(p.ocr_applied and p.ocr_confidence is not None and p.ocr_confidence < LOW_OCR_CONFIDENCE),
                })

    if record["document_id"]:
        doc = (await db.execute(select(Document).where(Document.id == record["document_id"]))).scalar_one()
        pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_id == doc.id)
                                  .order_by(DocumentPage.physical_page_number))).scalars().all()
        add_pages(doc, pages, f"FIR document '{doc.document_title or doc.original_filename}'")
    if case:
        fields = (await db.execute(select(CaseField).where(CaseField.case_id == case.id))).scalars().all()
        block = _case_block(case, fields)
        if block:
            sources.append(block)
            registered = _case_block(case, [])
            if not record["document_id"] and registered:
                text_chars += len(registered["text"])  # counted as in list_records
        if not record["document_id"]:
            narrative = (case.narrative or "").strip()
            for part in split_text(narrative, max_chars=1800, overlap=0) if narrative else []:
                text_chars += len(part)
                sources.append({"label": "Case narrative recorded at registration", "text": part, "document_id": None, "page": None})
            # Other documents filed on the case (evidence) also describe the incident
            others = (await db.execute(select(Document).where(Document.case_id == case.id, Document.is_archived == False))).scalars().all()  # noqa: E712
            for doc in others:
                pages = (await db.execute(select(DocumentPage).where(DocumentPage.document_id == doc.id)
                                          .order_by(DocumentPage.physical_page_number))).scalars().all()
                add_pages(doc, pages, f"{doc.doc_category.title()} document '{doc.document_title or doc.original_filename}'")
    return sources, text_chars


# ── Generation ──────────────────────────────────────────────────────────────

_NUMBER = re.compile(r"\d[\d/.,:-]*\d|\d")
_NAME = re.compile(r"\b[A-Z][a-z]{2,}\b")
# Capitalised words a summary may use that are not names taken from the record
_GENERIC_WORDS = {
    "The", "This", "That", "These", "Those", "There", "His", "Her", "Their", "And", "But", "According", "Between",
    "After", "Before", "During", "From", "With", "Without", "Under", "Sri", "Smt", "Mr", "Mrs", "Ms", "Shri",
    "Indian", "India", "Andhra", "Pradesh", "State", "District", "Dist", "Mandal", "Village", "Police", "Station",
    "Excise", "Prohibition", "Department", "Court", "Act", "Acts", "Code", "Penal", "Section", "Sections", "Rule",
    "Rules", "Report", "Information", "First", "Case", "Crime", "Complaint", "Complainant", "Accused", "Officer",
    "Inspector", "Sub", "Advocate", "Source", "Sources", "Not", "None", "Unknown", "Details", "Date", "Year",
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "Liquor", "Vehicle", "Seized", "Seizure", "Alleged", "Allegedly", "Reportedly",
    "Investigation", "Witness", "Witnesses", "Prevention", "Corruption", "Narcotic", "Drugs", "Psychotropic",
    "Substances", "Bharatiya", "Nyaya", "Sanhita", "Nagarik", "Suraksha", "Sakshya", "Adhiniyam", "Registered",
    "Record", "Records", "Document", "Page", "Nationality", "Occupation", "Address", "Resident", "Son", "Daughter",
    "Wife", "Aged", "Male", "Female", "Total", "Quantity", "Further", "Also", "However", "Both",
}


def _unsupported_names(text: str, cited_text: str) -> List[str]:
    """Capitalised names in an English statement that do not occur in the sources it cites (e.g. an
    OCR spelling the model 'corrected')."""
    low = cited_text.lower()
    return sorted({w for w in _NAME.findall(text or "") if w not in _GENERIC_WORDS and w.lower() not in low})


def _unsupported_numbers(text: str, cited_text: str) -> List[str]:
    """Numbers in a generated statement that do not occur in the sources it cites."""
    plain = re.sub(r"\s+", "", cited_text)
    out = []
    for n in _NUMBER.findall(text or ""):
        core = n.strip(".,:-/")
        if len(core) >= 2 and core not in plain and core.replace(",", "") not in plain.replace(",", ""):
            out.append(core)
    return sorted(set(out))


_MONTH_NAMES = {
    1: ["january", "jan", "జనవరి", "जनवरी"], 2: ["february", "feb", "ఫిబ్రవరి", "फ़रवरी", "फरवरी"],
    3: ["march", "mar", "మార్చి", "मार्च"], 4: ["april", "apr", "ఏప్రిల్", "अप्रैल"], 5: ["may", "మే", "मई"],
    6: ["june", "jun", "జూన్", "जून"], 7: ["july", "jul", "జూలై", "జులై", "जुलाई"],
    8: ["august", "aug", "ఆగస్టు", "ఆగస్ట్", "अगस्त"], 9: ["september", "sep", "sept", "సెప్టెంబర్", "సెప్టెంబరు", "सितंबर", "सितम्बर"],
    10: ["october", "oct", "అక్టోబర్", "అక్టోబరు", "अक्टूबर"], 11: ["november", "nov", "నవంబర్", "నవంబరు", "नवंबर", "नवम्बर"],
    12: ["december", "dec", "డిసెంబర్", "డిసెంబరు", "दिसंबर", "दिसम्बर"],
}
_MONTH_RX = re.compile(r"(?<!\w)(?:" + "|".join(sorted((re.escape(n) for ns in _MONTH_NAMES.values() for n in ns),
                                                       key=len, reverse=True)) + r")(?!\w)", re.I)
_MONTH_OF = {n.lower(): m for m, ns in _MONTH_NAMES.items() for n in ns}


def number_values(text: str) -> set:
    """
    The numbers a statement contains, script-independent: digit runs in any script plus month names
    next to a number ("14th August 2024", "ఆగస్టు 14, 2024" and "14.08.2024" all give {14, 8, 2024}).
    """
    text = text or ""
    values = {int(d) for d in re.findall(r"\d+", text)}
    for m in _MONTH_RX.finditer(text):
        window = text[max(0, m.start() - 5):m.end() + 5]
        if re.search(r"\d", window) and (m.group(0)[0].isupper() or not m.group(0).isascii()
                                         or len(m.group(0)) > 3):
            values.add(_MONTH_OF[m.group(0).lower()])
    return values


_MONTH_ALT = "|".join(sorted((re.escape(n) for ns in _MONTH_NAMES.values() for n in ns), key=len, reverse=True))
_DATE_DAY_FIRST = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s,.-]*(" + _MONTH_ALT + r")(?![a-z])", re.I)
_DATE_MONTH_FIRST = re.compile(r"(?<![a-z])(" + _MONTH_ALT + r")[\s,.-]*(\d{1,2})(?:st|nd|rd|th)?(?!\d)", re.I)
_DATE_NUMERIC = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](?:\d{4}|\d{2})(?!\d)")
_DATE_ISO = re.compile(r"(?<!\d)\d{4}-(\d{1,2})-(\d{1,2})(?!\d)")


def date_values(text: str) -> set:
    """
    Every (day, month) a statement names, script- and format-independent: "14th August 2024",
    "ఆగస్టు 14, 2024", "2024 ఆగస్టు 14న", "14.08.2024" and "2024-08-14" all give {(14, 8)}. An added
    alternative date ("20th August 2024 or 14th August 2024") gives a second pair, even when 20 occurs
    elsewhere in the statement (an age, a quantity), which number_values() alone cannot see.
    """
    text = text or ""
    out = set()
    for d, mon in _DATE_DAY_FIRST.findall(text):
        out.add((int(d), _MONTH_OF[mon.lower()]))
    for mon, d in _DATE_MONTH_FIRST.findall(text):
        out.add((int(d), _MONTH_OF[mon.lower()]))
    for d, m in _DATE_NUMERIC.findall(text):
        out.add((int(d), int(m)))
    for m, d in _DATE_ISO.findall(text):
        out.add((int(d), int(m)))
    return {(d, m) for d, m in out if 1 <= d <= 31 and 1 <= m <= 12}


_VEHICLE_REG = re.compile(r"\b[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{1,3}[ -]?\d{3,4}\b")
_SECTION_NO = re.compile(r"(?<![\w/])\d{1,3}(?:\([0-9A-Za-z]{1,3}\))+|(?<![\w/])\d{1,3}[A-Z]{1,2}\b")
_IDENTIFIER = re.compile(r"\b(?=[A-Z0-9/-]*\d)(?=[A-Z0-9/-]*[A-Z])[A-Z0-9]+(?:[-/][A-Z0-9]+)+\b")
_PERSON = re.compile(r"\b(?:[A-Z]\.\s?){1,3}[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})?|\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,}){1,2}\b")
PEOPLE_FIELDS = ("complainant", "accused", "witnesses", "officers")


def person_names(english_fields: Dict[str, Dict]) -> List[str]:
    """Person names in the English people fields ("Ramu Naidu", "K. Venkateshwarlu"), generic words dropped."""
    names: List[str] = []
    for key in PEOPLE_FIELDS:
        text = ((english_fields or {}).get(key) or {}).get("text") or ""
        for m in _PERSON.finditer(text):
            words = [w for w in m.group(0).split() if w.strip(".") not in _GENERIC_WORDS]
            name = " ".join(words)
            if (len(words) >= 2 or "." in name) and name not in names:
                names.append(name)
    return names


def protected_tokens(text: str, names: Sequence[str] = ()) -> List[str]:
    """
    Values a translation must keep exactly as the English writes them: vehicle registrations, FIR and
    other identifiers, section numbers and person names. (Dates and numbers are compared by value.)
    """
    text = text or ""
    found: List[str] = []
    for rx in (_VEHICLE_REG, _IDENTIFIER, _SECTION_NO):
        for m in rx.finditer(text):
            if m.group(0) not in found:
                found.append(m.group(0))
    found += [n for n in names if n in text and n not in found]
    return found


def _squash(s: str) -> str:
    return re.sub(r"[\s-]+", "", s or "").lower()


def translation_problems(translated: str, english: str, names: Sequence[str] = ()) -> List[str]:
    """What a translated statement got wrong against its English source; empty when it is faithful."""
    problems = []
    if date_values(translated) != date_values(english):
        problems.append("dates")
    if number_values(translated) != number_values(english):
        problems.append("numbers")
    flat = _squash(translated)
    missing = [t for t in protected_tokens(english, names) if _squash(t) not in flat]
    if missing:
        problems.append("protected: " + ", ".join(missing[:5]))
    return problems


def _normalise_language(lang_data: Dict, n_sources: int, sources: List[Dict], lang: str,
                        reference: Optional[Dict] = None) -> Tuple[Dict, str, List[str]]:
    """
    Validated structured summary, display text and warnings for one language. A Telugu or Hindi
    statement whose dates or numbers differ from the English one (the `reference`) is replaced by
    the English text, so a translation can never change a date, quantity or section number.
    """
    labels = FIELD_LABELS[lang]
    warnings: List[str] = []
    names = person_names(reference) if reference else []

    def check_translation(key: str, entry: Dict) -> None:
        ref = (reference or {}).get(key)
        if lang == "en" or not ref or not ref.get("available") or not entry["available"]:
            return
        problems = translation_problems(entry["text"], ref["text"], names)
        if problems:
            entry["translation_mismatch"] = True
            entry["translation_problems"] = problems
            entry["translated_text"] = entry["text"]
            entry["text"] = ref["text"]
            entry["citations"] = ref["citations"]
            warnings.append(f"{labels.get(key, key)}: the translation changed a date or number "
                            f"({'; '.join(problems)}), so the English text is shown")

    def clean(entry) -> Dict:
        if not isinstance(entry, dict):
            entry = {"text": str(entry or NOT_IN_SOURCE), "citations": []}
        text = str(entry.get("text") or NOT_IN_SOURCE).strip()
        cites = sorted({int(c) for c in entry.get("citations") or [] if str(c).isdigit() and 0 < int(c) <= n_sources})
        available = text.upper() != NOT_IN_SOURCE
        return {"text": text if available else None, "available": available, "citations": cites if available else []}

    overview = clean(lang_data.get("overview"))
    check_translation("overview", overview)
    fields = {}
    raw_fields = lang_data.get("fields") if isinstance(lang_data.get("fields"), dict) else {}
    for key in FIELD_KEYS:
        entry = clean(raw_fields.get(key))
        check_translation(key, entry)
        if entry["available"]:
            if not entry["citations"] and key not in ("missing_information",):
                entry["uncited"] = True
                warnings.append(f"{labels.get(key, key)}: no source citation")
            cited_sources = [sources[c - 1] for c in entry["citations"]] if entry["citations"] else sources
            cited = " ".join(f"{s.get('label', '')} {s['text']}" for s in cited_sources)
            unsupported = _unsupported_numbers(entry["text"], cited)
            if unsupported and lang == "en":
                entry["unverified_numbers"] = unsupported
                warnings.append(f"{labels.get(key, key)}: numbers not found in the cited source ({', '.join(unsupported[:5])})")
            names = _unsupported_names(entry["text"], cited) if lang == "en" else []
            if names:
                entry["unverified_names"] = names
                warnings.append(f"{labels.get(key, key)}: names not found in the cited source ({', '.join(names[:5])})")
        fields[key] = entry

    lines = []
    if overview["available"]:
        lines.append(overview["text"] + "".join(f" [S{c}]" for c in overview["citations"]))
    for key in FIELD_KEYS:
        e = fields[key]
        body = (e["text"] + "".join(f" [S{c}]" for c in e["citations"])) if e["available"] else labels["_na"]
        lines.append(f"{labels[key]}: {body}")
    return {"overview": overview, "fields": fields, "labels": {k: labels[k] for k in ["overview"] + FIELD_KEYS}}, "\n".join(lines), warnings


async def _upsert(db: AsyncSession, record: Dict, lang: str, **values) -> FIRSummary:
    row = (await db.execute(select(FIRSummary).where(FIRSummary.record_key == record["record_key"],
                                                     FIRSummary.language == lang))).scalar_one_or_none()
    if row is None:
        row = FIRSummary(id=str(uuid.uuid4()), record_key=record["record_key"], language=lang, version=0,
                         document_id=record["document_id"], case_id=record["case_id"])
        db.add(row)
    for k, v in values.items():
        setattr(row, k, v)
    return row


async def needs_review_reason(db: AsyncSession, record: Dict) -> str:
    """Specific, actionable reason a record has too little readable text to summarise."""
    if record.get("document_id"):
        doc = (await db.execute(select(Document).where(Document.id == record["document_id"]))).scalar_one_or_none()
        if doc and doc.error_message:
            return doc.error_message[:500]
        return ("OCR_NO_TEXT: the FIR document has no readable page text. Press Re-process to run OCR again "
                "(two engines, enhanced image); if it still fails, re-upload a clearer scan or archive it.")
    return ("NO_SOURCE_DOCUMENT: this case has no FIR document and too few recorded details to summarise. "
            "Attach the FIR document to the case or complete the case record.")


async def _retry_unfaithful_translation(lang_data: Dict, reference: Dict, lang: str) -> Tuple[Dict, List[str]]:
    """
    Statements of a Telugu/Hindi summary that change a date, number, identifier, section or name of the
    English one are translated once more from the English, with those values passed as protected tokens.
    Returns the (possibly) repaired language data and the keys that were retried; a statement still
    wrong after the retry falls back to the English text in _normalise_language.
    """
    from .gemini import gemini_service
    names = person_names(reference)
    raw_fields = lang_data.get("fields") if isinstance(lang_data.get("fields"), dict) else {}

    def text_of(key):
        entry = lang_data.get("overview") if key == "overview" else raw_fields.get(key)
        return str((entry or {}).get("text") if isinstance(entry, dict) else entry or "").strip()

    bad: Dict[str, Dict] = {}
    for key in ["overview"] + FIELD_KEYS:
        ref = reference.get(key) or {}
        translated = text_of(key)
        if not ref.get("available") or not translated or translated.upper() == NOT_IN_SOURCE:
            continue
        if translation_problems(translated, ref["text"], names):
            bad[key] = {"text": ref["text"], "protected": protected_tokens(ref["text"], names)}
    if not bad:
        return lang_data, []
    try:
        fixed = await asyncio.to_thread(gemini_service.translate_summary_statements, bad, lang)
    except Exception as e:
        logger.warning(f"Translation retry ({lang}) failed: {type(e).__name__}: {e}")
        fixed = None
    if not fixed:
        return lang_data, list(bad)
    repaired = {**lang_data, "fields": dict(raw_fields)}
    for key, text in fixed.items():
        if key not in bad or not isinstance(text, str) or not text.strip():
            continue
        cites = reference[key].get("citations") or []
        if key == "overview":
            repaired["overview"] = {"text": text.strip(), "citations": cites}
        else:
            repaired["fields"][key] = {"text": text.strip(), "citations": cites}
    return repaired, list(bad)


async def generate_record(db: AsyncSession, user: User, record: Dict, force: bool = False) -> Dict:
    """
    Summarise one authorised record in all three languages (or reuse up-to-date summaries).
    Returns {"status": "COMPLETED" | "UP_TO_DATE" | "NEEDS_REVIEW" | "FAILED" | "QUOTA_EXHAUSTED", "error": ...}.
    """
    from .gemini import gemini_service
    existing = (await summary_rows(db, [record["record_key"]])).get(record["record_key"], {})
    if not force and all(existing.get(l) is not None and existing[l].status == "COMPLETED"
                         and existing[l].source_hash == record["source_hash"] for l in LANGUAGES):
        return {"status": "UP_TO_DATE"}

    sources, text_chars = await build_sources(db, record)
    now = datetime.utcnow()
    if text_chars < MIN_SOURCE_CHARS:
        reason = await needs_review_reason(db, record)
        for lang in LANGUAGES:
            if not (existing.get(lang) and existing[lang].status == "COMPLETED"):
                await _upsert(db, record, lang, status="NEEDS_REVIEW", error_message=reason, source_hash=record["source_hash"],
                              source_chars=text_chars, generated_by=user.id, generated_at=now, summary_json=None,
                              summary_text=None, citations_json=None)
        await db.commit()
        return {"status": "NEEDS_REVIEW", "error": reason}

    result = await asyncio.to_thread(gemini_service.summarize_fir_record, sources, FIELD_KEYS)
    if result["status"] != "OK":
        error = result.get("error") or result["status"]
        for lang in LANGUAGES:
            # A previous good summary stays available (shown as stale); only record the failure otherwise
            if not (existing.get(lang) and existing[lang].status == "COMPLETED"):
                await _upsert(db, record, lang, status="FAILED", error_message=error[:500], source_hash=record["source_hash"],
                              source_chars=text_chars, generated_by=user.id, generated_at=now)
        await db.commit()
        return {"status": "QUOTA_EXHAUSTED" if result["status"] == "QUOTA_EXHAUSTED" else "FAILED", "error": error}

    data = result["data"]
    citations = [{"n": i, "label": s["label"], "document_id": s.get("document_id"), "page": s.get("page"),
                  "ocr_uncertain": bool(s.get("ocr_uncertain"))} for i, s in enumerate(sources, start=1)]
    produced = 0
    reference = None  # the English statements the translations are checked against
    for lang in LANGUAGES:
        lang_data = (data.get("languages") or {}).get(lang)
        if not isinstance(lang_data, dict):
            await _upsert(db, record, lang, status="FAILED", error_message=f"The model returned no {lang} summary.",
                          source_hash=record["source_hash"], generated_at=now, generated_by=user.id)
            continue
        retried: List[str] = []
        if lang != "en" and reference:
            lang_data, retried = await _retry_unfaithful_translation(lang_data, reference, lang)
        structured, text, warnings = _normalise_language(lang_data, len(sources), sources, lang, reference)
        if retried:
            structured["translation_retried"] = retried
        if lang == "en":
            reference = {"overview": structured["overview"], **structured["fields"]}
        structured["ocr_uncertain"] = bool(data.get("ocr_uncertain")) or any(s.get("ocr_uncertain") for s in sources)
        structured["warnings"] = warnings
        old = existing.get(lang)
        version = (old.version or 0) + 1 if old and old.status == "COMPLETED" else 1
        await _upsert(db, record, lang, status="COMPLETED", summary_json=json.dumps(structured, ensure_ascii=False),
                      summary_text=text, citations_json=json.dumps(citations, ensure_ascii=False),
                      source_hash=record["source_hash"], source_chars=text_chars, model=result.get("model"),
                      version=version, error_message=None, generated_by=user.id, generated_at=now)
        produced += 1
    await db.commit()
    return {"status": "COMPLETED" if produced == len(LANGUAGES) else "FAILED",
            "error": None if produced == len(LANGUAGES) else "Some languages were not produced."}


def serialize_summary(row: Optional[FIRSummary], record: Dict) -> Dict:
    if row is None:
        return {"status": "PENDING"}
    state = summary_state(record, {row.language: row})[row.language]
    return {
        "status": state, "language": row.language, "version": row.version,
        "generated_at": row.generated_at.isoformat() + "Z" if row.generated_at else None,
        "model": row.model, "error": row.error_message, "source_chars": row.source_chars,
        "summary": json.loads(row.summary_json) if row.summary_json else None,
        "summary_text": row.summary_text,
        "citations": json.loads(row.citations_json) if row.citations_json else [],
        "is_ai_generated": True,
    }


# ── Batches (progress kept in bulk_jobs) ────────────────────────────────────

_BATCH_TYPE = "SUMMARY"
_STALE_AFTER = timedelta(minutes=15)


async def active_batch(db: AsyncSession, user: User):
    from ..models.bulk import BulkJob
    job = (await db.execute(select(BulkJob).where(BulkJob.file_type == _BATCH_TYPE, BulkJob.user_id == user.id,
                                                  BulkJob.status == "RUNNING").order_by(BulkJob.created_at.desc()))).scalars().first()
    if job and job.updated_at and datetime.utcnow() - job.updated_at > _STALE_AFTER:
        job.status = "FAILED"
        job.errors_json = json.dumps((json.loads(job.errors_json or "[]") or []) +
                                     [{"error": "Interrupted (server restart or crash); start the batch again to resume."}])
        await db.commit()
        return None
    return job


async def start_batch(db: AsyncSession, user: User, record_keys: List[str]) -> "object":
    from ..models.bulk import BulkJob
    running = await active_batch(db, user)
    if running:
        return running
    job = BulkJob(filename=f"FIR summaries ({len(record_keys)} records, en/te/hi)", file_type=_BATCH_TYPE,
                  file_hash=uuid.uuid4().hex, total_records=len(record_keys), processed_records=0, success_count=0,
                  failure_count=0, status="RUNNING", errors_json="[]", user_id=user.id)
    db.add(job)
    await db.commit()
    asyncio.create_task(_run_batch(job.id, list(record_keys), user.id))
    return job


async def _run_batch(job_id: str, record_keys: List[str], user_id: str, pause_seconds: float = 1.0) -> None:
    """Summarise records one by one; per-record errors are recorded and the batch continues.
    A quota error pauses the batch: re-running it later resumes, skipping up-to-date records."""
    from ..database import AsyncSessionLocal
    from ..models.bulk import BulkJob
    async with AsyncSessionLocal() as db:
        try:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            records = {r["record_key"]: r for r in await list_records(db, user)}
            errors, counts = [], {"COMPLETED": 0, "UP_TO_DATE": 0, "NEEDS_REVIEW": 0, "FAILED": 0}
            final = "COMPLETED"
            for i, key in enumerate(record_keys, start=1):
                job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one()
                if job.status == "CANCELLED":
                    final = "CANCELLED"
                    break
                rec = records.get(key)
                if rec is None:
                    outcome = {"status": "FAILED", "error": "Record not found or not authorised."}
                else:
                    try:
                        outcome = await generate_record(db, user, rec)
                    except Exception as e:  # one bad record must not stop the batch
                        await db.rollback()
                        # A rollback expires loaded objects; reload the user before the next record
                        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
                        logger.exception(f"Summary failed for {key}")
                        outcome = {"status": "FAILED", "error": f"{type(e).__name__}: {str(e)[:200]}"}
                status_ = outcome["status"]
                if status_ == "QUOTA_EXHAUSTED":
                    errors.append({"record_key": key, "fir_number": rec and rec["fir_number"], "status": "PAUSED",
                                   "error": "AI provider quota exhausted; start the batch again later to resume."})
                    final = "PAUSED"
                    i -= 1
                else:
                    counts[status_] = counts.get(status_, 0) + 1
                    if status_ in ("FAILED", "NEEDS_REVIEW"):
                        errors.append({"record_key": key, "fir_number": rec and rec["fir_number"], "status": status_,
                                       "error": (outcome.get("error") or "")[:300]})
                job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one()
                job.processed_records = i
                job.success_count = counts["COMPLETED"] + counts["UP_TO_DATE"]
                job.failure_count = counts["FAILED"] + counts["NEEDS_REVIEW"]
                job.errors_json = json.dumps({"counts": counts, "errors": errors[-200:]}, ensure_ascii=False)
                job.updated_at = datetime.utcnow()
                await db.commit()
                if status_ == "COMPLETED" and rec is not None:
                    # Each AI-generated summary is audited, as for a single generation
                    from .audit import log_audit_event
                    await log_audit_event(db=db, actor_id=user.id, actor_username=user.username,
                                          action_type="FIR_SUMMARY_GENERATED", object_type="FIR_RECORD",
                                          object_id=key, after_state={"batch_job_id": job_id,
                                                                      "languages": list(LANGUAGES)},
                                          refresh=False)
                if final == "PAUSED":
                    break
                if status_ == "COMPLETED":
                    await asyncio.sleep(pause_seconds)  # stay well inside the provider's per-minute limit
            job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one()
            if job.status != "CANCELLED":
                job.status = final
            job.updated_at = datetime.utcnow()
            await db.commit()
        except Exception:
            logger.exception(f"Summary batch {job_id} failed")
            await db.rollback()
            job = (await db.execute(select(BulkJob).where(BulkJob.id == job_id))).scalar_one_or_none()
            if job:
                job.status = "FAILED"
                await db.commit()


def serialize_batch(job) -> Dict:
    info = {}
    try:
        info = json.loads(job.errors_json or "{}")
    except Exception:
        pass
    if isinstance(info, list):
        info = {"errors": info}
    return {
        "job_id": job.id, "status": job.status, "total": job.total_records, "processed": job.processed_records,
        "succeeded": job.success_count, "failed_or_review": job.failure_count,
        "counts": info.get("counts", {}), "errors": info.get("errors", []),
        "started_at": job.created_at.isoformat() + "Z" if job.created_at else None,
        "updated_at": job.updated_at.isoformat() + "Z" if job.updated_at else None,
    }
