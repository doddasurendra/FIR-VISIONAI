"""
Regenerate FIR summaries whose source changed (STALE in any language) and, always, the summaries of
FIR-2024-KNL-0042 (its earlier Telugu summary added a second date). Runs through the same
generate_record path as the AI Case Summaries page, so English, Telugu and Hindi are produced from the
same sources and every translation is checked against the English (dates, numbers, names, section
numbers as protected tokens; retried once, then the English text is shown).

Acts as a STATE user (all jurisdictions), and writes one FIR_SUMMARY_GENERATED audit entry per record
through the locked audit append, with the status and version of each language before and after.

  python scripts/regenerate_stale_summaries.py                  # dry run: lists what would be regenerated
  python scripts/regenerate_stale_summaries.py --apply
  python scripts/regenerate_stale_summaries.py --apply --as-user state_director --also FIR-2024-GNT-0088
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func, select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import fir_summaries as fs  # noqa: E402
from app.services.audit import log_audit_event  # noqa: E402

ALWAYS = ("FIR-2024-KNL-0042",)


async def _actor(db, username):
    stmt = select(User).where(func.upper(User.role) == "STATE", User.is_active == True)  # noqa: E712
    if username:
        stmt = select(User).where(User.username == username)
    user = (await db.execute(stmt.order_by(User.username))).scalars().first()
    if not user or (user.role or "").upper() != "STATE":
        raise SystemExit("A STATE user is needed so every jurisdiction is covered (use --as-user).")
    return user


def _states(rows):
    return {lang: {"status": getattr(r, "status", None), "version": getattr(r, "version", None)} for lang, r in rows.items()}


async def main(apply: bool, username: str, also: list, include_pending: bool = False) -> None:
    forced_firs = set(ALWAYS) | set(also or [])
    async with AsyncSessionLocal() as db:
        user = await _actor(db, username)
        records = await fs.list_records(db, user)
        rows = await fs.summary_rows(db, [r["record_key"] for r in records])
        todo = []
        for rec in records:
            state = fs.summary_state(rec, rows.get(rec["record_key"], {}))
            forced = rec.get("fir_number") in forced_firs
            stale = any(s == "STALE" for s in state.values()) or (
                include_pending and any(s in ("PENDING", "FAILED") for s in state.values()))
            if (stale or forced) and rec["source_chars"] >= fs.MIN_SOURCE_CHARS:
                todo.append((rec, state, forced))
        print(f"{len(todo)} record(s) to regenerate (acting as {user.username}, {'APPLY' if apply else 'DRY RUN'}):")
        for rec, state, forced in todo:
            print(f"  {rec['record_key']}  {rec.get('fir_number') or '-'}  {state}{'  [forced]' if forced else ''}")
        if not apply:
            print("Dry run only; nothing was changed. Re-run with --apply.")
            return

        done = failed = 0
        for rec, state, forced in todo:
            before = _states(rows.get(rec["record_key"], {}))
            outcome = await fs.generate_record(db, user, rec, force=True)
            after_rows = (await fs.summary_rows(db, [rec["record_key"]])).get(rec["record_key"], {})
            after = _states(after_rows)
            mismatches = {}
            for lang, row in after_rows.items():
                try:
                    data = json.loads(row.summary_json or "{}")
                except Exception:
                    continue
                keys = [k for k, e in (data.get("fields") or {}).items() if isinstance(e, dict) and e.get("translation_mismatch")]
                if (data.get("overview") or {}).get("translation_mismatch"):
                    keys.insert(0, "overview")
                if keys:
                    mismatches[lang] = keys
            await log_audit_event(
                db=db, actor_id=user.id, actor_username=user.username, action_type="FIR_SUMMARY_GENERATED",
                object_type="FIR_RECORD", object_id=rec["record_key"],
                before_state={"languages": before, "reason": "forced" if forced else "stale"},
                after_state={"languages": after, "outcome": outcome["status"], "error": outcome.get("error"),
                             "english_shown_for": mismatches, "ai_assisted": True,
                             "script": "regenerate_stale_summaries.py"})
            ok = outcome["status"] in ("COMPLETED", "UP_TO_DATE")
            done += ok
            failed += not ok
            print(f"  {rec['record_key']}: {outcome['status']}{' ' + str(outcome.get('error')) if not ok else ''}"
                  f"{'  english shown for ' + json.dumps(mismatches, ensure_ascii=False) if mismatches else ''}")
            if outcome["status"] == "QUOTA_EXHAUSTED":
                print("AI quota exhausted; stopping. Re-run later to continue.")
                break
        print(f"Regenerated {done}, failed {failed}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="regenerate (default: dry run)")
    ap.add_argument("--as-user", default=None, help="username of the STATE user to act as")
    ap.add_argument("--also", nargs="*", default=[], help="FIR numbers to regenerate even when up to date")
    ap.add_argument("--include-pending", action="store_true", help="also summarise PENDING and FAILED records")
    args = ap.parse_args()
    asyncio.run(main(args.apply, args.as_user, args.also, args.include_pending))
