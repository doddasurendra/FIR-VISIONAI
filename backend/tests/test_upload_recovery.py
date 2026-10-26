"""
Evidence upload / OCR recovery: failures are persisted on the document, a lost in-memory job is
recovered from the database, interrupted processing can be retried without a new upload,
re-uploading an unfinished file reuses its record, and text recovered after ingestion makes the
document searchable.
"""
import io
import sqlite3
import time
import uuid

from PIL import Image

from app.config import settings
from app.api.v1 import documents as documents_api
from tests.test_knowledge_base_rag import make_pdf, station_headers  # noqa: F401


def _db():
    return sqlite3.connect(settings.DATABASE_URL.split("///", 1)[1])


def _pdf(token):
    return make_pdf([[f"FIRST INFORMATION REPORT - SYNTHETIC TEST {token} (NOT A REAL CASE)",
                      "FIR number 77/2026 of Kurnool Town Excise Station, District Kurnool.",
                      "On 02.01.2026 a vehicle was found transporting 20 litres of ID liquor."]])


def _upload(client, headers, content, name):
    res = client.post("/api/v1/documents/upload", headers=headers, files={"file": (name, content, "application/pdf")})
    return res


def _wait_job(client, headers, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get(f"/api/v1/documents/jobs/{job_id}/status", headers=headers)
        if res.status_code == 200 and res.json()["stage"] in ("COMPLETED", "FAILED"):
            return res.json()
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def _doc_row(doc_id):
    con = _db()
    try:
        return con.execute("SELECT ingestion_status, index_status, error_message FROM documents WHERE id=?", (doc_id,)).fetchone()
    finally:
        con.close()


def test_processing_failure_is_saved_on_the_document_and_retry_recovers(client, station_headers, monkeypatch):
    token = uuid.uuid4().hex[:8]
    real = documents_api.pdf_pipeline.process_document

    async def broken(*a, **k):
        raise RuntimeError("simulated OCR provider crash")
    monkeypatch.setattr(documents_api.pdf_pipeline, "process_document", broken)
    content = _pdf(token)  # built once: PDFs carry a creation timestamp, so the same bytes are re-uploaded
    up = _upload(client, station_headers, content, f"fail_{token}.pdf")
    assert up.status_code == 200, up.text
    doc_id, job = up.json()["document_id"], _wait_job(client, station_headers, up.json()["job_id"])
    assert job["stage"] == "FAILED"
    status_, _, error = _doc_row(doc_id)
    assert status_ == "FAILED" and "simulated OCR provider crash" in error  # persisted, not only in memory

    st = client.get(f"/api/v1/documents/{doc_id}/intake-status", headers=station_headers).json()
    assert st["stage"] == "FAILED" and st["retryable"] is True

    # Uploading the same file again resumes the same record instead of creating a duplicate
    monkeypatch.setattr(documents_api.pdf_pipeline, "process_document", real)
    again = _upload(client, station_headers, content, f"fail_{token}.pdf")
    assert again.status_code == 200, again.text
    assert again.json()["document_id"] == doc_id and again.json()["resumed_existing"] is True
    done = _wait_job(client, station_headers, again.json()["job_id"])
    assert done["stage"] == "COMPLETED"
    assert _doc_row(doc_id)[0] == "COMPLETED"
    con = _db()
    try:
        assert con.execute("SELECT COUNT(*) FROM documents WHERE original_filename=?", (f"fail_{token}.pdf",)).fetchone()[0] == 1
    finally:
        con.close()


def test_lost_job_is_recovered_from_the_database(client, station_headers):
    token = uuid.uuid4().hex[:8]
    up = _upload(client, station_headers, _pdf(token), f"lost_{token}.pdf")
    doc_id, job_id = up.json()["document_id"], up.json()["job_id"]
    _wait_job(client, station_headers, job_id)
    documents_api._PROCESSING_JOBS.pop(job_id, None)  # what a server restart does
    assert client.get(f"/api/v1/documents/jobs/{job_id}/status", headers=station_headers).status_code == 404
    st = client.get(f"/api/v1/documents/{doc_id}/intake-status", headers=station_headers).json()
    assert st["stage"] == "COMPLETED" and st["document_id"] == doc_id
    assert st["run_id"] and st["extraction_payload"].get("structured_fields") is not None


def test_interrupted_processing_can_be_retried_without_a_new_upload(client, station_headers):
    token = uuid.uuid4().hex[:8]
    up = _upload(client, station_headers, _pdf(token), f"stall_{token}.pdf")
    doc_id = up.json()["document_id"]
    _wait_job(client, station_headers, up.json()["job_id"])
    con = _db()
    try:  # a background task killed by a restart leaves the record PROCESSING
        con.execute("UPDATE documents SET ingestion_status='PROCESSING', updated_at=datetime('now','-2 hours') WHERE id=?", (doc_id,))
        con.commit()
    finally:
        con.close()
    st = client.get(f"/api/v1/documents/{doc_id}/intake-status", headers=station_headers).json()
    assert st["stage"] == "INTERRUPTED" and st["retryable"] is True and "Retry processing" in st["error"]
    retry = client.post(f"/api/v1/documents/{doc_id}/intake-retry", headers=station_headers)
    assert retry.status_code == 200, retry.text
    assert _wait_job(client, station_headers, retry.json()["job_id"])["stage"] == "COMPLETED"
    assert _doc_row(doc_id)[0] == "COMPLETED"
    # A running document is not processed twice
    con = _db()
    try:
        con.execute("UPDATE documents SET ingestion_status='PROCESSING', updated_at=datetime('now') WHERE id=?", (doc_id,))
        con.commit()
    finally:
        con.close()
    assert client.post(f"/api/v1/documents/{doc_id}/intake-retry", headers=station_headers).status_code == 409
    con = _db()
    try:
        con.execute("UPDATE documents SET ingestion_status='COMPLETED' WHERE id=?", (doc_id,))
        con.commit()
    finally:
        con.close()


def test_text_recovered_after_ingestion_makes_the_document_searchable(client, station_headers, monkeypatch):
    from app.api.v1 import extraction as extraction_api

    # An image whose OCR fails at ingestion (no OCR provider in tests) is marked NEEDS_REVIEW
    img =Image.new("RGB", (320, 240), color=(255, 255, 255))
    for i, b in enumerate(uuid.uuid4().bytes):
        img.putpixel((i * 11 % 320, i * 7 % 240), (b, b, 255 - b))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    token = uuid.uuid4().hex[:8]
    up = client.post("/api/v1/documents/upload", headers=station_headers,
                     files={"file": (f"scan_{token}.jpg", buf.getvalue(), "image/jpeg")})
    assert up.status_code == 200, up.text
    doc_id = up.json()["document_id"]
    _wait_job(client, station_headers, up.json()["job_id"])
    assert _doc_row(doc_id)[1] == "NEEDS_REVIEW"

    # Sarvam Digitise later reads the page: the text must reach the index
    recovered = f"FIRST INFORMATION REPORT recovered{token} Kurnool Town Excise Station seized 15 litres of ID liquor."

    class FakeSarvam:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        async def process_document(**kwargs):
            return {"extract": {"result": {"fir_number": "88/2026"}, "annotations": {}},
                    "pages_text_map": {1: recovered}, "sarvam_job_id": "sv-test", "provider": "Sarvam (test)"}
    monkeypatch.setattr(extraction_api, "sarvam_doc_ai", FakeSarvam)
    run = client.post("/api/v1/extraction/run", headers=station_headers, json={"document_id": doc_id})
    assert run.status_code == 200, run.text
    assert _doc_row(doc_id)[1] in ("INDEXED", "PARTIALLY_INDEXED")
    search = client.get("/api/v1/documents/", headers=station_headers, params={"q": f"recovered{token}"})
    assert search.status_code == 200 and doc_id in search.text
