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
