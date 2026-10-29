"""
Re-extract a registered case from its FIR text.

Values read verbatim by the FIR form parser win; the model-based extraction only fills fields the
parser could not read (each such value must still occur in the text). Every change is audit-logged
with its before and after value, the case's entities are re-linked, and all six workflow stages run
again. dry_run=True reports the changes without writing anything.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import generate_uuid
from ..models.case import Case, CaseField
from ..models.entity import Entity, EntityMention, GraphEdge
from .extraction_quality import check_case_against_text, fir_text_for_case
from .field_validation import CONTRABAND_NOT_APPLICABLE, canonical_contraband
from .fir_form_parser import ParsedFIR, normalise_registration, parse_fir_text
from .jurisdiction import station_master_district
from .text_processing import clean_extracted_text

logger = logging.getLogger(__name__)

# Offences that involve seized contraband; any other case records "Not applicable", not "Unknown"
_SEIZURE = re.compile(r"liquor|arrack|ganja|cannabis|toddy|ndps|narcotic|excise|distill|contraband|seiz|wash|"
                      r"spurious|ndpl|bottle", re.I)
_APP_ROLE = re.compile(r"system|architect|engineer|developer|admin", re.I)


def _in_text(value: Optional[str], text: str) -> bool:
    words = [w for w in re.findall(r"[A-Za-z]{3,}", value or "")]
    return bool(words) and all(w.lower() in text.lower() for w in words)


def contraband_not_applicable(case: Case, text: str = "") -> bool:
    """
    True for a case whose offence involves no seized contraband (theft, missing person, cheating,
    accident ...): neither its offence nor the sections in its FIR text are excise or NDPS offences.
    """
    subject = f"{case.offence_nature or ''} {case.offence_category or ''}"
    if _SEIZURE.search(subject):
        return False
    acts = {act for act, _ in parse_fir_text(text).sections} if text else set()
    return not ({"AP Excise Act", "NDPS Act"} & acts) and not re.search(r"excise|ndps|prohibition", text[:400] if text else "", re.I)


def planned_updates(case: Case, p: ParsedFIR, text: str, ai: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Case column changes (column -> new value) supported by the FIR text."""
    ai = ai or {}
    up: Dict[str, Any] = {}
    flags = {f["check_code"] for f in check_case_against_text(case, [], text, None)}

    if p.offence_date and (not case.offence_date or case.offence_date.date() != p.offence_date.date()):
        when = p.offence_date
        if p.time_from:
            h, m = map(int, p.time_from.split(":"))
            when = when.replace(hour=h, minute=m)
        up["offence_date"] = when
    label = p.offence_label()
    if "OFFENCE_NOT_IN_TEXT" in flags or not case.offence_nature:
        if label:
            nature = label[0].upper() + label[1:]
            if p.particulars:
                nature += " - " + re.sub(r"^The above named person\s+", "", p.particulars).rstrip(".")
            up["offence_nature"] = nature[:1000]
        elif ai.get("offence_nature") and _in_text(ai["offence_nature"], text):
            up["offence_nature"] = ai["offence_nature"]
    if p.place and ({"PLACE_MISSING", "PLACE_MISMATCH"} & flags):
        place = p.place
        if p.address and p.address.lower() not in place.lower():
            place = f"{p.address}, {place}" if "near" not in place.lower() else f"{place} ({p.address})"
        up.update({"incident_place_raw": place, "location_description": place,
                   "incident_landmark": (p.address or p.place)[:255]})
        if p.town:
            up["incident_village"] = p.town
        if p.district:
            up["incident_district"] = p.district
        up["incident_location_evidence_passage"] = p.evidence.get("place")
        up["incident_location_verified"] = False
    # Contraband, quantity, vehicle
    if p.contraband_type:
        # Quantity and unit change only with the contraband type: a stored 4.5 Litres is not replaced by
        # the FIR's "25 Bottles (180ml each)" for the same seizure
        if canonical_contraband(case.contraband_type) != p.contraband_type:
            up["contraband_type"] = p.contraband_type
            if p.seized_quantity is not None and (case.seized_quantity or 0) != p.seized_quantity:
                up["seized_quantity"] = p.seized_quantity
            if p.seized_unit and case.seized_unit != p.seized_unit:
                up["seized_unit"] = p.seized_unit
    elif not (case.contraband_type or "").strip() or canonical_contraband(case.contraband_type) is None:
        if contraband_not_applicable(Case(offence_nature=up.get("offence_nature", case.offence_nature),
                                          offence_category=case.offence_category), text) or \
                (label and not _SEIZURE.search(label)):
            up.update({"contraband_type": CONTRABAND_NOT_APPLICABLE, "seized_quantity": None, "seized_unit": None})
    if p.vehicle_details and normalise_registration(case.vehicle_details) != p.vehicle_registration:
        up["vehicle_details"] = p.vehicle_details
    elif case.vehicle_details and not normalise_registration(case.vehicle_details) and not p.vehicle_registration \
            and not re.search(r"\b(auto|car|bike|lorry|truck|van|motor ?cycle|scooter|jeep|bolero|tractor)\b",
                              case.vehicle_details, re.I):
        up["vehicle_details"] = None   # e.g. "vehicle transporting contraband without valid transit permit"
    # Officer: only one named in the FIR; never an application user
    if case.seizing_officer_name and _APP_ROLE.search(case.seizing_officer_name):
        officer = p.officer or (ai.get("seizing_officer_name") if _in_text(ai.get("seizing_officer_name"), text) else None)
        up["seizing_officer_name"] = officer
        up["seizing_officer_rank"] = None if not officer else (ai.get("seizing_officer_rank") or case.seizing_officer_rank)
    # Narrative: FIR text without picture descriptions
    if case.narrative:
        cleaned = clean_extracted_text(case.narrative)
        if cleaned != case.narrative.strip():
            up["narrative"] = cleaned[:3000]
    return {k: v for k, v in up.items() if getattr(case, k, None) != v}


