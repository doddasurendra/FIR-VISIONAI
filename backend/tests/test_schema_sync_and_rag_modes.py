import os
import sqlite3
import sys

from sqlalchemy import create_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, ensure_model_columns  # noqa: E402
from app.services import rag_engine as rag_module  # noqa: E402
from app.services import retrieval as retrieval_module  # noqa: E402
from tests.test_backend import get_demo_fir_document  # noqa: E402


def test_schema_sync_adds_missing_columns_without_touching_rows(tmp_path):
    """Existing tables missing newer model columns are extended in place; rows are preserved."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    # A legacy 'documents' table that predates the Knowledge Base columns
    conn.execute(
        "CREATE TABLE documents (id VARCHAR(36) PRIMARY KEY, original_filename VARCHAR(255) NOT NULL, "
        "stored_path VARCHAR(512) NOT NULL, file_hash VARCHAR(64) NOT NULL, ingestion_status VARCHAR(20) NOT NULL, "
        "created_by VARCHAR(36) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
    )
    conn.execute(
        "INSERT INTO documents VALUES ('doc-1', 'old.pdf', '/tmp/old.pdf', 'abc', 'COMPLETED', 'u1', "
        "'2024-01-01 00:00:00', '2024-01-01 00:00:00')"
    )
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    added = ensure_model_columns(engine)

    assert "documents.doc_category" in added
    assert "documents.is_archived" in added
    assert ensure_model_columns(engine) == []  # idempotent

    conn = sqlite3.connect(db_file)
    row = conn.execute("SELECT original_filename, doc_category, is_archived FROM documents WHERE id='doc-1'").fetchone()
    conn.close()
    engine.dispose()
    assert row == ("old.pdf", "FIR", 0)  # existing row kept and back-filled with model defaults


def test_rag_without_fts_index_still_cites_page(client, station_token, monkeypatch):
    """
    Without SQLite FTS5 (PostgreSQL before the search migration), retrieval falls back to term
    matching on the chunk table and must still cite the correct page.
    """
    headers = {"Authorization": f"Bearer {station_token}"}
    target_doc = get_demo_fir_document(client, headers)

    async def no_pg_tsv(db):
        return False

    monkeypatch.setattr(retrieval_module, "_is_sqlite", lambda db: False)
    monkeypatch.setattr(retrieval_module, "_has_pg_tsv", no_pg_tsv)
    rag_module.RAGEngine.invalidate_cache(target_doc["id"])

    res = client.post(
        "/api/v1/rag/query",
        json={"query": "What quantity of contraband was seized?", "mode": "PDF_ONLY",
              "document_id": target_doc["id"], "language": "en"},
        headers=headers,
    )
    rag_module.RAGEngine.invalidate_cache(target_doc["id"])
    assert res.status_code == 200
    data = res.json()
    assert data["citations"], data
    assert any(c["physical_page_number"] == 2 for c in data["citations"])
