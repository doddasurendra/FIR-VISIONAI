from sqlalchemy import Column, String, Integer, Text
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class BulkJob(Base, TimeStampedModel):
    __tablename__ = "bulk_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False) # CSV, JSON, PDF
    file_hash = Column(String(64), nullable=False)
    
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    
    # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    status = Column(String(20), default="PENDING", index=True, nullable=False)
    errors_json = Column(Text, default="[]")
    user_id = Column(String(36), nullable=False)
