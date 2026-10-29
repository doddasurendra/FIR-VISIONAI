"""
Case diary and chargesheet: charges framed from accepted sections (or the suggested ones as pending
officer acceptance with a link to Legal Section Assistance), date / time / place from the case, the
extracted fields or the FIR text, accused names in the chargesheet header, correct section numbers
(172 CrPC / 192 BNSS for the diary, 173 CrPC / 193 BNSS for the chargesheet) in EN, TE and HI,
jurisdiction, kept versions, and translations that never change a date or number.
"""
import uuid
from datetime import datetime

import pytest

from app.database import SyncSessionLocal
from app.models.case import Case
from app.models.generation import GeneratedDocument
from app.services.fir_summaries import _normalise_language, number_values
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401

FIR_TEXT = (
    "--- Page 1 ---\nFIRST INFORMATION REPORT\n1. District : Prakasam\nFIR No : {fir}\n"
    "2. (ii) Act, Indian Penal Code : Sections 379, 411 IPC.\n"
    "3. (a) Occurrence of Offence: Day : 14.08.2024 (Wednesday)\n"
    "Time Period : Between 21.00 hrs and 22.00 hrs\n"
    "(b) Information received at the Police Station : Date : 16.08.2024 Time : 09.30 hours\n"
    "5. Place of occurrence : Near Kandukur Road, Ongole Town, Prakasam District.\n"
    "6. Complainant / Informant : (a) Name : Bandi Ramesh\n"
    "7. Accused: Kalla Suresh\n"
    "Witness 1: P. Ravi Teja, Son of Narayana\n"
    "An unknown person stole the complainant's two wheeler (Honda Activa, AP 39 AB 5678) which was parked "
    "in front of Sri Sai Bike Service Centre, Ongole, and fled from the place.")
DIARY_HEADERS = {"en": "SECTION 172 CrPC / SECTION 192 BNSS", "te": "సెక్షన్ 172 Cr.P.C. / సెక్షన్ 192 BNSS",
                 "hi": "धारा 172 Cr.P.C. / धारा 192 BNSS"}
CHARGESHEET_HEADERS = {"en": "SECTION 173 CrPC / SECTION 193 BNSS", "te": "సెక్షన్ 173 CrPC / సెక్షన్ 193 BNSS",
                       "hi": "धारा 173 CrPC / धारा 193 BNSS"}


@pytest.fixture
def case_8924():
    """Like 89/2024: no offence_date or extracted date; date, time, place and people only in the FIR text."""
    db = SyncSessionLocal()
    fir = f"89/2024-D{uuid.uuid4().hex[:5]}"
    case = Case(fir_number=fir, year=2024, district="Prakasam", station="Ongole PS",
                offence_nature="Sections 379, 411 IPC.", narrative=FIR_TEXT.format(fir=fir),
                incident_location_normalized="Prakasam District, Andhra Pradesh, India",
                status="DRAFT", created_by="test", registration_date=datetime(2024, 8, 16))
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()
    yield case_id
    db = SyncSessionLocal()
    for d in db.query(GeneratedDocument).filter(GeneratedDocument.case_id == case_id).all():
        db.delete(d)
    db.delete(db.get(Case, case_id))
    db.commit()
    db.close()


def _draft(client, headers, case_id, doc_type, lang):
    res = client.post("/api/v1/generation/draft", headers=headers,
                      json={"case_id": case_id, "doc_type": doc_type, "language": lang})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.parametrize("lang", ["en", "te", "hi"])
def test_case_diary_has_facts_from_the_fir_and_section_192_bnss(client, state_headers, case_8924, lang):
    content = _draft(client, state_headers, case_8924, "CASE_DIARY", lang)["content"]
    assert DIARY_HEADERS[lang] in content and "193 BNSS" not in content
    assert "14-08-2024, Between 21.00 hrs and 22.00 hrs" in content          # not the 09.30 hrs information time
    assert "Near Kandukur Road, Ongole Town, Prakasam District" in content    # FIR place over the vague geocode
    assert "Sri Sai Bike Service Centre" in content                          # FIR text, not "under investigation"
    assert "--- Page 1 ---" not in content
    assert "Under investigation" not in content and "Kalla Suresh" in content and "Bandi Ramesh" in content


