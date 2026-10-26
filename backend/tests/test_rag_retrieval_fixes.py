"""
Regression tests for the assistant and evidence viewer fixes:
- OCR table markup is cleaned without losing cell text
- a question naming an Act is answered from that Act, not from other Acts that cite it
- short FIR records are read in full, so questions sharing no words with the form still reach the model
- the viewer finds an original whose recorded path is stale, and reports a genuinely missing file clearly
"""
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings  # noqa: E402
from app.services.retrieval import query_terms, title_named_in  # noqa: E402
from app.services.text_processing import clean_extracted_text, strip_markup  # noqa: E402
from tests.test_backend import get_demo_fir_document  # noqa: E402
from tests.test_knowledge_base_rag import (  # noqa: E402
    archive, make_pdf, station_headers, state_headers, upload_kb, wait_for_ingestion,
)

__all__ = ["state_headers", "station_headers"]  # fixtures re-exported for pytest


def _letters(n=8):
    # Letters only, so the token never looks like a year that title normalisation strips
    return "".join(chr(97 + int(c, 16)) for c in uuid.uuid4().hex[:n])


def _sqlite_path():
    url = settings.DATABASE_URL
    assert url.startswith("sqlite"), "these checks edit the local test database directly"
    return url.split("///", 1)[1]


# ── Text cleanup and Act-name detection ─────────────────────────────────────

def test_ocr_table_markup_is_cleaned_and_cell_text_kept():
    raw = ("FIRST INFORMATION REPORT\n<table><tr><td>1. District</td><td>Guntur</td>"
           "<td>Police Station ACB, Guntur</td></tr><tr><td>Date 15.09.2020</td></tr></table>\n"
           "Quantity &lt; 5 kg &amp; 2 bottles; dose < 5 ml stays")
    out = clean_extracted_text(raw)
    assert "<td>" not in out and "<table>" not in out and "&amp;" not in out
    assert "1. District | Guntur | Police Station ACB, Guntur" in out
    assert "Date 15.09.2020" in out
    assert "Quantity < 5 kg & 2 bottles" in out
    assert "dose < 5 ml stays" in out
    assert strip_markup("plain text") == "plain text"


def test_fir_form_rows_are_not_mistaken_for_legacy_font_garbage():
    # FIR form rows have few English function words and contain slashes; they must survive cleanup
    rows = ("<table><tr><td>1. District</td><td>Guntur</td><td>Police Station ACB, Guntur</td><td>Year 2020</td>"
            "<td>FIR No DB/RC9-ACB-GNT/ 2020</td><td>Date 15.09.2020</td></tr></table>\n"
            "Accused Ramaiah S/o Venkaiah, Kurnool District, Andhra Pradesh State India\n"
            "7. Details of known / suspected / unknown accused with full particulars. [Attach separate sheet if necessary]")
    out = clean_extracted_text(rows)
    assert "[Attach separate sheet if necessary]" in out
    assert "FIR No DB/RC9-ACB-GNT/ 2020 | Date 15.09.2020" in out
    assert "1. District | Guntur" in out
    assert "Ramaiah S/o Venkaiah" in out
    # Legacy (Kruti Dev) Hindi lines are still dropped
    assert clean_extracted_text("vlk/kkj.k EXTRAORDINARY Hkkx II [k.M 1") == ""


def test_act_names_and_initials_are_recognised():
    bns = "The Bharatiya Nyaya Sanhita, 2023 (Act No. 45 of 2023)"
    bnss = "The Bharatiya Nagarik Suraksha Sanhita, 2023 (Act No. 46 of 2023)"
    q = "What is the punishment for theft under the Bharatiya Nyaya Sanhita?"
    assert title_named_in(q, bns) and not title_named_in(q, bnss)
    assert title_named_in("Which BNS section covers theft?", bns)
    assert not title_named_in("Which BNS section covers theft?", bnss)
    assert title_named_in("Under BNSS, when is bail granted?", bnss)
    assert title_named_in("What does Article 21 of the Constitution say?", "The Constitution of India [As on 1st May, 2024]")
    assert not title_named_in("What incident is described?", bns)
    assert query_terms("What is the punishment for theft?") == ["punishment", "theft"]


