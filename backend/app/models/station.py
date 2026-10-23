"""
Verified Station Registry Model for Andhra Pradesh Prohibition & Excise Department.
Stores official station codes, coordinates, addresses, and jurisdictional attributes.
"""
from sqlalchemy import Column, String, Float, Text, Boolean, Integer, Index
from ..database import Base
from .base import generate_uuid, TimeStampedModel


class VerifiedStation(Base, TimeStampedModel):
    """
    Official Andhra Pradesh Prohibition & Excise Department Station Registry.
    Used for high-precision station location verification and boundary matching.
    """
    __tablename__ = "verified_stations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    station_code = Column(String(30), unique=True, nullable=False, index=True)
    station_name = Column(String(100), nullable=False, index=True)
    district = Column(String(50), nullable=False, index=True)
    mandal = Column(String(60), nullable=True)
    locality = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    state = Column(String(50), default="Andhra Pradesh", nullable=False)
    
    # Official WGS84 coordinates of the excise station premises
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    # Verification and operational flags
    is_active = Column(Boolean, default=True, index=True)
    verification_source = Column(String(80), default="AP_EXCISE_OFFICIAL_REGISTRY_2024")

    __table_args__ = (
        Index("idx_station_coords", "latitude", "longitude"),
        Index("idx_station_dist_name", "district", "station_name"),
    )