@pytest.mark.parametrize("lang", ["en", "te", "hi"])
def test_chargesheet_lists_suggested_sections_as_pending_when_none_accepted(client, state_headers, case_8924, lang):
    content = _draft(client, state_headers, case_8924, "CHARGESHEET", lang)["content"]
    assert CHARGESHEET_HEADERS[lang] in content and "192 BNSS" not in content
    assert "Charges Framed Under Laws" in content
    assert "Section 303(2) Bharatiya Nyaya Sanhita" in content or "Section 303(2) BNS" in content
    assert "Pending officer acceptance" in content and f"/legal?caseId={case_8924}" in content
    assert "Section 379 Indian Penal Code" not in content and "Section 379 IPC" not in content  # ruled out by the date
    assert "A-1 Kalla Suresh" in content                                      # accused in the header
    assert "DRAFT CANNOT BE COMPLETED" not in content
    assert ": 2024\n" in content                                              # the FIR's year, not today's
    assert "L.W. 1: Bandi Ramesh" in content and "P. Ravi Teja" in content    # complainant and FIR witnesses
    assert "\n   \n" not in content and "]\n\n   * " not in content          # no blank lines left by template tags


def test_accepted_sections_flow_into_the_chargesheet(client, state_headers, case_8924):
    body = client.get(f"/api/v1/legal/recommend/{case_8924}", headers=state_headers).json()
    cand = next(c for c in body["candidates"] if c["section_number"] == "Section 303(2)")
    assert cand["legal_corpus_id"], "the test corpus must hold BNS 303(2)"
    ok = client.post("/api/v1/legal/decision", headers=state_headers, json={
        "case_id": case_8924, "legal_corpus_id": cand["legal_corpus_id"], "decision": "ACCEPTED",
        "reason": "Theft of the two wheeler is recorded"})
    assert ok.status_code == 200, ok.text
    content = _draft(client, state_headers, case_8924, "CHARGESHEET", "en")["content"]
    charges = content.split("2. Charges Framed Under Laws:")[1].split("3. Prosecution Facts")[0]
    assert "303(2)" in charges and "Accepted by officer" in charges
    assert "Pending officer acceptance" not in charges and "/legal?caseId=" not in charges


def test_kn0042_documents_have_no_blank_sections(client, state_headers):
    cases = client.get("/api/v1/cases/", headers=state_headers).json()
    knl = next(c for c in cases if c["fir_number"] == "FIR-2024-KNL-0042")
    for lang in ("en", "te", "hi"):
        diary = _draft(client, state_headers, knl["id"], "CASE_DIARY", lang)["content"]
        sheet = _draft(client, state_headers, knl["id"], "CHARGESHEET", lang)["content"]
        assert DIARY_HEADERS[lang] in diary and CHARGESHEET_HEADERS[lang] in sheet
        assert "14-08-2024, 21:30 hrs" in diary and "14-08-2024, 21:30 hrs" in sheet
        assert "A-1 Ramu Naidu" in sheet and "(Verified)" not in sheet.split("1. ")[0]
        assert "No section is recorded or suggested yet" not in sheet


def test_unknown_accused_are_described_as_the_fir_records_them(client, state_headers):
    db = SyncSessionLocal()
    text = FIR_TEXT.format(fir="x").replace(
        "7. Accused: Kalla Suresh\n",
        "7. Details of known / suspected / unknown accused with full particulars:\n(a) Name : : Unknown person(s)\n"
        "(b) Father's Name : Not known\n(c) Age : : About 25 to 30 years\n")
    case = Case(fir_number=f"90/2024-D{uuid.uuid4().hex[:5]}", year=2024, district="Prakasam", station="Ongole PS",
                offence_nature="Sections 379, 411 IPC.", narrative=text, status="DRAFT", created_by="test")
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()
    try:
        sheet = _draft(client, state_headers, case_id, "CHARGESHEET", "en")["content"]
        assert "Accused Persons: Unknown person(s), age About 25 to 30 years (as recorded in the FIR) — identification pending" in sheet
    finally:
        db = SyncSessionLocal()
        for d in db.query(GeneratedDocument).filter(GeneratedDocument.case_id == case_id).all():
            db.delete(d)
        db.delete(db.get(Case, case_id))
        db.commit()
        db.close()


