"""
Migration: Add FIR application tracking fields to cases table.
Applies schema updates to Supabase PostgreSQL (primary) and SQLite (fallback).
Safe to run multiple times — adds columns only if they don't exist.
"""
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
env_path = os.path.join(backend_dir, "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

from sqlalchemy import create_engine, text, inspect
from app.config import settings

NEW_COLUMNS_PG = [
    ("application_date", "TIMESTAMP"),
    ("incident_date", "TIMESTAMP"),
    ("form_template", "VARCHAR(50)"),
    ("form_language", "VARCHAR(5)"),
    ("form_values_json", "TEXT"),
    ("application_status", "VARCHAR(20) DEFAULT 'DRAFT'"),
]

NEW_COLUMNS_SQLITE = [
    ("application_date", "DATETIME"),
    ("incident_date", "DATETIME"),
    ("form_template", "TEXT"),
    ("form_language", "TEXT"),
    ("form_values_json", "TEXT"),
    ("application_status", "TEXT DEFAULT 'DRAFT'"),
]

INDEXES = [
    ("ix_cases_application_date", "CREATE INDEX IF NOT EXISTS ix_cases_application_date ON cases(application_date)"),
    ("ix_cases_incident_date", "CREATE INDEX IF NOT EXISTS ix_cases_incident_date ON cases(incident_date)"),
    ("ix_cases_application_status", "CREATE INDEX IF NOT EXISTS ix_cases_application_status ON cases(application_status)"),
]

def migrate_engine(engine, is_pg: bool, label: str):
    print(f"\n--- Migrating {label} ---")
    columns = NEW_COLUMNS_PG if is_pg else NEW_COLUMNS_SQLITE
    with engine.connect() as conn:
        inspector = inspect(conn)
        if "cases" not in inspector.get_table_names():
            print("  [WARN] 'cases' table does not exist in this database yet.")
            return

        existing_cols = {col["name"] for col in inspector.get_columns("cases")}
        for col_name, col_type in columns:
            if col_name in existing_cols:
                print(f"  [SKIP] Column '{col_name}' already exists")
            else:
                alter_sql = f"ALTER TABLE cases ADD COLUMN {col_name} {col_type}"
                conn.execute(text(alter_sql))
                conn.commit()
                print(f"  [OK]   Added column '{col_name}'")

        existing_indexes = {idx["name"] for idx in inspector.get_indexes("cases")}
        for idx_name, idx_sql in INDEXES:
            if idx_name in existing_indexes:
                print(f"  [SKIP] Index '{idx_name}' already exists")
            else:
                try:
                    conn.execute(text(idx_sql))
                    conn.commit()
                    print(f"  [OK]   Created index '{idx_name}'")
                except Exception as e:
                    print(f"  [WARN] Index '{idx_name}': {e}")

def run():
    print("=" * 65)
    print("FIR VisionAI — Database Migration: FIR Application Fields")
    print("=" * 65)

    # 1. Supabase PostgreSQL
    supabase_url = settings.SUPABASE_DATABASE_URL or os.getenv("SUPABASE_DATABASE_URL")
    if supabase_url:
        sync_pg_url = supabase_url
        if sync_pg_url.startswith("postgresql+asyncpg://"):
            sync_pg_url = sync_pg_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif sync_pg_url.startswith("postgres://"):
            sync_pg_url = sync_pg_url.replace("postgres://", "postgresql+psycopg2://", 1)
        try:
            pg_engine = create_engine(sync_pg_url, pool_pre_ping=True)
            migrate_engine(pg_engine, is_pg=True, label="Supabase PostgreSQL (Cloud)")
        except Exception as e:
            print(f"  [ERROR] Could not connect to Supabase PostgreSQL: {e}")
    else:
        print("  [INFO] SUPABASE_DATABASE_URL not set.")

    # 2. Local SQLite
    sqlite_url = settings.SYNC_DATABASE_URL or os.getenv("SYNC_DATABASE_URL")
    if sqlite_url and sqlite_url.startswith("sqlite:"):
        try:
            sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
            migrate_engine(sqlite_engine, is_pg=False, label="SQLite Database (Local)")
        except Exception as e:
            print(f"  [ERROR] Could not connect to SQLite: {e}")

    print("\n" + "=" * 65)
    print("MIGRATION CHECK COMPLETE")
    print("=" * 65)

if __name__ == "__main__":
    run()
