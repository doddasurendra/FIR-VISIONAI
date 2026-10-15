from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine, text
import sqlite3
import os
from .config import settings

Base = declarative_base()

# Async engine for FastAPI requests
engine = create_async_engine(
    settings.DATABASE_URL,
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

# Synchronous engine for migrations, initial seeding, and backups
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
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
    """Initialize SQLite FTS5 tables for document chunks and case facts."""
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
    db_file = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_file)
    try:
        init_fts5(conn)
    finally:
        conn.close()
