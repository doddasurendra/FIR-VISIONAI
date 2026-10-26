"""
Historical FIR summaries: coverage, multilingual generation from the same sources, caching and
staleness, records without usable text, quota handling, batches and jurisdiction.
The model is replaced by a deterministic fake that only uses the numbered sources it is given.
"""
import sqlite3
import time
import uuid

import pytest

from app.config import settings
from app.services import fir_summaries as fs
from app.services.gemini import gemini_service
from tests.test_knowledge_base_rag import archive, make_pdf, station_headers, state_headers, wait_for_ingestion  # noqa: F401


def _fake_model(calls):
    def summarize(sources, field_keys):
        calls.append(len(sources))
        text = " ".join(s["text"] for s in sources)
        fir = next((w for w in text.split() if w.startswith("FIRNO")), None)
        fields = {k: {"text": fs.NOT_IN_SOURCE, "citations": []} for k in field_keys}
        if fir:
            fields["fir_number"] = {"text": fir, "citations": [1]}
        fields["seized_items"] = {"text": "35 litres of ID liquor (alleged)", "citations": [1]}
        fields["legal_sections"] = {"text": "Section 34(a) of the A.P. Excise Act", "citations": [1]}
        fields["missing_information"] = {"text": "Witness names are not recorded.", "citations": []}
        langs = {}
        for lang, overview in (("en", "It is alleged that ID liquor was transported."),
                               ("te", "ఐడి మద్యం రవాణా చేసినట్లు ఆరోపణ ఉంది."), ("hi", "आरोप है कि आईडी शराब का परिवहन किया गया।")):
            langs[lang] = {"overview": {"text": overview, "citations": [1]}, "fields": fields}
        return {"status": "OK", "model": "fake-model", "data": {"ocr_uncertain": False, "languages": langs}}
    return summarize


def _upload_fir(client, headers, lines):
    token = uuid.uuid4().hex[:8]
    res = client.post("/api/v1/documents/upload", headers=headers,
                      files={"file": (f"fir_{token}.pdf", make_pdf([lines]), "application/pdf")})
    assert res.status_code == 200, res.text
    doc_id = res.json().get("document_id") or res.json()["id"]
    wait_for_ingestion(client, headers, doc_id)
    return doc_id


FIR_LINES = lambda fir: [  # noqa: E731
    "FIRST INFORMATION REPORT - SYNTHETIC TEST RECORD (NOT A REAL CASE)",
    f"FIR number {fir} of Kurnool Town Excise Station, District Kurnool.",
    "On 12.03.2024 the complainant reported that a vehicle was transporting 35 litres of ID liquor.",
    "Acts and sections: Section 34(a) of the A.P. Excise Act. Investigation is in progress.",
]


@pytest.fixture
def fake_model(monkeypatch):
    calls = []
    monkeypatch.setattr(gemini_service, "summarize_fir_record", _fake_model(calls))
    return calls


def test_summary_in_three_languages_is_cited_cached_and_versioned(client, station_headers, fake_model):
    fir = f"FIRNO{uuid.uuid4().hex[:6]}"
    doc_id = _upload_fir(client, station_headers, FIR_LINES(fir))
    key = f"doc:{doc_id}"
    try:
        listing = client.get("/api/v1/summaries/records", headers=station_headers, params={"search": doc_id[:0] or None}).json()
        rec = next(r for r in listing["items"] if r["record_key"] == key)
        assert rec["usable_text"] and rec["summary_state"] == {"en": "PENDING", "te": "PENDING", "hi": "PENDING"}
        assert listing["coverage"]["total_records"] >= 1

        res = client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, params={"language": "te"}, json={})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["outcome"] == "COMPLETED" and body["status"] == "COMPLETED" and body["language"] == "te"
        assert body["summary"]["overview"]["text"].startswith("ఐడి")
        # Identifiers stay exactly as in the source, in every language
        assert body["summary"]["fields"]["fir_number"]["text"] == fir
        assert body["citations"][0]["document_id"] == doc_id and body["citations"][0]["page"] == 1
        assert body["summary"]["fields"]["witnesses"]["available"] is False
        assert len(fake_model) == 1

        for lang in ("en", "hi"):
            s = client.get(f"/api/v1/summaries/records/{key}", headers=station_headers, params={"language": lang}).json()
            assert s["status"] == "COMPLETED" and s["version"] == 1
            assert s["summary"]["fields"]["legal_sections"]["text"] == "Section 34(a) of the A.P. Excise Act"
            assert s["summary"]["fields"]["legal_sections"]["citations"] == [1]

        # Up to date: no second model call
        again = client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, json={}).json()
        assert again["outcome"] == "UP_TO_DATE" and len(fake_model) == 1

        # Source changes -> the summary is stale; regenerating bumps the version
        con = sqlite3.connect(settings.DATABASE_URL.split("///", 1)[1])
        con.execute("UPDATE document_pages SET raw_text = raw_text || ' Corrected by officer.', updated_at = CURRENT_TIMESTAMP WHERE document_id = ?", (doc_id,))
        con.commit()
        con.close()
        stale = client.get(f"/api/v1/summaries/records/{key}", headers=station_headers, params={"language": "en"}).json()
        assert stale["status"] == "STALE"
        regen = client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, json={}).json()
        assert regen["outcome"] == "COMPLETED" and regen["version"] == 2 and regen["status"] == "COMPLETED"
    finally:
        archive(client, station_headers, doc_id)


