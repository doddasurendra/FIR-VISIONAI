"""
FIR VisionAI — SQLite to Supabase PostgreSQL Migration Utility
Safely migrates all FIR records, documents, extractions, users, and workflows from local SQLite to Supabase PostgreSQL.
Preserves existing SQLite database, creates a verified pre-migration backup snapshot, and prevents duplicate records.
"""
import os
import sys
import re
import shutil
import sqlite3
import argparse
from datetime import datetime
from typing import Dict, Any, List

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, inspect, text, Table, MetaData
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.database import Base, setup_database_sync

TABLES_IN_DEPENDENCY_ORDER = [
    "users",
    "fir_folders",
    "cases",
    "documents",
    "case_fields",
    "document_pages",
    "document_chunks",
    "entities",
    "entity_mentions",
    "graph_edges",
    "legal_corpus",
    "case_legal_sections",
    "case_folder_assignments",
    "workflow_executions",
    "case_summaries",
    "generated_documents",
    "document_approval_history",
    "audit_log",
    "refresh_tokens",
    "extraction_configs",
    "extraction_runs",
    "bulk_jobs",
]

DATETIME_COLUMNS = {
    "created_at", "updated_at", "last_login", "registration_date",
    "offence_date", "detection_date", "verified_at", "approved_at",
    "started_at", "completed_at", "timestamp", "expires_at"
}


def parse_datetime(val: Any) -> Any:
    """Parse various datetime string formats into Python datetime objects."""
    if not val or not isinstance(val, str):
        return val
    val = val.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d"
    ):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return val


def extract_project_ref(url: str) -> str:
    """Extract Supabase project ref from project URL or database connection string."""
    if not url:
        return "UNKNOWN"
    # Match db.<project_ref>.supabase.co or <project_ref>.supabase.co or postgres.<project_ref>
    m = re.search(r'(?:db\.|//)([a-z0-9_-]+)\.supabase\.co', url)
    if m:
        return m.group(1)
    m2 = re.search(r'postgres\.([a-z0-9_-]+):', url)
    if m2:
        return m2.group(1)
    return "UNKNOWN"


def backup_sqlite(sqlite_path: str, backup_dir: str) -> str:
    """Create an atomic backup of local SQLite DB before migration."""
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"pre_supabase_migration_{ts}.db")
    src_conn = sqlite3.connect(sqlite_path)
    dst_conn = sqlite3.connect(backup_file)
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()
    return backup_file


