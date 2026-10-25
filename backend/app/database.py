from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine, text, inspect
import sqlite3
import os
import re
import logging
from .config import settings

logger = logging.getLogger(__name__)

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
        sync_db_url = raw_sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif raw_sync_url.startswith("postgres://"):
        sync_db_url = raw_sync_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif raw_sync_url.startswith("postgresql://"):
        sync_db_url = raw_sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        sync_db_url = raw_sync_url

    engine = create_async_engine(
        async_db_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_recycle=300,
        pool_pre_ping=True,
        connect_args={"server_settings": {"application_name": "fir_sahayak"}, "timeout": 15, "command_timeout": 30}
    )

    sync_engine = create_engine(
        sync_db_url,
        echo=False,
        pool_recycle=300,
        pool_pre_ping=True
    )
else:
    # SQLite local engine for development and offline testing
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30}
    )

    sync_engine = create_engine(
        settings.SYNC_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30}
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
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def init_fts5(conn: sqlite3.Connection):
    """Initialize SQLite FTS5 tables for document chunks and case facts in local mode."""
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    
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
    # Ensure all models are registered with Base.metadata before create_all
    from .models import (
        User, RefreshToken, Case, CaseField, Document, DocumentPage, DocumentChunk,
        Entity, EntityMention, GraphEdge, LegalCorpus, CaseLegalSection,
        AuditLog, CaseSummary, GeneratedDocument, DocumentApprovalHistory,
        BulkJob, ExtractionConfig, ExtractionRun
    )
    from .models.folder import FIRFolder, CaseFolderAssignment, WorkflowExecution
    Base.metadata.create_all(bind=sync_engine)
    # create_all never alters existing tables, so add any model columns they lack
    ensure_model_columns(sync_engine)
    if not is_postgres:
        db_file = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
        if os.path.exists(os.path.dirname(db_file)):
            conn = sqlite3.connect(db_file)
            try:
                init_fts5(conn)
            finally:
                conn.close()

def _column_default_sql(column, dialect) -> "str | None":
    """Render a model column's scalar Python default as a SQL literal, or None if it has none."""
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if isinstance(value, bool):
        if dialect.name == "sqlite":
            return "1" if value else "0"
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None

def ensure_model_columns(bind) -> list:
    """
    Additive schema sync: ADD COLUMN for every model column missing from an existing table.
    Never drops, renames or retypes anything. NOT NULL is applied only when a default exists,
    so existing rows are always back-filled safely. Returns the list of columns added.
    """
    inspector = inspect(bind)
    dialect = bind.dialect
    added = []
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or column.primary_key:
                    continue
                default_sql = _column_default_sql(column, dialect)
                ddl = (
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                    f"{column.type.compile(dialect=dialect)}"
                )
                if default_sql is not None:
                    ddl += f" DEFAULT {default_sql}"
                    if not column.nullable:
                        ddl += " NOT NULL"
                conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
    if added:
        logger.info(f"Schema sync added {len(added)} missing column(s): {', '.join(added)}")
    return added

def get_database_status() -> dict:
    """Return database engine status and active cloud connection type."""
    return {
        "engine_type": "SUPABASE_POSTGRESQL" if is_postgres else "SQLITE_LOCAL",
        "is_postgres": is_postgres,
        "is_cloud_active": is_postgres,
        "status": "ONLINE" if is_postgres else "LOCAL_OFFLINE_READY"
    }
