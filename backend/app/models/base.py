import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from ..database import Base

def generate_uuid():
    return str(uuid.uuid4())

class TimeStampedModel:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
