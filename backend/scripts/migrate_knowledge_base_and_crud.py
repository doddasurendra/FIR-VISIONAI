"""
Supabase & SQLite Safe Migration:
Adds Knowledge Base & Document Replacement / Soft-Delete fields to documents and cases.
Preserves all existing data, foreign keys, and indexes.
"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import text
from app.database import sync_engine, SyncSessionLocal

def run_migration():
    print("================================================================")
    print("RUNNING INCREMENTAL MIGRATION FOR KNOWLEDGE BASE & CRUD MANAGEMENT")
    print("================================================================")
    
    session = SyncSessionLocal()
    try:
        # 1. Inspect existing columns in 'documents' table
        print("Checking 'documents' table columns...")
        inspector = sync_engine.dialect.name
        print(f"Dialect detected: {inspector}")

        doc_columns_to_add = [
            ("doc_category", "VARCHAR(50) DEFAULT 'FIR'"),
            ("document_title", "VARCHAR(255)"),
            ("source_department", "VARCHAR(100)"),
            ("version_date", "VARCHAR(50)"),
            ("district", "VARCHAR(50)"),
            ("station", "VARCHAR(100)"),
            ("is_verified_official", "BOOLEAN DEFAULT FALSE"),
            ("is_archived", "BOOLEAN DEFAULT FALSE"),
            ("archived_at", "TIMESTAMP"),
            ("archived_by", "VARCHAR(36)"),
            ("archive_reason", "TEXT"),
            ("replaced_by_id", "VARCHAR(36)"),
            ("replacement_reason", "TEXT"),
            ("replaces_id", "VARCHAR(36)")
        ]

        for col_name, col_type in doc_columns_to_add:
            try:
                sql = f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                if inspector == "sqlite":
                    sql = f"ALTER TABLE documents ADD COLUMN {col_name} {col_type};"
                session.execute(text(sql))
                session.commit()
                print(f"  + Added column 'documents.{col_name}'")
            except Exception as e:
                session.rollback()
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  . Column 'documents.{col_name}' already exists.")
                else:
                    print(f"  ! Column 'documents.{col_name}': {e}")

        # 2. Inspect existing columns in 'cases' table
        print("\nChecking 'cases' table columns...")
        case_columns_to_add = [
            ("archived_at", "TIMESTAMP"),
            ("deleted_at", "TIMESTAMP"),
            ("deletion_reason", "TEXT"),
            ("deleted_by", "VARCHAR(36)")
        ]

        for col_name, col_type in case_columns_to_add:
            try:
                sql = f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                if inspector == "sqlite":
                    sql = f"ALTER TABLE cases ADD COLUMN {col_name} {col_type};"
                session.execute(text(sql))
                session.commit()
                print(f"  + Added column 'cases.{col_name}'")
            except Exception as e:
                session.rollback()
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  . Column 'cases.{col_name}' already exists.")
                else:
                    print(f"  ! Column 'cases.{col_name}': {e}")

        # 3. Create indexes for performance
        indexes_to_create = [
            ("idx_docs_category", "documents", "doc_category"),
            ("idx_docs_archived", "documents", "is_archived"),
            ("idx_docs_district", "documents", "district"),
            ("idx_cases_archived", "cases", "is_archived")
        ]

        print("\nVerifying database indexes...")
        for idx_name, table_name, col_name in indexes_to_create:
            try:
                session.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({col_name});"))
                session.commit()
                print(f"  + Index '{idx_name}' verified.")
            except Exception as e:
                session.rollback()
                print(f"  . Index '{idx_name}': {e}")

        print("\nMIGRATION COMPLETED SUCCESSFULLY.")
    except Exception as e:
        session.rollback()
        print(f"Migration error: {e}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    run_migration()
