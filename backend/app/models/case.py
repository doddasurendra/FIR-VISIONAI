from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from datetime import datetime
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class Case(Base, TimeStampedModel):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    fir_number = Column(String(100), unique=True, index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    
    # Jurisdiction data scoping
    district = Column(String(50), index=True, nullable=False)
    station = Column(String(100), index=True, nullable=False)
    mandal = Column(String(50), nullable=True)
    village = Column(String(50), nullable=True)
    location_description = Column(Text, nullable=True)

    # Dates
    offence_date = Column(DateTime, nullable=True)
    detection_date = Column(DateTime, nullable=True)
    registration_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Offence Details
    offence_nature = Column(String(150), nullable=False)  # e.g., Illicit Distillation, NDPS Transport, Unlawful Possession
    offence_category = Column(String(100), nullable=True) # Section 27 classification: EXCISE, THEFT, ACCIDENT, etc.
    contraband_type = Column(String(100), nullable=True)  # e.g., ID Liquor, Ganja (Cannabis), Non-Duty Paid Liquor
    seized_quantity = Column(Float, nullable=True)
    seized_unit = Column(String(20), nullable=True)       # Litres, Kgs, Bottles, Packets
    vehicle_details = Column(String(200), nullable=True)   # e.g., Auto AP21TY4567, Hero Splendor AP04AB1234
    
    # Officers & Witnesses
    seizing_officer_name = Column(String(100), nullable=True)
    seizing_officer_rank = Column(String(50), nullable=True)
    witnesses_summary = Column(Text, nullable=True)
    narrative = Column(Text, nullable=True)

    # Status: DRAFT, IN_REVIEW, APPROVED, ARCHIVED
    status = Column(String(20), default="DRAFT", index=True, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    archived_reason = Column(String(255), nullable=True)
    archived_by = Column(String(36), nullable=True)

    created_by = Column(String(36), nullable=False)

class CaseField(Base, TimeStampedModel):
    __tablename__ = "case_fields"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    field_name = Column(String(50), index=True, nullable=False)
    original_value = Column(Text, nullable=True)
    normalized_value = Column(Text, nullable=True)
    
    # Provenance
    source_doc_id = Column(String(36), nullable=True)
    page_number = Column(Integer, nullable=True)
    extraction_method = Column(String(50), default="GEMINI_VISION") # OCR, GEMINI_TEXT, GEMINI_VISION, MANUAL
    confidence_score = Column(Float, default=1.0) # 0.0 to 1.0

    # Human Verification
    verification_status = Column(String(20), default="UNVERIFIED") # UNVERIFIED, VERIFIED, OVERRIDDEN
    human_override_value = Column(Text, nullable=True)
    verified_by = Column(String(36), nullable=True)
    verified_at = Column(DateTime, nullable=True)
