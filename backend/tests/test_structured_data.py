"""
Turning records into structured data: field format/consistency validation, blocked overrides,
short crime categories, entity extraction from FIR text, bulk import of scanned FIRs (files or
ZIP) with per-file progress and duplicate detection, and the 'unknown contraband' case filter.
"""
import io
import time
import uuid
import zipfile
from types import SimpleNamespace

import pytest

from app.database import SyncSessionLocal
from app.models.case import Case, CaseField
from app.services.bulk_scans import expand_uploads
from app.services.field_validation import canonical_contraband, validate_field
from app.services.fir_text_facts import crime_category, find_people_and_identifiers
from tests.test_knowledge_base_rag import auth, make_pdf, station_headers, state_headers  # noqa: F401

FIR19_TEXT = (
    "ANDHRA PRADESH POLICE FIRST INFORMATION REPORT 1. District : Guntur Police Station : Tenali PS FIR No : 178/2024 "
    "(ii) Act, Indian Penal Code : Sections 420, 468, 471 IPC. 6. Complainant / Informant : (a) Name : K. Lakshmi Prasad "
    "(b) Father's / Husband's Name : K. Venkata Rao 7. Details of known / suspected / unknown accused with full "
    "particulars: (a) Name : Ramesh Kumar (b) Father's Name : Suresh. Witness 1: P. Anil Kumar, Clerk. "
    "Vehicle AP 07 CD 1234. Phone +91 98480 12345.")


# ── Validation rules ─────────────────────────────────────────────────────────

def test_field_formats():
    case = SimpleNamespace(fir_number="FIR-2024-KNL-0042", contraband_type="ID Liquor", seized_quantity=45.0,
                           district="Kurnool", station="Kurnool Town Station")
    assert validate_field("fir_number", "FIR-2024-KNL-0042", case) == []
    codes = {i["code"] for i in validate_field("fir_number", "Cr. No. 999/2026", case)}
    assert codes == {"MISMATCH_WITH_CASE"}  # a valid pattern, but not this case's number
    assert validate_field("fir_number", "hello world")[0]["code"] == "FORMAT"
    block = validate_field("contraband_type", "Verified 50.0 Litres", case)
    assert block[0]["level"] == "BLOCK" and block[0]["code"] == "QUANTITY_IN_TYPE_FIELD"
    assert canonical_contraband("arrack") == "ID Liquor (Arrack)" and canonical_contraband("stolen phone") is None
    assert validate_field("seized_quantity", "45.0 Litres", case) == []
    assert validate_field("seized_quantity", "about half", case)[0]["level"] == "BLOCK"
    assert validate_field("offence_nature", "14th August 2024 at 21:30 Hours")[0]["code"] == "DATE_IN_TEXT_FIELD"


@pytest.fixture
def knl_fields():
    """Bad values like those found on FIR-2024-KNL-0042 (test database only); removed afterwards."""
    db = SyncSessionLocal()
    case = db.query(Case).filter(Case.fir_number == "FIR-2024-KNL-0042").one()
    rows = [CaseField(case_id=case.id, field_name="fir_number", original_value="Cr. No. 999/2026",
                      normalized_value="Cr. No. 999/2026", confidence_score=0.9, verification_status="VERIFIED"),
            CaseField(case_id=case.id, field_name="contraband_type", original_value="ID Liquor",
                      normalized_value="ID Liquor", confidence_score=0.9, verification_status="VERIFIED")]
    db.add_all(rows)
    db.commit()
    ids = {r.field_name: r.id for r in rows}
    yield case.id, ids
    for fid in ids.values():
        db.delete(db.get(CaseField, fid))
    db.commit()
    db.close()


def test_quantity_cannot_be_put_into_the_contraband_type_field(client, station_headers, knl_fields):
    case_id, ids = knl_fields
    res = client.post(f"/api/v1/cases/{case_id}/fields/{ids['contraband_type']}/override", headers=station_headers,
                      json={"human_override_value": "Verified 50.0 Litres", "verification_status": "OVERRIDDEN"})
    assert res.status_code == 422 and "quantity" in res.json()["detail"]
    ok = client.post(f"/api/v1/cases/{case_id}/fields/{ids['contraband_type']}/override", headers=station_headers,
                     json={"human_override_value": "arrack", "verification_status": "OVERRIDDEN"})
    assert ok.status_code == 200 and ok.json()["human_override_value"] == "ID Liquor (Arrack)"


def test_field_checks_flag_values_that_disagree_with_the_case(client, station_headers, knl_fields):
    case_id, ids = knl_fields
    body = client.get(f"/api/v1/cases/{case_id}/field-checks", headers=station_headers).json()
    fir = next(f for f in body["fields"] if f["field_id"] == ids["fir_number"])
    assert fir["needs_review"] and fir["issues"][0]["code"] == "MISMATCH_WITH_CASE"
    assert body["fields_needing_review"] >= 1


def test_other_jurisdiction_cannot_override_or_read_checks(client, knl_fields):
    case_id, ids = knl_fields
    other = SyncSessionLocal()
    from app.models.user import User
    from app.services.auth import hash_password
    uname = f"guntur_{uuid.uuid4().hex[:6]}"
    other.add(User(username=uname, email=f"{uname}@test.local", full_name="Guntur officer", role="STATION",
                   district="Guntur", station="Tenali Station", password_hash=hash_password("Guntur@2024x"),
                   approval_status="APPROVED", is_active=True))
    other.commit()
    other.close()
    h = auth(client, uname, "Guntur@2024x")
    assert client.get(f"/api/v1/cases/{case_id}/field-checks", headers=h).status_code == 403
    assert client.post(f"/api/v1/cases/{case_id}/fields/{ids['fir_number']}/override", headers=h,
                       json={"human_override_value": "x", "verification_status": "OVERRIDDEN"}).status_code == 403


