from sqlalchemy import Column, String, Boolean, DateTime
from datetime import datetime
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class User(Base, TimeStampedModel):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # STATION, DISTRICT, STATE
    role = Column(String(20), nullable=False, default="STATION")
    district = Column(String(50), nullable=False)   # e.g., Kurnool, Guntur, Visakhapatnam
    station = Column(String(100), nullable=True)    # e.g., Kurnool Town Station
    badge_number = Column(String(50), nullable=True)
    designation = Column(String(50), default="Excise Sub-Inspector")
    department = Column(String(100), default="AP Prohibition & Excise Department", nullable=True)
    approval_status = Column(String(20), default="APPROVED", nullable=False) # APPROVED, PENDING_APPROVAL, REJECTED

    is_active = Column(Boolean, default=True, nullable=False)
    last_login = Column(DateTime, nullable=True)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