def test_record_without_text_needs_review_and_is_not_sent_to_the_model(client, station_headers, fake_model):
    doc_id = _upload_fir(client, station_headers, ["FIR"])  # almost no text
    key = f"doc:{doc_id}"
    try:
        res = client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, json={})
        assert res.status_code == 200, res.text
        assert res.json()["outcome"] == "NEEDS_REVIEW" and res.json()["status"] == "NEEDS_REVIEW"
        assert "OCR" in res.json()["error"]
        assert fake_model == []
    finally:
        archive(client, station_headers, doc_id)


def test_quota_error_keeps_existing_summary(client, station_headers, fake_model, monkeypatch):
    fir = f"FIRNO{uuid.uuid4().hex[:6]}"
    doc_id = _upload_fir(client, station_headers, FIR_LINES(fir))
    key = f"doc:{doc_id}"
    try:
        assert client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, json={}).status_code == 200
        monkeypatch.setattr(gemini_service, "summarize_fir_record",
                            lambda sources, keys: {"status": "QUOTA_EXHAUSTED", "error": "429 RESOURCE_EXHAUSTED"})
        res = client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, json={"regenerate": True})
        assert res.status_code == 503 and "quota" in res.json()["detail"]
        kept = client.get(f"/api/v1/summaries/records/{key}", headers=station_headers).json()
        assert kept["status"] == "COMPLETED" and kept["version"] == 1
    finally:
        archive(client, station_headers, doc_id)


def test_record_that_gains_text_is_summarised_again():
    from types import SimpleNamespace
    rec = {"source_chars": 1200, "source_hash": "new"}
    flagged = SimpleNamespace(status="NEEDS_REVIEW", source_hash="old")
    assert fs.summary_state(rec, {"en": flagged, "te": flagged, "hi": flagged}) == {"en": "PENDING", "te": "PENDING", "hi": "PENDING"}
    # Still without usable text: stays NEEDS_REVIEW
    assert fs.summary_state({"source_chars": 10, "source_hash": "x"}, {"en": flagged})["en"] == "NEEDS_REVIEW"


def test_unsupported_numbers_are_flagged():
    sources = [{"text": "35 litres seized on 12.03.2024 under Section 34(a)", "label": "x"}]
    data = {"overview": {"text": "x", "citations": [1]},
            "fields": {"seized_items": {"text": "50 litres seized", "citations": [1]},
                       "incident_date": {"text": "12.03.2024", "citations": [1]}}}
    structured, _, warnings = fs._normalise_language(data, 1, sources, "en")
    assert structured["fields"]["seized_items"]["unverified_numbers"] == ["50"]
    assert "unverified_numbers" not in structured["fields"]["incident_date"]
    assert any("50" in w for w in warnings)


