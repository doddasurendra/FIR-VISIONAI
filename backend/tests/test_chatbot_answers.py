"""
Chatbot answers without the AI (the test environment has no AI key): exact identifier matching,
answers from structured case records with cited FIR quotes, jurisdiction on every query, counts by
station, and the backup model / retry behaviour of the AI client.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.config import settings
from app.database import SyncSessionLocal
from app.models.case import Case
from app.services import rag_engine
from app.services.fact_answers import detect_intents
from app.services.gemini import GeminiService
from app.services.retrieval import id_tokens
from tests.test_backend import get_demo_fir_document
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401

ASK = "/api/v1/rag/query"
Q1 = "What items were seized and in what quantity, and which vehicle was used?"
Q2 = "Which cases involve the vehicle AP21TY4567 and who are the accused persons?"


@pytest.fixture(autouse=True)
def fresh_answer_cache():
    rag_engine.invalidate_cache()
    yield
    rag_engine.invalidate_cache()


# ── Identifiers ──────────────────────────────────────────────────────────────

def test_identifiers_are_normalised_so_spacing_and_case_do_not_matter():
    norms = lambda q: [t["norm"] for t in id_tokens(q)]  # noqa: E731
    assert norms("vehicle AP 21 TY 4567") == norms("vehicle ap-21-ty-4567") == norms("AP21TY4567") == ["AP21TY4567"]
    assert id_tokens("FIR-2024-KNL-0042")[0] == {"kind": "FIR", "raw": "FIR-2024-KNL-0042", "norm": "FIR2024KNL0042"}
    assert [t["kind"] for t in id_tokens("case 89/2024")] == ["FIR"]
    assert id_tokens("call +91 98480 12345")[0]["norm"] == "9848012345"
    # A FIR number is not also read as a vehicle number, and ordinary words are not identifiers
    assert [t["kind"] for t in id_tokens("FIR-2024-KNL-0042")] == ["FIR"]
    assert id_tokens("What items were seized?") == []


def test_question_parts_are_recognised():
    assert detect_intents(Q1) == ["seized", "vehicle"]
    assert "accused" in detect_intents("Who are the accused persons?")
    assert "district" in detect_intents("జిల్లా ఏది?")


# ── The two reported questions, AI disabled ──────────────────────────────────

def test_selected_fir_seizure_and_vehicle_question_is_answered_from_records_with_page_quotes(client, station_headers):
    fir = get_demo_fir_document(client, station_headers)
    body = client.post(ASK, headers=station_headers,
                       json={"query": Q1, "scope": "CURRENT_FIR", "document_id": fir["id"]}).json()
    assert body["answer_method"] == "CASE_RECORDS_AND_QUOTES" and body["not_found"] is False
    assert "AI summary unavailable" in body["answer"]
    assert "45 Litres" in body["answer"] and "AP21TY4567" in body["answer"]
    quotes = " ".join(c["evidence_excerpt"] for c in body["citations"])
    assert "45.0 Litres" in quotes and "AP21TY4567" in quotes
    assert {c["physical_page_number"] for c in body["citations"]} == {2}
    assert all(c["document_id"] == fir["id"] for c in body["citations"])


@pytest.mark.parametrize("question", [Q2, "Which cases involve vehicle ap 21 ty 4567?"])
def test_vehicle_question_across_all_authorised_lists_cases_and_accused(client, station_headers, question):
    body = client.post(ASK, headers=station_headers, json={"query": question, "scope": "ALL_AUTHORIZED"}).json()
    assert body["answer_method"] == "CASE_RECORDS_AND_QUOTES" and body["not_found"] is False
    cases = {c["fir_number"]: c for c in body["matched_cases"]}
    assert set(cases["FIR-2024-KNL-0042"]["accused"]) == {"Ramu Naidu", "Someshwar Rao"}
    assert "Ramu Naidu" in body["answer"] and "FIR-2024-KNL-0042" in body["answer"]
    assert any("AP21TY4567" in c["evidence_excerpt"] and c["physical_page_number"] == 2 for c in body["citations"])


def test_identifier_answers_say_ai_unavailable_only_when_it_is(client, station_headers, monkeypatch):
    from app.services.gemini import gemini_service
    rag_engine._CACHE.clear()
    monkeypatch.setattr(gemini_service, "ai_ready", lambda: False)
    off = client.post(ASK, headers=station_headers, json={"query": Q2, "scope": "ALL_AUTHORIZED"}).json()
    assert "AI summary unavailable" in off["answer"]
    rag_engine._CACHE.clear()
    monkeypatch.setattr(gemini_service, "ai_ready", lambda: True)
    on = client.post(ASK, headers=station_headers, json={"query": Q2, "scope": "ALL_AUTHORIZED"}).json()
    assert "AI summary unavailable" not in on["answer"] and "by exact match" in on["answer"]
    rag_engine._CACHE.clear()


def test_quotes_do_not_start_with_the_tail_of_a_cut_word():
    excerpt = rag_engine.best_excerpt("ermit. Contraband Seized: 40 Litres ID Arrack. Vehicle: Auto AP21TY4567.", ["vehicle"])
    assert excerpt.startswith("…Contraband Seized") and "ermit" not in excerpt
    assert rag_engine.best_excerpt("Crime No: 89/2024. Vehicle seized.", ["vehicle"]).startswith("Crime No")


@pytest.fixture
def other_station_case_with_same_vehicle():
    """A Guntur case using the same vehicle (test database only); removed afterwards."""
    db = SyncSessionLocal()
    fir = f"TEST-GNT-{uuid.uuid4().hex[:6]}"
    case = Case(fir_number=fir, year=2024, district="Guntur", station="Tenali Station", offence_nature="Transport of ID liquor",
                vehicle_details="Auto AP 21 TY 4567", status="DRAFT", created_by="test", registration_date=datetime(2024, 9, 1))
    db.add(case)
    db.commit()
    yield fir
    db.delete(db.get(Case, case.id))
    db.commit()
    db.close()


def test_station_officer_never_sees_another_stations_case(client, station_headers, state_headers,
                                                          other_station_case_with_same_vehicle):
    fir = other_station_case_with_same_vehicle
    station = client.post(ASK, headers=station_headers, json={"query": Q2, "scope": "ALL_AUTHORIZED"}).json()
    assert fir not in station["answer"] and fir not in {c["fir_number"] for c in station["matched_cases"]}
    assert all(c["station"] == "Kurnool Town Station" for c in station["matched_cases"])
    rag_engine.invalidate_cache()
    state = client.post(ASK, headers=state_headers, json={"query": Q2, "scope": "ALL_AUTHORIZED"}).json()
    assert fir in {c["fir_number"] for c in state["matched_cases"]}


def test_counts_by_station_stay_within_jurisdiction(client, station_headers, state_headers):
    q = {"query": "How many cases are there by station?", "scope": "ALL_AUTHORIZED"}
    station = client.post(ASK, headers=station_headers, json=q).json()
    assert station["answer_method"] == "DATABASE_COUNT"
    assert {b["station"] for b in station["breakdown"]} == {"Kurnool Town Station"}
    state = client.post(ASK, headers=state_headers, json=q).json()
    assert len(state["breakdown"]) > 1 and state["count"] >= station["count"]


# ── Backup model and retry ───────────────────────────────────────────────────

SOURCES = [{"chunk_text": "District: Kurnool", "document_title": "FIR", "physical_page_number": 1}]


class _Models:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content(self, model, contents, config=None):
        self.calls.append(model)
        return self.behaviour(model, len(self.calls))


def test_backup_model_answers_when_the_main_model_is_out_of_quota(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_BACKUP_MODEL", "backup-model-x")

    def behaviour(model, n):
        if model == settings.GEMINI_TEXT_MODEL:
            raise Exception("429 RESOURCE_EXHAUSTED. {'retryDelay': '3600s'}")
        return SimpleNamespace(text="Kurnool [S1].")
    svc = GeminiService()
    svc.client = SimpleNamespace(models=_Models(behaviour))
    result = svc.answer_from_sources("district?", SOURCES)
    assert result["status"] == "ANSWERED" and result["model"] == "backup:backup-model-x"
    assert svc.client.models.calls == [settings.GEMINI_TEXT_MODEL, "backup-model-x"]


def test_backup_model_uses_its_own_key_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_BACKUP_MODEL", "backup-model-x")
    svc = GeminiService()
    primary = SimpleNamespace(models=_Models(lambda m, n: (_ for _ in ()).throw(Exception("429 RESOURCE_EXHAUSTED"))))
    backup = SimpleNamespace(models=_Models(lambda m, n: SimpleNamespace(text="Kurnool [S1].")))
    svc.client, svc.backup_client = primary, backup
    assert svc.answer_from_sources("district?", SOURCES)["status"] == "ANSWERED"
    assert backup.models.calls == ["backup-model-x"] and settings.GEMINI_TEXT_MODEL in primary.models.calls


def test_an_overloaded_model_is_retried_after_a_short_backoff():
    def behaviour(model, n):
        if n == 1:
            raise Exception("503 UNAVAILABLE. The model is overloaded.")
        return SimpleNamespace(text="Kurnool [S1].")
    svc = GeminiService()
    svc.client = SimpleNamespace(models=_Models(behaviour))
    result = svc.answer_from_sources("district?", SOURCES, timeout_s=8.0)
    assert result["status"] == "ANSWERED"
    assert result["attempts"] == [settings.GEMINI_TEXT_MODEL, settings.GEMINI_TEXT_MODEL]
