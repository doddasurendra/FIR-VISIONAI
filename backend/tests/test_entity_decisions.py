"""
Entity review decisions: "keep separate" is saved and audited and the pair leaves the queue; merges,
match decisions, entity lists and profiles stay within the user's jurisdiction.
"""
import json
import uuid
from datetime import datetime

import pytest

from app.database import SyncSessionLocal
from app.models.case import Case
from app.models.entity import Entity, EntityMention
from tests.test_knowledge_base_rag import auth, station_headers, state_headers  # noqa: F401


@pytest.fixture
def entity_pairs():
    """A look-alike pair inside Kurnool Town Station, and an entity seen only in a Prakasam case."""
    db = SyncSessionLocal()
    tok = uuid.uuid4().hex[:6]
    kurnool = Case(fir_number=f"ENT-KNL-{tok}", year=2024, district="Kurnool", station="Kurnool Town Station",
                   offence_nature="ID liquor", status="IN_REVIEW", created_by="test", registration_date=datetime(2024, 9, 1))
    prakasam = Case(fir_number=f"ENT-PKM-{tok}", year=2024, district="Prakasam", station="Ongole PS",
                    offence_nature="Theft", status="IN_REVIEW", created_by="test", registration_date=datetime(2024, 9, 1))
    db.add_all([kurnool, prakasam])
    db.flush()
    a = Entity(canonical_name=f"Kalla Venkatesh {tok}", entity_type="PERSON", attributes_json=json.dumps({"district": "Kurnool"}))
    b = Entity(canonical_name=f"Kalla Venkatesh Rao {tok}", entity_type="PERSON", attributes_json=json.dumps({"district": "Kurnool"}))
    far = Entity(canonical_name=f"Ongole Person {tok}", entity_type="PERSON", attributes_json="{}")
    db.add_all([a, b, far])
    db.flush()
    mentions = [EntityMention(entity_id=a.id, case_id=kurnool.id, mention_text=a.canonical_name, role_in_case="ACCUSED"),
                EntityMention(entity_id=b.id, case_id=kurnool.id, mention_text=b.canonical_name, role_in_case="ACCUSED"),
                EntityMention(entity_id=far.id, case_id=prakasam.id, mention_text=far.canonical_name, role_in_case="ACCUSED")]
    db.add_all(mentions)
    db.commit()
    ids = {"a": a.id, "b": b.id, "far": far.id, "prakasam_case": prakasam.id}
    mention_ids, case_ids = [m.id for m in mentions], [kurnool.id, prakasam.id]
    db.close()
    yield ids
    db = SyncSessionLocal()
    for m in mention_ids:
        db.delete(db.get(EntityMention, m))
    for e in (ids["a"], ids["b"], ids["far"]):
        db.delete(db.get(Entity, e))
    for c in case_ids:
        db.delete(db.get(Case, c))
    db.commit()
    db.close()


def _pair_in_queue(client, headers, ids):
    queue = client.get("/api/v1/entities/review-queue", headers=headers).json()
    return any({c["entity_1"]["id"], c["entity_2"]["id"]} == {ids["a"], ids["b"]} for c in queue)


def test_keep_separate_is_saved_audited_and_removes_the_pair(client, station_headers, state_headers, entity_pairs):
    assert _pair_in_queue(client, station_headers, entity_pairs)
    res = client.post("/api/v1/entities/keep-separate", headers=station_headers,
                      json={"entity_1_id": entity_pairs["a"], "entity_2_id": entity_pairs["b"], "reason": "Different fathers"})
    assert res.status_code == 200, res.text
    assert not _pair_in_queue(client, station_headers, entity_pairs)
    audit = client.get("/api/v1/audit/", headers=state_headers, params={"action_type": "ENTITY_KEPT_SEPARATE"}).json()
    assert audit and entity_pairs["b"] in audit[0]["after_state_json"]


def test_entities_outside_the_jurisdiction_cannot_be_merged_or_viewed(client, station_headers, entity_pairs):
    merge = client.post("/api/v1/entities/merge", headers=station_headers,
                        json={"primary_entity_id": entity_pairs["a"], "secondary_entity_id": entity_pairs["far"]})
    assert merge.status_code == 403
    assert client.post("/api/v1/entities/keep-separate", headers=station_headers, json={
        "entity_1_id": entity_pairs["a"], "entity_2_id": entity_pairs["far"]}).status_code == 403
    assert client.get(f"/api/v1/entities/{entity_pairs['far']}", headers=station_headers).status_code == 403
    assert client.post("/api/v1/entities/matches/decision", headers=station_headers, json={
        "case_id": entity_pairs["prakasam_case"], "entity_id": entity_pairs["far"], "decision": "CONFIRM"}).status_code == 403
    listed = {e["id"] for e in client.get("/api/v1/entities/", headers=station_headers).json()}
    assert entity_pairs["a"] in listed and entity_pairs["far"] not in listed


def test_state_sees_every_entity(client, state_headers, entity_pairs):
    listed = {e["id"] for e in client.get("/api/v1/entities/", headers=state_headers).json()}
    assert {entity_pairs["a"], entity_pairs["far"]} <= listed
    assert client.get(f"/api/v1/entities/{entity_pairs['far']}", headers=state_headers).status_code == 200
