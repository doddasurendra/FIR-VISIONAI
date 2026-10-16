from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from datetime import datetime
from ..database import Base
from .base import generate_uuid, TimeStampedModel


class FIRFolder(Base, TimeStampedModel):
    """Configurable FIR category folders for grouping and browsing cases."""
    __tablename__ = "fir_folders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    slug = Column(String(80), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    color_code = Column(String(20), default="#0f5132")   # Tailwind/hex color
    icon_name = Column(String(50), default="Folder")       # Lucide icon name
    group_label = Column(String(50), default="FIR Types")  # Grouping header
    parent_id = Column(String(36), ForeignKey("fir_folders.id", ondelete="SET NULL"), nullable=True)
    is_restricted = Column(Boolean, default=False)         # Requires elevated role
    required_role = Column(String(20), nullable=True)      # STATION / DISTRICT / STATE
    is_system = Column(Boolean, default=True)              # System-seeded, not deletable
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)


class CaseFolderAssignment(Base, TimeStampedModel):
    """Many-to-many link between a Case and FIRFolder categories."""
    __tablename__ = "case_folder_assignments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(String(36), ForeignKey("fir_folders.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(String(36), nullable=True)         # User id
    is_primary = Column(Boolean, default=False)             # Primary classification folder
    confidence_score = Column(Float, default=1.0)           # 0.0–1.0 auto-classification score
    assignment_source = Column(String(20), default="MANUAL")  # AUTO / MANUAL
    notes = Column(Text, nullable=True)


class WorkflowExecution(Base, TimeStampedModel):
    """Tracks 4-stage automated intelligence workflow per case."""
    __tablename__ = "workflow_executions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    # INTAKE / CLASSIFICATION / ENTITY_EXTRACTION / AI_SUMMARY
    stage = Column(String(30), nullable=False, index=True)
    # PENDING / RUNNING / COMPLETED / FAILED / SKIPPED
    status = Column(String(20), default="PENDING", nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    result_summary = Column(Text, nullable=True)  # JSON string of stage output