def test_embedding_failures_are_reported_with_their_cause():
    from app.services.embeddings import describe_embedding_error
    daily = Exception("429 RESOURCE_EXHAUSTED quotaId: EmbedContentRequestsPerDayPerProjectPerModel-FreeTier")
    assert "daily embedding quota exhausted for gemini-embedding-001" in describe_embedding_error(daily, "gemini-embedding-001")
    assert "rate limit" in describe_embedding_error(Exception("429 RESOURCE_EXHAUSTED PerMinute"))
    assert describe_embedding_error(ValueError("bad dims")).startswith("ValueError: bad dims")


def test_provision_numbers_not_in_sources_are_flagged():
    from app.services.rag_engine import unsupported_references
    sources = [{"section_ref": "Section 303", "chunk_text": "(2) Whoever commits theft shall be punished ..."},
               {"section_ref": None, "chunk_text": "under section 307 of the Sanhita"}]
    assert unsupported_references("Under Section 303(2) theft is punished [S1]; see Section 307 [S2].", sources) == []
    assert unsupported_references("Section 302(2) states the punishment [S1].", sources) == ["Section 302"]
    assert unsupported_references("Article 21 protects life [S1].", sources) == ["Article 21"]


# ── Retrieval ───────────────────────────────────────────────────────────────

def test_question_naming_an_act_is_answered_from_that_act(client, state_headers):
    token = _letters()
    alpha_title, beta_title = f"Synthetic Alpha Code {token}", f"Synthetic Beta Code {token}"
    alpha = make_pdf([[f"SYNTHETIC ALPHA CODE {token} (TEST DATA, NOT LAW)",
                       "1. Short title.- This Code may be called the Synthetic Alpha Code.",
                       f"2. Pilferage.- Whoever commits pilferage{token} shall be punished with imprisonment of",
                       "either description for a term which may extend to two years."]])
    # A second Act that cites the first one everywhere, the way BNSS cites BNS
    beta = make_pdf([[f"SYNTHETIC BETA CODE {token} (TEST DATA, NOT LAW)",
                      "1. Short title.- This Code may be called the Synthetic Beta Code.",
                      f"2. Trial.- Offences of pilferage{token} punishable under the Synthetic Alpha Code {token}",
                      f"are tried summarily; punishment under the Synthetic Alpha Code {token} applies.",
                      f"3. Appeal.- An appeal lies in pilferage{token} cases under the Synthetic Alpha Code {token}."]])
    ids = []
    try:
        for content, title in ((alpha, alpha_title), (beta, beta_title)):
            res = upload_kb(client, state_headers, content, f"{title.replace(' ', '_')}.pdf", title, category="LEGAL_ACT")
            assert res.status_code == 200, res.text
            ids.append(res.json()["id"])
        for doc_id in ids:
            assert wait_for_ingestion(client, state_headers, doc_id)["index_status"] == "INDEXED"

        rag = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": f"What is the punishment for pilferage{token} under the Synthetic Alpha Code {token}?",
            "scope": "KNOWLEDGE_BASE", "categories": ["LEGAL_ACT"], "language": "en"}).json()
        assert rag["retrieval"]["named_documents"] == 1, rag["retrieval"]
        assert rag["not_found"] is False, rag
        assert rag["citations"] and all(c["document_id"] == ids[0] for c in rag["citations"]), rag["citations"]
        assert any(c["section_ref"] == "Section 2" for c in rag["citations"])
    finally:
        for doc_id in ids:
            archive(client, state_headers, doc_id)


def test_words_found_only_in_a_document_title_still_find_it(client, state_headers):
    token = _letters()
    title = f"Synthetic Circular {token} - Border Checkpost Inspection Protocol"
    # The body never says "protocol" or the token; only the title does
    body = make_pdf([["PROHIBITION AND EXCISE DEPARTMENT - SYNTHETIC TEST CIRCULAR (NOT AN OFFICIAL RECORD)",
                      "1. Every commercial vehicle entering at the border must undergo manifest verification.",
                      "2. Suspected consignments must be impounded and reported within two hours."]])
    res = upload_kb(client, state_headers, body, f"circular_{token}.pdf", title, category="CIRCULAR")
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]
    try:
        wait_for_ingestion(client, state_headers, doc_id)
        rag = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": f"What does the {token} checkpost inspection protocol require?",
            "scope": "KNOWLEDGE_BASE", "categories": ["CIRCULAR"], "language": "en"}).json()
        assert rag["retrieval"]["title_hits"] >= 1, rag["retrieval"]
        assert rag["not_found"] is False, rag
        assert any(c["document_id"] == doc_id for c in rag["citations"]), rag["citations"]
    finally:
        archive(client, state_headers, doc_id)


