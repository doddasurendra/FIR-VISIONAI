import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ..models.audit import AuditLog, GENESIS_HASH

def serialize_canonical(data: Any) -> str:
    """Deterministic JSON serialization with sorted keys."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return json.dumps(data, sort_keys=True, separators=(',', ':'))

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
    """Append a tamper-evident audit record linking to the previous hash. refresh=False skips re-reading it."""
    # Find previous entry
    stmt = select(AuditLog).order_by(desc(AuditLog.id)).limit(1)
    result = await db.execute(stmt)
    last_entry = result.scalar_one_or_none()

    previous_hash = last_entry.entry_hash if last_entry else GENESIS_HASH
    timestamp_now = datetime.utcnow()
    
    before_json = serialize_canonical(before_state) if before_state else None
    after_json = serialize_canonical(after_state) if after_state else None

    # Canonical content string for SHA-256
    canonical_payload = (
        f"{actor_id}|{actor_username}|{action_type}|{object_type}|{object_id}|"
        f"{before_json or ''}|{after_json or ''}|{timestamp_now.isoformat()}|{client_ip or ''}"
    )
    entry_hash = AuditLog.compute_hash(previous_hash, canonical_payload)

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


async def verify_audit_chain(db: AsyncSession) -> Tuple[bool, int, Optional[str]]:
    """
    Verify the cryptographic integrity of the entire audit hash chain.
    Returns: (is_valid, verified_count, error_description)
    """
    stmt = select(AuditLog).order_by(AuditLog.id.asc())
    result = await db.execute(stmt)
    entries = result.scalars().all()

    if not entries:
        return True, 0, None

    expected_prev = GENESIS_HASH
    for idx, entry in enumerate(entries):
        if entry.previous_entry_hash != expected_prev:
            return False, idx, f"Hash broken at entry ID {entry.id}. Expected prev {expected_prev}, got {entry.previous_entry_hash}"

        canonical_payload = (
            f"{entry.actor_id}|{entry.actor_username}|{entry.action_type}|{entry.object_type}|{entry.object_id}|"
            f"{entry.before_state_json or ''}|{entry.after_state_json or ''}|{entry.timestamp.isoformat()}|{entry.client_ip or ''}"
        )
        recalculated_hash = AuditLog.compute_hash(entry.previous_entry_hash, canonical_payload)
        
        # Verify hash match
        if recalculated_hash != entry.entry_hash:
            return False, idx, f"Content tampering detected at entry ID {entry.id}. Hash does not match canonical payload."
        
        expected_prev = entry.entry_hash

    return True, len(entries), None
