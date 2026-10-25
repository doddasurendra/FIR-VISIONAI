from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from datetime import datetime
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class Document(Base, TimeStampedModel):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    original_filename = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True) # SHA-256 immutable digest
    mime_type = Column(String(100), default="application/pdf")
    physical_page_count = Column(Integer, default=1)
    is_scanned = Column(Boolean, default=False)
    
    # Ingestion Status: PENDING, PROCESSING, COMPLETED, FAILED
    ingestion_status = Column(String(20), default="PENDING", index=True, nullable=False)
    sarvam_job_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=False)

    # Knowledge Base & Document Classification
    doc_category = Column(String(50), default="FIR", index=True, nullable=False)
    # FIR, HISTORICAL_FIR, LEGAL_ACT, CIRCULAR, SEIZURE_REPORT, INVESTIGATION_GUIDE, REFERENCE, EVIDENCE
    document_title = Column(String(255), nullable=True)
    source_department = Column(String(100), nullable=True)
    version_date = Column(String(50), nullable=True)
    district = Column(String(50), index=True, nullable=True)
    station = Column(String(100), nullable=True)
    is_verified_official = Column(Boolean, default=False, nullable=False)

    # Document Lifecycle & Soft-Delete / Archival
    is_archived = Column(Boolean, default=False, index=True, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    archived_by = Column(String(36), nullable=True)
    archive_reason = Column(Text, nullable=True)

    # Document Replacement & Version Lineage
    replaced_by_id = Column(String(36), nullable=True)
    replacement_reason = Column(Text, nullable=True)
    replaces_id = Column(String(36), nullable=True)

    # Source provenance for legal and departmental documents
    source_type = Column(String(20), default="UNVERIFIED", index=True, nullable=True)
    # OFFICIAL (verified government source), SECONDARY, SYNTHETIC (demo/sample), UNVERIFIED
    record_kind = Column(String(20), nullable=True)  # FIRs/evidence: ACTUAL, REDACTED, SYNTHETIC
    source_url = Column(String(500), nullable=True)
    issuing_authority = Column(String(255), nullable=True)
    reference_number = Column(String(100), nullable=True)  # Act / order / notification / circular number
    jurisdiction = Column(String(100), nullable=True)     # e.g. Central, Andhra Pradesh
    publication_date = Column(String(30), nullable=True)
    commencement_date = Column(String(30), nullable=True)
    legal_status = Column(String(20), nullable=True, index=True)
    # IN_FORCE, AMENDED, REPEALED, SUPERSEDED, HISTORICAL, UNKNOWN
    language = Column(String(20), nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    verification_note = Column(Text, nullable=True)

    # Search index state (separate from ingestion_status, which tracks text extraction)
    index_status = Column(String(20), default="NOT_INDEXED", index=True, nullable=True)
    # NOT_INDEXED, INDEXED, PARTIALLY_INDEXED, NEEDS_REVIEW, FAILED
    indexed_chunk_count = Column(Integer, default=0, nullable=True)
    embedded_chunk_count = Column(Integer, default=0, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    indexed_at = Column(DateTime, nullable=True)

class DocumentPage(Base, TimeStampedModel):
    __tablename__ = "document_pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    physical_page_number = Column(Integer, nullable=False) # 1-indexed physical PDF page
    printed_page_number = Column(Integer, nullable=True)   # Printed page number on physical FIR if different
    raw_text = Column(Text, nullable=True)
    ocr_applied = Column(Boolean, default=False)
    ocr_confidence = Column(Float, default=1.0)
    is_unreadable = Column(Boolean, default=False)

class DocumentChunk(Base, TimeStampedModel):
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    physical_page_number = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    char_start = Column(Integer, default=0)
    char_end = Column(Integer, default=0)
    embedding_json = Column(Text, nullable=True) # Vector embedding JSON array
    # Structural location inside legal/departmental texts, e.g. "Section 303" / "Article 21"
    section_ref = Column(String(100), nullable=True, index=True)
    section_title = Column(String(300), nullable=True)

class IngestionJob(Base, TimeStampedModel):
    """One ingestion or re-processing attempt for a document, kept for status, failures and retries."""
    __tablename__ = "ingestion_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="QUEUED", index=True, nullable=False)
    # QUEUED, PROCESSING, INDEXED, PARTIALLY_INDEXED, NEEDS_REVIEW, FAILED
    stage = Column(String(30), nullable=True)  # VALIDATE, EXTRACT, CHUNK, EMBED, INDEX, VERIFY
    trigger = Column(String(30), nullable=True)  # UPLOAD, RETRY, IMPORT
    pages_total = Column(Integer, default=0)
    pages_with_text = Column(Integer, default=0)
    chunks_written = Column(Integer, default=0)
    chunks_embedded = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)
