from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey
from ..database import Base
from .base import generate_uuid, TimeStampedModel


class ExtractionConfig(Base, TimeStampedModel):
    """Configuration for AI Document Extraction schema and defensive prompt instructions."""
    __tablename__ = "extraction_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, default="FIR Standard Extraction")
    version = Column(Integer, nullable=False, default=1)
    schema_json = Column(Text, nullable=False)
    instructions = Column(Text, nullable=True)
    sarvam_config_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(String(36), nullable=True)


class ExtractionRun(Base, TimeStampedModel):
    """Tracks an extraction run for a specific document, including reviewed results."""
    __tablename__ = "extraction_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    config_id = Column(String(36), ForeignKey("extraction_configs.id", ondelete="SET NULL"), nullable=True)
    config_version = Column(Integer, default=1)
    status = Column(String(20), default="PENDING", nullable=False, index=True)  # PENDING, PROCESSING, COMPLETED, FAILED
    raw_extracted_json = Column(Text, nullable=True)
    reviewed_extracted_json = Column(Text, nullable=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    sarvam_job_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=True)
