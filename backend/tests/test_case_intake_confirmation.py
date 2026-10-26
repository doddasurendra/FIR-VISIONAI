"""
New Case Intake confirmation: the HTTP 500 regression and the guarantees around it.

Root cause of the reported 500: cases.offence_nature was VARCHAR(150); an officer-reviewed
allegation of 155 characters made PostgreSQL reject the insert and the unhandled error reached the
browser as a bare 500. SQLite (used here) does not enforce VARCHAR lengths, so these tests check
the model and the pre-write length validation directly.
"""
import io
import time
import uuid

from PIL import Image
from sqlalchemy.exc import OperationalError

from app.models.case import Case


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _new_run(client, headers):
    """Upload a blank FIR image through intake and return the review payload of its extraction run."""
    # Unique pixels: uploads are deduplicated by file hash, and each test needs its own document
    img = Image.new("RGB", (300, 300), color=(255, 255, 255))
    for i, b in enumerate(uuid.uuid4().bytes):
        img.putpixel((i * 7 % 300, i * 13 % 300), (b, 255 - b, b // 2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    up = client.post("/api/v1/documents/upload", headers=headers,
                     files={"file": (f"intake_{uuid.uuid4().hex[:8]}.jpg", buf.getvalue(), "image/jpeg")})
    assert up.status_code == 200, up.text
    run_id = up.json().get("run_id")
    if not run_id:
        # New uploads are processed in the background; then the officer opens an extraction run
        from tests.test_knowledge_base_rag import wait_for_ingestion
        doc_id = up.json()["document_id"]
        wait_for_ingestion(client, headers, doc_id)
        started = client.post("/api/v1/extraction/run", headers=headers, json={"document_id": doc_id})
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
    run = client.get(f"/api/v1/extraction/run/{run_id}", headers=headers)
    assert run.status_code == 200, run.text
    return run.json()


def _reviewed(run, **values):
    fields = {f["key"]: f for f in run["structured_fields"]}
    for k, v in values.items():
        fields[k] = {**fields.get(k, {"key": k}), "key": k, "value": v, "reviewed": True}
    return {**run, "structured_fields": list(fields.values())}


def _kurnool(**extra):
    base = {"fir_number": f"TEST-INTAKE-{uuid.uuid4().hex[:8]}", "district": "Kurnool",
            "station": "Kurnool Town Station", "offence_nature": "Illegal transport of non-duty paid liquor"}
    return {**base, **extra}


def _confirm(client, headers, run, payload):
    return client.post(f"/api/v1/extraction/run/{run['run_id']}/confirm", headers=headers,
                       json={"reviewed_data": _reviewed(run, **payload)})


def test_offence_column_holds_long_allegations():
    # The live column was VARCHAR(150); it must not have a length limit any more
    assert getattr(Case.__table__.c.offence_nature.type, "length", None) is None


def test_long_allegation_confirms_and_retry_does_not_duplicate(client, station_token):
    headers = _headers(station_token)
    run = _new_run(client, headers)
    long_offence = ("Cheated the complainant by using forged documents and obtained a personal loan of "
                    "Rs. 2,50,000/- from the SBI branch by furnishing fake identity proofs and false address records.")
    assert len(long_offence) > 150
    payload = _kurnool(offence_nature=long_offence)

    first = _confirm(client, headers, run, payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["confirmation_status"] == "CONFIRMED" and body["case_id"]
    assert body["workflow_status"] in ("COMPLETED", "NEEDS_REVIEW", "FAILED", "RUNNING")
    assert {s["stage"] for s in body["workflow_stages"]} >= {"INTAKE", "AI_LEGAL", "ADMIN"}

    # A retried confirmation (double click, network retry) returns the same case
    again = _confirm(client, headers, run, payload)
    assert again.status_code == 200, again.text
    assert again.json()["case_id"] == body["case_id"]
    found = client.get("/api/v1/cases/", headers=headers, params={"search": payload["fir_number"]})
    if found.status_code == 200:
        items = found.json() if isinstance(found.json(), list) else found.json().get("items", found.json().get("cases", []))
        assert sum(1 for c in items if c.get("fir_number") == payload["fir_number"]) <= 1
    case = client.get(f"/api/v1/cases/{body['case_id']}", headers=headers).json()["case"]
    assert case["offence_nature"] == long_offence


def test_field_longer_than_its_column_is_a_correction_not_a_500(client, station_token):
    headers = _headers(station_token)
    run = _new_run(client, headers)
    res = _confirm(client, headers, run, _kurnool(seized_unit="Litres of illicitly distilled arrack in plastic cans"))
    assert res.status_code == 400, res.text
    body = res.json()
    assert body["code"] == "VALIDATION_FAILED"
    issue = next(i for i in body["validation_report"] if i["field"] == "seized_unit")
    assert issue["issue"] == "TOO_LONG" and issue["max_length"] == 20
    assert client.get(f"/api/v1/extraction/run/{run['run_id']}", headers=headers).json().get("case_id") is None


def test_station_officer_cannot_register_another_jurisdiction(client, station_token):
    headers = _headers(station_token)
    run = _new_run(client, headers)
    res = _confirm(client, headers, run, _kurnool(district="Guntur", station="Tenali PS"))
    assert res.status_code == 400, res.text
    issue = next(i for i in res.json()["validation_report"] if i["issue"] == "OUT_OF_JURISDICTION")
    assert issue["candidate_value"]


def test_fir_number_of_another_jurisdiction_is_never_overwritten(client, station_token, state_token):
    fir = f"TEST-GNT-{uuid.uuid4().hex[:8]}"
    created = client.post("/api/v1/cases/", headers=_headers(state_token), json={
        "fir_number": fir, "year": 2026, "district": "Guntur", "station": "Tenali PS",
        "offence_nature": "Test case owned by Guntur"})
    assert created.status_code == 201, created.text

    headers = _headers(station_token)
    run = _new_run(client, headers)
    res = _confirm(client, headers, run, _kurnool(fir_number=fir))
    assert res.status_code == 409, res.text
    assert res.json()["code"] == "DUPLICATE_FIR_NUMBER"
    owner = client.get(f"/api/v1/cases/{created.json()['id']}", headers=_headers(state_token)).json()["case"]
    assert owner["district"] == "Guntur" and owner["offence_nature"] == "Test case owned by Guntur"


def test_database_failure_returns_actionable_error_and_saves_nothing(client, station_token, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    headers = _headers(station_token)
    run = _new_run(client, headers)
    payload = _kurnool()

    # The draft is saved (first commit), then the connection drops at the registration commit
    real_commit, calls = AsyncSession.commit, {"n": 0}

    async def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OperationalError("COMMIT", {}, Exception("connection timeout"))
        return await real_commit(self)
    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)
    res = _confirm(client, headers, run, payload)
    monkeypatch.setattr(AsyncSession, "commit", real_commit)
    assert res.status_code == 503, res.text
    assert res.json()["code"] == "DATABASE_UNAVAILABLE" and "Nothing was saved" in res.json()["detail"]
    # Rolled back: the case does not exist and the run is not linked to one
    assert client.get(f"/api/v1/extraction/run/{run['run_id']}", headers=headers).json().get("case_id") is None


def test_failed_ai_stage_keeps_the_case_and_retry_resumes_only_unfinished_stages(client, station_token, monkeypatch):
    from app.services import workflow

    original = workflow._run_ai_legal_stage

    async def broken_ai(db, case_id):
        await workflow._upsert_workflow_stage(db, case_id, "AI_LEGAL", "FAILED", error_message="Simulated AI provider outage")
    monkeypatch.setattr(workflow, "_run_ai_legal_stage", broken_ai)

    headers = _headers(station_token)
    run = _new_run(client, headers)
    res = _confirm(client, headers, run, _kurnool())
    assert res.status_code == 200, res.text
    body = res.json()
    case_id = body["case_id"]
    stages = {s["stage"]: s for s in body["workflow_stages"]}
    assert stages["AI_LEGAL"]["status"] == "FAILED"
    # The readiness check ran but must not claim the case is complete
    assert stages["ADMIN"]["status"] == "NEEDS_REVIEW"
    assert body["workflow_status"] == "FAILED" and body["warnings"]
    intake_done_at = stages["INTAKE"]["completed_at"]

    # Retry with the provider back: only unfinished stages run again
    monkeypatch.setattr(workflow, "_run_ai_legal_stage", original)
    retry = client.post(f"/api/v1/folders/workflow/{case_id}/retry", headers=headers)
    assert retry.status_code == 200, retry.text
    assert "INTAKE" not in retry.json()["stages_to_run"] and "AI_LEGAL" in retry.json()["stages_to_run"]
    final = {}
    for _ in range(40):
        final = {s["stage"]: s for s in client.get(f"/api/v1/folders/workflow/{case_id}", headers=headers).json()}
        if final.get("ADMIN", {}).get("status") in ("COMPLETED", "NEEDS_REVIEW") and final["AI_LEGAL"]["status"] != "FAILED":
            break
        time.sleep(0.25)
    assert final["AI_LEGAL"]["status"] == "COMPLETED"
    assert final["INTAKE"]["completed_at"] == intake_done_at  # completed work was not repeated


def test_workflow_status_and_retry_require_jurisdiction(client, station_token, state_token):
    created = client.post("/api/v1/cases/", headers=_headers(state_token), json={
        "fir_number": f"TEST-WF-{uuid.uuid4().hex[:8]}", "year": 2026, "district": "Guntur",
        "station": "Tenali PS", "offence_nature": "Workflow access test"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert client.get(f"/api/v1/folders/workflow/{case_id}", headers=_headers(station_token)).status_code == 404
    assert client.post(f"/api/v1/folders/workflow/{case_id}/retry", headers=_headers(station_token)).status_code == 404
    assert client.get(f"/api/v1/folders/workflow/{case_id}", headers=_headers(state_token)).status_code == 200


def test_database_errors_are_described_without_internals():
    from sqlalchemy.exc import DataError, IntegrityError
    from app.services.case_validation import describe_db_error
    code, body = describe_db_error(DataError("INSERT ...", {"x": "secret narrative"}, Exception("value too long for type character varying(150)")))
    assert code == 422 and "150" in body["detail"] and "secret" not in body["detail"] and "INSERT" not in body["detail"]
    code, body = describe_db_error(IntegrityError("INSERT", {}, Exception('duplicate key value violates unique constraint "ix_cases_fir_number"')))
    assert code == 409 and body["code"] == "DUPLICATE_FIR_NUMBER"
