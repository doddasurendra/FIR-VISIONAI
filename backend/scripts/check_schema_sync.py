"""
Read-only check that the SQLAlchemy models (which create the local SQLite schema) match the
configured PostgreSQL / Supabase schema: every table and column present, VARCHAR lengths equal,
and row-level security enabled on every public table. Run it after applying a migration from
supabase/migrations/. Exits 1 on any mismatch. Credentials are never printed.

Usage (from backend/, with SUPABASE_DATABASE_URL configured in .env):
    python scripts/check_schema_sync.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text  # noqa: E402
from app.database import Base, engine, is_postgres  # noqa: E402
import app.models  # noqa: E402,F401  (registers the models)
import app.models.folder  # noqa: E402,F401

# Columns that exist only in PostgreSQL by design (full-text search and pgvector)
POSTGRES_ONLY = {("document_chunks", "content_tsv"), ("document_chunks", "embedding")}


async def main() -> int:
    if not is_postgres:
        print("The configured database is SQLite; nothing to compare (its schema is created from the models).")
        return 0
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "select table_name, column_name, character_maximum_length "
            "from information_schema.columns where table_schema='public'"))).all()
        rls = dict((await conn.execute(text(
            "select tablename, rowsecurity from pg_tables where schemaname='public'"))).all())
    live = {}
    for table, column, length in rows:
        live.setdefault(table, {})[column] = length
    problems = []
    for name, table in sorted(Base.metadata.tables.items()):
        if name not in live:
            problems.append(f"table {name} is missing in PostgreSQL")
            continue
        for col in table.columns:
            if col.name not in live[name]:
                problems.append(f"column {name}.{col.name} is missing in PostgreSQL")
            elif getattr(col.type, "length", None) and live[name][col.name] \
                    and col.type.length != live[name][col.name]:
                problems.append(f"{name}.{col.name}: model VARCHAR({col.type.length}), "
                                f"PostgreSQL VARCHAR({live[name][col.name]})")
        for extra in sorted(set(live[name]) - {c.name for c in table.columns}):
            if (name, extra) not in POSTGRES_ONLY:
                problems.append(f"column {name}.{extra} exists only in PostgreSQL")
    for name in sorted(set(live) - set(Base.metadata.tables)):
        problems.append(f"table {name} exists only in PostgreSQL")
    for name, enabled in sorted(rls.items()):
        if not enabled:
            problems.append(f"row-level security is off on {name}")
    for p in problems:
        print("MISMATCH:", p)
    print(f"{len(Base.metadata.tables)} model tables, {len(live)} PostgreSQL tables, "
          f"RLS on {sum(1 for v in rls.values() if v)}/{len(rls)}; {len(problems)} mismatch(es).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
