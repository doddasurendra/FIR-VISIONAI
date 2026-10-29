"""
Translations keep dates, numbers, names and section numbers exactly as the English summary (protected
tokens, checked after translation, retried once, then the English is shown); the case diary names the
case's investigating officer, never the viewer; the case page and Hotspots use one location rule; and
the chatbot's vehicle answer reads accused names from the case records.
"""
import asyncio
import sqlite3
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.config import settings
from app.database import SyncSessionLocal
from app.models.case import Case, CaseField
from app.models.generation import GeneratedDocument
from app.services import fir_summaries as fs
from app.services import rag_engine
from app.services.case_location import case_location
from app.services.fact_answers import _split_names
from app.services.gemini import gemini_service
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401

# ── Part 4: translations ─────────────────────────────────────────────────────

# The English and Telugu overviews stored for FIR-2024-KNL-0042 (the Telugu one added "20th August")
KNL_EN = ("This FIR record documents an alleged excise violation on 14th August 2024 at Kallur Toll Plaza, NH-44 "
          "Highway, where officers reportedly seized 45.0 Litres of illicit distilled arrack from two accused "
          "individuals. Complainant K. Venkateshwarlu registered the case under Section 34(a) of the Andhra Pradesh "
          "Excise Act, 1968, involving an auto rickshaw bearing number AP21TY4567.")
KNL_TE_BAD = ("ఈ ఎఫ్‌ఐఆర్ రికార్డు 20th ఆగస్టు 2024న లేదా 14th ఆగస్టు 2024న కర్నూలు జిల్లాలోని కల్లూరు టోల్ ప్లాజా వద్ద "
              "NH-44 పై జరిగిన ఒక ఆరోపించిన ఎక్సైజ్ ఉల్లంఘనను నమోదు చేస్తుంది, ఇక్కడ అధికారులు 45.0 లీటర్ల అక్రమ సారాను "
              "స్వాధీనం చేసుకున్నారు. ఫిర్యాదుదారు K. Venkateshwarlu ఆంధ్రప్రదేశ్ ఎక్సైజ్ చట్టం, 1968 యొక్క సెక్షన్ 34(a) "
              "కింద AP21TY4567 నంబర్ గల ఆటో రిక్షాతో ఈ కేసును నమోదు చేశారు.")
KNL_TE_GOOD = KNL_TE_BAD.replace("20th ఆగస్టు 2024న లేదా ", "")
KNL_SOURCES = [{"label": "FIR document 'FIR-2024-KNL-0042_Official.pdf'",
                "text": "Date of offence 14.08.2024 at 21:30 hrs near Kallur Toll Plaza, NH-44. 45.0 Litres. "
                        "Complainant K. Venkateshwarlu. Section 34(a) A.P. Excise Act, 1968. Auto AP21TY4567."}]


def _en_reference():
    en = {"overview": {"text": KNL_EN, "citations": [1]},
          "fields": {"incident_date": {"text": "14th August 2024 at 21:30 Hours", "citations": [1]},
                     "complainant": {"text": "K. Venkateshwarlu, Sub-Inspector of Prohibition & Excise", "citations": [1]},
                     "accused": {"text": "A-1: Ramu Naidu, Male; A-2: Someshwar Rao, Male", "citations": [1]}}}
    struct, _, _ = fs._normalise_language(en, 1, KNL_SOURCES, "en")
    return {"overview": struct["overview"], **struct["fields"]}


def test_dates_are_compared_by_value_in_any_script_and_format():
    assert fs.date_values("14th August 2024") == fs.date_values("ఆగస్టు 14, 2024") == fs.date_values("14.08.2024") \
        == fs.date_values("2024 ఆగస్టు 14న") == fs.date_values("2024-08-14") == fs.date_values("14 अगस्त 2024") == {(14, 8)}
    # An added alternative date is caught even when its day number occurs elsewhere (an age of 20)
    assert fs.date_values("Age 20. 20th August 2024 or 14th August 2024") == {(20, 8), (14, 8)}
    assert fs.date_values("Kumar 12 aged 45 years, he may go") == set()