def test_regenerating_keeps_earlier_versions(client, state_headers, case_8924):
    first = _draft(client, state_headers, case_8924, "CASE_DIARY", "en")
    second = _draft(client, state_headers, case_8924, "CASE_DIARY", "en")
    assert second["version"] == first["version"] + 1 and second["id"] != first["id"]
    docs = client.get(f"/api/v1/generation/case/{case_8924}/documents", headers=state_headers).json()
    assert {first["id"], second["id"]} <= {d["id"] for d in docs}
    assert docs[0]["id"] == second["id"] and docs[0]["is_outdated"] is False


def test_drafts_from_the_old_template_are_marked_outdated(client, state_headers, case_8924):
    db = SyncSessionLocal()
    db.add(GeneratedDocument(case_id=case_8924, doc_type="CASE_DIARY", language="en", title="old", version=1,
                             status="DRAFT", created_by="test", content="CASE DIARY (SECTION 172 CrPC / 193 BNSS)"))
    db.commit()
    db.close()
    docs = client.get(f"/api/v1/generation/case/{case_8924}/documents", headers=state_headers).json()
    assert next(d for d in docs if d["title"] == "old")["is_outdated"] is True


def test_documents_of_other_jurisdictions_are_refused(client, station_headers, state_headers, case_8924):
    res = client.post("/api/v1/generation/draft", headers=station_headers,
                      json={"case_id": case_8924, "doc_type": "CASE_DIARY", "language": "en"})
    assert res.status_code == 403
    assert client.get(f"/api/v1/generation/case/{case_8924}/documents", headers=station_headers).status_code == 403
    doc = _draft(client, state_headers, case_8924, "CASE_DIARY", "en")
    assert client.put(f"/api/v1/generation/{doc['id']}", headers=station_headers,
                      params={"content": "x"}).status_code == 403
    assert client.post(f"/api/v1/generation/{doc['id']}/approve", headers=station_headers,
                       json={"action": "APPROVED", "comments": "x"}).status_code == 403


def test_a_database_timeout_is_reported_as_unavailable_not_as_a_bug():
    from sqlalchemy.engine import base
    from app.services.audit import is_connection_error

    code = compile("raise TimeoutError()", base.__file__, "exec")  # raised from a SQLAlchemy frame
    try:
        exec(code)
    except TimeoutError as e:
        assert is_connection_error(e)
    try:
        raise TimeoutError()
    except TimeoutError as e:
        assert not is_connection_error(e)                                    # other timeouts stay real errors


# ── Translations keep dates and numbers ──────────────────────────────────────

def test_number_values_ignore_script_and_date_format():
    assert number_values("14th August 2024") == number_values("ఆగస్టు 14, 2024") == number_values("14.08.2024") == {14, 8, 2024}
    assert number_values("14 अगस्त 2024") == {14, 8, 2024}
    assert number_values("20th August 2024 or 14th August 2024") != number_values("14th August 2024")
    assert number_values("he may go") == set()


def test_a_translation_that_changes_a_date_shows_the_english_text():
    sources = [{"label": "FIR", "text": "Date of offence 14.08.2024. Seized 45 litres."}]
    en = {"overview": {"text": "Offence on 14th August 2024; 45 litres seized.", "citations": [1]},
          "fields": {"incident_date": {"text": "14th August 2024", "citations": [1]}}}
    en_struct, _, _ = _normalise_language(en, 1, sources, "en")
    reference = {"overview": en_struct["overview"], **en_struct["fields"]}
    te = {"overview": {"text": "2024 ఆగస్టు 14న నేరం; 45 లీటర్లు స్వాధీనం.", "citations": [1]},
          "fields": {"incident_date": {"text": "20 ఆగస్టు 2024 లేదా 14 ఆగస్టు 2024", "citations": [1]}}}
    te_struct, text, warnings = _normalise_language(te, 1, sources, "te", reference)
    assert te_struct["overview"]["text"].startswith("2024 ఆగస్టు 14")             # faithful translation kept
    assert te_struct["fields"]["incident_date"]["text"] == "14th August 2024"     # wrong date replaced
    assert te_struct["fields"]["incident_date"]["translation_mismatch"] is True
    assert any("changed a date or number" in w for w in warnings)