def planned_fields(case: Case, p: ParsedFIR) -> Dict[str, str]:
    """Case fields (field_name -> value) read from the FIR text."""
    out = {}
    if p.complainant:
        out["complainant"] = p.complainant
    if p.accused:
        out["accused"] = ", ".join(p.accused)
    if p.sections:
        out["law_sections"] = ", ".join(p.section_labels())
    if p.time_from:
        out["offence_time"] = f"{p.time_from} to {p.time_to}" if p.time_to else p.time_from
    if p.place:
        out["incident_place"] = p.place + (f" ({p.address})" if p.address else "")
    return out


async def _person(db: AsyncSession, name: str) -> Entity:
    ent = (await db.execute(select(Entity).where(Entity.entity_type == "PERSON", Entity.is_canonical == True,  # noqa: E712
                                                 func.lower(func.replace(Entity.canonical_name, " (Verified)", "")) == name.lower())
                            )).scalars().first()
    if not ent:
        ent = Entity(id=generate_uuid(), canonical_name=name[:150], entity_type="PERSON", risk_score=0.1)
        db.add(ent)
        await db.flush()
    return ent


async def relink_people(db: AsyncSession, case: Case, p: ParsedFIR, doc_id: Optional[str]) -> Dict[str, List[str]]:
    """Accused and complainant entity mentions for the case, as named in the FIR."""
    added = {"ACCUSED": [], "COMPLAINANT": []}
    for role, names in (("ACCUSED", p.accused), ("COMPLAINANT", [p.complainant] if p.complainant else [])):
        for name in names:
            ent = await _person(db, name)
            exists = (await db.execute(select(EntityMention).where(EntityMention.case_id == case.id,
                                                                   EntityMention.entity_id == ent.id))).scalars().first()
            if not exists:
                db.add(EntityMention(id=generate_uuid(), entity_id=ent.id, case_id=case.id, mention_text=name[:150],
                                     role_in_case=role, source_doc_id=doc_id, page_number=1))
                added[role].append(name)
    return added


async def drop_invalid_vehicle_links(db: AsyncSession, case: Case) -> List[str]:
    """Remove this case's links to vehicle entities that have no registration (e.g. 'None', a sentence)."""
    removed = []
    rows = (await db.execute(select(EntityMention, Entity).join(Entity, Entity.id == EntityMention.entity_id).where(
        EntityMention.case_id == case.id, Entity.entity_type == "VEHICLE"))).all()
    for mention, ent in rows:
        if normalise_registration(ent.canonical_name):
            continue
        for edge in (await db.execute(select(GraphEdge).where(GraphEdge.case_id == case.id, (
                (GraphEdge.source_entity_id == ent.id) | (GraphEdge.target_entity_id == ent.id))))).scalars().all():
            await db.delete(edge)
        await db.delete(mention)
        removed.append(ent.canonical_name)
        others = (await db.execute(select(func.count(EntityMention.id)).where(EntityMention.entity_id == ent.id,
                                                                             EntityMention.case_id != case.id))).scalar()
        if not others:
            ent.verification_status = "REJECTED"   # kept for the audit trail, out of the network
            ent.is_canonical = False
    return removed


