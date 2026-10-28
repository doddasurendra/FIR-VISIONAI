"""
Repeat offenders and networks: vehicles linked across all cases (drafts tagged) by normalised
registration, no wrong duplicate suggestions (different registrations, different districts),
placeholder names excluded, jurisdiction on every query, and honest risk-model metrics.
"""
import json
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.database import SyncSessionLocal
from app.models.case import Case
from app.models.entity import Entity, EntityMention
from app.services.entity_resolution import EntityResolutionService, is_placeholder, registration_of
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401


def _ent(name, etype, **attrs):
    return SimpleNamespace(id=str(uuid.uuid4()), canonical_name=name, entity_type=etype, attributes_json=json.dumps(attrs))


# ── Matching rules ───────────────────────────────────────────────────────────

def test_vehicles_match_only_on_the_normalised_registration():
    sim = EntityResolutionService.compute_similarity
    a = _ent("Hero Splendor AP21AB1234", "VEHICLE", registration_number="Hero Splendor AP21AB1234")
    b = _ent("Hero Splendor AP31AB9988", "VEHICLE", registration_number="Hero Splendor AP31AB9988")
    c = _ent("Two-wheeler ap 21 ab 1234", "VEHICLE")
    assert sim(a, b) == 0.0
    assert sim(a, c) == 1.0
    assert registration_of("Auto AP 21 TY 4567") == "AP21TY4567"


def test_locations_match_only_within_the_same_district():
    sim = EntityResolutionService.compute_similarity
    chennai = _ent("Chennai Excise Jurisdiction", "LOCATION", district="Chennai")
    cyberabad = _ent("Cyberabad Excise Jurisdiction", "LOCATION", district="Cyberabad")
    assert sim(chennai, cyberabad) == 0.0
    a = _ent("Kallur Toll Plaza", "LOCATION", district="Kurnool")
    b = _ent("Kallur Toll Plaza NH-44", "LOCATION", district="Kurnool")
    assert sim(a, b) > 0.7


def test_persons_keep_fuzzy_names_boosted_by_phone_and_address():
    sim = EntityResolutionService.compute_similarity
    a = _ent("Ramu Naidu", "PERSON", phone="+91 98480 12345", address="Kallur Village, Kurnool")
    b = _ent("Ramu Naidu Kallur", "PERSON", phone="9848012345", address="Kallur village Kurnool")
    plain_a, plain_b = _ent("Ramu Naidu", "PERSON"), _ent("Ramu Naidu Kallur", "PERSON")
    assert sim(a, b) > sim(plain_a, plain_b)
    assert sim(_ent("Unknown Suspect", "PERSON"), _ent("Unknown Suspect", "PERSON")) == 0.0
    assert is_placeholder("Unknown Suspect") and is_placeholder("N/A") and not is_placeholder("Ramu Naidu")


# ── Network and analytics on the test database ───────────────────────────────

@pytest.fixture
def network_fixture():
    """Draft cases with the same vehicle, look-alike vehicles, and a placeholder accused (test DB only)."""
    db = SyncSessionLocal()
    tok = uuid.uuid4().hex[:6]
    made = []

    def case(fir, vehicle, status="DRAFT", district="Kurnool", station="Kurnool Town Station"):
        c = Case(fir_number=f"{fir}-{tok}", year=2024, district=district, station=station, offence_nature="ID liquor",
                 vehicle_details=vehicle, status=status, created_by="test", registration_date=datetime(2024, 9, 1))
        db.add(c)
        made.append(c)
        return c
    d1 = case("TEST-DRAFT-A", "Auto AP 21 TY 4567")
    d2 = case("TEST-DRAFT-B", "auto ap21ty4567")
    c3 = case("TEST-SPL-1", "Hero Splendor AP21AB1234", status="IN_REVIEW")
    c4 = case("TEST-SPL-2", "Hero Splendor AP31AB9988", status="IN_REVIEW")
    db.flush()
    ents = [Entity(canonical_name=f"Hero Splendor AP21AB1234", entity_type="VEHICLE",
                   attributes_json=json.dumps({"registration_number": "Hero Splendor AP21AB1234"})),
            Entity(canonical_name=f"Hero Splendor AP31AB9988", entity_type="VEHICLE",
                   attributes_json=json.dumps({"registration_number": "Hero Splendor AP31AB9988"})),
            Entity(canonical_name="Unknown Suspect", entity_type="PERSON", attributes_json="{}")]
    db.add_all(ents)
    db.flush()
    mentions = [EntityMention(entity_id=ents[0].id, case_id=c3.id, mention_text=ents[0].canonical_name, role_in_case="CONVEYANCE"),
                EntityMention(entity_id=ents[1].id, case_id=c4.id, mention_text=ents[1].canonical_name, role_in_case="CONVEYANCE"),
                EntityMention(entity_id=ents[2].id, case_id=c3.id, mention_text="Unknown Suspect", role_in_case="ACCUSED"),
                EntityMention(entity_id=ents[2].id, case_id=c4.id, mention_text="Unknown Suspect", role_in_case="ACCUSED")]
    db.add_all(mentions)
    db.commit()
    yield {"drafts": {d1.fir_number, d2.fir_number}}
    for m in mentions:
        db.delete(db.get(EntityMention, m.id))
    for e in ents:
        db.delete(db.get(Entity, e.id))
    for c in made:
        db.delete(db.get(Case, c.id))
    db.commit()
    db.close()


def test_vehicle_links_every_case_including_drafts(client, state_headers, network_fixture):
    graph = client.get("/api/v1/entities/network-graph", headers=state_headers).json()
    node = next(n for n in graph["nodes"] if registration_of(n["label"]) == "AP21TY4567")
    firs = {c["fir_number"]: c for c in node["source_cases"]}
    assert "FIR-2024-KNL-0042" in firs                                # the seeded case with the vehicle entity
    assert network_fixture["drafts"] <= set(firs)                     # drafts linked by the same registration
    assert all(firs[f]["is_draft"] for f in network_fixture["drafts"])
    assert node["case_count"] >= 3


def test_look_alike_vehicles_are_not_suggested_as_duplicates(client, state_headers, network_fixture):
    queue = client.get("/api/v1/entities/review-queue", headers=state_headers).json()
    for c in queue:
        names = {c["entity_1"]["name"], c["entity_2"]["name"]}
        assert names != {"Hero Splendor AP21AB1234", "Hero Splendor AP31AB9988"}


def test_placeholder_names_are_not_repeat_offenders_or_network_nodes(client, state_headers, network_fixture):
    offenders = client.get("/api/v1/analytics/repeat-offenders", headers=state_headers).json()
    assert all(not is_placeholder(o["name"]) for o in offenders)
    graph = client.get("/api/v1/entities/network-graph", headers=state_headers).json()
    assert all(not is_placeholder(n["label"]) for n in graph["nodes"])


def test_repeat_offenders_stay_within_jurisdiction(client, station_headers):
    offenders = client.get("/api/v1/analytics/repeat-offenders", headers=station_headers).json()
    for o in offenders:
        assert all(c["district"] == "Kurnool" for c in o["associated_cases"]), o


def test_risk_metrics_report_test_set_size_and_warn_when_small(client, state_headers):
    ev = client.get("/api/v1/analytics/risk-evaluation", headers=state_headers).json()
    assert ev["test_set_size"] == ev["sample_counts"]["test_split"]
    assert ev["real_samples_in_test"] + ev["synthetic_samples_in_test"] == ev["test_set_size"]
    if ev["test_set_size"] < 100:
        assert any("at least 100" in w for w in ev["reliability_warnings"])
