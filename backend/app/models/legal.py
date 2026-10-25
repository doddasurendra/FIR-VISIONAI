from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class LegalCorpus(Base, TimeStampedModel):
    __tablename__ = "legal_corpus"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    act_name = Column(String(150), index=True, nullable=False) # e.g. Andhra Pradesh Excise Act, 1968, Bharatiya Nyaya Sanhita, 2023
    section_number = Column(String(50), index=True, nullable=False) # e.g. Section 34, Section 303(2)
    section_title = Column(String(200), nullable=False)
    full_text = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    
    # Statutory Elements / Ingredients needed for offence conviction
    essential_ingredients_json = Column(Text, default="[]")
    penalty_text = Column(Text, nullable=True)
    
    # Versioning & Dates
    effective_date = Column(String(30), nullable=True) # YYYY-MM-DD
    repeal_date = Column(String(30), nullable=True)    # If repealed by newer Act (e.g., IPC -> BNS)
    version = Column(String(20), default="1.0")
    jurisdiction = Column(String(50), default="Andhra Pradesh")
    
    # Authoritative Source provenance
    source_url = Column(String(300), nullable=True)
    source_gazette = Column(String(200), nullable=True)
    verification_status = Column(String(20), default="VERIFIED") # VERIFIED, DRAFT
    document_id = Column(String(36), nullable=True, index=True) # Linked Document id
    category = Column(String(50), nullable=True, index=True) # CONSTITUTIONAL, CRIMINAL_CENTRAL, CRIMINAL_HISTORICAL, SPECIAL_CENTRAL, STATE_EXCISE_PROHIBITION
    # OFFICIAL = text parsed from an official source file; others are summaries or demo content
    source_type = Column(String(20), nullable=True, index=True)  # OFFICIAL, SECONDARY, SYNTHETIC, UNVERIFIED
    physical_page_number = Column(Integer, nullable=True)  # Page of the linked document where the provision starts
    source_checksum = Column(String(64), nullable=True)    # SHA-256 of the official source file
    last_verified_at = Column(DateTime, nullable=True)

class CaseLegalSection(Base, TimeStampedModel):
    __tablename__ = "case_legal_sections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    legal_corpus_id = Column(String(36), ForeignKey("legal_corpus.id", ondelete="CASCADE"), nullable=False)
    act_name = Column(String(150), nullable=False)
    section_number = Column(String(50), nullable=False)
    section_title = Column(String(200), nullable=False)
    
    # Recommendation metadata
    recommendation_type = Column(String(30), default="AI_RECOMMENDED") # AI_RECOMMENDED, HUMAN_SELECTED
    confidence_score = Column(Float, default=0.85)
    matched_facts_json = Column(Text, default="[]")       # List of specific facts in FIR supporting this
    missing_elements_json = Column(Text, default="[]")    # Statutory elements not evidenced yet
    
    # Human Review & Officer Decision
    officer_decision = Column(String(20), default="PENDING") # ACCEPTED, REJECTED, PENDING
    decision_reason = Column(Text, nullable=True)
    reviewed_by = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
