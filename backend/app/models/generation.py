from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from datetime import datetime
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class CaseSummary(Base, TimeStampedModel):
    __tablename__ = "case_summaries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_text = Column(Text, nullable=False)
    language = Column(String(10), default="en") # en, te, hi
    is_ai_generated = Column(Boolean, default=True)
    version = Column(Integer, default=1)

class FIRSummary(Base, TimeStampedModel):
    """
    AI summary of one historical FIR record in one language. A record is an FIR document
    (record_key "doc:<id>") or a registered case that has no FIR document ("case:<id>").
    source_hash fingerprints the source text and officer-approved fields the summary was built
    from, so a summary is known to be stale when its source changes.
    """
    __tablename__ = "fir_summaries"
    __table_args__ = (UniqueConstraint("record_key", "language", name="uq_fir_summaries_record_language"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    record_key = Column(String(50), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    language = Column(String(5), nullable=False)  # en, te, hi
    # COMPLETED, FAILED, NEEDS_REVIEW (source text missing or unusable: nothing was generated)
    status = Column(String(20), nullable=False, index=True)
    summary_json = Column(Text, nullable=True)
    summary_text = Column(Text, nullable=True)
    citations_json = Column(Text, nullable=True)
    source_hash = Column(String(64), nullable=True)
    source_chars = Column(Integer, nullable=True)
    model = Column(String(60), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    error_message = Column(Text, nullable=True)
    generated_by = Column(String(36), nullable=True)
    generated_at = Column(DateTime, nullable=True)


class GeneratedDocument(Base, TimeStampedModel):
    __tablename__ = "generated_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False) # CASE_DIARY, CHARGESHEET, CASE_SUMMARY
    language = Column(String(10), default="en", nullable=False) # en, te, hi
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    
    # Workflow status: DRAFT, IN_REVIEW, APPROVED
    status = Column(String(20), default="DRAFT", index=True, nullable=False)
    approved_by = Column(String(36), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    pdf_path = Column(String(500), nullable=True)
    created_by = Column(String(36), nullable=False)

class DocumentApprovalHistory(Base, TimeStampedModel):
    __tablename__ = "document_approval_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("generated_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    action = Column(String(30), nullable=False) # SUBMITTED, EDITED, APPROVED, REJECTED
    officer_id = Column(String(36), nullable=False)
    comments = Column(Text, nullable=True)