def test_protected_tokens_are_identifiers_sections_vehicles_and_names():
    ref = _en_reference()
    names = fs.person_names(ref)
    assert "K. Venkateshwarlu" in names and "Ramu Naidu" in names and "Someshwar Rao" in names
    tokens = fs.protected_tokens(KNL_EN, names)
    assert {"AP21TY4567", "34(a)", "NH-44", "K. Venkateshwarlu"} <= set(tokens)
    assert fs.protected_tokens("Sections 66C and 66D of the IT Act; FIR-2024-KNL-0042") == ["FIR-2024-KNL-0042", "66C", "66D"]


def test_knl0042_telugu_summary_with_an_added_date_shows_the_english_text():
    ref = _en_reference()
    te = {"overview": {"text": KNL_TE_BAD, "citations": [1]}, "fields": {}}
    struct, _, warnings = fs._normalise_language(te, 1, KNL_SOURCES, "te", ref)
    assert struct["overview"]["text"] == KNL_EN and "20th" not in struct["overview"]["text"]
    assert struct["overview"]["translation_mismatch"] is True and "dates" in struct["overview"]["translation_problems"]
    assert any("changed a date or number" in w for w in warnings)
    # The faithful Telugu (only 14 August 2024) is kept
    good, _, _ = fs._normalise_language({"overview": {"text": KNL_TE_GOOD, "citations": [1]}, "fields": {}},
                                         1, KNL_SOURCES, "te", ref)
    assert good["overview"]["text"] == KNL_TE_GOOD and "translation_mismatch" not in good["overview"]


def test_a_transliterated_name_or_changed_section_is_not_accepted():
    ref = _en_reference()
    names = fs.person_names(ref)
    assert fs.translation_problems(KNL_TE_GOOD.replace("K. Venkateshwarlu", "కె. వెంకటేశ్వర్లు"), KNL_EN, names)
    assert fs.translation_problems(KNL_TE_GOOD.replace("34(a)", "34(b)"), KNL_EN, names)
    assert fs.translation_problems(KNL_TE_GOOD, KNL_EN, names) == []


def test_an_unfaithful_translation_is_retried_with_protected_tokens(monkeypatch):
    ref = _en_reference()
    sent = {}

    def retry(statements, language):
        sent.update(statements)
        return {"overview": KNL_TE_GOOD}
    monkeypatch.setattr(gemini_service, "translate_summary_statements", retry)
    te = {"overview": {"text": KNL_TE_BAD, "citations": [1]},
          "fields": {"incident_date": {"text": "14 ఆగస్టు 2024, 21:30 గంటలకు", "citations": [1]}}}
    repaired, retried = asyncio.run(fs._retry_unfaithful_translation(te, ref, "te"))
    assert retried == ["overview"] and "AP21TY4567" in sent["overview"]["protected"]
    struct, _, _ = fs._normalise_language(repaired, 1, KNL_SOURCES, "te", ref)
    assert struct["overview"]["text"] == KNL_TE_GOOD and "translation_mismatch" not in struct["overview"]
    assert struct["fields"]["incident_date"]["text"].startswith("14 ఆగస్టు")      # faithful, untouched


def test_a_retry_that_is_still_wrong_falls_back_to_english(monkeypatch):
    ref = _en_reference()
    monkeypatch.setattr(gemini_service, "translate_summary_statements", lambda s, l: {"overview": KNL_TE_BAD})
    repaired, _ = asyncio.run(fs._retry_unfaithful_translation(
        {"overview": {"text": KNL_TE_BAD, "citations": [1]}, "fields": {}}, ref, "te"))
    struct, _, _ = fs._normalise_language(repaired, 1, KNL_SOURCES, "te", ref)
    assert struct["overview"]["text"] == KNL_EN


# ── Part 5.1: investigating officer in the case diary ───────────────────────

def _draft(client, headers, case_id, lang="en"):
    res = client.post("/api/v1/generation/draft", headers=headers,
                      json={"case_id": case_id, "doc_type": "CASE_DIARY", "language": lang})
    assert res.status_code == 200, res.text
    return res.json()["content"]


