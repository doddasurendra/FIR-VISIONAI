"""
AI FIR Assistant (chatbot) reliability.

- The selected FIR is read in full (no redundant search) and answers cite its document and page.
- A missing answer is reported as missing, in the question's language.
- AI provider timeouts, quota exhaustion and malformed or uncited replies give honest answers within
  the time budget, never a 500 and never a guess; degraded answers are not cached.
- A dropped database connection (error reference 0127eb95) is retried once for the audit write and
  otherwise reported as 503 with a reference - not as an opaque 500.
- Bad requests and other jurisdictions' documents are refused on the server.
- Slow AI calls do not block other requests.
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.api.v1 import rag as rag_api
from app.services import audit as audit_module
from app.services import rag_engine
from app.services.gemini import GeminiService, gemini_service
from app.services.retrieval import embedding_service
from tests.test_backend import get_demo_fir_document
from tests.test_knowledge_base_rag import (  # noqa: F401
    archive, make_pdf, station_headers, state_headers, upload_kb, wait_for_ingestion,
)

ASK = "/api/v1/rag/query"


@pytest.fixture(autouse=True)
def fresh_answer_cache():
    rag_engine.invalidate_cache()
    yield
    rag_engine.invalidate_cache()


def ask(client, headers, query, **body):
    return client.post(ASK, headers=headers, json={"query": query, **body})


def model_citing(marker, calls=None):
    """Fake model: answers from the first passage containing marker (citing it), else NOT_FOUND."""
    def fake(query, sources, language="en", legal_mode=False, timeout_s=30.0):
        if calls is not None:
            calls.append({"sources": sources, "language": language, "timeout_s": timeout_s})
        for i, s in enumerate(sources, start=1):
            if marker.lower() in (s.get("chunk_text") or "").lower():
                return {"status": "ANSWERED", "text": f"Answer from the record [S{i}].", "used": [i], "model": "fake"}
        return {"status": "NOT_FOUND", "text": "", "used": [], "model": "fake"}
    return fake


async def no_search(*args, **kwargs):
    raise AssertionError("the selected FIR is read in full; it must not be searched again")


# ── Answers from the selected FIR ────────────────────────────────────────────

def test_selected_fir_is_read_in_full_and_cited_by_page(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    calls = []
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("Total Quantity Seized", calls))
    monkeypatch.setattr(rag_engine, "hybrid_search", no_search)

    res = ask(client, station_headers, "What quantity was seized?", scope="CURRENT_FIR", document_id=fir["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["not_found"] is False and body["answer_method"] == "GENERATED_FROM_SOURCES"
    cite = body["citations"][0]
    assert cite["document_id"] == fir["id"] and cite["physical_page_number"] == 2
    assert "45.0 Litres" in cite["evidence_excerpt"]
    # Every page of the selected FIR, and nothing else, reached the model
    sources = calls[0]["sources"]
    assert {s["document_id"] for s in sources} == {fir["id"]}
    assert {s["physical_page_number"] for s in sources} == {1, 2, 3}
    assert body["retrieval"]["search"] == "SKIPPED_WHOLE_SCOPE_READ"
    # Traceable: the response names the log line and how long each stage took
    assert len(body["trace_id"]) == 8 and body["timings"]["total_ms"] >= 0
    assert body["generation"]["status"] == "ANSWERED"


def test_answer_absent_from_the_fir_is_reported_as_missing(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("no-such-text-in-this-fir"))
    body = ask(client, station_headers, "What is the accused person's bank account number?",
               scope="CURRENT_FIR", document_id=fir["id"]).json()
    assert body["not_found"] is True and body["citations"] == []
    assert body["answer"] == rag_engine.NOT_FOUND["en"]
    assert body["retrieval"]["outcome"] == "MODEL_FOUND_INSUFFICIENT_SUPPORT"
    assert body["can_expand_scope"] is True


@pytest.mark.parametrize("language,question", [
    ("en", "Which district is this?"),
    ("te", "జిల్లా ఏది?"),
    ("hi", "ज़िला कौन सा है?"),
])
def test_question_language_reaches_the_model_and_the_reply(client, station_headers, monkeypatch, language, question):
    fir = get_demo_fir_document(client, station_headers)
    calls = []
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("no-such-text", calls))
    # The whole record is in hand, so a Telugu/Hindi question needs no translation for searching
    monkeypatch.setattr(gemini_service, "translate_for_search",
                        lambda *a, **k: pytest.fail("translation is not needed for the selected FIR"))
    body = ask(client, station_headers, question, scope="CURRENT_FIR", document_id=fir["id"],
               language=language).json()
    assert calls[0]["language"] == language
    assert body["answer"] == rag_engine.NOT_FOUND[language]


# ── Request validation and permissions ───────────────────────────────────────

def test_invalid_requests_are_refused_with_a_reason(client, station_headers):
    fir = get_demo_fir_document(client, station_headers)
    assert ask(client, station_headers, "district?", scope="CURRENT_FIR").status_code == 400          # no FIR chosen
    assert ask(client, station_headers, "district?", scope="CURRENT_FIR",
               document_id=str(uuid.uuid4())).status_code == 404                                       # unknown FIR
    assert ask(client, station_headers, "   ", scope="CURRENT_FIR", document_id=fir["id"]).status_code == 400
    too_long = ask(client, station_headers, "x" * (rag_engine.MAX_QUESTION_CHARS + 1),
                   scope="CURRENT_FIR", document_id=fir["id"])
    assert too_long.status_code == 400 and "too long" in too_long.json()["detail"]
    assert ask(client, station_headers, "district?", scope="EVERYTHING").status_code == 400


def test_another_jurisdictions_fir_cannot_be_questioned(client, state_headers, station_headers, monkeypatch):
    monkeypatch.setattr(gemini_service, "answer_from_sources",
                        lambda *a, **k: pytest.fail("no passage of another jurisdiction may reach the model"))
    token = uuid.uuid4().hex[:8]
    pdf = make_pdf([[f"Guntur record {token}.", "District: Guntur. Tenali Station."]])
    res = upload_kb(client, state_headers, pdf, f"guntur_chat_{token}.pdf", f"Guntur record {token}",
                    category="EVIDENCE", district="Guntur", station="Tenali Station", record_kind="SYNTHETIC")
    doc_id = res.json()["id"]
    try:
        wait_for_ingestion(client, state_headers, doc_id)
        for scope in ("CURRENT_FIR", "CASE", "FIR_AND_LAW"):
            r = ask(client, station_headers, "Which district?", scope=scope, document_id=doc_id)
            assert r.status_code == 403, (scope, r.status_code)
    finally:
        archive(client, state_headers, doc_id)


# ── AI provider failures ─────────────────────────────────────────────────────

def test_slow_ai_gives_quoted_passages_within_the_budget_and_is_not_cached(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(rag_engine, "ANSWER_BUDGET_S", 1.0)
    monkeypatch.setattr(rag_engine, "MIN_GENERATION_S", 0.5)

    def slow(*a, **k):
        time.sleep(3)
        return {"status": "ANSWERED", "text": "late [S1].", "used": [1], "model": "fake"}
    monkeypatch.setattr(gemini_service, "answer_from_sources", slow)
    started = time.perf_counter()
    body = ask(client, station_headers, "Which district?", scope="CURRENT_FIR", document_id=fir["id"]).json()
    assert time.perf_counter() - started < 2.5
    # Answered without the model: from the case record or plain quotes, always cited
    assert body["answer_method"] in ("CASE_RECORDS_AND_QUOTES", "EXTRACTIVE_QUOTES") and body["not_found"] is False
    assert body["generation"]["reason"] == "PROVIDER_TIMEOUT" and body["can_retry"] is True
    assert all(c["document_id"] == fir["id"] for c in body["citations"])
    assert any("district" in c["evidence_excerpt"].lower() for c in body["citations"])

    # Not cached: once the AI answers again, the same question gets a generated answer
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("Kurnool"))
    again = ask(client, station_headers, "Which district?", scope="CURRENT_FIR", document_id=fir["id"]).json()
    assert again["answer_method"] == "GENERATED_FROM_SOURCES" and not again.get("from_cache")


def test_quota_exhausted_and_no_matching_passage_says_so_instead_of_not_found(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources",
                        lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": [], "reason": "QUOTA_EXHAUSTED"})
    body = ask(client, station_headers, "Who wrote the remarks?", scope="CURRENT_FIR", document_id=fir["id"]).json()
    assert body["not_found"] is True and body["can_retry"] is True
    assert body["retrieval"]["outcome"] == "AI_UNAVAILABLE_NO_MATCHING_PASSAGE"
    assert "quota" in body["answer"] and "Nothing was guessed" in body["answer"]


def test_fir_form_wording_is_matched_when_the_ai_is_unavailable(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources",
                        lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": [], "reason": "PROVIDER_TIMEOUT"})
    # The form says "Date of Offence", not "incident date"
    body = ask(client, station_headers, "What is the incident date?", scope="CURRENT_FIR", document_id=fir["id"]).json()
    assert body["answer_method"] in ("CASE_RECORDS_AND_QUOTES", "EXTRACTIVE_QUOTES"), body
    assert any("14th August 2024" in c["evidence_excerpt"] for c in body["citations"])


def test_quotes_that_miss_the_questions_subject_are_not_offered_as_an_answer(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources",
                        lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": [], "reason": "PROVIDER_TIMEOUT"})
    # The FIR describes the accused but records no bank account: quoting the accused's particulars
    # would look like an answer while not being one
    body = ask(client, station_headers, "What is the accused person's bank account number?",
               scope="CURRENT_FIR", document_id=fir["id"]).json()
    assert body["not_found"] is True and body["citations"] == []
    assert body["retrieval"]["outcome"] == "AI_UNAVAILABLE_NO_MATCHING_PASSAGE"


class _FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "timeout_ms": config.http_options.timeout if config else None})
        return self.behaviour(model)


def _service(behaviour):
    svc = GeminiService()
    svc.client = SimpleNamespace(models=_FakeModels(behaviour))
    return svc


SOURCES = [{"chunk_text": "District: Kurnool", "document_title": "FIR", "physical_page_number": 1}]


def test_uncited_or_malformed_model_replies_are_never_returned_as_answers():
    uncited = _service(lambda m: SimpleNamespace(text="The district is Kurnool."))
    assert uncited.answer_from_sources("district?", SOURCES)["status"] == "NOT_FOUND"

    def broken(model):
        class Blocked:
            @property
            def text(self):
                raise ValueError("response blocked / no candidates")
        return Blocked()
    svc = _service(broken)
    result = svc.answer_from_sources("district?", SOURCES)
    assert result["status"] == "UNAVAILABLE" and result["reason"] == "PROVIDER_ERROR"
    assert len(svc.client.models.calls) >= 2  # the next model was tried


def test_model_deadline_respects_the_providers_10_second_minimum():
    svc = _service(lambda m: SimpleNamespace(text="Kurnool [S1]."))
    svc.answer_from_sources("district?", SOURCES, timeout_s=4.0)
    # "Minimum allowed deadline is 10s": shorter budgets are enforced by the caller, not sent to the API
    assert svc.client.models.calls[0]["timeout_ms"] == 10000


def test_daily_quota_cools_the_model_until_reset_and_then_fails_fast():
    def exhausted(model):
        raise Exception("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'details': [{'quotaId': "
                        "'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}, {'retryDelay': '51482s'}]}}")
    svc = _service(exhausted)
    first = svc.answer_from_sources("district?", SOURCES, timeout_s=8.0)
    assert first["status"] == "UNAVAILABLE" and first["reason"] == "QUOTA_EXHAUSTED"
    remaining = max(svc._cooldown_until.values()) - time.time()
    assert 51000 < remaining <= 51482
    calls_before = len(svc.client.models.calls)
    started = time.perf_counter()
    second = svc.answer_from_sources("district?", SOURCES, timeout_s=8.0)
    assert second["reason"] == "QUOTA_EXHAUSTED" and time.perf_counter() - started < 0.1
    assert len(svc.client.models.calls) == calls_before  # no call that cannot succeed


def test_the_configured_models_quota_is_reported_rather_than_a_slow_fallback():
    def primary_out_of_quota_fallback_slow(model):
        if model == svc._primary:
            raise Exception("429 RESOURCE_EXHAUSTED. {'retryDelay': '3600s'}")
        raise Exception("504 DEADLINE_EXCEEDED")
    svc = _service(primary_out_of_quota_fallback_slow)
    from app.config import settings
    svc._primary = settings.GEMINI_TEXT_MODEL
    assert svc.answer_from_sources("district?", SOURCES)["reason"] == "QUOTA_EXHAUSTED"
    # Everything is cooling now: the fast path reports the same actionable reason
    assert svc.answer_from_sources("district?", SOURCES)["reason"] == "QUOTA_EXHAUSTED"


def test_excerpt_shows_the_value_next_to_its_form_label():
    record = ("District : Prakasam Police Station : Ongole PS FIR No : 89/2024 Date : 16.08.2024 "
              "2. (i) Act, the Prevention of Corruption Act, 1988 : Nil (ii) Act, Indian Penal Code : Sections 379, 411 IPC. "
              "(iii) Other Acts & Sections : Section 102 of the Motor Vehicles Act, 1988. "
              "3. (a) Occurrence of Offence: Day : 14.08.2024 (Wednesday) Time Period : Between 21.00 hrs and 22.00 hrs "
              "(b) Information received at the Police Station : Date : 16.08.2024 Time : 09.30 hours")
    assert "14.08.2024" in rag_engine.best_excerpt(record, ["incident", "date"])


def test_a_timed_out_model_is_skipped_briefly():
    def times_out(model):
        raise Exception("The read operation timed out")
    svc = _service(times_out)
    assert svc.answer_from_sources("district?", SOURCES)["reason"] == "PROVIDER_TIMEOUT"
    assert all(0 < t - time.time() <= 120 for t in svc._cooldown_until.values())


def test_missing_question_embedding_still_finds_passages(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(embedding_service, "embed_query", lambda text: None)  # provider down / no embeddings
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("Total Quantity Seized"))
    body = ask(client, station_headers, "What quantity of contraband was seized?", scope="ALL_AUTHORIZED").json()
    assert body["not_found"] is False and body["retrieval"]["semantic_search"] is False
    assert any(c["document_id"] == fir["id"] and c["physical_page_number"] == 2 for c in body["citations"])


# ── Database connection failures (error reference 0127eb95) ──────────────────

def _connection_lost():
    return OperationalError("SELECT audit_log.id FROM audit_log", {},
                            Exception("connection was closed in the middle of operation"))


def test_audit_write_on_a_dropped_connection_is_retried_once(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("Kurnool"))
    real, attempts = audit_module.log_audit_event, []

    async def flaky(db, **event):
        attempts.append(1)
        if len(attempts) == 1:
            raise _connection_lost()
        return await real(db, **event)
    monkeypatch.setattr(audit_module, "log_audit_event", flaky)
    res = ask(client, station_headers, "Which district?", scope="CURRENT_FIR", document_id=fir["id"])
    assert res.status_code == 200, res.text
    assert len(attempts) == 2


def test_audit_write_that_keeps_failing_is_a_503_with_a_reference(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("Kurnool"))

    async def always_lost(db, **event):
        raise _connection_lost()
    monkeypatch.setattr(audit_module, "log_audit_event", always_lost)
    res = ask(client, station_headers, "Which district?", scope="CURRENT_FIR", document_id=fir["id"])
    assert res.status_code == 503
    assert "reference" in res.json()["detail"] and "audit" in res.json()["detail"]


def test_database_unreachable_during_retrieval_is_a_503_not_a_500(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)

    async def unreachable(*a, **k):
        raise OperationalError("SELECT 1", {}, OSError("[Errno 11001] getaddrinfo failed"))
    monkeypatch.setattr(rag_api, "answer", unreachable)
    res = ask(client, station_headers, "Which district?", scope="CURRENT_FIR", document_id=fir["id"])
    assert res.status_code == 503 and "could not be reached" in res.json()["detail"]


def test_any_endpoint_losing_the_database_answers_503_database_unavailable(client):
    from app.main import app

    async def boom():
        raise OperationalError("SELECT 1", {}, OSError("[Errno 11001] getaddrinfo failed"))
    app.add_api_route("/api/v1/__test_db_down", boom)
    try:
        res = client.get("/api/v1/__test_db_down")
        assert res.status_code == 503
        assert res.json()["code"] == "DATABASE_UNAVAILABLE" and res.json()["reference"]
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/api/v1/__test_db_down"]


# ── Concurrency and monitoring ───────────────────────────────────────────────

def test_slow_ai_calls_do_not_block_other_questions(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)

    def one_second(query, sources, **k):
        time.sleep(1.0)
        return {"status": "ANSWERED", "text": "Kurnool [S1].", "used": [1], "model": "fake"}
    monkeypatch.setattr(gemini_service, "answer_from_sources", one_second)
    questions = [f"Which district is recorded ({i})?" for i in range(4)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda q: ask(client, station_headers, q, scope="CURRENT_FIR",
                                              document_id=fir["id"]), questions))
    elapsed = time.perf_counter() - started
    assert all(r.status_code == 200 for r in results)
    # Four 1-second model calls side by side; a blocked event loop would take 4 s or more
    assert elapsed < 3.0, elapsed


def test_readiness_reports_recent_chat_latency(client, station_headers, monkeypatch):
    fir = get_demo_fir_document(client, station_headers)
    monkeypatch.setattr(gemini_service, "answer_from_sources", model_citing("Kurnool"))
    ask(client, station_headers, "Which district?", scope="CURRENT_FIR", document_id=fir["id"])
    chat = client.get("/api/v1/health/ready").json()["chat"]
    assert chat["recent"]["requests"] >= 1 and chat["recent"]["p95_ms"] >= 0
    assert "models_in_cooldown_s" in chat