# ── Crime category and entities ──────────────────────────────────────────────

def test_crime_type_is_a_short_category():
    assert crime_category("cheated the complainant by using forged documents and obtained a personal loan") == "Cheating / Forgery"
    assert crime_category("An unknown person stole the complainant's two wheeler") == "Theft"
    assert crime_category("Transport of 45 litres of ID arrack") == "Illicit liquor (Excise)"


def test_people_and_identifiers_are_read_from_fir_text():
    found = find_people_and_identifiers(FIR19_TEXT)
    assert found["complainant"] == ["K. Lakshmi Prasad"] and found["accused"] == ["Ramesh Kumar"]
    assert found["witnesses"] == ["P. Anil Kumar"]
    assert found["vehicles"] and found["phones"]
    assert find_people_and_identifiers("Accused: Unknown person(s). Complainant: Not known")["accused"] == []


def _upload_and_wait(client, headers, content, name):
    up = client.post("/api/v1/documents/upload", headers=headers, files={"file": (name, content, "application/pdf")})
    assert up.status_code == 200, up.text
    deadline = time.time() + 60
    while time.time() < deadline:
        job = client.get(f"/api/v1/documents/jobs/{up.json()['job_id']}/status", headers=headers).json()
        if job.get("stage") in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.3)
    return client.get(f"/api/v1/documents/{up.json()['document_id']}/intake-status", headers=headers).json()


def test_extraction_always_finds_accused_and_complainant(client, station_headers):
    token = uuid.uuid4().hex[:6]
    pdf = make_pdf([[f"SYNTHETIC TEST FIR {token}. District : Kurnool Police Station : Kurnool Town Station.",
                     "6. Complainant / Informant : (a) Name : K. Lakshmi Prasad (b) Occupation : Clerk.",
                     "7. Details of known / suspected / unknown accused: (a) Name : Ramesh Kumar (b) Age : 40.",
                     "The accused cheated the complainant by using forged documents and obtained a personal loan of "
                     "Rs. 2,50,000 from the bank in her name without her knowledge."]])
    st = _upload_and_wait(client, station_headers, pdf, f"fir19_like_{token}.pdf")
    ents = {(e["type"], e["name"]) for e in st["extraction_payload"]["entities"]}
    assert ("COMPLAINANT", "K. Lakshmi Prasad") in ents and ("ACCUSED", "Ramesh Kumar") in ents


# ── Bulk scanned FIRs ────────────────────────────────────────────────────────

def test_zip_safety_rules():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../evil.pdf", b"%PDF-1.4 x")         # path in the name is never used as a path
        z.writestr("inner.zip", b"PK")
        z.writestr("notes.txt", b"hello")
        z.writestr("__MACOSX/._a.pdf", b"x")
    items, skipped = expand_uploads([("batch.zip", buf.getvalue())])
    assert [n for n, _ in items] == ["batch.zip/../../evil.pdf"]
    reasons = {s["name"].rsplit("/", 1)[-1]: s["reason"] for s in skipped}
    assert "Nested" in reasons["inner.zip"] and "Unsupported" in reasons["notes.txt"]


def test_zip_of_five_scanned_firs_imports_in_one_job(client, station_headers):
    token = uuid.uuid4().hex[:6]
    pdfs = [make_pdf([[f"SYNTHETIC BULK FIR {token}-{i}. District : Kurnool Police Station : Kurnool Town Station.",
                       f"FIR No : {100 + i}/2024. Accused A-1: Person {token}{i}, Male."]]) for i in range(5)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, p in enumerate(pdfs):
            z.writestr(f"scans/fir_{token}_{i}.pdf", p)
        z.writestr("scans/readme.txt", b"not a scan")
    res = client.post("/api/v1/bulk/upload-scans", headers=station_headers, files=[
        ("files", (f"firs_{token}.zip", buf.getvalue(), "application/zip")),
        ("files", (f"again_{token}.pdf", pdfs[0], "application/pdf")),   # duplicate of a file in the ZIP
    ])
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["file_type"] == "SCANNED_FIRS" and job["total_records"] == 6
    deadline = time.time() + 120
    while time.time() < deadline and job["status"] == "PROCESSING":
        time.sleep(0.5)
        job = client.get(f"/api/v1/bulk/jobs/{job['id']}", headers=station_headers).json()
    assert job["status"] in ("COMPLETED", "PARTIALLY_FAILED"), job
    statuses = [f["status"] for f in job["files"]]
    assert sum(s in ("COMPLETED", "NEEDS_REVIEW") for s in statuses) == 5
    assert statuses.count("DUPLICATE") == 1
    assert any(s["name"].endswith("readme.txt") for s in job["skipped"])
    assert job["processed_records"] == 6
    # Jobs are listed for the officer who started them
    assert any(j["id"] == job["id"] for j in client.get("/api/v1/bulk/jobs", headers=station_headers).json())


def test_unknown_contraband_filter(client, state_headers):
    db = SyncSessionLocal()
    fir = f"TEST-UNK-{uuid.uuid4().hex[:6]}"
    c = Case(fir_number=fir, year=2024, district="Kurnool", station="Kurnool Town Station", offence_nature="Unknown",
             contraband_type=None, status="DRAFT", created_by="test")
    db.add(c)
    db.commit()
    try:
        cases = client.get("/api/v1/cases/", headers=state_headers, params={"contraband": "unknown"}).json()
        assert fir in {x["fir_number"] for x in cases}
        assert all(not x["contraband_type"] or x["contraband_type"].lower() == "unknown" for x in cases)
    finally:
        db.delete(db.get(Case, c.id))
        db.commit()
        db.close()
