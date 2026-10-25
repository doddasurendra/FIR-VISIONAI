from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Auth & User
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    role: str # STATION, DISTRICT, STATE
    district: str
    station: Optional[str] = None
    badge_number: Optional[str] = None
    designation: Optional[str] = "Excise Sub-Inspector"
    department: Optional[str] = "AP Prohibition & Excise Department"

class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: str
    full_name: str
    role: str = "STATION" # STATION, DISTRICT, STATE
    district: str
    station: Optional[str] = None
    badge_number: Optional[str] = None
    designation: Optional[str] = "Excise Sub-Inspector"
    department: Optional[str] = "AP Prohibition & Excise Department"

class PasswordResetRequest(BaseModel):
    new_password: str

class ApprovalDecisionRequest(BaseModel):
    decision: str # APPROVE or REJECT
    reason: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: str
    district: str
    station: Optional[str]
    badge_number: Optional[str]
    designation: Optional[str]
    department: Optional[str] = "AP Prohibition & Excise Department"
    approval_status: Optional[str] = "APPROVED"
    is_active: bool

# Case
class CaseCreate(BaseModel):
    fir_number: str
    year: int = 2024
    district: str
    station: str
    mandal: Optional[str] = None
    village: Optional[str] = None
    location_description: Optional[str] = None
    offence_date: Optional[str] = None
    detection_date: Optional[str] = None
    offence_nature: str
    contraband_type: Optional[str] = None
    seized_quantity: Optional[float] = 0.0
    seized_unit: Optional[str] = "Litres"
    vehicle_details: Optional[str] = None
    seizing_officer_name: Optional[str] = None
    seizing_officer_rank: Optional[str] = None
    narrative: Optional[str] = None
    accused_names: Optional[List[str]] = []
    document_ids: Optional[List[str]] = []

class CaseUpdate(BaseModel):
    offence_nature: Optional[str] = None
    contraband_type: Optional[str] = None
    seized_quantity: Optional[float] = None
    seized_unit: Optional[str] = None
    vehicle_details: Optional[str] = None
    narrative: Optional[str] = None
    status: Optional[str] = None

class CaseFieldOverride(BaseModel):
    human_override_value: str
    verification_status: str = "VERIFIED" # VERIFIED or OVERRIDDEN

# RAG
class RAGQueryRequest(BaseModel):
    query: str
    # Preferred: CURRENT_FIR, CASE, FIR_AND_LAW, KNOWLEDGE_BASE, ALL_AUTHORIZED
    scope: Optional[str] = None
    # Legacy alias for scope: PDF_ONLY, IMAGE_ONLY, KNOWLEDGE_BASE_ONLY, FIR_PLUS_LEGAL, CROSS_CASE
    mode: str = "PDF_ONLY"
    document_id: Optional[str] = None
    case_id: Optional[str] = None
    language: str = "en" # en, te, hi
    category: Optional[str] = "ALL" # ALL, LEGAL_ACT, CIRCULAR, SEIZURE_REPORT, INVESTIGATION_GUIDE, REFERENCE, HISTORICAL_FIR, EVIDENCE
    categories: Optional[List[str]] = None

class CitationItem(BaseModel):
    physical_page_number: Optional[int] = None
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    case_id: Optional[str] = None
    fir_number: Optional[str] = None
    district: Optional[str] = None
    station: Optional[str] = None
    source_label: str
    category: Optional[str] = None
    is_image: Optional[bool] = False
    evidence_excerpt: Optional[str] = None
    verification_status: Optional[str] = "VERIFIED_EXTRACTED_TEXT"
    model_config = {"extra": "allow"}

class RAGQueryResponse(BaseModel):
    answer: str
    citations: List[CitationItem] = []
    mode: str
    scope: Optional[str] = None
    not_found: Optional[bool] = False
    can_expand_scope: Optional[bool] = False
    suggested_scope: Optional[str] = None
    category: Optional[str] = None
    document_id: Optional[str] = None
    original_filename: Optional[str] = None
    is_aggregate_count: Optional[bool] = False
    count: Optional[int] = None
    total_sources_consulted: Optional[int] = None
    from_cache: Optional[bool] = None
    model_config = {"extra": "allow"}

# Legal
class OfficerLegalDecisionRequest(BaseModel):
    case_id: str
    legal_corpus_id: str
    decision: str # ACCEPTED, REJECTED
    reason: Optional[str] = "Verified against FIR facts and evidence"

# Entities
class EntityMergeRequest(BaseModel):
    primary_entity_id: str
    secondary_entity_id: str

# Generation
class DocumentGenerateRequest(BaseModel):
    case_id: str
    doc_type: str # CASE_DIARY, CHARGESHEET, CASE_SUMMARY
    language: str = "en" # en, te, hi

class DocumentApprovalRequest(BaseModel):
    action: str = "APPROVED" # APPROVED, REJECTED
    comments: Optional[str] = "Reviewed and approved by station officer"

# Incident Location & Geocoding
class IncidentLocationUpdate(BaseModel):
    incident_place_raw: Optional[str] = None
    incident_location_normalized: Optional[str] = None
    incident_village: Optional[str] = None
    incident_mandal: Optional[str] = None
    incident_district: Optional[str] = None
    incident_state: Optional[str] = "Andhra Pradesh"
    incident_pincode: Optional[str] = None
    incident_landmark: Optional[str] = None
    incident_latitude: Optional[float] = None
    incident_longitude: Optional[float] = None
    incident_location_geocoder_status: Optional[str] = None
    incident_location_verified: Optional[bool] = None
    notes: Optional[str] = None
    model_config = {"extra": "allow"}

class IncidentLocationResponse(BaseModel):
    case_id: str
    fir_number: Optional[str] = None
    station: Optional[str] = None
    district: Optional[str] = None
    incident_place_raw: Optional[str] = None
    incident_location_normalized: Optional[str] = None
    incident_village: Optional[str] = None
    incident_mandal: Optional[str] = None
    incident_district: Optional[str] = None
    incident_state: Optional[str] = "Andhra Pradesh"
    incident_pincode: Optional[str] = None
    incident_landmark: Optional[str] = None
    incident_latitude: Optional[float] = None
    incident_longitude: Optional[float] = None
    incident_location_confidence: Optional[float] = 1.0
    incident_location_source_doc_id: Optional[str] = None
    incident_location_source_page: Optional[int] = 1
    incident_location_evidence_passage: Optional[str] = None
    incident_location_geocoder_status: Optional[str] = "PENDING"
    incident_location_verified: Optional[bool] = False
    incident_location_verified_by: Optional[str] = None
    incident_location_verified_at: Optional[datetime] = None
    model_config = {"extra": "allow"}

class RegeocodeRequest(BaseModel):
    custom_address: Optional[str] = None
    model_config = {"extra": "allow"}
