import asyncio
import json
import logging
import weakref
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text
from ..models.audit import AuditLog, GENESIS_HASH

# Appends to the hash chain must be serialised: two writers that read the same last entry would both
# link to it and fork the chain (seen as entries #3377/#3378 sharing a previous hash).
# PostgreSQL: a transaction-scoped advisory lock (works across processes and servers).
# SQLite: one writer at a time in this process (the SQLite fallback runs a single server process).
AUDIT_CHAIN_LOCK_KEY = 0x46495241  # "FIRA"
# asyncio locks belong to one event loop; keep one per loop (tests and tools may run several)
_sqlite_chain_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def _sqlite_chain_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _sqlite_chain_locks.get(loop)
    if lock is None:
        lock = _sqlite_chain_locks[loop] = asyncio.Lock()
    return lock


def serialize_canonical(data: Any) -> str:
    """Deterministic JSON serialization with sorted keys."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


def canonical_payload(actor_id, actor_username, action_type, object_type, object_id,
                      before_json, after_json, timestamp: datetime, client_ip) -> str:
    """The content an entry's hash covers (shared by append, verify and the repair script)."""
    return (f"{actor_id}|{actor_username}|{action_type}|{object_type}|{object_id}|"
            f"{before_json or ''}|{after_json or ''}|{timestamp.isoformat()}|{client_ip or ''}")


def entry_payload(entry: AuditLog) -> str:
    return canonical_payload(entry.actor_id, entry.actor_username, entry.action_type, entry.object_type,
                             entry.object_id, entry.before_state_json, entry.after_state_json, entry.timestamp,
                             entry.client_ip)


def _is_postgres(db: AsyncSession) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


@asynccontextmanager
async def _chain_append_lock(db: AsyncSession):
    """Hold the chain head for the duration of one append (read last entry -> insert -> commit)."""
    if _is_postgres(db):
        # Released automatically when the transaction commits or rolls back
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_CHAIN_LOCK_KEY})
        yield
    else:
        async with _sqlite_chain_lock():
            yield


async def log_audit_event(
    db: AsyncSession,
    actor_id: str,
    actor_username: str,
    action_type: str,
    object_type: str,
    object_id: str,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    client_ip: Optional[str] = None,
    refresh: bool = True,
) -> AuditLog:
    """
    Append a tamper-evident audit record linking to the previous hash. Atomic: concurrent appends are
    serialised, so each links to the entry written just before it. refresh=False skips re-reading it.
    """
    before_json = serialize_canonical(before_state) if before_state else None
    after_json = serialize_canonical(after_state) if after_state else None
    async with _chain_append_lock(db):
        last_entry = (await db.execute(select(AuditLog).order_by(desc(AuditLog.id)).limit(1))).scalar_one_or_none()
        previous_hash = last_entry.entry_hash if last_entry else GENESIS_HASH
        timestamp_now = datetime.utcnow()
        entry_hash = AuditLog.compute_hash(previous_hash, canonical_payload(
            actor_id, actor_username, action_type, object_type, object_id, before_json, after_json,
            timestamp_now, client_ip))
        new_log = AuditLog(
            actor_id=actor_id,
            actor_username=actor_username,
            action_type=action_type,
            object_type=object_type,
            object_id=object_id,
            before_state_json=before_json,
            after_state_json=after_json,
            client_ip=client_ip,
            timestamp=timestamp_now,
            previous_entry_hash=previous_hash,
            entry_hash=entry_hash
        )
        db.add(new_log)
        await db.commit()
    if refresh:
        await db.refresh(new_log)
    return new_log

def is_connection_error(error: Exception) -> bool:
    """True when a database call failed because the connection was lost, not because of the statement."""
    from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
    if isinstance(error, DBAPIError) and getattr(error, "connection_invalidated", False):
        return True
    if isinstance(error, (OperationalError, InterfaceError)):
        return True
    if isinstance(error, TimeoutError):
        # asyncpg raises a bare TimeoutError (no message) when the pooler does not answer
        tb = error.__traceback__
        while tb is not None:
            if "sqlalchemy" in tb.tb_frame.f_code.co_filename or "asyncpg" in tb.tb_frame.f_code.co_filename:
                return True
            tb = tb.tb_next
    msg = str(error).lower()
    return isinstance(error, (DBAPIError, ConnectionError, OSError)) and any(
        m in msg for m in ("connection was closed", "connection is closed", "connection reset",
                           "forcibly closed", "server closed the connection", "getaddrinfo", "timed out"))


async def log_audit_event_with_retry(db: AsyncSession, **event) -> AuditLog:
    """
    log_audit_event, retried once on a fresh connection if the first attempt lost its connection
    (e.g. the pooler closed it). Statement errors are not retried. At most one retry, so a dropped
    acknowledgement can add at most one extra, correctly chained entry.
    """
    try:
        return await log_audit_event(db, **event)
    except Exception as e:
        if not is_connection_error(e):
            raise
        logging.getLogger(__name__).warning(f"Audit write lost its database connection; retrying once: {str(e)[:120]}")
        try:
            await db.rollback()
        except Exception:
            pass
        return await log_audit_event(db, **event)


def verify_entries(entries) -> Dict[str, Any]:
    """
    Walk the chain in id order. Intact only if every entry links to the one before it and its stored
    hash matches its recalculated content hash. Reports the first broken entry and why.
    """
    by_hash = {e.entry_hash: e.id for e in entries}
    expected_prev, prev_id = GENESIS_HASH, None
    for idx, entry in enumerate(entries):
        if entry.previous_entry_hash != expected_prev:
            linked_to = by_hash.get(entry.previous_entry_hash)
            if linked_to is not None:
                reason = (f"it links to entry #{linked_to} instead of the entry written just before it "
                          f"(#{prev_id}); two entries were appended at the same moment and the chain forked")
                kind = "FORK"
            else:
                reason = "its previous-hash link matches no entry in the log (an entry before it was removed or altered)"
                kind = "BROKEN_LINK"
            return {"intact": False, "verified": idx, "first_broken_entry_id": entry.id, "kind": kind,
                    "reason": reason, "linked_to_entry_id": linked_to, "expected_previous_entry_id": prev_id}
        if AuditLog.compute_hash(entry.previous_entry_hash, entry_payload(entry)) != entry.entry_hash:
            return {"intact": False, "verified": idx, "first_broken_entry_id": entry.id, "kind": "CONTENT_CHANGED",
                    "reason": "its stored hash does not match its content (the entry was modified after it was written)",
                    "linked_to_entry_id": None, "expected_previous_entry_id": prev_id}
        expected_prev, prev_id = entry.entry_hash, entry.id
    return {"intact": True, "verified": len(entries), "first_broken_entry_id": None, "kind": None, "reason": None}


async def verify_audit_chain_report(db: AsyncSession) -> Dict[str, Any]:
    entries = (await db.execute(select(AuditLog).order_by(AuditLog.id.asc()))).scalars().all()
    report = verify_entries(entries)
    report["total_entries"] = len(entries)
    if report["intact"]:
        report["message"] = f"Chain intact – {len(entries)} entries verified."
    else:
        report["message"] = (f"Chain broken at entry #{report['first_broken_entry_id']}: {report['reason']}. "
                             f"The {report['verified']} entries before it verify correctly; "
                             f"{len(entries) - report['verified']} from there on are not verified.")
    return report


async def verify_audit_chain(db: AsyncSession) -> Tuple[bool, int, Optional[str]]:
    """Verify the whole chain. Returns: (is_valid, verified_count, error_description)."""
    report = await verify_audit_chain_report(db)
    return report["intact"], report["verified"], None if report["intact"] else report["message"]
