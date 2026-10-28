"""
Case 178/2024 (Tenali PS): cheating with forged documents to obtain an SBI loan, IPC 420/468/471 and
IT Act 66C/66D, offence on 20.09.2024. It was suggested BNS 281 (rash driving) because the cue "rash"
matched inside "Maharashtra" in an image description the OCR step had added to the text. Also covers
the ingredient messages and the cleanup of official Gazette text.
"""
import uuid
from datetime import date, datetime

import pytest

from app.database import SyncSessionLocal
from app.models.case import Case
from app.services import legal_rules as rules
from app.services.legal_text import clean_statutory_text, subsection_text
from tests.test_knowledge_base_rag import auth, state_headers  # noqa: F401

# The stored OCR text of FIR 19.png, including the invented emblem paragraph that caused the bad match
FIR_178_TEXT = """A.P.P.M. Orders 470, 500

The image depicts the emblem of the Maharashtra Police. The emblem is circular in shape and predominantly black and white.

1. District : Guntur
FIRST INFORMATION REPORT
(Under Sections 154 & 157 Cr.P.C)
Police Year : FIR No : Date : Station : Tenali PS 2024 178/2024 22.09.2024
2. (i) Act, the Prevention of Corruption Act, 1988 : - Nil -
(ii) Act, Indian Penal Code : Sections 420, 468, 471 IPC.
(iii) Other Acts & Sections : Section 66C, 66D of IT Act, 2000.
3. (a) Occurrence of Offence: Day : 20.09.2024 (Friday)
Time Period : Between 10.30 hrs and 11.30 hrs
5. Place of occurrence : Near State Bank of India, Tenali, Guntur District.
(b) Address : SBI Main Branch, Market Road, Tenali.
6. Complainant / Informant : (a) Name : K. Lakshmi Prasad
7. Details of known / suspected / unknown accused with full particulars:
(a) Name : Ramesh Kumar
(e) Particulars : The above named person cheated the complainant by using forged documents and obtained a personal loan of Rs. 2,50,000/- from SBI Tenali branch by furnishing fake identity proofs.
"""


# ── Rules ────────────────────────────────────────────────────────────────────

def test_cues_match_at_word_start_only():
    assert not rules._cue_present("rash", "the emblem of the maharashtra police")
    assert rules._cue_present("rash", "drove in a rash manner")
    assert rules._cue_present("distill", "illicit distillation unit")
    assert rules._cue_present("kg", "seized 18.5kg of ganja")


def test_178_records_ipc_and_it_act_sections():
    recorded = rules.recorded_sections([FIR_178_TEXT])
    for pair in [(rules.IPC, "Section 420"), (rules.IPC, "Section 468"), (rules.IPC, "Section 471"),
                 (rules.IT_ACT, "Section 66C"), (rules.IT_ACT, "Section 66D")]:
        assert pair in recorded, pair
    assert rules.incident_date_from_text(FIR_178_TEXT) == date(2024, 9, 20)


def test_178_bns_counterparts_come_from_the_mapping_table():
    assert rules.IPC_TO_BNS["Section 420"] == "Section 318(4)"
    assert rules.IPC_TO_BNS["Section 468"] == "Section 336(3)"
    assert rules.IPC_TO_BNS["Section 471"] == "Section 340(2)"
    assert len(rules.load_ipc_bns_mapping()) >= 100


def test_178_facts_do_not_trigger_rash_driving():
    facts = FIR_178_TEXT.lower()
    rash = next(r for r in rules.RULES if r["key"] == "rash_driving")
    assert not rules.triggered(rash, facts, has_vehicle=False)
    for key in ("cheating", "forgery_for_cheating", "using_forged_document"):
        rule = next(r for r in rules.RULES if r["key"] == key)
        assert rules.triggered(rule, facts, False) and rules.key_ingredients_met(rule, facts), key


def test_a_cue_word_alone_does_not_suggest_a_section():
    """'accident' triggers the rash-driving rule, but without a vehicle on a road driven rashly it is not suggested."""
    facts = "the complainant met with an accident at home and was injured."
    rash = next(r for r in rules.RULES if r["key"] == "rash_driving")
    assert not (rules.triggered(rash, facts, has_vehicle=False) and rules.key_ingredients_met(rash, facts))