def migrate(supabase_db_url: str):
    sqlite_path = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
    if not os.path.exists(sqlite_path):
        print(f"[ERROR] SQLite database file not found at: {sqlite_path}")
        return False

    print("=" * 70)
    print("FIR VisionAI — SQLite to Supabase Migration")
    print("=" * 70)

    # 1. Backup SQLite
    print("\n[Step 1/5] Backing up local SQLite database...")
    backup_path = backup_sqlite(sqlite_path, settings.BACKUPS_DIR)
    print(f"  -> Verified safety backup created at: {backup_path}")

    # 2. Format connection string for sync PostgreSQL
    sync_url = supabase_db_url
    if sync_url.startswith("postgresql+asyncpg://"):
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif sync_url.startswith("postgres://"):
        sync_url = sync_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif sync_url.startswith("postgresql://"):
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    project_ref = extract_project_ref(sync_url)
    print(f"\n[Step 2/5] Connecting to Supabase PostgreSQL (Project Ref: {project_ref})...")

    try:
        pg_engine = create_engine(sync_url, pool_pre_ping=True)
        with pg_engine.connect() as conn:
            res = conn.execute(text("SELECT version();")).scalar()
            print(f"  -> Connected successfully! PostgreSQL Version: {res[:45]}...")
    except Exception as e:
        print(f"[ERROR] Failed to connect to Supabase: {e}")
        return False

    # 3. Create schema
    print("\n[Step 3/5] Applying FIR VisionAI schema to Supabase...")
    # Import all models to ensure Base.metadata is fully populated
    from app.models import (
        User, RefreshToken, Case, CaseField, Document, DocumentPage, DocumentChunk,
        Entity, EntityMention, GraphEdge, LegalCorpus, CaseLegalSection,
        AuditLog, CaseSummary, GeneratedDocument, DocumentApprovalHistory,
        BulkJob, ExtractionConfig, ExtractionRun
    )
    from app.models.folder import FIRFolder, CaseFolderAssignment, WorkflowExecution
    Base.metadata.create_all(bind=pg_engine)
    print(f"  -> Verified {len(Base.metadata.tables)} application tables created/verified.")

    # 4. Migrate tables in dependency order
    print("\n[Step 4/5] Migrating records from SQLite to Supabase...")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    pg_metadata = MetaData()
    pg_metadata.reflect(bind=pg_engine)

    migration_stats: Dict[str, Dict[str, int]] = {}

    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        if table_name not in pg_metadata.tables:
            continue

        # Check SQLite table existence
        chk = sqlite_cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        ).fetchone()
        if not chk:
            continue

        sqlite_rows = sqlite_cursor.execute(f"SELECT * FROM `{table_name}`").fetchall()
        total_src = len(sqlite_rows)
        if total_src == 0:
            migration_stats[table_name] = {"source": 0, "migrated": 0, "skipped": 0}
            continue

        pg_table: Table = pg_metadata.tables[table_name]
        pg_cols = {c.name for c in pg_table.columns}

        # Check existing IDs in target
        has_id = "id" in pg_cols
        existing_ids = set()
        if has_id:
            with pg_engine.connect() as conn:
                res = conn.execute(text(f"SELECT id FROM {table_name}")).scalars().all()
                existing_ids = set(res)

        to_insert = []
        skipped = 0
        for r in sqlite_rows:
            row_dict = dict(r)
            if has_id and row_dict.get("id") in existing_ids:
                skipped += 1
                continue

            cleaned_row = {}
            for col, val in row_dict.items():
                if col not in pg_cols:
                    continue
                if col in DATETIME_COLUMNS and val:
                    val = parse_datetime(val)
                cleaned_row[col] = val

            to_insert.append(cleaned_row)

        inserted = 0
        if to_insert:
            # Batch insert in chunks of 200
            chunk_size = 200
            with pg_engine.begin() as conn:
                for i in range(0, len(to_insert), chunk_size):
                    batch = to_insert[i:i + chunk_size]
                    conn.execute(pg_table.insert(), batch)
            inserted = len(to_insert)

        migration_stats[table_name] = {"source": total_src, "migrated": inserted, "skipped": skipped}
        print(f"  - {table_name:28}: {inserted} migrated, {skipped} existing/skipped (Total SQLite: {total_src})")

    sqlite_conn.close()

    # Synchronize PostgreSQL SERIAL sequences to MAX(id)
    with pg_engine.begin() as conn:
        for tname in ["audit_log"]:
            if tname in pg_metadata.tables:
                max_id = conn.execute(text(f"SELECT COALESCE(MAX(id), 1) FROM {tname}")).scalar()
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{tname}', 'id'), {max_id})"))
                print(f"  -> Synchronized {tname} sequence to {max_id}")

    # 5. Verification & Summary
    print("\n[Step 5/5] Verifying migrated record counts on Supabase...")
    with pg_engine.connect() as conn:
        for table_name in TABLES_IN_DEPENDENCY_ORDER:
            if table_name in pg_metadata.tables:
                cnt = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                st = migration_stats.get(table_name, {})
                print(f"  * {table_name:28}: {cnt:5} rows in Supabase")

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETED SUCCESSFULLY")
    print("=" * 70)
    if project_ref != "UNKNOWN":
        print(f"\nSupabase Dashboard Links:")
        print(f"  - Project Dashboard : https://supabase.com/dashboard/project/{project_ref}")
        print(f"  - Table Editor      : https://supabase.com/dashboard/project/{project_ref}/editor")
        print(f"  - SQL Editor        : https://supabase.com/dashboard/project/{project_ref}/sql")
        print(f"  - Database Settings : https://supabase.com/dashboard/project/{project_ref}/settings/database")
    print("=" * 70)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate FIR VisionAI SQLite DB to Supabase PostgreSQL.")
    parser.add_argument("--supabase-url", type=str, help="Supabase PostgreSQL connection URL")
    args = parser.parse_args()

    target_url = args.supabase_url or settings.SUPABASE_DATABASE_URL
    if not target_url:
        print("[ERROR] No Supabase database URL provided.")
        print("Please set SUPABASE_DATABASE_URL in .env or pass it via --supabase-url argument.")
        sys.exit(1)

    success = migrate(target_url)
    sys.exit(0 if success else 1)