def _io_line(content):
    return next(l for l in content.splitlines() if l.startswith(("Investigating Officer:", "దర్యాప్తు అధికారి:", "अन्वेषण अधिकारी:")))


def test_diary_names_the_firs_officer_not_the_viewer(client, state_headers):
    me = client.get("/api/v1/auth/me", headers=state_headers).json()
    cases = client.get("/api/v1/cases/", headers=state_headers).json()
    knl = next(c for c in cases if c["fir_number"] == "FIR-2024-KNL-0042")
    for lang in ("en", "te", "hi"):
        line = _io_line(_draft(client, state_headers, knl["id"], lang))
        assert "K. Venkateshwarlu" in line and me["full_name"] not in line


@pytest.fixture
def case_without_officer():
    """A Kurnool Town case whose only 'officer' is its creator's account name (older intake did this)."""
    con = sqlite3.connect(settings.DATABASE_URL.split("///", 1)[1])
    creator_id, creator_name = con.execute("SELECT id, full_name FROM users WHERE upper(role)='STATE' LIMIT 1").fetchone()
    con.close()
    db = SyncSessionLocal()
    case = Case(fir_number=f"IO-TEST-{uuid.uuid4().hex[:6]}", year=2024, district="Kurnool", station="Kurnool Town Station",
                offence_nature="Illicit distillation", narrative="FIR text without any officer named.",
                seizing_officer_name=creator_name, status="DRAFT", created_by=creator_id, registration_date=datetime(2024, 9, 1))
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()
    yield case_id, creator_name
    db = SyncSessionLocal()
    for d in db.query(GeneratedDocument).filter(GeneratedDocument.case_id == case_id).all():
        db.delete(d)
    db.delete(db.get(Case, case_id))
    db.commit()
    db.close()


def test_diary_falls_back_to_the_station_sho(client, state_headers, case_without_officer):
    case_id, creator_name = case_without_officer
    line = _io_line(_draft(client, state_headers, case_id))
    con = sqlite3.connect(settings.DATABASE_URL.split("///", 1)[1])
    station_users = {r[0] for r in con.execute(
        "SELECT full_name FROM users WHERE upper(role)='STATION' AND station='Kurnool Town Station' AND is_active=1")}
    con.close()
    assert creator_name not in line
    assert "SHO" in line or "Station House Officer" in line
    assert any(n in line for n in station_users) or "Station House Officer, Kurnool Town Station" in line


# ── Part 5.2: one location rule ──────────────────────────────────────────────

def _case(**kw):
    base = dict(incident_location_geocoder_status=None, incident_latitude=None, incident_longitude=None,
                incident_location_verified=False, incident_mandal=None, mandal=None, incident_district=None,
                district="Guntur")
    return SimpleNamespace(**{**base, **kw})


def test_location_rule():
    assert case_location(_case(incident_latitude=16.29, incident_longitude=80.45,
                               incident_location_geocoder_status="APPROXIMATE"))["precision"] == "APPROXIMATE"
    assert case_location(_case(incident_latitude=16.29, incident_longitude=80.45,
                               incident_location_geocoder_status="EXACT"))["is_approximate"] is False
    assert case_location(_case(incident_latitude=1, incident_longitude=2, incident_location_verified=True))["precision"] == "VERIFIED"
    # Placeholder coordinates from a failed geocode are not used; the mandal centroid is, marked approximate
    loc = case_location(_case(incident_latitude=16.3067, incident_longitude=80.4365,
                              incident_location_geocoder_status="UNRESOLVED", mandal="Tenali"))
    assert loc["source"] == "centroid" and loc["is_approximate"] and (loc["latitude"], loc["longitude"]) == (16.2435, 80.64)
    assert case_location(_case(district="Somewhere Else"))["precision"] == "NONE"


