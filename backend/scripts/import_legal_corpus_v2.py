"""
Import the legal corpus additions and the IPC -> BNS mapping into the configured database
(Supabase PostgreSQL when SUPABASE_DATABASE_URL is set, otherwise the local SQLite fallback).

  python scripts/import_legal_corpus_v2.py            # dry run: counts only, nothing written
  python scripts/import_legal_corpus_v2.py --apply    # write, then one LEGAL_CORPUS_IMPORTED audit entry

Sources:
  corpus/special_acts_and_forgery.json  IPC 468/471, BNS 336(3)/340(2), IT Act, NDPS, Arms Act, MV Act rows
  corpus/ipc_bns_mapping.json           IPC -> BNS correspondence table with its sources

Idempotent: a corpus row is matched on (act_name, section_number) among the non-official rows (the
official Gazette rows are never touched) and updated only when its content differs; a mapping row is
matched on ipc_section. On PostgreSQL the ipc_bns_mapping table must exist first
(supabase/migrations/20261028100000_legal_ipc_bns_mapping.sql); on SQLite it is created here.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect as sa_inspect, select  # noqa: E402

from app.database import AsyncSessionLocal, is_postgres, sync_engine  # noqa: E402
from app.models.base import generate_uuid  # noqa: E402
from app.models.legal import IpcBnsMapping, LegalCorpus  # noqa: E402
from app.services.audit import log_audit_event  # noqa: E402

CORPUS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "corpus"))
ROWS_FILE = os.path.join(CORPUS_DIR, "special_acts_and_forgery.json")
MAPPING_FILE = os.path.join(CORPUS_DIR, "ipc_bns_mapping.json")
CORPUS_FIELDS = ("section_title", "full_text", "explanation", "essential_ingredients_json", "penalty_text",
                 "effective_date", "repeal_date", "jurisdiction", "category", "source_url", "source_gazette")


def corpus_values(row: dict) -> dict:
    return {
        "section_title": row["section_title"], "full_text": row["full_text"], "explanation": row.get("explanation"),
        "essential_ingredients_json": json.dumps(row.get("essential_ingredients") or [], ensure_ascii=False),
        "penalty_text": row.get("penalty_text"), "effective_date": row.get("effective_date"),
        "repeal_date": row.get("repeal_date"), "jurisdiction": row.get("jurisdiction") or "National (India)",
        "category": row.get("category"), "source_url": row.get("source_url"), "source_gazette": row.get("source_gazette"),
    }


def mapping_values(m: dict, source: str, source_url: str) -> dict:
    return {"ipc_title": m.get("ipc_title"), "bns_section": m.get("bns"), "bns_title": m.get("bns_title"),
            "note": m.get("note"), "source": source, "source_url": source_url}


def mapping_table_exists() -> bool:
    return sa_inspect(sync_engine).has_table(IpcBnsMapping.__tablename__)


async def run(apply: bool) -> dict:
    with open(ROWS_FILE, encoding="utf-8") as f:
        rows = json.load(f)
    with open(MAPPING_FILE, encoding="utf-8") as f:
        mapping_doc = json.load(f)
    source = "; ".join(s["name"] for s in mapping_doc["sources"])[:300]
    source_url = mapping_doc["sources"][0]["url"]

    has_table = mapping_table_exists()
    if apply and not has_table:
        if is_postgres:
            raise SystemExit("ipc_bns_mapping does not exist: apply "
                             "supabase/migrations/20261028100000_legal_ipc_bns_mapping.sql first.")
        IpcBnsMapping.__table__.create(bind=sync_engine)
        has_table = True

    counts = {"legal_corpus": {"insert": 0, "update": 0, "unchanged": 0},
              "ipc_bns_mapping": {"insert": 0, "update": 0, "unchanged": 0}}
    changed = []
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        for row in rows:
            values = corpus_values(row)
            existing = (await db.execute(select(LegalCorpus).where(
                LegalCorpus.act_name == row["act_name"], LegalCorpus.section_number == row["section_number"],
                (LegalCorpus.source_type != "OFFICIAL") | LegalCorpus.source_type.is_(None)))).scalars().first()
            if existing is None:
                counts["legal_corpus"]["insert"] += 1
                changed.append(f"+ {row['act_name']} {row['section_number']}")
                if apply:
                    db.add(LegalCorpus(id=generate_uuid(), act_name=row["act_name"], section_number=row["section_number"],
                                       verification_status="VERIFIED", source_type="UNVERIFIED", version="1.0",
                                       last_verified_at=now, **values))
            elif any(getattr(existing, k) != v for k, v in values.items()):
                counts["legal_corpus"]["update"] += 1
                changed.append(f"~ {row['act_name']} {row['section_number']}")
                if apply:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    existing.last_verified_at = now
            else:
                counts["legal_corpus"]["unchanged"] += 1

        current = {}
        if has_table:
            current = {m.ipc_section: m for m in (await db.execute(select(IpcBnsMapping))).scalars().all()}
        for m in mapping_doc["mappings"]:
            values = mapping_values(m, source, source_url)
            existing = current.get(m["ipc"])
            if existing is None:
                counts["ipc_bns_mapping"]["insert"] += 1
                if apply:
                    db.add(IpcBnsMapping(id=generate_uuid(), ipc_section=m["ipc"], **values))
            elif any(getattr(existing, k) != v for k, v in values.items()):
                counts["ipc_bns_mapping"]["update"] += 1
                if apply:
                    for k, v in values.items():
                        setattr(existing, k, v)
            else:
                counts["ipc_bns_mapping"]["unchanged"] += 1

        if apply:
            await db.commit()
            if any(c["insert"] or c["update"] for c in counts.values()):
                await log_audit_event(
                    db, actor_id="system", actor_username="import_legal_corpus_v2", action_type="LEGAL_CORPUS_IMPORTED",
                    object_type="LEGAL_CORPUS", object_id="corpus/special_acts_and_forgery.json+ipc_bns_mapping.json",
                    before_state=None, after_state={"counts": counts, "provisions": changed})
    return {"counts": counts, "changes": changed, "mapping_table_exists": has_table}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the rows (default: dry run)")
    ap.add_argument("--dry-run", action="store_true", help="count only (the default)")
    args = ap.parse_args()
    result = asyncio.run(run(apply=args.apply and not args.dry_run))
    mode = "APPLIED" if args.apply and not args.dry_run else "DRY RUN (nothing written)"
    print(f"{mode} - database: {'PostgreSQL' if is_postgres else 'SQLite'}")
    if not result["mapping_table_exists"]:
        print("  ipc_bns_mapping table does not exist yet; every mapping row is counted as an insert.")
    for table, c in result["counts"].items():
        print(f"  {table}: insert {c['insert']}, update {c['update']}, unchanged {c['unchanged']}")
    for line in result["changes"]:
        print(f"    {line}")


if __name__ == "__main__":
    main()
