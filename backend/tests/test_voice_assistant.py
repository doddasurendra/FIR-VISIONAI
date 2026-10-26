"""
Voice assistant: intent routing in English, Telugu and Hindi, live data under jurisdiction,
guide-grounded help, refusal of record actions, speech text, and metadata-only audit.
"""
import sqlite3
import uuid

import pytest

from app.config import settings
from app.services import voice_assistant as va
from app.services.gemini import gemini_service
from tests.test_knowledge_base_rag import station_headers, state_headers  # noqa: F401


def _ask(client, headers, question, language="auto", history=None):
    res = client.post("/api/v1/assistant/query", headers=headers,
                      json={"question": question, "language": language, "history": history or [], "input_mode": "voice"})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.parametrize("question,intent", [
    ("How many pending drafts do I have?", "LIVE_COUNTS"),
    ("ఎన్ని కేసులు సమీక్షలో ఉన్నాయి?", "LIVE_COUNTS"),
    ("कितने स्वीकृत एफआईआर हैं?", "LIVE_COUNTS"),
    ("What is the workflow status of FIR 178/2024?", "WORKFLOW_STATUS"),
    ("What is the status of FIR 08/RCO-ACB-GNT/2020?", "FIR_STATUS"),
    ("What is the punishment for theft under the BNS?", "LEGAL"),
    ("How do I register a new FIR?", "APP_HELP"),
    ("డాష్‌బోర్డ్‌లో Quick Access ఎలా ఉపయోగించాలి?", "APP_HELP"),
    ("नॉलेज बेस में दस्तावेज़ कैसे खोजें?", "APP_HELP"),
    ("Approve this case now", "ACTION_REQUEST"),
    ("How many historical FIRs are summarised?", "SUMMARY_COVERAGE"),
])
def test_intents_in_three_languages(question, intent):
    assert va.classify(question) == intent


def test_language_detection_and_speech_text():
    assert va.detect_language("ఎఫ్‌ఐఆర్ స్థితి") == "te"
    assert va.detect_language("एफआईआर की स्थिति") == "hi"
    assert va.detect_language("FIR status") == "en"
    spoken = va.speech_text("Open Case Management [G1]. Case 3388b4f3-d2d9-48e8-94fc-2668dc126514 is {\"x\": 1} ready [S2].")
    assert "[G1]" not in spoken and "3388b4f3" not in spoken and "{" not in spoken


def test_live_counts_match_the_dashboard_for_the_officer(client, station_headers):
    kpis = client.get("/api/v1/analytics/dashboard", headers=station_headers).json()
    out = _ask(client, station_headers, "How many pending drafts do I have?")
    assert out["intent"] == "LIVE_COUNTS" and out["grounding"] == "LIVE_DATA"
    assert out["data"]["counts"]["DRAFT"] == (kpis.get("cases_by_status") or {}).get("DRAFT", 0)
    assert str(out["data"]["counts"]["DRAFT"]) in out["answer"]
    te = _ask(client, station_headers, "ఎన్ని కేసులు ఉన్నాయి?")
    assert te["language"] == "te" and str(kpis.get("total_cases", 0)) in te["answer"]


def test_fir_status_never_reveals_another_jurisdiction(client, station_headers, state_headers):
    fir = f"GNT-{uuid.uuid4().hex[:6].upper()}"
    created = client.post("/api/v1/cases/", headers=state_headers, json={
        "fir_number": fir, "year": 2026, "district": "Guntur", "station": "Tenali PS",
        "offence_nature": "Voice assistant access test"})
    assert created.status_code == 201, created.text
    station = _ask(client, station_headers, f"What is the status of FIR {fir}?")
    assert station["intent"] == "FIR_STATUS" and "could not find" in station["answer"] and "Tenali" not in station["answer"]
    state = _ask(client, state_headers, f"What is the status of FIR {fir}?")
    assert "Tenali PS" in state["answer"] and "under review" in state["answer"]
    # Follow-up refers back to the FIR from the conversation
    follow = _ask(client, state_headers, "What is its workflow status?",
                  history=[{"role": "user", "text": f"What is the status of FIR {fir}?"}, {"role": "assistant", "text": state["answer"]}])
    assert follow["intent"] == "WORKFLOW_STATUS" and fir in follow["answer"]


def test_app_help_is_grounded_in_the_guide(client, station_headers, monkeypatch):
    seen = {}

    def fake_answer(question, guide, language="en", history=None):
        seen["titles"] = [g["title"] for g in guide]
        return {"status": "ANSWERED", "text": "Open New Case Intake and use Evidence Upload / OCR [G1].", "used": [1]}
    monkeypatch.setattr(gemini_service, "answer_app_question", fake_answer)
    out = _ask(client, station_headers, "How do I register a new FIR?")
    assert out["grounding"] == "APP_GUIDE" and "New Case Intake" in seen["titles"]
    assert out["citations"][0]["type"] == "guide" and "[G1]" not in out["answer"]
    assert out["navigate_to"] == "/intake"


def test_without_ai_the_verified_passage_is_read_not_guessed(client, station_headers, monkeypatch):
    monkeypatch.setattr(gemini_service, "answer_app_question", lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": []})
    out = _ask(client, station_headers, "డాష్‌బోర్డ్ ఎలా ఉపయోగించాలి?", language="te")
    assert out["language"] == "te" and out.get("ai_unavailable") is True
    assert "Quick Access" in out["answer"] and "AI అనువాదం" in out["answer"]


def test_voice_intake_is_described_as_unavailable(client, station_headers, monkeypatch):
    monkeypatch.setattr(gemini_service, "answer_app_question", lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": []})
    out = _ask(client, station_headers, "How do I use voice intake to dictate an FIR?")
    assert "not a working recorder" in out["answer"] and "Typed Narrative" in out["answer"]


def test_record_actions_are_refused(client, station_headers, monkeypatch):
    monkeypatch.setattr(gemini_service, "answer_app_question", lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": []})
    out = _ask(client, station_headers, "Approve this case now")
    assert out["intent"] == "ACTION_REQUEST" and out["answer"].startswith("I cannot approve")


def test_audit_keeps_metadata_only(client, station_headers, monkeypatch):
    monkeypatch.setattr(gemini_service, "answer_app_question", lambda *a, **k: {"status": "UNAVAILABLE", "text": "", "used": []})
    marker = f"zebra{uuid.uuid4().hex[:8]}"
    _ask(client, station_headers, f"How do I search cases for {marker}?")
    con = sqlite3.connect(settings.DATABASE_URL.split("///", 1)[1])
    try:
        rows = con.execute("SELECT * FROM audit_log WHERE action_type = 'VOICE_ASSISTANT_QUERY' ORDER BY rowid DESC LIMIT 5").fetchall()
    finally:
        con.close()
    assert rows and not any(marker in str(r) for r in rows)
