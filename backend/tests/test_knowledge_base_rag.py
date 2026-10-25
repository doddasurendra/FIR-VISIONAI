"""
Knowledge Base ingestion, retrieval, citations and access control.

All documents created here are synthetic (source_type SYNTHETIC) and are archived at the end of
each test so they do not remain searchable in the local database.
"""
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import uuid
from types import SimpleNamespace

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import embeddings as embeddings_module  # noqa: E402
from app.services.document_access import can_access_document  # noqa: E402
from app.services.rag_engine import NOT_FOUND, best_excerpt  # noqa: E402
from app.services.retrieval import query_terms  # noqa: E402
from app.services.text_processing import (  # noqa: E402
    PageText, build_chunks, clean_extracted_text, section_label_for, segment_pages,
)
from tests.test_backend import get_demo_fir_document  # noqa: E402

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_pdf(pages):
    """Build a text PDF; each item in pages is a list of lines for one page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(50, y, line)
            y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


def synthetic_act_pdf(token):
    """A small synthetic 'Act' with numbered sections across three pages (test data, not law)."""
    return make_pdf([
        [f"SYNTHETIC TEST STATUTE {token} (NOT AN OFFICIAL LAW)", "1. Short title.— This test statute exists only for automated tests.",
         "2. Definitions.— In this statute, unless the context otherwise requires, words carry their usual meaning."],
        ["3. Possession of marked contraband.— Whoever keeps marked contraband shall be liable under this test statute.",
         f"The marker word for this section is zephyrquartz{token}."],
        ["4. Transport by vehicle.— Whoever transports marked contraband in a motor vehicle commits an offence.",
         "5. Seizure procedure.— The officer shall prepare an inventory and obtain two panch witnesses."],
    ])


def upload_kb(client, headers, content, filename, title, **fields):
    data = {"document_title": title, "category": fields.pop("category", "REFERENCE"),
            "source_type": fields.pop("source_type", "SYNTHETIC"), **fields}
    return client.post("/api/v1/documents/knowledge-base/upload", headers=headers,
                       files={"file": (filename, content, "application/octet-stream")}, data=data)


def wait_for_ingestion(client, headers, doc_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = client.get(f"/api/v1/documents/{doc_id}/detail", headers=headers).json()
        if d.get("status") not in ("PROCESSING", "PENDING"):
            return d
        time.sleep(0.5)
    raise AssertionError(f"Ingestion of {doc_id} did not finish in {timeout}s")


def archive(client, headers, doc_id):
    client.delete(f"/api/v1/documents/{doc_id}", params={"reason": "automated test cleanup"}, headers=headers)


def auth(client, username, password):
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def state_headers(client):
    return auth(client, "state_director", "StateAdmin@2024")


@pytest.fixture
def station_headers(client):
    return auth(client, "station_officer", "StationPass@2024")


@pytest.fixture
def district_headers(client):
    return auth(client, "district_admin", "DistrictPass@2024")


# ── Text processing ──────────────────────────────────────────────────────────

def test_cleanup_drops_legacy_font_lines_and_keeps_english_and_telugu():
    text = ("vlk/kkj.k EXTRAORDINARY Hkkx II [k.M 1\n"
            "£ÉÉ®iÉ BÉEÉ ºÉÆÉÊ´ÉvÉÉxÉ\n"
            "303. (1) Whoever, intending to take dishonestly any movable property commits theft.\n"
            "నిందితుడు వాహనంలో మద్యం రవాణా చేశాడు.")
    out = clean_extracted_text(text)
    assert "vlk/kkj.k" not in out and "£ÉÉ" not in out
    assert "Whoever, intending" in out
    assert "నిందితుడు" in out


def test_segmentation_tracks_sections_across_pages_and_skips_toc():
    toc = PageText(1, "\n".join(f"{i}. Heading number {i}." for i in range(1, 25)))
    p2 = PageText(2, "1. Short title.— This Act may be called the Test Act.\n2. Definitions.— words mean things.")
    p3 = PageText(3, "continued definitions text on the next page.\n3. Theft.— Whoever takes property.")
    p4 = PageText(4, "1. Subs. by Act 5 of 2012 (footnote).\nmore text of section three.")
    segments, provisions = segment_pages([toc, p2, p3, p4], "Section")
    assert [p.section_ref for p in provisions] == ["Section 1", "Section 2", "Section 3"]
    assert provisions[2].page_start == 3
    # Text continuing on page 3 still belongs to Section 2; the footnote on page 4 stays in Section 3
    p3_first = [s for s in segments if s.page_number == 3][0]
    assert p3_first.section_ref == "Section 2"
    assert all(s.section_ref == "Section 3" for s in segments if s.page_number == 4)
    assert all(s.section_ref is None for s in segments if s.page_number == 1)
    chunks = build_chunks(segments)
    assert {c["physical_page_number"] for c in chunks} == {1, 2, 3, 4}


def test_section_label_and_query_terms():
    assert section_label_for("The Constitution of India", "LEGAL_ACT") == "Article"
    assert section_label_for("AP Excise (Retail) Rules, 2019", "LEGAL_ACT") == "Rule"
    assert section_label_for("Bharatiya Nyaya Sanhita, 2023", "LEGAL_ACT") == "Section"
    assert section_label_for("FIR scan.pdf", "FIR") is None
    assert query_terms("What quantity of contraband was seized in this FIR?") == ["quantity", "contraband", "seized"]
    ex = best_excerpt("Intro text. " * 40 + "Total Quantity Seized: 45.0 Litres of arrack. " + "Tail. " * 40,
                      ["quantity", "seized"])
    assert "45.0 Litres" in ex


def test_access_rules_unit():
    station = SimpleNamespace(id="u1", role="STATION", district="Kurnool", station="Kurnool Town Station")
    district = SimpleNamespace(id="u2", role="DISTRICT", district="Kurnool", station=None)
    doc = lambda **kw: SimpleNamespace(**{"doc_category": "EVIDENCE", "district": None, "station": None,
                                          "case_id": None, "created_by": "other", **kw})
    other_area_case = SimpleNamespace(district="Guntur", station="Tenali Station")
    own_case = SimpleNamespace(district="Kurnool", station="Kurnool Town Station")
    assert can_access_document(station, doc(doc_category="LEGAL_ACT"))
    assert not can_access_document(station, doc(district="Guntur"))
    assert can_access_document(district, doc(district="kurnool"))
    assert not can_access_document(station, doc(case_id="c1"), case=other_area_case)
    assert can_access_document(station, doc(case_id="c1"), case=own_case)
    assert not can_access_document(station, doc(case_id="c1"), case=None)  # dangling case link fails closed
    assert can_access_document(station, doc(created_by="u1"))
    other_creator = SimpleNamespace(district="Guntur", station="Tenali Station")
    assert not can_access_document(station, doc(), creator=other_creator)


# ── Ingestion, search and citations ──────────────────────────────────────────

def test_kb_ingestion_sections_search_and_cited_answer(client, state_headers):
    token = uuid.uuid4().hex[:8]
    res = upload_kb(client, state_headers, synthetic_act_pdf(token), f"synthetic_statute_{token}.pdf",
                    f"Synthetic Test Statute {token}", category="LEGAL_ACT")
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]
    try:
        d = wait_for_ingestion(client, state_headers, doc_id)
        assert d["status"] == "COMPLETED"
        assert d["index_status"] == "INDEXED"
        assert d["pages_total"] == 3 and d["pages_with_text"] == 3
        assert d["chunk_count"] >= 3
        assert {"Section 3", "Section 4", "Section 5"} <= set(d["sections"])
        assert d["source_type"] == "SYNTHETIC"
        assert d["ingestion_jobs"][0]["status"] == "INDEXED"
        assert d["pages"][1]["physical_page_number"] == 2 and "zephyrquartz" in d["pages"][1]["text"]

        listing = client.get("/api/v1/documents/", headers=state_headers,
                             params={"search": f"zephyrquartz{token}", "search_content": True}).json()
        hit = next(x for x in listing["documents"] if x["id"] == doc_id)
        assert hit["match"]["physical_page_number"] == 2

        rag = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": f"What does the statute say about marked contraband zephyrquartz{token}?",
            "scope": "KNOWLEDGE_BASE", "categories": ["LEGAL_ACT"], "language": "en"}).json()
        assert rag["not_found"] is False, rag
        cit = next(c for c in rag["citations"] if c["document_id"] == doc_id)
        assert cit["physical_page_number"] == 2
        assert cit["section_ref"] == "Section 3"
        assert cit["source_type"] == "SYNTHETIC"
        assert cit["open_url"].endswith("#page=2")
        assert f"[S{cit['source_number']}]" in rag["answer"]

        # Questions naming a section and document match the section label and title, not only the body text
        named = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": f"What does Section 4 of the Synthetic Test Statute {token} say?",
            "scope": "KNOWLEDGE_BASE", "categories": ["LEGAL_ACT"]}).json()
        assert named["not_found"] is False, named
        assert any(c["document_id"] == doc_id and c["section_ref"] == "Section 4" for c in named["citations"])
    finally:
        archive(client, state_headers, doc_id)

    # Archived documents are excluded from retrieval
    rag2 = client.post("/api/v1/rag/query", headers=state_headers, json={
        "query": f"zephyrquartz{token} marked contraband", "scope": "KNOWLEDGE_BASE", "language": "en"}).json()
    assert all(c["document_id"] != doc_id for c in rag2["citations"])


def test_duplicate_empty_and_invalid_uploads(client, state_headers):
    token = uuid.uuid4().hex[:8]
    pdf = make_pdf([[f"Synthetic circular {token} about reporting timelines for seizure registers."]])
    first = upload_kb(client, state_headers, pdf, f"circ_{token}.pdf", f"Synthetic circular {token}", category="CIRCULAR")
    assert first.status_code == 200
    doc_id = first.json()["id"]
    try:
        dup = upload_kb(client, state_headers, pdf, f"circ_copy_{token}.pdf", "Copy", category="CIRCULAR")
        assert dup.status_code == 409
        assert dup.json()["detail"]["duplicate_document_id"] == doc_id

        empty = upload_kb(client, state_headers, b"", "empty.pdf", "Empty", category="CIRCULAR")
        assert empty.status_code == 400

        bad = upload_kb(client, state_headers, b"%PDF-1.4 this is not really a pdf " + token.encode(),
                        f"broken_{token}.pdf", f"Broken {token}", category="CIRCULAR")
        assert bad.status_code == 200
        bad_id = bad.json()["id"]
        d = wait_for_ingestion(client, state_headers, bad_id)
        assert d["status"] == "FAILED" and d["index_status"] == "FAILED"
        assert "Invalid or corrupted PDF" in (d["error_message"] or "")
        assert d["ingestion_jobs"][0]["status"] == "FAILED"
        retry = client.post(f"/api/v1/documents/{bad_id}/reprocess", headers=state_headers, params={"mode": "full"})
        assert retry.status_code == 200
        d2 = wait_for_ingestion(client, state_headers, bad_id)
        assert d2["status"] == "FAILED" and len(d2["ingestion_jobs"]) >= 2
        archive(client, state_headers, bad_id)
    finally:
        archive(client, state_headers, doc_id)


def test_image_without_ocr_needs_review_and_is_not_searchable(client, state_headers, monkeypatch):
    from PIL import Image
    from app.services import gemini as gemini_module
    monkeypatch.setattr(gemini_module.gemini_service, "client", None)  # no OCR provider
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(int(uuid.uuid4().int % 255), 10, 10)).save(buf, format="PNG")
    res = upload_kb(client, state_headers, buf.getvalue(), f"evidence_{uuid.uuid4().hex[:6]}.png",
                    "Synthetic evidence photo", category="EVIDENCE", district="Kurnool")
    assert res.status_code == 200
    doc_id = res.json()["id"]
    try:
        d = wait_for_ingestion(client, state_headers, doc_id)
        assert d["status"] == "NEEDS_REVIEW" and d["index_status"] == "NEEDS_REVIEW"
        assert d["chunk_count"] == 0
        assert all(not p["text"] for p in d["pages"])  # no placeholder text stored
        rag = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": "What is written in this image?", "scope": "CURRENT_FIR", "document_id": doc_id}).json()
        assert rag["not_found"] is True and rag["document_status"] == "NEEDS_REVIEW"
        assert rag["answer"] == NOT_FOUND["en"]
    finally:
        archive(client, state_headers, doc_id)


def test_reference_documents_cannot_become_case_evidence(client, state_headers):
    token = uuid.uuid4().hex[:8]
    res = upload_kb(client, state_headers, synthetic_act_pdf(token), f"ref_{token}.pdf",
                    f"Synthetic Reference Statute {token}", category="LEGAL_ACT")
    doc_id = res.json()["id"]
    try:
        wait_for_ingestion(client, state_headers, doc_id)
        run = client.post("/api/v1/extraction/run", json={"document_id": doc_id}, headers=state_headers).json()
        confirm = client.post(f"/api/v1/extraction/run/{run['run_id']}/confirm", headers=state_headers,
                              json={"reviewed_data": run})
        assert confirm.status_code == 400
        assert client.get(f"/api/v1/documents/{doc_id}/detail", headers=state_headers).json()["case_id"] is None
    finally:
        archive(client, state_headers, doc_id)


def test_upload_permissions(client, station_headers, district_headers):
    pdf = make_pdf([["Synthetic permission test document."]])
    assert upload_kb(client, station_headers, pdf, "x.pdf", "X", category="LEGAL_ACT").status_code == 403
    r = upload_kb(client, district_headers, pdf, "x.pdf", "X", category="CIRCULAR",
                  source_type="OFFICIAL", source_url="https://example.gov.in/x.pdf")
    assert r.status_code == 403  # only STATE may mark a document as official


# ── Jurisdiction isolation ───────────────────────────────────────────────────

def test_other_jurisdiction_document_is_isolated_everywhere(client, state_headers, station_headers):
    token = uuid.uuid4().hex[:8]
    pdf = make_pdf([[f"Synthetic Guntur evidence record {token}.", f"Seized vehicle marker quillfeather{token} at Tenali."]])
    res = upload_kb(client, state_headers, pdf, f"guntur_{token}.pdf", f"Guntur evidence {token}",
                    category="EVIDENCE", district="Guntur", station="Tenali Station", record_kind="SYNTHETIC")
    assert res.status_code == 200
    doc_id = res.json()["id"]
    try:
        assert wait_for_ingestion(client, state_headers, doc_id)["index_status"] == "INDEXED"
        for path in ("pages", "detail", "view", "download", "extract"):
            r = client.get(f"/api/v1/documents/{doc_id}/{path}", headers=station_headers)
            assert r.status_code == 403, (path, r.status_code)
        assert client.delete(f"/api/v1/documents/{doc_id}", headers=station_headers).status_code == 403
        listing = client.get("/api/v1/documents/", headers=station_headers,
                             params={"search": f"quillfeather{token}", "search_content": True}).json()
        assert all(d["id"] != doc_id for d in listing["documents"])
        hist = client.get("/api/v1/documents/historical-firs", headers=station_headers).json()
        assert all(r["document_id"] != doc_id for r in hist["records"])

        direct = client.post("/api/v1/rag/query", headers=station_headers, json={
            "query": "What vehicle was seized?", "scope": "CURRENT_FIR", "document_id": doc_id})
        assert direct.status_code == 403
        for scope in ("KNOWLEDGE_BASE", "ALL_AUTHORIZED"):
            rag = client.post("/api/v1/rag/query", headers=station_headers, json={
                "query": f"seized vehicle marker quillfeather{token}", "scope": scope}).json()
            assert all(c["document_id"] != doc_id for c in rag.get("citations", [])), scope

        # The owning jurisdiction (here: STATE) still sees it
        assert client.get(f"/api/v1/documents/{doc_id}/pages", headers=state_headers).status_code == 200
    finally:
        archive(client, state_headers, doc_id)


# ── Scopes ───────────────────────────────────────────────────────────────────

def test_case_and_all_authorized_scopes_cite_the_demo_fir(client, station_headers):
    fir = get_demo_fir_document(client, station_headers)
    q = "What quantity of contraband was seized?"
    if fir.get("case_id"):
        case_res = client.post("/api/v1/rag/query", headers=station_headers,
                               json={"query": q, "scope": "CASE", "case_id": fir["case_id"]}).json()
        assert any(c["document_id"] == fir["id"] for c in case_res["citations"]), case_res
    all_res = client.post("/api/v1/rag/query", headers=station_headers,
                          json={"query": q, "scope": "ALL_AUTHORIZED"}).json()
    assert all_res["not_found"] is False
    assert any(c["document_id"] == fir["id"] and c["physical_page_number"] == 2 for c in all_res["citations"])
    count = client.post("/api/v1/rag/query", headers=station_headers,
                        json={"query": "How many cases are registered?", "scope": "ALL_AUTHORIZED"}).json()
    assert count["is_aggregate_count"] is True and isinstance(count["count"], int)


def test_fir_and_law_scope_only_uses_selected_fir_and_legal_documents(client, station_headers):
    fir = get_demo_fir_document(client, station_headers)
    res = client.post("/api/v1/rag/query", headers=station_headers, json={
        "query": "seized contraband quantity", "scope": "FIR_AND_LAW", "document_id": fir["id"]}).json()
    assert res["not_found"] is False
    for c in res["citations"]:
        assert c["document_id"] == fir["id"] or c["category"] == "LEGAL_ACT"
    bad = client.post("/api/v1/rag/query", headers=station_headers, json={"query": "x", "scope": "NOPE"})
    assert bad.status_code == 400


# ── Embeddings (deterministic fake provider) ────────────────────────────────

def _fake_vector(text):
    v = [0.0] * embeddings_module.EMBEDDING_DIM
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % len(v)] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def test_embeddings_are_stored_and_used_for_hybrid_retrieval(client, state_headers, monkeypatch):
    svc = embeddings_module.embedding_service
    monkeypatch.setattr(svc, "is_available", lambda: True)
    monkeypatch.setattr(svc, "embed_documents", lambda texts: [_fake_vector(t) for t in texts])
    monkeypatch.setattr(svc, "embed_query", lambda t: _fake_vector(t))
    monkeypatch.setattr(svc, "model", "fake-test-embedding")

    token = uuid.uuid4().hex[:8]
    res = upload_kb(client, state_headers, synthetic_act_pdf(token), f"embed_{token}.pdf",
                    f"Synthetic Embedded Statute {token}", category="INVESTIGATION_GUIDE")
    doc_id = res.json()["id"]
    try:
        d = wait_for_ingestion(client, state_headers, doc_id)
        assert d["index_status"] == "INDEXED"
        assert d["embedded_chunk_count"] == d["chunk_count"] > 0
        assert d["embedding_model"] == "fake-test-embedding"
        rag = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": f"panch witnesses inventory seizure procedure {token}", "scope": "KNOWLEDGE_BASE",
            "categories": ["INVESTIGATION_GUIDE"]}).json()
        assert rag["retrieval"]["semantic_search"] is True and rag["retrieval"]["vector_hits"] > 0
        cit = next(c for c in rag["citations"] if c["document_id"] == doc_id)
        assert cit["physical_page_number"] == 3  # guides are not split into statutory sections
    finally:
        archive(client, state_headers, doc_id)


# ── Official source manifest ─────────────────────────────────────────────────

def test_official_sources_manifest_is_complete_and_official():
    with open(os.path.join(REPO_DIR, "corpus", "official_sources.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    assert {s["id"] for s in sources} >= {"bns_2023", "bnss_2023", "bsa_2023", "constitution_2024"}
    for s in sources:
        for key in ("title", "act_name", "reference_number", "jurisdiction", "issuing_authority",
                    "legal_status", "source_url", "download_url", "expect_text", "status"):
            assert s.get(key) not in (None, "", []), (s["id"], key)
        host = re.match(r"https://([^/]+)/", s["download_url"]).group(1)
        assert host.endswith(".gov.in") or host.endswith(".nic.in"), (s["id"], host)


def test_official_manifest_values_fit_postgres_column_limits():
    """SQLite ignores VARCHAR lengths; PostgreSQL (Supabase) rejects longer values."""
    from app.models.document import Document
    from app.models.legal import LegalCorpus
    with open(os.path.join(REPO_DIR, "corpus", "official_sources.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    doc_cols = {"title": "document_title", "issuing_authority": "issuing_authority", "reference_number": "reference_number",
                "jurisdiction": "jurisdiction", "source_url": "source_url", "legal_status": "legal_status",
                "language": "language", "publication_date": "publication_date", "commencement_date": "commencement_date"}
    legal_cols = {"act_name": "act_name", "source_url": "source_url", "reference_number": "source_gazette",
                  "jurisdiction": "jurisdiction", "legal_corpus_category": "category", "commencement_date": "effective_date"}
    for s in sources:
        for key, col in doc_cols.items():
            limit = Document.__table__.c[col].type.length
            assert not s.get(key) or len(s[key]) <= limit, (s["id"], key, len(s[key]), limit)
        for key, col in legal_cols.items():
            limit = LegalCorpus.__table__.c[col].type.length
            assert not s.get(key) or len(s[key]) <= limit, (s["id"], key, len(s[key]), limit)
