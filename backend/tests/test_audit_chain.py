"""
Audit hash chain: appends are atomic (no forks under concurrency), verification reports the first
broken entry and why, and the repair script re-links forked entries without changing content.
"""
import asyncio
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.database import AsyncSessionLocal
from app.models.audit import GENESIS_HASH, AuditLog
from app.services.audit import entry_payload, log_audit_event, verify_entries

_spec = importlib.util.spec_from_file_location(
    "repair_audit_chain", os.path.join(os.path.dirname(__file__), "..", "scripts", "repair_audit_chain.py"))
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


def _entry(i, prev, ts, action="TEST"):
    e = SimpleNamespace(id=i, actor_id="u", actor_username="tester", action_type=action, object_type="X",
                        object_id=str(i), before_state_json=None, after_state_json=None, timestamp=ts,
                        client_ip=None, previous_entry_hash=prev, entry_hash=None)
    e.entry_hash = AuditLog.compute_hash(prev, entry_payload(e))
    return e


def _chain(n, fork_at=None):
    """n entries; with fork_at, that entry links to the same previous entry as the one before it."""
    t0 = datetime(2026, 10, 27, 17, 9, 33)
    out, prev = [], GENESIS_HASH
    for i in range(1, n + 1):
        link = out[-2].entry_hash if (fork_at and i == fork_at) else prev
        e = _entry(i, link, t0 + timedelta(milliseconds=i))
        out.append(e)
        prev = e.entry_hash
    return out


# ── Verification ─────────────────────────────────────────────────────────────

def test_intact_chain_verifies():
    report = verify_entries(_chain(10))
    assert report["intact"] and report["verified"] == 10


def test_fork_is_reported_at_the_first_broken_entry_with_the_reason():
    report = verify_entries(_chain(10, fork_at=6))
    assert not report["intact"]
    assert report["first_broken_entry_id"] == 6 and report["kind"] == "FORK"
    assert report["linked_to_entry_id"] == 4 and report["expected_previous_entry_id"] == 5
    assert report["verified"] == 5


def test_modified_content_is_reported_as_such():
    chain = _chain(5)
    chain[2].object_id = "edited later"
    report = verify_entries(chain)
    assert report["kind"] == "CONTENT_CHANGED" and report["first_broken_entry_id"] == 3


def test_verify_endpoint_message_matches_the_result(client):
    from tests.test_knowledge_base_rag import auth
    body = client.get("/api/v1/audit/verify-integrity", headers=auth(client, "state_director", "StateAdmin@2024")).json()
    assert body["is_chain_intact"] is True
    assert body["message"] == f"Chain intact – {body['total_entries']} entries verified."
    assert body["first_broken_entry_id"] is None


# ── Atomic appends ───────────────────────────────────────────────────────────

def test_fifty_concurrent_appends_leave_an_intact_chain():
    async def write(i):
        async with AsyncSessionLocal() as db:
            await log_audit_event(db, actor_id="t", actor_username="concurrency_test", action_type="CONCURRENCY_TEST",
                                  object_type="TEST", object_id=str(i), refresh=False)

    async def run():
        await asyncio.gather(*(write(i) for i in range(50)))
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            return (await db.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()

    entries = asyncio.run(run())
    report = verify_entries(entries)
    assert report["intact"], report
    prevs = [e.previous_entry_hash for e in entries]
    assert len(prevs) == len(set(prevs))  # no two entries share a previous hash


def test_fifty_concurrent_audited_requests_leave_an_intact_chain(client):
    """Each login writes an audit entry; 50 at once through the API."""
    def login(_):
        return client.post("/api/v1/auth/login", json={"username": "station_officer", "password": "StationPass@2024"})
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(login, range(50)))
    assert all(r.status_code == 200 for r in results)
    from tests.test_knowledge_base_rag import auth
    body = client.get("/api/v1/audit/verify-integrity", headers=auth(client, "state_director", "StateAdmin@2024")).json()
    assert body["is_chain_intact"] is True, body["message"]


# ── Repair script ────────────────────────────────────────────────────────────

def test_repair_plan_relinks_forked_entries_and_the_result_verifies():
    chain = _chain(12, fork_at=7)
    contents_before = [(e.id, e.action_type, e.object_id, e.timestamp) for e in chain]
    start, changes = repair.plan_repair(chain)
    assert chain[start].id == 7 and [e.id for e, _, _ in changes] == list(range(7, 13))
    for e, new_prev, new_hash in changes:
        e.previous_entry_hash, e.entry_hash = new_prev, new_hash
    assert verify_entries(chain)["intact"]
    assert [(e.id, e.action_type, e.object_id, e.timestamp) for e in chain] == contents_before  # nothing deleted or edited


def test_repair_refuses_when_an_entry_was_modified():
    chain = _chain(8, fork_at=5)
    chain[2].object_id = "tampered"
    try:
        repair.plan_repair(chain)
    except SystemExit as e:
        assert "Refusing to repair" in str(e)
    else:
        raise AssertionError("repair must refuse a modified entry")
