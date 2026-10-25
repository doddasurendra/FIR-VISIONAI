import pytest
import os
import hashlib
from app.services.storage import storage_service
from app.database import get_database_status
from app.config import settings

def test_storage_service_status_diagnostics():
    """Verify that storage_service reports clear status diagnostics."""
    status = storage_service.get_status()
    assert "primary_backend" in status
    assert "cloud_configured" in status
    assert "cloud_status" in status
    assert status["bucket_name"] == "evidence"

def test_storage_service_sha256_computation():
    """Verify SHA-256 calculation matches standard hashlib."""
    sample_content = b"%PDF-1.4 Test FIR VisionAI Grounded Document"
    calculated_hash = storage_service.compute_sha256(sample_content)
    expected_hash = hashlib.sha256(sample_content).hexdigest()
    assert calculated_hash == expected_hash

@pytest.mark.asyncio
async def test_storage_service_local_fallback_upload_and_read():
    """Verify that file upload safely stores file and can be retrieved."""
    sample_pdf_bytes = b"%PDF-1.5 \n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    filename = "test_case_fir.pdf"

    upload_result = await storage_service.upload_file(
        file_bytes=sample_pdf_bytes,
        filename=filename,
        content_type="application/pdf"
    )

    assert upload_result["file_hash"] == storage_service.compute_sha256(sample_pdf_bytes)
    assert upload_result["file_size"] == len(sample_pdf_bytes)
    assert os.path.exists(upload_result["stored_path"])

    # Retrieve bytes
    retrieved_bytes = await storage_service.get_file_bytes(
        stored_path=upload_result["stored_path"],
        storage_type=upload_result["storage_type"]
    )
    assert retrieved_bytes == sample_pdf_bytes

    # Clean up test file
    try:
        os.remove(upload_result["stored_path"])
    except Exception:
        pass

def test_database_status_diagnostics():
    """Verify database status returns engine information."""
    db_status = get_database_status()
    assert "engine_type" in db_status
    assert "is_postgres" in db_status
    assert "status" in db_status

def test_supabase_sql_schema_completeness():
    """Verify that scripts/supabase_schema.sql defines all required core tables and RLS."""
    schema_path = os.path.join(settings.BASE_DIR, "scripts", "supabase_schema.sql")
    assert os.path.exists(schema_path), "Supabase schema SQL file must exist"

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # Core tables
    required_tables = [
        "users",
        "refresh_tokens",
        "cases",
        "case_fields",
        "documents",
        "document_pages",
        "document_chunks",
        "entities",
        "entity_mentions",
        "graph_edges",
        "legal_corpus",
        "case_legal_sections",
        "audit_log",
        "case_summaries",
        "generated_documents",
        "bulk_jobs"
    ]
    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"Missing table {table} in schema"

    # Row Level Security
    assert "ENABLE ROW LEVEL SECURITY" in sql
    # Storage bucket
    assert "storage.buckets" in sql