async def reextract_case(db: AsyncSession, case: Case, actor_id: str, actor_username: str, *,
                         use_ai: bool = True, dry_run: bool = False, run_workflow: bool = True,
                         only: Optional[set] = None, source: Optional[tuple] = None) -> Dict[str, Any]:
    """
    Re-extract one case from its FIR text. Returns the before/after of every change. `only` limits
    the change to those case columns (no case fields, entities or workflow), e.g. a contraband fix.
    `source` = (document id, text) overrides the case's linked FIR text (used by dry runs).
    """
    doc_id, text = source if source else await fir_text_for_case(db, case)
    if source:
        text = clean_extracted_text(text)
    report: Dict[str, Any] = {"case_id": case.id, "fir_number": case.fir_number, "document_id": doc_id,
                              "changes": {}, "fields": {}, "people": {}, "vehicle_links_removed": []}
    master = await station_master_district(db, case.station)
    if master and (case.district or "").lower() != master.lower():
        report["changes"]["district"] = {"before": case.district, "after": master}
    if not text:
        report["note"] = "No readable FIR text is linked to this case; only the district rule and contraband were checked."
        if not (case.contraband_type or "").strip() and contraband_not_applicable(case):
            report["changes"]["contraband_type"] = {"before": case.contraband_type, "after": CONTRABAND_NOT_APPLICABLE}
        if not dry_run and report["changes"]:
            await _apply(db, case, report, actor_id, actor_username)
        return report

    p = parse_fir_text(text)
    ai: Dict[str, Any] = {}
    if use_ai and not dry_run and only is None:
        from .gemini import gemini_service
        ai = await asyncio.to_thread(gemini_service.extract_structured_case, text[:12000]) or {}
    for k, v in planned_updates(case, p, text, ai).items():
        if only is None or k in only:
            report["changes"][k] = {"before": getattr(case, k, None), "after": v}
    if only is not None:
        if not dry_run and report["changes"]:
            await _apply(db, case, report, actor_id, actor_username)
        return report
    existing = {f.field_name: f for f in (await db.execute(select(CaseField).where(CaseField.case_id == case.id))).scalars().all()}
    for name, value in planned_fields(case, p).items():
        old = existing.get(name)
        if not old or (old.human_override_value or old.normalized_value) != value:
            report["fields"][name] = {"before": (old.human_override_value or old.normalized_value) if old else None, "after": value}
    report["parsed"] = {"accused": p.accused, "complainant": p.complainant, "sections": p.section_labels()}
    if dry_run:
        return report

    for name, ch in report["fields"].items():
        row = existing.get(name)
        if row is None:
            db.add(CaseField(id=generate_uuid(), case_id=case.id, field_name=name, original_value=ch["after"],
                             normalized_value=ch["after"], source_doc_id=doc_id, page_number=1,
                             extraction_method="FIR_FORM_PARSER", confidence_score=0.95, verification_status="UNVERIFIED"))
        elif not row.human_override_value:   # an officer's override is never replaced
            row.original_value, row.normalized_value, row.extraction_method = ch["after"], ch["after"], "FIR_FORM_PARSER"
    report["people"] = await relink_people(db, case, p, doc_id)
    report["vehicle_links_removed"] = await drop_invalid_vehicle_links(db, case)
    await _apply(db, case, report, actor_id, actor_username, ai_used=bool(ai))
    if run_workflow:
        from .workflow import trigger_post_intake_workflow
        await trigger_post_intake_workflow(case.id, db)
    return report


async def _apply(db: AsyncSession, case: Case, report: Dict[str, Any], actor_id: str, actor_username: str,
                 ai_used: bool = False) -> None:
    from .audit import log_audit_event
    changes = report["changes"]
    for k, ch in changes.items():
        setattr(case, k, ch["after"])
    if {"incident_place_raw", "incident_village"} & set(changes):
        from .geocoder import geocoder_service
        try:
            geo = await geocoder_service.geocode_incident_location(
                raw_place=case.incident_place_raw, village=case.incident_village, mandal=case.incident_mandal,
                district=case.incident_district or case.district)
            case.incident_latitude, case.incident_longitude = geo.get("latitude"), geo.get("longitude")
            case.incident_location_geocoder_status = geo.get("status", "APPROXIMATE")
            case.incident_location_confidence = geo.get("confidence")
            case.incident_location_normalized = geo.get("display_name") or case.incident_place_raw
        except Exception as e:
            logger.warning(f"Geocoding {case.fir_number} failed: {e}")
    case.updated_at = datetime.utcnow()
    await db.commit()
    await log_audit_event(
        db=db, actor_id=actor_id, actor_username=actor_username,
        action_type="AI_CASE_REEXTRACTION" if ai_used else "CASE_DATA_CORRECTION", object_type="CASE", object_id=case.id,
        before_state={"fir_number": case.fir_number, **{k: _plain(v["before"]) for k, v in changes.items()},
                      **{f"field:{k}": v["before"] for k, v in report.get("fields", {}).items()}},
        after_state={"fir_number": case.fir_number, **{k: _plain(v["after"]) for k, v in changes.items()},
                     **{f"field:{k}": v["after"] for k, v in report.get("fields", {}).items()},
                     "people_linked": report.get("people"), "vehicle_links_removed": report.get("vehicle_links_removed"),
                     "source_document_id": report.get("document_id"),
                     "method": "FIR form parser" + (" + Gemini structured extraction" if ai_used else "")},
    )


def _plain(v):
    return v.isoformat() if isinstance(v, datetime) else v
