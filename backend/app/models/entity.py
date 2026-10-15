from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from ..database import Base
from .base import generate_uuid, TimeStampedModel

class Entity(Base, TimeStampedModel):
    __tablename__ = "entities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    canonical_name = Column(String(150), index=True, nullable=False)
    # PERSON, VEHICLE, LOCATION, ORGANIZATION
    entity_type = Column(String(30), index=True, nullable=False)
    
    # JSON encoded alternate spellings, aliases, transliterations
    aliases_json = Column(Text, default="[]")
    
    # JSON encoded attributes: age, address, father_name, registration_num, etc.
    attributes_json = Column(Text, default="{}")
    
    # Explainable Risk Scoring (based on repeat offenses, network centrality)
    risk_score = Column(Float, default=0.0)
    risk_factors_json = Column(Text, default="[]")
    
    # Entity Resolution / Deduplication
    is_canonical = Column(Boolean, default=True, index=True)
    merged_into_id = Column(String(36), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    verification_status = Column(String(20), default="CONFIRMED") # CONFIRMED, REVIEW_PENDING, REJECTED

class EntityMention(Base, TimeStampedModel):
    __tablename__ = "entity_mentions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    entity_id = Column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    mention_text = Column(String(150), nullable=False)
    role_in_case = Column(String(50), default="ACCUSED") # ACCUSED, WITNESS, SEIZING_OFFICER, OWNER
    source_doc_id = Column(String(36), nullable=True)
    page_number = Column(Integer, nullable=True)

class GraphEdge(Base, TimeStampedModel):
    __tablename__ = "graph_edges"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_entity_id = Column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    target_entity_id = Column(String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_type = Column(String(50), default="CO_ACCUSED") # CO_ACCUSED, VEHICLE_USED, ASSOCIATE
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    weight = Column(Float, default=1.0)
    community_id = Column(Integer, default=0) # Detected Louvain community ID