def test_title_match_keeps_a_slot_when_vector_and_keyword_hits_fill_the_results(client, state_headers, monkeypatch):
    from app.services import embeddings as embeddings_module
    from tests.test_knowledge_base_rag import _fake_vector
    svc = embeddings_module.embedding_service
    monkeypatch.setattr(svc, "is_available", lambda: True)
    monkeypatch.setattr(svc, "embed_documents", lambda texts: [_fake_vector(t) for t in texts])
    monkeypatch.setattr(svc, "embed_query", lambda t: _fake_vector(t))
    monkeypatch.setattr(svc, "model", "fake-test-embedding")

    token = _letters()
    title = f"Synthetic Circular {token} - Border Checkpost Inspection Protocol"
    # The body shares no words with the question; only the title does
    circular = make_pdf([["PROHIBITION AND EXCISE DEPARTMENT - SYNTHETIC TEST NOTICE (NOT AN OFFICIAL RECORD)",
                          "1. Every commercial vehicle entering at the border must undergo manifest verification.",
                          "2. Suspected consignments must be impounded and reported within two hours."]])
    # A long reference text whose passages match the question's words and meaning far better than the
    # circular's body does, enough to fill every result slot on keyword and vector rank
    filler = "The officer keeps the register of every vehicle stopped and every document produced. " * 14
    decoy_pages = [[f"SYNTHETIC PROCEDURE CODE {token} (TEST DATA, NOT LAW)",
                    f"{p}. What does the checkpost inspection require? The checkpost inspection requires what "
                    f"the inspection officer requires at the checkpost {token}.", filler]
                   for p in range(1, 13)]
    ids = []
    try:
        for content, name, t, cat in ((circular, f"circular_{token}.pdf", title, "CIRCULAR"),
                                      (make_pdf(decoy_pages), f"decoy_{token}.pdf", f"Synthetic Procedure Code {token}", "LEGAL_ACT")):
            res = upload_kb(client, state_headers, content, name, t, category=cat)
            assert res.status_code == 200, res.text
            ids.append(res.json()["id"])
            wait_for_ingestion(client, state_headers, ids[-1])
        rag = client.post("/api/v1/rag/query", headers=state_headers, json={
            "query": f"What does the {token} checkpost inspection circular require?",
            "scope": "KNOWLEDGE_BASE", "categories": ["CIRCULAR", "LEGAL_ACT"], "language": "en"}).json()
        assert rag["retrieval"]["vector_hits"] > 0 and rag["retrieval"]["title_hits"] >= 1, rag["retrieval"]
        assert any(c["document_id"] == ids[0] for c in rag["citations"]), rag["citations"]
    finally:
        for doc_id in ids:
            archive(client, state_headers, doc_id)


def test_current_fir_reads_short_record_in_full(client, station_headers):
    doc = get_demo_fir_document(client, station_headers)
    res = client.post("/api/v1/rag/query", headers=station_headers, json={
        "query": "Summarise this record", "scope": "CURRENT_FIR", "document_id": doc["id"], "language": "en"})
    assert res.status_code == 200, res.text
    body = res.json()
    # Every passage of the selected FIR reaches the answer step even though the question shares no
    # words with it; nothing from other documents is added
    assert body["retrieval"]["whole_record_passages"] >= 1, body["retrieval"]
    assert body["retrieval"]["outcome"] != "NO_MATCHING_PASSAGES"
    assert all(c["document_id"] == doc["id"] for c in body.get("citations", []))


# ── Embedding backfill ──────────────────────────────────────────────────────