def test_case_page_and_hotspots_agree(client, state_headers, monkeypatch):
    """A case without stored coordinates (geocoding unavailable) is on the map in Hotspots exactly where its case page puts it."""
    from app.services.geocoder import geocoder_service

    async def unresolved(**kw):
        return {"latitude": 16.3067, "longitude": 80.4365, "status": "UNRESOLVED", "display_name": "x"}
    monkeypatch.setattr(geocoder_service, "geocode_incident_location", unresolved)
    db = SyncSessionLocal()
    case = Case(fir_number=f"LOC-TEST-{uuid.uuid4().hex[:6]}", year=2024, district="Guntur", station="Tenali PS",
                mandal="Tenali", offence_nature="Cheating", status="DRAFT", created_by="test",
                registration_date=datetime(2024, 9, 20))
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()
    try:
        page = client.get(f"/api/v1/cases/{case_id}/location", headers=state_headers).json()
        assert page["is_approximate"] is True and page["location_precision"] == "APPROXIMATE"
        body = client.get("/api/v1/analytics/hotspots", headers=state_headers).json()
        assert case_id not in {c["case_id"] for c in body["unlocated_cases"]}
        inc = next(i for i in body["incidents"] if i["case_id"] == case_id)
        assert (inc["latitude"], inc["longitude"]) == (page["incident_latitude"], page["incident_longitude"])
        assert inc["is_approximate"] is True
        # The failed geocode's placeholder point was not stored
        db = SyncSessionLocal()
        assert db.get(Case, case_id).incident_latitude is None
        db.close()
    finally:
        db = SyncSessionLocal()
        db.delete(db.get(Case, case_id))
        db.commit()
        db.close()


# ── Part 5.3: accused names in the vehicle answer ───────────────────────────

def test_accused_names_are_split_from_extracted_fields():
    assert _split_names("Ramu Naidu (A-1), Someshwar Rao (A-2)") == ["Ramu Naidu", "Someshwar Rao"]
    assert _split_names('["A-1: Ramu Naidu"]') == ["Ramu Naidu"]
    assert _split_names("Unknown") == [] and _split_names("40.0") == []


@pytest.fixture
def case_with_accused_field():
    """Like FIR-2024-EXC-IMAGE-01: the accused only in the extracted fields and FIR text, no entity yet."""
    db = SyncSessionLocal()
    reg = f"AP77ZZ{uuid.uuid4().int % 9000 + 1000}"
    case = Case(fir_number=f"EXC-TEST-{uuid.uuid4().hex[:6]}", year=2024, district="Kurnool", station="Kurnool Town Station",
                offence_nature="Transport of ID Arrack", vehicle_details=f"Auto Rickshaw {reg}", contraband_type="ID Arrack",
                seized_quantity=40, seized_unit="Litres", status="DRAFT", created_by="test", registration_date=datetime(2024, 9, 1),
                narrative=f"Contraband Seized: 40 Litres ID Arrack. Vehicle: Auto Rickshaw {reg} | Accused: Ramu Naidu (A-1)")
    db.add(case)
    db.commit()
    db.add(CaseField(case_id=case.id, field_name="accused_names", original_value="Ramu Naidu (A-1)",
                     normalized_value="Ramu Naidu (A-1)"))
    db.commit()
    case_id = case.id
    db.close()
    yield reg
    db = SyncSessionLocal()
    for f in db.query(CaseField).filter(CaseField.case_id == case_id).all():
        db.delete(f)
    db.delete(db.get(Case, case_id))
    db.commit()
    db.close()


def test_vehicle_answer_reads_accused_from_the_case_records(client, station_headers, case_with_accused_field):
    rag_engine.invalidate_cache()
    body = client.post("/api/v1/rag/query", headers=station_headers,
                       json={"query": f"Which cases involve vehicle {case_with_accused_field}?", "scope": "ALL_AUTHORIZED"}).json()
    (match,) = [c for c in body["matched_cases"] if c["fir_number"].startswith("EXC-TEST-")]
    assert match["accused"] == ["Ramu Naidu"]
    assert "accused: Ramu Naidu" in body["answer"]
    rag_engine.invalidate_cache()
