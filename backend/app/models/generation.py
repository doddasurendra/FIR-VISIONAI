from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
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

class GeneratedDocument(Base, TimeStampedModel):
    __tablename__ = "generated_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False) # CASE_DIARY, CHARGESHEET, CASE_SUMMARY
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