def test_backfill_skips_rejected_passages_and_stops_cleanly_on_daily_quota(client, state_headers, monkeypatch):
    import argparse
    import asyncio
    from app.services import embeddings as embeddings_module
    from scripts import backfill_embeddings
    from tests.test_knowledge_base_rag import _fake_vector

    token = _letters()
    filler = "The inspecting officer records every seized article in the inventory before the panch witnesses. " * 12
    pdf = make_pdf([[f"Synthetic backfill guide {token} page one.", filler],
                    [f"Synthetic backfill guide {token} rejectpage{token}.", filler],
                    [f"Synthetic backfill guide {token} page three.", filler]])
    res = upload_kb(client, state_headers, pdf, f"backfill_{token}.pdf", f"Backfill test {token}", category="INVESTIGATION_GUIDE")
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]
    con = sqlite3.connect(_sqlite_path())
    try:
        wait_for_ingestion(client, state_headers, doc_id)
        con.execute("UPDATE document_chunks SET embedding_json=NULL WHERE document_id=?", (doc_id,))
        con.execute("UPDATE documents SET embedding_model=NULL WHERE id=?", (doc_id,))
        con.commit()
        args = argparse.Namespace(max_chunks=0, batch_size=50, document_id=doc_id, official_first=False)
        svc = embeddings_module.embedding_service
        monkeypatch.setattr(svc, "is_available", lambda: True)
        monkeypatch.setattr(svc, "model", "fake-test-embedding")

        # The provider's daily limit is reached: nothing is written and nothing is marked embedded
        def quota(texts, task_type):
            if texts != ["model check"]:
                raise Exception("429 RESOURCE_EXHAUSTED EmbedContentRequestsPerDayPerProjectPerModel-FreeTier")
            return [_fake_vector("model check")]
        monkeypatch.setattr(svc, "_embed", quota)
        asyncio.run(backfill_embeddings.run(args))
        assert con.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id=? AND embedding_json IS NOT NULL",
                           (doc_id,)).fetchone()[0] == 0

        # One passage is rejected: the others are embedded, the rejected one stays without a vector
        def reject(texts, task_type):
            if any(f"rejectpage{token}" in t for t in texts):
                raise ValueError("input rejected")
            return [_fake_vector(t) for t in texts]
        monkeypatch.setattr(svc, "_embed", reject)
        asyncio.run(backfill_embeddings.run(args))
        rows = con.execute("SELECT chunk_text, embedding_json FROM document_chunks WHERE document_id=?", (doc_id,)).fetchall()
        assert any(f"rejectpage{token}" in t and e is None for t, e in rows)
        assert all(e is not None for t, e in rows if f"rejectpage{token}" not in t)
        status, count = con.execute("SELECT index_status, embedded_chunk_count FROM documents WHERE id=?", (doc_id,)).fetchone()
        assert count == sum(e is not None for _, e in rows)
        assert count == len(rows) - 1 and status == "PARTIALLY_INDEXED"
    finally:
        con.close()
        archive(client, state_headers, doc_id)


# ── Evidence viewer ─────────────────────────────────────────────────────────

def test_viewer_finds_original_with_stale_path_and_reports_missing_file(client, state_headers):
    token = _letters()
    pdf = make_pdf([[f"Synthetic viewer test document {token}."]])
    res = upload_kb(client, state_headers, pdf, f"viewer_{token}.pdf", f"Viewer test {token}", category="REFERENCE")
    assert res.status_code == 200, res.text
    doc_id = res.json()["id"]
    try:
        wait_for_ingestion(client, state_headers, doc_id)
        con = sqlite3.connect(_sqlite_path())
        try:
            # A record pointing at a deleted temporary copy still opens: the stored original is found
            con.execute("UPDATE documents SET stored_path=? WHERE id=?",
                        (os.path.join(settings.EVIDENCE_DIR, "cloud_cache", f"gone_{token}.pdf"), doc_id))
            con.commit()
            ok = client.get(f"/api/v1/documents/{doc_id}/view", headers=state_headers)
            assert ok.status_code == 200 and ok.content.startswith(b"%PDF")
            assert ok.headers["content-type"].startswith("application/pdf")

            # With no original anywhere, the viewer gets a specific code and the text stays available
            con.execute("UPDATE documents SET file_hash=? WHERE id=?", (uuid.uuid4().hex * 2, doc_id))
            con.commit()
            missing = client.get(f"/api/v1/documents/{doc_id}/view", headers=state_headers)
            assert missing.status_code == 404
            assert missing.json()["detail"]["code"] == "ORIGINAL_FILE_MISSING"
            pages = client.get(f"/api/v1/documents/{doc_id}/pages", headers=state_headers)
            assert pages.status_code == 200 and token in str(pages.json())
        finally:
            con.close()
    finally:
        archive(client, state_headers, doc_id)


def test_viewer_requires_authorisation(client, station_headers):
    res = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000/view", headers=station_headers)
    assert res.status_code == 404
    assert client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000/view").status_code == 401