def test_ingredient_messages_never_contradict():
    assert rules.ingredient_summary([], ["A", "B"]) == ("NOT_ESTABLISHED", "Not yet established: A; B.")
    assert rules.ingredient_summary(["A"], [])[0] == "ESTABLISHED"
    status, message = rules.ingredient_summary(["A"], ["B"])
    assert status == "PARTIAL" and "Not yet established: B." in message
    status, message = rules.ingredient_summary([], [])
    assert status == "NONE_LISTED" and "Every listed ingredient" not in message


# ── Official text cleanup ───────────────────────────────────────────────────

GAZETTE_281 = """281. Whoever drives any vehicle, or rides, on any public way in a manner so rash or
negligent as to endanger human life, or to be likely to cause hurt or injury to any other
Negligent act
likely to spread
infection of
disease
dangerous to
life.
Adulteration
of drugs.
Rash driving
or riding on a
public way.
74
THE GAZETTE OF INDIA EXTRAORDINARY
[Part II—
____________________________________________________________
_____________________________________________________________
75
person, shall be punished with imprisonment of either description for a term which may
extend to six months, or with fine which may extend to one thousand rupees, or with both."""


def test_gazette_furniture_and_side_notes_are_removed():
    cleaned = clean_statutory_text(GAZETTE_281)
    assert "GAZETTE" not in cleaned and "[Part II" not in cleaned and "___" not in cleaned
    assert "Negligent act" not in cleaned and "Adulteration" not in cleaned
    assert "\n74" not in cleaned and "75" not in cleaned
    assert "injury to any other person, shall be punished" in cleaned
    assert cleaned.endswith("or with both.")


def test_subsection_is_taken_from_the_parent_section():
    text = clean_statutory_text("318. (1) Whoever, by deceiving any person, is said to cheat.\n"
                                "(2) Whoever cheats shall be punished with three years.\n"
                                "(4) Whoever cheats and thereby dishonestly induces the person deceived to\n"
                                "deliver any property, shall be punished with seven years.")
    sub = subsection_text(text, "Section 318(4)")
    assert sub.startswith("(4) Whoever cheats and thereby dishonestly induces") and "seven years" in sub
    assert "three years" not in sub


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture
def case_178():
    db = SyncSessionLocal()
    fir = f"178/2024-T{uuid.uuid4().hex[:5]}"
    case = Case(fir_number=fir, year=2024, district="Guntur", station="Tenali PS",
                offence_nature="Cheating with forged documents", narrative=FIR_178_TEXT,
                status="DRAFT", created_by="test", registration_date=datetime(2024, 9, 22))
    db.add(case)
    db.commit()
    case_id = case.id
    db.close()
    yield case_id
    db = SyncSessionLocal()
    db.delete(db.get(Case, case_id))
    db.commit()
    db.close()


def test_178_suggests_bns_318_336_340_and_it_act_not_rash_driving(client, state_headers, case_178):
    res = client.get(f"/api/v1/legal/recommend/{case_178}", headers=state_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["regime"] == "BNS" and body["offence_date"] == "2024-09-20"
    by_section = {(c["act_name"], c["section_number"]): c for c in body["candidates"]}
    assert not any(c["section_number"] in ("Section 281", "Section 279") for c in body["candidates"])
    for number in ("Section 318(4)", "Section 336(3)", "Section 340(2)"):
        assert (rules.BNS, number) in by_section, number
        assert by_section[(rules.BNS, number)]["regime_applies"] is True
    for number in ("Section 66C", "Section 66D"):
        cand = by_section[(rules.IT_ACT, number)]
        assert cand["is_recorded_in_fir"] and cand["is_other_act"]
    assert "Section 66C Information Technology Act, 2000" in body["recorded_other_act_sections"]
    for c in body["candidates"]:
        # One consistent verdict per provision
        if not c["matched_ingredients"]:
            assert c["ingredient_status"] in ("NOT_ESTABLISHED", "NONE_LISTED")
            assert "Every listed ingredient" not in c["ingredient_message"]
