"""
One-off repair of forked audit-chain entries.

Before the atomic-append fix, two audit entries written at the same moment could both link to the
same previous entry (e.g. #3377 and #3378 both pointing at f66a4bfc...). Verification walks the chain
in id order, so everything from the first fork onward failed to verify.

This script re-links each entry, from the first broken one onward, to the entry immediately before it
(in id order) and recomputes its hash. Nothing is deleted and no entry's content (actor, action,
object, states, timestamp) changes - only previous_entry_hash / entry_hash. It refuses to run if any
entry's own content hash is invalid (that would indicate tampering, not a fork).

  python scripts/repair_audit_chain.py              # dry run: shows exactly what would change
  python scripts/repair_audit_chain.py --apply      # backup old hashes, repair, append AUDIT_CHAIN_REPAIRED

The backup (old hashes of every changed row) is written to data/backups/ before anything is changed.
Run from the backend folder; uses the database configured in .env.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SyncSessionLocal, is_postgres  # noqa: E402
from app.models.audit import GENESIS_HASH, AuditLog  # noqa: E402
from app.services.audit import AUDIT_CHAIN_LOCK_KEY, canonical_payload, entry_payload, verify_entries  # noqa: E402


def plan_repair(entries):
    """Return (first_broken_index, [(entry, new_prev, new_hash)]) or raise if content is inconsistent."""
    report = verify_entries(entries)
    if report["intact"]:
        return None, []
    bad = [e.id for e in entries if AuditLog.compute_hash(e.previous_entry_hash, entry_payload(e)) != e.entry_hash]
    if bad:
        raise SystemExit(f"Refusing to repair: {len(bad)} entr(y/ies) do not match their own content hash "
                         f"(first: #{bad[0]}). That indicates modification, not a concurrent-write fork.")
    start = report["verified"]
    prev = entries[start - 1].entry_hash if start > 0 else GENESIS_HASH
    changes = []
    for e in entries[start:]:
        new_hash = AuditLog.compute_hash(prev, entry_payload(e))
        changes.append((e, prev, new_hash))
        prev = new_hash
    return start, changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="perform the repair (default is a dry run)")
    ap.add_argument("--actor", default="system_audit_repair", help="username recorded on the repair entry")
    args = ap.parse_args()

    db = SyncSessionLocal()
    try:
        if is_postgres:
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_CHAIN_LOCK_KEY})
        entries = db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
        forks = {h: n for h, n in Counter(e.previous_entry_hash for e in entries).items() if n > 1}
        forked_ids = sorted(e.id for e in entries if e.previous_entry_hash in forks)
        start, changes = plan_repair(entries)
        print(f"Database: {'Supabase PostgreSQL' if is_postgres else 'SQLite'}; {len(entries)} audit entries.")
        if start is None:
            print("Chain intact - nothing to repair.")
            return 0
        print(f"Forks (entries sharing one previous hash): {len(forks)}")
        for h, n in forks.items():
            ids = [e.id for e in entries if e.previous_entry_hash == h]
            print(f"  previous {h[:12]}... shared by entries {ids}")
        print(f"First broken entry: #{entries[start].id}. Entries to re-link: {len(changes)} "
              f"(#{changes[0][0].id} .. #{changes[-1][0].id}). No entry is deleted; no content changes.")
        for e, new_prev, new_hash in changes[:5]:
            print(f"  #{e.id} {e.action_type}: previous {e.previous_entry_hash[:12]} -> {new_prev[:12]}, "
                  f"hash {e.entry_hash[:12]} -> {new_hash[:12]}")
        if len(changes) > 5:
            print(f"  ... and {len(changes) - 5} more")

        # Prove the planned chain verifies before touching anything
        class _Row:
            def __init__(self, e, prev, h):
                self.__dict__.update({c: getattr(e, c) for c in ("id", "actor_id", "actor_username", "action_type",
                                      "object_type", "object_id", "before_state_json", "after_state_json",
                                      "timestamp", "client_ip")})
                self.previous_entry_hash, self.entry_hash = prev, h
        simulated = entries[:start] + [_Row(e, p, h) for e, p, h in changes]
        sim = verify_entries(simulated)
        print(f"Simulated repaired chain: {'intact' if sim['intact'] else 'STILL BROKEN at #' + str(sim['first_broken_entry_id'])}"
              f" ({sim['verified']} entries).")
        if not sim["intact"]:
            return 1
        if not args.apply:
            print("\nDry run only. Re-run with --apply to back up the old hashes and repair.")
            return 0

        os.makedirs(settings.BACKUPS_DIR, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        backup = os.path.join(settings.BACKUPS_DIR, f"audit_chain_hashes_before_repair_{stamp}.json")
        with open(backup, "w", encoding="utf-8") as f:
            json.dump({"created_utc": stamp, "database": "postgresql" if is_postgres else "sqlite",
                       "rows": [{"id": e.id, "entry_uuid": e.entry_uuid, "previous_entry_hash": e.previous_entry_hash,
                                 "entry_hash": e.entry_hash} for e, _, _ in changes]}, f, indent=1)
        print(f"Backup of old hashes written: {backup}")

        old_head = entries[-1].entry_hash
        for e, new_prev, new_hash in changes:
            e.previous_entry_hash, e.entry_hash = new_prev, new_hash
        db.flush()
        # Record the repair itself as the next link of the repaired chain
        ts = datetime.utcnow()
        before = json.dumps({"forked_entry_ids": forked_ids,
                             "first_broken_entry_id": changes[0][0].id, "old_head_hash": old_head},
                            sort_keys=True, separators=(",", ":"))
        after = json.dumps({"rows_relinked": len(changes), "first_relinked_id": changes[0][0].id,
                            "last_relinked_id": changes[-1][0].id, "new_head_hash": changes[-1][2],
                            "backup_file": os.path.basename(backup), "content_changed": False},
                           sort_keys=True, separators=(",", ":"))
        payload = canonical_payload("system", args.actor, "AUDIT_CHAIN_REPAIRED", "AUDIT_CHAIN", "audit_log",
                                    before, after, ts, None)
        repair = AuditLog(actor_id="system", actor_username=args.actor, action_type="AUDIT_CHAIN_REPAIRED",
                          object_type="AUDIT_CHAIN", object_id="audit_log", before_state_json=before,
                          after_state_json=after, client_ip=None, timestamp=ts,
                          previous_entry_hash=changes[-1][2], entry_hash=AuditLog.compute_hash(changes[-1][2], payload))
        db.add(repair)
        db.commit()

        final = verify_entries(db.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all())
        print(f"Repaired. Verification: {'Chain intact - ' + str(final['verified']) + ' entries verified' if final['intact'] else 'BROKEN at #' + str(final['first_broken_entry_id'])}")
        return 0 if final["intact"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
