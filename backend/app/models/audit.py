import hashlib
import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from ..database import Base
from .base import generate_uuid

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_uuid = Column(String(36), default=generate_uuid, unique=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor_id = Column(String(36), nullable=False)
    actor_username = Column(String(50), nullable=False)
    
    # Event details
    action_type = Column(String(50), index=True, nullable=False) # e.g. CASE_CREATED, FIELD_OVERRIDE, SECTION_ACCEPTED, DOCUMENT_APPROVED
    object_type = Column(String(50), index=True, nullable=False) # CASE, FIELD, ENTITY, LEGAL_SECTION, DOCUMENT
    object_id = Column(String(100), index=True, nullable=False)
    
    # State snapshots (deterministic JSON)
    before_state_json = Column(Text, nullable=True)
    after_state_json = Column(Text, nullable=True)
    client_ip = Column(String(50), nullable=True)
    
    # Cryptographic Hash Chaining for Tamper Evidence
    previous_entry_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False)

    @staticmethod
    def compute_hash(previous_hash: str, canonical_content: str) -> str:
        """Deterministic SHA-256 computation over chain link and canonical content."""
        hasher = hashlib.sha256()
        hasher.update((previous_hash + canonical_content).encode("utf-8"))
        return hasher.hexdigest()
