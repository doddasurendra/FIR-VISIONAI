"""
Legal section suggestions: recorded vs suggested provisions, the BNS/IPC date rule with the incident
date taken from the FIR text when the case has none, ingredient evaluation, verified vs unverified
text, jurisdiction, and the accept/reject flow with audit entries.
"""
import uuid
from datetime import date, datetime

import pytest

from app.database import SyncSessionLocal
from app.models.case import Case
from app.services import legal_rules as rules
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401

THEFT_NARRATIVE = (
    "FIRST INFORMATION REPORT. District: Prakasam. Police Station: Ongole PS. FIR No: {fir}. "
    "3. (a) Occurrence of Offence: Day : 14.08.2024 (Wednesday) Time: 21.00 hrs. "
    "An unknown person stole the complainant's two wheeler (Honda Activa, AP 39 AB 5678) which was parked "
    "in front of Sri Sai Bike Service Centre, Ongole, and fled from the place.")


# ── Rules ────────────────────────────────────────────────────────────────────

def test_recorded_sections_are_read_from_fir_wording():
    assert rules.recorded_sections(["Sections 379, 411 IPC."]) == [(rules.IPC, "Section 379"), (rules.IPC, "Section 411")]
    assert (rules.EXCISE, "Section 34(a)") in rules.recorded_sections(
        ["Recorded Statutory Provision: Andhra Pradesh Excise Act, 1968 - Section 34(a)."])
    assert rules.recorded_sections(["Section 20(b)(ii)(B) of the NDPS Act"]) == [(rules.NDPS, "Section 20(b)(ii)(B)")]


def test_incident_date_is_read_from_fir_text():
    assert rules.incident_date_from_text("3. (a) Occurrence of Offence: Day : 14.08.2024 (Wednesday)") == date(2024, 8, 14)
    assert rules.incident_date_from_text("Date of Offence: 14th August 2024 at 21:30 Hours") == date(2024, 8, 14)
    assert rules.regime_for(date(2024, 7, 1)) == "BNS" and rules.regime_for(date(2024, 6, 30)) == "IPC"
    assert rules.regime_for(None) == "UNKNOWN"


def test_ingredients_are_split_into_established_and_missing():
    rule = next(r for r in rules.RULES if r["key"] == "stolen_property")
    matched, missing = rules.evaluate_ingredients(rule, THEFT_NARRATIVE.lower())
    assert "The property is stolen property" in matched
    assert "The accused received or retained it" in missing


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture
def theft_case_8924():
    """A case like 89/2024: IPC sections recorded, no offence_date, incident on 14.08.2024 in the FIR text."""
    db = SyncSessionLocal()
    fir = f"89/2024-T{uuid.uuid4().hex[:5]}"
    case = Case(fir_number=fir, year=2024, district="Prakasam", station="Ongole PS",
                offence_nature="Sections 379, 411 IPC.", narrative=THEFT_NARRATIVE.format(fir=fir),
                status="DRAFT", created_by="test", registration_date=datetime(2024, 8, 16))
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()
    yield case_id
    db = SyncSessionLocal()
    db.delete(db.get(Case, case_id))
    db.commit()
    db.close()


def test_8924_gets_recorded_and_suggested_sections_with_the_bns_rule(client, state_headers, theft_case_8924):
    res = client.get(f"/api/v1/legal/recommend/{theft_case_8924}", headers=state_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["regime"] == "BNS" and body["offence_date"] == "2024-08-14"
    assert body["offence_date_source"] == "FIR text"
    by_section = {(c["act_name"], c["section_number"]): c for c in body["candidates"]}

    ipc379 = by_section[(rules.IPC, "Section 379")]
    assert ipc379["label"] == "Recorded in FIR" and ipc379["regime_applies"] is False
    assert any("Section 303(2)" in w for w in ipc379["warnings"])

    bns_theft = by_section[(rules.BNS, "Section 303(2)")]
    assert bns_theft["label"] == "Suggested – not in FIR" and bns_theft["regime_applies"] is True
    assert "Taken without that person's consent" in bns_theft["matched_ingredients"]

    bns_317 = by_section[(rules.BNS, "Section 317(2)")]           # counterpart of IPC 411
    assert bns_317["label"] == "Suggested – not in FIR"
    assert "The accused received or retained it" in bns_317["missing_ingredients"]
    # Not in the test corpus: listed, but cannot be accepted until its text is imported
    assert by_section[(rules.IPC, "Section 411")]["text_status"] == "NOT_IN_CORPUS"
    assert by_section[(rules.IPC, "Section 411")]["can_accept"] is False


def test_statutory_text_is_verified_only_for_official_sources(client, state_headers, theft_case_8924):
    body = client.get(f"/api/v1/legal/recommend/{theft_case_8924}", headers=state_headers).json()
    for c in body["candidates"]:
        assert c["text_status"] in ("VERIFIED_STATUTORY_TEXT", "UNVERIFIED_SUMMARY", "NOT_IN_CORPUS")
        assert (c["verified_text"] is not None) == (c["text_status"] == "VERIFIED_STATUTORY_TEXT")


def test_other_jurisdictions_case_is_refused(client, station_headers, theft_case_8924):
    assert client.get(f"/api/v1/legal/recommend/{theft_case_8924}", headers=station_headers).status_code == 403
    assert client.get(f"/api/v1/legal/case/{theft_case_8924}/sections", headers=station_headers).status_code == 403


def test_every_case_in_the_dropdown_loads(client, state_headers):
    cases = client.get("/api/v1/cases/", headers=state_headers).json()
    assert cases
    for c in cases:
        res = client.get(f"/api/v1/legal/recommend/{c['id']}", headers=state_headers)
        assert res.status_code == 200, (c["fir_number"], res.status_code, res.text[:200])


def test_accepting_and_rejecting_is_recorded_and_audited(client, state_headers, theft_case_8924):
    body = client.get(f"/api/v1/legal/recommend/{theft_case_8924}", headers=state_headers).json()
    cand = next(c for c in body["candidates"] if c["section_number"] == "Section 303(2)")
    ok = client.post("/api/v1/legal/decision", headers=state_headers, json={
        "case_id": theft_case_8924, "legal_corpus_id": cand["legal_corpus_id"], "decision": "ACCEPTED",
        "reason": "Theft of the two wheeler is recorded"})
    assert ok.status_code == 200, ok.text
    again = client.get(f"/api/v1/legal/recommend/{theft_case_8924}", headers=state_headers).json()
    assert next(c for c in again["candidates"] if c["section_number"] == "Section 303(2)")["officer_decision"] == "ACCEPTED"
    audit = client.get("/api/v1/audit/", headers=state_headers, params={"action_type": "LEGAL_SECTION_ACCEPTED"}).json()
    assert audit and theft_case_8924 in audit[0]["after_state_json"]
    bad = client.post("/api/v1/legal/decision", headers=state_headers, json={
        "case_id": theft_case_8924, "legal_corpus_id": cand["legal_corpus_id"], "decision": "MAYBE", "reason": "x"})
    assert bad.status_code == 400
