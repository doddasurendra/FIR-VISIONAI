from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine, text
import sqlite3
import os
import re
from .config import settings

Base = declarative_base()

# Determine effective database URLs (Supabase PostgreSQL primary, SQLite offline fallback)
raw_db_url = settings.SUPABASE_DATABASE_URL or settings.DATABASE_URL
raw_sync_url = settings.SUPABASE_DATABASE_URL or settings.SYNC_DATABASE_URL

is_postgres = raw_db_url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://"))

if is_postgres:
    # Format asyncpg URL for async engine
    if raw_db_url.startswith("postgres://"):
        async_db_url = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif raw_db_url.startswith("postgresql://"):
        async_db_url = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        async_db_url = raw_db_url

    # Format standard URL for sync engine
    if raw_sync_url.startswith("postgresql+asyncpg://"):
        sync_db_url = raw_sync_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    elif raw_sync_url.startswith("postgres://"):
        sync_db_url = raw_sync_url.replace("postgres://", "postgresql://", 1)
    else:
        sync_db_url = raw_sync_url

    engine = create_async_engine(
        async_db_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True
    )

    sync_engine = create_engine(
        sync_db_url,
        echo=False,
        pool_pre_ping=True
    )
else:
    # SQLite local engine for development and offline testing
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )

    sync_engine = create_engine(
        settings.SYNC_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def init_fts5(conn: sqlite3.Connection):
    """Initialize SQLite FTS5 tables for document chunks and case facts in local mode."""
    cursor = conn.cursor()
    
    # FTS5 for document chunks (PDF-only RAG)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            document_id UNINDEXED,
            physical_page_number UNINDEXED,
            chunk_text,
            tokenize='porter unicode61'
        );
    """)
    
    # FTS5 for case narrative and facts
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
            case_id UNINDEXED,
            fir_number,
            district,
            station,
            offence_nature,
            contraband_type,
            accused_names,
            seized_details,
            narrative,
            tokenize='porter unicode61'
        );
    """)

    # FTS5 for legal corpus
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS legal_corpus_fts USING fts5(
            corpus_id UNINDEXED,
            act_name,
            section_number,
            section_title,
            full_text,
            ingredients,
            tokenize='porter unicode61'
        );
    """)
    conn.commit()

def setup_database_sync():
    """Create all tables and initialize FTS5 synchronously."""
    Base.metadata.create_all(bind=sync_engine)
    if not is_postgres:
        db_file = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
        if os.path.exists(os.path.dirname(db_file)):
            conn = sqlite3.connect(db_file)
            try:
                init_fts5(conn)
                # Ensure newly added classification columns exist on cases table
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(cases)")
                cols = {r[1] for r in cursor.fetchall()}
                if "classification_status" not in cols:
                    cursor.execute("ALTER TABLE cases ADD COLUMN classification_status VARCHAR(20) DEFAULT 'PENDING'")
                if "classification_confidence" not in cols:
                    cursor.execute("ALTER TABLE cases ADD COLUMN classification_confidence FLOAT")
                if "classification_source" not in cols:
                    cursor.execute("ALTER TABLE cases ADD COLUMN classification_source VARCHAR(20)")

                # Ensure Sarvam AI job and config tracking columns exist
                cursor.execute("PRAGMA table_info(documents)")
                doc_cols = {r[1] for r in cursor.fetchall()}
                if "sarvam_job_id" not in doc_cols:
                    cursor.execute("ALTER TABLE documents ADD COLUMN sarvam_job_id VARCHAR(100)")

                cursor.execute("PRAGMA table_info(extraction_runs)")
                run_cols = {r[1] for r in cursor.fetchall()}
                if "sarvam_job_id" not in run_cols:
                    cursor.execute("ALTER TABLE extraction_runs ADD COLUMN sarvam_job_id VARCHAR(100)")

                cursor.execute("PRAGMA table_info(extraction_configs)")
                cfg_cols = {r[1] for r in cursor.fetchall()}
                if "sarvam_config_id" not in cfg_cols:
                    cursor.execute("ALTER TABLE extraction_configs ADD COLUMN sarvam_config_id VARCHAR(100)")

                conn.commit()
            finally:
                conn.close()

def get_database_status() -> dict:
    """Return database engine status and active cloud connection type."""
    return {
        "engine_type": "SUPABASE_POSTGRESQL" if is_postgres else "SQLITE_LOCAL",
        "is_postgres": is_postgres,
        "is_cloud_active": is_postgres,
        "status": "ONLINE" if is_postgres else "LOCAL_OFFLINE_READY"
    }