def test_corrected_ocr_names_are_flagged():
    # Live case: the OCR reads "Osgole"; the model wrote "Ongole" in English
    sources = [{"text": "Sri Komatla Srinivasa Swamy Reddy, Advocate, resident of Osgole, Prakasam District", "label": "FIR document 'FIR 16.jpg'"}]
    data = {"overview": {"text": "x", "citations": [1]},
            "fields": {"complainant": {"text": "Sri Komatla Srinivasa Swamy Reddy, Advocate, resident of Ongole, Prakasam District", "citations": [1]},
                       "source_document": {"text": "FIR 16.jpg", "citations": [1]}}}
    structured, _, warnings = fs._normalise_language(data, 1, sources, "en")
    assert structured["fields"]["complainant"]["unverified_names"] == ["Ongole"]
    # Numbers in the source label (file name) are not flagged
    assert "unverified_numbers" not in structured["fields"]["source_document"]


def test_batch_records_progress_failures_and_resumes(client, station_headers, fake_model, monkeypatch):
    firs = [f"FIRNO{uuid.uuid4().hex[:6]}" for _ in range(3)]
    docs = [_upload_fir(client, station_headers, FIR_LINES(f)) for f in firs]
    keys = [f"doc:{d}" for d in docs]
    real = gemini_service.summarize_fir_record

    def one_fails(sources, field_keys):
        if firs[1] in " ".join(s["text"] for s in sources):
            raise RuntimeError("simulated provider error for one record")
        return real(sources, field_keys)
    monkeypatch.setattr(gemini_service, "summarize_fir_record", one_fails)
    monkeypatch.setattr(fs, "_run_batch", _fast(fs._run_batch))
    try:
        job = client.post("/api/v1/summaries/batch", headers=station_headers, json={"record_keys": keys}).json()
        assert job["status"] == "RUNNING" and job["total"] == 3
        final = _wait_batch(client, station_headers, job["job_id"])
        assert final["status"] == "COMPLETED" and final["processed"] == 3
        assert final["succeeded"] == 2 and final["failed_or_review"] == 1
        assert final["errors"][0]["record_key"] == keys[1]

        # Resume: only the failed record is generated again
        monkeypatch.setattr(gemini_service, "summarize_fir_record", real)
        before = len(fake_model)
        job2 = client.post("/api/v1/summaries/batch", headers=station_headers, json={"record_keys": keys}).json()
        final2 = _wait_batch(client, station_headers, job2["job_id"])
        assert final2["status"] == "COMPLETED" and final2["counts"]["UP_TO_DATE"] == 2 and final2["counts"]["COMPLETED"] == 1
        assert len(fake_model) == before + 1
    finally:
        for d in docs:
            archive(client, station_headers, d)


def _fast(run_batch):
    async def run(job_id, keys, user_id, pause_seconds=0.0):
        await run_batch(job_id, keys, user_id, pause_seconds=0.0)
    return run


def _wait_batch(client, headers, job_id):
    for _ in range(120):
        job = client.get(f"/api/v1/summaries/batch/{job_id}", headers=headers).json()
        if job["status"] != "RUNNING":
            return job
        time.sleep(0.25)
    raise AssertionError("batch did not finish")


def test_records_and_summaries_respect_jurisdiction(client, station_headers, state_headers, fake_model):
    created = client.post("/api/v1/cases/", headers=state_headers, json={
        "fir_number": f"TEST-SUM-{uuid.uuid4().hex[:8]}", "year": 2026, "district": "Guntur", "station": "Tenali PS",
        "offence_nature": "Guntur record for summary access test",
        "narrative": "Synthetic Guntur narrative for the access test. " * 8})
    assert created.status_code == 201, created.text
    key = f"case:{created.json()['id']}"
    station_keys = {r["record_key"] for r in client.get("/api/v1/summaries/records", headers=station_headers).json()["items"]}
    assert key not in station_keys
    assert client.get(f"/api/v1/summaries/records/{key}", headers=station_headers).status_code == 404
    assert client.post(f"/api/v1/summaries/records/{key}/generate", headers=station_headers, json={}).status_code == 404
    assert client.post("/api/v1/summaries/batch", headers=station_headers, json={"record_keys": [key]}).status_code == 404
    # The state officer can summarise it from its case narrative
    res = client.post(f"/api/v1/summaries/records/{key}/generate", headers=state_headers, json={})
    assert res.status_code == 200 and res.json()["status"] == "COMPLETED", res.text
    # The case summary endpoint also enforces jurisdiction now
    assert client.get(f"/api/v1/generation/case/{created.json()['id']}/summary", headers=station_headers).status_code == 404
