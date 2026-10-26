import io
import re
import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import Response, FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.exc import SQLAlchemyError

from ...database import get_db
from ...models.user import User
from ...models.document import Document, DocumentPage
from ...models.case import Case, CaseField
from ...models.entity import Entity, EntityMention
from ...models.extraction import ExtractionConfig, ExtractionRun
from ...models.base import generate_uuid
from ...services.auth import get_current_user, enforce_data_scope
from ...services.audit import log_audit_event
from ...services.gemini import gemini_service
from ...services.sarvam_doc_ai import sarvam_doc_ai
from ...services.workflow import trigger_post_intake_workflow
from ...services.extraction_export import (
    generate_xlsx_bytes,
    generate_docx_bytes,
    generate_csv_bytes,
    generate_json_bytes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extraction", tags=["Multimodal Intake & Extraction"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class NarrativeExtractionRequest(BaseModel):
    narrative: str
    language: Optional[str] = "en"  # en, te, hi


class ConfigUpdateRequest(BaseModel):
    name: Optional[str] = None
    schema_content: str = Field(alias="schema_json")
    instructions: Optional[str] = None
    sarvam_config_id: Optional[str] = None
    model_config = {"populate_by_name": True}

    @property
    def schema_json(self) -> str:
        return self.schema_content


class SchemaValidateRequest(BaseModel):
    schema_content: str = Field(alias="schema_json")
    model_config = {"populate_by_name": True}

    @property
    def schema_json(self) -> str:
        return self.schema_content


class ExtractionRunRequest(BaseModel):
    document_id: str
    config_id: Optional[str] = None


class ReviewUpdateRequest(BaseModel):
    reviewed_data: Dict[str, Any]


class ConfirmCaseRequest(BaseModel):
    case_id: Optional[str] = None
    reviewed_data: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Default Schema & Extraction Helpers
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_FIR_SCHEMA = [
    # ─── Group 1: Document & FIR Identification ───
    {"id": "f_document_title", "key": "document_title", "label": "Document Title", "data_type": "string", "required": False, "description": "Header title of the document (e.g. First Information Report)", "validation_rules": ""},
    {"id": "f_document_type", "key": "document_type", "label": "Document Type", "data_type": "string", "required": False, "description": "Form type, e.g. Form II, FIR under Section 154 Cr.P.C. or Section 173 BNSS", "validation_rules": ""},
    {"id": "f_fir_number", "key": "fir_number", "label": "FIR / Crime Number", "data_type": "string", "required": True, "description": "Official Crime or FIR registration number", "validation_rules": "Format: [Number]/[Year]"},
    {"id": "f_year", "key": "year", "label": "Registration Year", "data_type": "number", "required": True, "description": "Four-digit registration year", "validation_rules": "Four digit year (e.g. 2024)"},
    {"id": "f_general_diary_reference", "key": "general_diary_reference", "label": "General Diary (GD) Ref", "data_type": "string", "required": False, "description": "General Diary entry number and time", "validation_rules": ""},
    {"id": "f_information_received_date", "key": "information_received_date", "label": "Information Received Date", "data_type": "string", "required": False, "description": "Date and time when initial information was received at PS", "validation_rules": ""},
    {"id": "f_offence_date", "key": "offence_date", "label": "Date & Time of Offence", "data_type": "string", "required": False, "description": "Date and approximate time when offence occurred", "validation_rules": ""},
    {"id": "f_registration_date", "key": "registration_date", "label": "FIR Registration Date", "data_type": "string", "required": False, "description": "Date and time when FIR was officially registered", "validation_rules": ""},
    {"id": "f_district", "key": "district", "label": "District", "data_type": "string", "required": True, "description": "Police / Excise district jurisdiction name", "validation_rules": "Valid district name"},
    {"id": "f_station", "key": "station", "label": "Police / Excise Station", "data_type": "string", "required": True, "description": "Jurisdiction police/excise station name", "validation_rules": ""},
    {"id": "f_place_of_occurrence", "key": "place_of_occurrence", "label": "Place of Occurrence", "data_type": "string", "required": False, "description": "Specific street, village, landmark or coordinates of offence", "validation_rules": ""},
    {"id": "f_type_of_information", "key": "type_of_information", "label": "Type of Information", "data_type": "string", "required": False, "description": "Written, Oral, Secret Information, Panchanama, etc.", "validation_rules": ""},

    # ─── Group 2: People & Contact Details ───
    {"id": "f_complainant_name", "key": "complainant_name", "label": "Complainant / Informant Name", "data_type": "string", "required": False, "description": "Full name of the complainant or seizing officer", "validation_rules": ""},
    {"id": "f_complainant_parentage", "key": "complainant_parentage", "label": "Complainant Father/Husband Name", "data_type": "string", "required": False, "description": "Father's or husband's name of the complainant", "validation_rules": ""},
    {"id": "f_complainant_age", "key": "complainant_age", "label": "Complainant Age", "data_type": "string", "required": False, "description": "Age of complainant or date of birth", "validation_rules": ""},
    {"id": "f_complainant_address", "key": "complainant_address", "label": "Complainant Residential Address", "data_type": "string", "required": False, "description": "Residential address, house number, village, mandal", "validation_rules": ""},
    {"id": "f_complainant_occupation", "key": "complainant_occupation", "label": "Complainant Occupation", "data_type": "string", "required": False, "description": "Occupation, designation, or department of complainant", "validation_rules": ""},
    {"id": "f_complainant_nationality", "key": "complainant_nationality", "label": "Complainant Nationality", "data_type": "string", "required": False, "description": "Nationality (e.g. Indian)", "validation_rules": ""},
    {"id": "f_complainant_contact", "key": "complainant_contact", "label": "Complainant Phone / Contact", "data_type": "string", "required": False, "description": "Mobile number or contact phone of complainant", "validation_rules": ""},
    {"id": "f_accused_names", "key": "accused_names", "label": "Accused Persons", "data_type": "array", "required": False, "description": "List of accused person names", "validation_rules": ""},
    {"id": "f_accused_details", "key": "accused_details", "label": "Accused Particulars / Descriptions", "data_type": "array", "required": False, "description": "Parentage, age, alias, address or description of accused", "validation_rules": ""},
    {"id": "f_witness_names", "key": "witness_names", "label": "Panch / Witness Persons", "data_type": "array", "required": False, "description": "Names of panchas, independent witnesses, or mediators", "validation_rules": ""},
    {"id": "f_victim_names", "key": "victim_names", "label": "Victim / Injured Persons", "data_type": "array", "required": False, "description": "Names of victims, deceased, or injured persons", "validation_rules": ""},
    {"id": "f_other_named_persons", "key": "other_named_persons", "label": "Other Mentioned Persons", "data_type": "array", "required": False, "description": "Any other individuals referenced in the FIR narrative", "validation_rules": ""},

    # ─── Group 3: Incident & Evidence Details ───
    {"id": "f_offence_nature", "key": "offence_nature", "label": "Offence Nature / Gist", "data_type": "string", "required": True, "description": "Brief gist or category of alleged criminal act", "validation_rules": ""},
    {"id": "f_brief_facts", "key": "brief_facts", "label": "Brief Facts of the Case", "data_type": "string", "required": False, "description": "Summary of facts leading to registration of FIR", "validation_rules": ""},
    {"id": "f_incident_narrative", "key": "incident_narrative", "label": "Incident Narrative / Allegation", "data_type": "string", "required": False, "description": "Detailed narration of events and panchanama sequence", "validation_rules": ""},
    {"id": "f_reported_offences_acts", "key": "reported_offences_acts", "label": "Reported Acts / Enactments", "data_type": "string", "required": False, "description": "Acts mentioned (e.g. AP Excise Act 1968, NDPS Act 1985, BNS 2023, IPC)", "validation_rules": ""},
    {"id": "f_property_loss_amount", "key": "property_loss_amount", "label": "Property Loss / Stolen Value", "data_type": "string", "required": False, "description": "Monetary value of loss, theft, fraud, or damage in Rs.", "validation_rules": ""},
    {"id": "f_vehicle_details", "key": "vehicle_details", "label": "Vehicle Details", "data_type": "string", "required": False, "description": "Registration number, vehicle type, make, engine/chassis number", "validation_rules": ""},
    {"id": "f_contraband_type", "key": "contraband_type", "label": "Contraband / Seized Property", "data_type": "string", "required": False, "description": "Type of seized contraband, property, weapon, or cash", "validation_rules": ""},
    {"id": "f_seized_quantity", "key": "seized_quantity", "label": "Seized Quantity", "data_type": "number", "required": False, "description": "Numerical quantity of seized goods", "validation_rules": "Numeric value"},
    {"id": "f_seized_unit", "key": "seized_unit", "label": "Quantity Unit", "data_type": "string", "required": False, "description": "Unit of measurement (e.g. Litres, Kgs, Grams, Packets, Bottles)", "validation_rules": ""},
    {"id": "f_seized_property_details", "key": "seized_property_details", "label": "Seized Property Particulars", "data_type": "string", "required": False, "description": "Complete description of all articles seized under panchanama", "validation_rules": ""},
    {"id": "f_digital_identifiers", "key": "digital_identifiers", "label": "Digital Identifiers / Phone / UPI", "data_type": "string", "required": False, "description": "Mobile numbers, email IDs, IMEI, bank/UPI handles", "validation_rules": ""},
    {"id": "f_law_sections", "key": "law_sections", "label": "Statutory Law Sections", "data_type": "array", "required": False, "description": "List of legal sections invoked (e.g. Section 34(a) AP Excise Act)", "validation_rules": ""},
    {"id": "f_investigating_officer", "key": "investigating_officer", "label": "Investigating Officer (IO)", "data_type": "string", "required": False, "description": "Name, rank and general number of officer taking up investigation", "validation_rules": ""},
    {"id": "f_officer_signature_details", "key": "officer_signature_details", "label": "Officer Signature & Seal", "data_type": "string", "required": False, "description": "Signature details, stamp, designation, and signing date", "validation_rules": ""},
]

DEFAULT_INSTRUCTIONS = (
    "CRITICAL DEFENSIVE EXTRACTION RULES:\n"
    "1. STRICT DOCUMENT GROUNDING: Extract ONLY information explicitly present in this document. Never invent missing details.\n"
    "2. ZERO ASSUMPTIONS: Do not assume this is an excise or liquor offence unless explicitly stated in the document text.\n"
    "3. UNKNOWN / MISSING FIELDS: If any field cannot be found or verified in the document text, return null or empty array.\n"
    "4. CITATION INTEGRITY: Tag extracted entities and structured fields with the exact source physical page number where the information appears."
)


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Field Mapping & Dynamic Alias Resolution
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_FIELD_ALIASES: Dict[str, List[str]] = {
    "fir_number": [
        "fir_number", "fir_no", "crime_number", "crime_no", "cr_no",
        "case_number", "case_no", "fir_num", "fir_id", "crime_num", "crno"
    ],
    "district": [
        "district", "dist", "dist.", "district_name", "revenue_district",
        "dist_name", "jurisdiction_district", "zilla", "jilla"
    ],
    "station": [
        "station", "police_station", "excise_station", "ps_name",
        "station_name", "thana", "police_thana", "police_station_name",
        "jurisdiction_station", "seb_station", "ps"
    ],
    "offence_nature": [
        "offence_nature", "crime_type", "allegation", "offence",
        "nature_of_offence", "offence_description", "act_and_section",
        "offences_charged", "incident_description", "brief_facts"
    ],
    "offence_date": [
        "offence_date", "date_of_offence", "occurrence_date",
        "date_of_occurrence", "incident_date"
    ],
    "registration_date": [
        "registration_date", "date_of_registration", "fir_date",
        "booked_date", "reporting_date"
    ],
    "year": [
        "year", "registration_year", "fir_year"
    ],
    "complainant_name": [
        "complainant_name", "complainant_details", "informant_name",
        "informant", "reporting_officer", "complainant"
    ],
    "investigating_officer": [
        "investigating_officer", "seizing_officer_name", "io_name",
        "investigating_officer_name", "si_name", "officer_name"
    ],
    "contraband_type": [
        "contraband_type", "seized_property_details", "stolen_property",
        "item_seized", "contraband", "seized_material"
    ],
    "seized_quantity": [
        "seized_quantity", "quantity", "quantity_seized", "amount_seized"
    ],
    "seized_unit": [
        "seized_unit", "unit", "measurement_unit"
    ],
    "vehicle_details": [
        "vehicle_details", "vehicle_number", "transport_vehicle",
        "seized_vehicle", "vehicle"
    ],
    "place_of_occurrence": [
        "place_of_occurrence", "location", "scene_of_offence",
        "occurrence_place", "incident_location"
    ],
    "mandal": [
        "mandal", "tehsil", "taluka", "block"
    ],
    "village": [
        "village", "gram", "panchayat"
    ],
    "law_sections": [
        "law_sections", "acts_and_sections", "sections", "penal_sections"
    ]
}


def resolve_canonical_field(extracted_data: Dict[str, Any], canonical_key: str) -> Any:
    """Resolve a field value by its canonical name or known aliases."""
    if canonical_key in extracted_data and extracted_data[canonical_key] is not None:
        val = extracted_data[canonical_key]
        if not (isinstance(val, str) and not val.strip()):
            return val

    aliases = CANONICAL_FIELD_ALIASES.get(canonical_key, [])
    for alias in aliases:
        if alias in extracted_data and extracted_data[alias] is not None:
            val = extracted_data[alias]
            if not (isinstance(val, str) and not val.strip()):
                return val
    return None


def normalize_extraction_dict(raw_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Map any alias keys in raw_dict to canonical keys without dropping extra fields."""
    normalized = dict(raw_dict)
    for canonical_key in CANONICAL_FIELD_ALIASES:
        resolved = resolve_canonical_field(raw_dict, canonical_key)
        if resolved is not None:
            normalized[canonical_key] = resolved
    return normalized


KNOWN_DISTRICTS: List[str] = [
    # Andhra Pradesh
    "Anakapalli", "Ananthapuramu", "Anantapur", "Annamayya", "Bapatla", "Chittoor",
    "Konaseema", "East Godavari", "Eluru", "Guntur", "Kakinada",
    "Krishna", "Kurnool", "Nandyal", "NTR", "Palnadu", "Prakasam",
    "Srikakulam", "Nellore", "Sri Potti Sriramulu Nellore", "Sri Sathya Sai",
    "Tirupati", "Visakhapatnam", "Vizag", "Vizianagaram", "West Godavari",
    "YSR Kadapa", "Kadapa", "Amaravati", "Parvathipuram Manyam", "Alluri Sitharama Raju",
    # Tamil Nadu
    "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem",
    "Tirunelveli", "Vellore", "Erode", "Tiruppur", "Kancheepuram",
    "Thanjavur", "Dindigul", "Cuddalore", "Villupuram", "Nagapattinam", "Chengalpattu",
    # Telangana
    "Hyderabad", "Secunderabad", "Cyberabad", "Rangareddy", "Medchal", "Warangal", "Karimnagar",
    "Nalgonda", "Nizamabad", "Khammam", "Mahbubnagar", "Adilabad", "Suryapet",
    # Karnataka
    "Bengaluru", "Bangalore", "Mysuru", "Hubli", "Mangaluru", "Belagavi", "Kalaburagi",
    # Maharashtra
    "Mumbai", "Pune", "Nagpur", "Nashik", "Thane", "Aurangabad", "Solapur",
    # National & Metros
    "Delhi", "New Delhi", "Kolkata", "Ahmedabad", "Surat", "Jaipur", "Lucknow",
    "Kanpur", "Patna", "Bhopal", "Indore", "Thiruvananthapuram", "Kochi", "Chandigarh"
]


def detect_district_from_text(text: str) -> Optional[str]:
    """Detect district by label pattern first, then by known district boundary match."""
    if not text:
        return None
    # 1. Label pattern
    dist_match = re.search(
        r'(?:District|Dist\.?|Revenue\s+District|జిల్లా|जिला)\s*[:\-\/\.]?\s*([A-Za-z\u0C00-\u0C7F\u0900-\u097F\s\.]+?)(?:\s*[,\n\r;]|$)',
        text, re.IGNORECASE
    )
    if dist_match:
        val = dist_match.group(1).strip()
        val = re.sub(r'^(?:is|at|in|name|of|the)\s+', '', val, flags=re.IGNORECASE).strip()
        if len(val) >= 3 and not any(fp in val.lower() for fp in ["page", "evidence", "document", "hash", "section"]):
            return val.title()
    # 2. Known districts word boundary match
    for dist in KNOWN_DISTRICTS:
        if re.search(rf'\b{re.escape(dist)}\b', text, re.IGNORECASE):
            return dist
    return None


def detect_station_from_text(text: str) -> Optional[str]:
    """Detect police or excise station by label pattern or station keyword patterns."""
    if not text:
        return None
    # 1. Label pattern
    stn_label = re.search(
        r'(?:Police\s*Station|Excise\s*Station|SEB\s*Station|P\.?S\.?|Thana|Station|పోలీస్\s*స్టేషన్|ఎక్సైజ్\s*స్టేషన్|थाना)\s*[:\-\/,]?\s*([^\n\r,;]+)',
        text, re.IGNORECASE
    )
    if stn_label:
        raw_station = stn_label.group(1).strip()
        raw_station = re.sub(r'^(?:is|at|in|name|of|the)\s+', '', raw_station, flags=re.IGNORECASE).strip()
        if len(raw_station) >= 3 and not any(fp in raw_station.lower() for fp in ["page", "evidence", "document", "hash"]):
            return raw_station.title()
    # 2. Inline regex pattern
    cand_stations = re.findall(
        r'\b([A-Za-z][A-Za-z\s]{1,30}?\s*(?:Town|Rural|Traffic|Excise|Urban|South|North|East|West|Central)?\s*(?:Police\s+Station|Excise\s+Station|SEB\s+Station|P\.?S\.?|Thana))\b',
        text,
        re.IGNORECASE
    )
    if cand_stations:
        return cand_stations[0].strip().title()
    return None


def _find_page_citation(text: str, pages: List[DocumentPage]) -> int:
    """Find the earliest physical page number containing text, or default to 1."""
    if not text or not isinstance(text, str):
        return 1
    t_clean = text.strip().lower()
    if len(t_clean) < 3:
        return 1
    for p in pages:
        if p.raw_text and t_clean in p.raw_text.lower():
            return p.physical_page_number
    return 1


async def _execute_extraction(
    document: Document,
    pages: List[DocumentPage],
    config: ExtractionConfig,
    user_id: str
) -> Dict[str, Any]:
    """Execute AI extraction using Sarvam Document AI (Digitise + Extract) with robust fallback to Gemini."""
    try:
        schema_fields = json.loads(config.schema_json)
    except Exception:
        schema_fields = DEFAULT_FIR_SCHEMA

    # Full verbatim text across pages with clear page breaks (initial baseline from local pages)
    page_texts = []
    for p in pages:
        p_num = p.physical_page_number
        raw = p.raw_text or ""
        page_texts.append(f"--- Page {p_num} ---\n{raw}")
    full_content = "\n\n".join(page_texts)

    sarvam_res = None
    sarvam_job_id = None
    annotations: Dict[str, Any] = {}
    provider = "Gemini Multimodal Vision"

    # Attempt official Sarvam AI Document Intelligence if available and the original file can be read
    # (stored_path is a Supabase key for cloud uploads; the local cache copy or a download is used)
    from ...services.ingestion import materialize_document_file
    source_path, source_is_temp = await materialize_document_file(document)
    file_size_bytes = os.path.getsize(source_path) if source_path else None
    if source_path and sarvam_doc_ai.is_available():
        try:
            logger.info(f"Triggering Sarvam Document AI for document {document.id} ({document.original_filename})")
            sarvam_res = await sarvam_doc_ai.process_document(
                file_path=source_path,
                mime_type=document.mime_type or "application/pdf",
                schema_fields=schema_fields,
                config_id=config.sarvam_config_id if hasattr(config, "sarvam_config_id") and config.sarvam_config_id else None,
            )
            if sarvam_res and "extract" in sarvam_res:
                sarvam_job_id = sarvam_res.get("sarvam_job_id")
                provider = sarvam_res.get("provider", "Sarvam Document AI (Sarvam Vision 1.5)")
                annotations = sarvam_res.get("extract", {}).get("annotations", {}) or {}

                # If Digitise returned clean page text, update DocumentPages and rebuild full_content
                pages_map = sarvam_res.get("pages_text_map", {})
                if pages_map:
                    new_page_texts = []
                    for p in pages:
                        p_num = p.physical_page_number
                        if p_num in pages_map and pages_map[p_num].strip():
                            p.raw_text = pages_map[p_num]
                            p.ocr_applied = True
                        new_page_texts.append(f"--- Page {p_num} ---\n{p.raw_text or ''}")
                    full_content = "\n\n".join(new_page_texts)
                    pass
                logger.info(f"Sarvam Document AI succeeded for document {document.id} (job_id: {sarvam_job_id})")
        except Exception as exc:
            logger.warning(f"Sarvam Document AI pass failed: {exc}. Falling back to Gemini extraction.")
            sarvam_res = None
    if source_is_temp:
        try:
            os.remove(source_path)
        except OSError:
            pass

    if sarvam_res and "extract" in sarvam_res and sarvam_res["extract"].get("result"):
        extracted_dict = sarvam_res["extract"]["result"]
    else:
        # Fallback raw extraction using Gemini or deterministic fallback
        extracted_dict = gemini_service.extract_structured_case(full_content)

    # Normalize extracted_dict using canonical alias resolution
    extracted_dict = normalize_extraction_dict(extracted_dict)

    # Dynamic detection fallback if district or station were not populated by extractor
    if not extracted_dict.get("district"):
        detected_d = detect_district_from_text(full_content)
        if detected_d:
            extracted_dict["district"] = detected_d

    if not extracted_dict.get("station"):
        detected_s = detect_station_from_text(full_content)
        if detected_s:
            extracted_dict["station"] = detected_s

    # Build structured fields matching schema
    structured_fields = []
    warnings = []

    for f in schema_fields:
        k = f.get("key")
        val = extracted_dict.get(k)
        if val is None or (isinstance(val, str) and not val.strip()):
            val = resolve_canonical_field(extracted_dict, k)
        if isinstance(val, str) and not val.strip():
            val = None

        # Resolve confidence and physical source page from Sarvam annotations or fallback citation
        field_conf = None
        src_pg = 1

        ann = annotations.get(k)
        if isinstance(ann, dict):
            field_conf = ann.get("confidence")
            srcs = ann.get("sources") or []
            if srcs and isinstance(srcs, list) and len(srcs) > 0:
                src_pg = srcs[0].get("page_num", 1)
            elif val is not None:
                src_pg = _find_page_citation(str(val), pages)
        elif isinstance(ann, list) and len(ann) > 0:
            conf_list = [a.get("confidence") for a in ann if isinstance(a, dict) and a.get("confidence") is not None]
            if conf_list:
                field_conf = round(sum(conf_list) / len(conf_list), 3)
            all_srcs = [s for a in ann if isinstance(a, dict) for s in a.get("sources", [])]
            if all_srcs:
                src_pg = all_srcs[0].get("page_num", 1)
            elif val and isinstance(val, list) and len(val) > 0:
                src_pg = _find_page_citation(str(val[0]), pages)
        elif val is not None:
            if isinstance(val, list) and val:
                src_pg = _find_page_citation(str(val[0]), pages)
            elif isinstance(val, (str, int, float)):
                src_pg = _find_page_citation(str(val), pages)

        # Enforce required check
        if f.get("required") and (val is None or val == "" or val == []):
            warnings.append(f"Required field '{f.get('label', k)}' was not found in document.")

        structured_fields.append({
            "id": f.get("id", f"field_{k}"),
            "key": k,
            "label": f.get("label", k.replace("_", " ").title()),
            "data_type": f.get("data_type", "string"),
            "required": f.get("required", False),
            "description": f.get("description", ""),
            "validation_rules": f.get("validation_rules", ""),
            "value": val,
            "confidence": round(field_conf, 3) if field_conf is not None else (0.95 if val is not None else None),
            "source_page": src_pg,
            "reviewed": False
        })

    # Station validation and multiple-station ambiguity detection
    found_stations = re.findall(
        r'\b([A-Za-z][A-Za-z\s]{1,30}?\s*(?:Town|Rural|Traffic|Excise|Urban|South|North|East|West|Central)?\s*(?:Police\s+Station|Excise\s+Station|SEB\s+Station|P\.?S\.?|Thana))\b',
        full_content,
        re.IGNORECASE
    )
    cleaned_stations = list({re.sub(r'\s+', ' ', s.strip()) for s in found_stations if len(s.strip()) > 3})
    if len(cleaned_stations) > 1:
        warnings.append(
            f"Multiple stations referenced in document: {', '.join(cleaned_stations)}. Please review and verify the jurisdictional station."
        )
    elif not extracted_dict.get("station"):
        if not any("Station" in w for w in warnings):
            warnings.append("Police/Excise Station not identified in document. Please review and provide the jurisdictional station.")

    stn_field = next((f for f in structured_fields if f["key"] == "station"), None)
    if stn_field and stn_field.get("value") and stn_field.get("confidence") is not None and stn_field["confidence"] < 0.70:
        warnings.append(f"Station '{stn_field['value']}' extracted with low confidence ({int(stn_field['confidence']*100)}%). Verification required.")

    # Build Entities from extracted fields and annotations
    entities = []

    # Accused entities
    accused_list = extracted_dict.get("accused_names") or []
    if isinstance(accused_list, str):
        accused_list = [accused_list]
    acc_ann = annotations.get("accused_names") or []
    for idx, acc in enumerate(accused_list, 1):
        if acc:
            ent_conf = 0.96
            ent_pg = 1
            if isinstance(acc_ann, list) and idx - 1 < len(acc_ann) and isinstance(acc_ann[idx - 1], dict):
                ent_conf = acc_ann[idx - 1].get("confidence", 0.96)
                s_list = acc_ann[idx - 1].get("sources", [])
                if s_list and isinstance(s_list[0], dict):
                    ent_pg = s_list[0].get("page_num", 1)
            else:
                ent_pg = _find_page_citation(str(acc), pages)

            entities.append({
                "id": f"ent_acc_{idx}",
                "name": str(acc).strip(),
                "type": "ACCUSED",
                "context": f"Accused person #{idx} named in FIR document",
                "source_page": ent_pg,
                "confidence": round(ent_conf, 3),
                "status": "EXTRACTED"
            })

    # Complainant / Informant
    complainant = (
        extracted_dict.get("complainant_name")
        or extracted_dict.get("complainant_details")
    )
    if complainant:
        comp_ann = annotations.get("complainant_name") or annotations.get("complainant_details") or {}
        comp_conf = comp_ann.get("confidence", 0.95) if isinstance(comp_ann, dict) else 0.95
        comp_pg = 1
        if isinstance(comp_ann, dict) and comp_ann.get("sources"):
            comp_pg = comp_ann["sources"][0].get("page_num", 1)
        else:
            comp_pg = _find_page_citation(str(complainant), pages)

        entities.append({
            "id": "ent_complainant",
            "name": str(complainant).strip(),
            "type": "COMPLAINANT",
            "context": "Person who filed or reported the FIR",
            "source_page": comp_pg,
            "confidence": round(comp_conf, 3),
            "status": "EXTRACTED"
        })

    # Witness entities
    witness_list = extracted_dict.get("witness_names") or []
    if isinstance(witness_list, str):
        witness_list = [witness_list]
    for idx, wit in enumerate(witness_list, 1):
        if wit:
            entities.append({
                "id": f"ent_wit_{idx}",
                "name": str(wit).strip(),
                "type": "WITNESS",
                "context": f"Witness #{idx} mentioned in panchanama or FIR",
                "source_page": _find_page_citation(str(wit), pages),
                "confidence": 0.90,
                "status": "EXTRACTED"
            })

    # Victim entities
    victim_list = extracted_dict.get("victim_names") or []
    if isinstance(victim_list, str):
        victim_list = [victim_list]
    for idx, vic in enumerate(victim_list, 1):
        if vic:
            entities.append({
                "id": f"ent_vic_{idx}",
                "name": str(vic).strip(),
                "type": "VICTIM",
                "context": f"Victim / Injured person #{idx} referenced in FIR",
                "source_page": _find_page_citation(str(vic), pages),
                "confidence": 0.92,
                "status": "EXTRACTED"
            })

    # Seizing / Investigating Officer
    io_name = extracted_dict.get("investigating_officer") or extracted_dict.get("seizing_officer_name")
    if io_name:
        io_ann = annotations.get("investigating_officer") or {}
        io_conf = io_ann.get("confidence", 0.94) if isinstance(io_ann, dict) else 0.94
        io_pg = 1
        if isinstance(io_ann, dict) and io_ann.get("sources"):
            io_pg = io_ann["sources"][0].get("page_num", 1)
        else:
            io_pg = _find_page_citation(str(io_name), pages)

        entities.append({
            "id": "ent_io",
            "name": str(io_name).strip(),
            "type": "OFFICER",
            "context": "Investigating or seizing officer",
            "source_page": io_pg,
            "confidence": round(io_conf, 3),
            "status": "EXTRACTED"
        })

    # Vehicle
    veh = extracted_dict.get("vehicle_details")
    if veh:
        veh_ann = annotations.get("vehicle_details") or {}
        veh_pg = 1
        if isinstance(veh_ann, dict) and veh_ann.get("sources"):
            veh_pg = veh_ann["sources"][0].get("page_num", 1)
        else:
            veh_pg = _find_page_citation(str(veh), pages)

        entities.append({
            "id": "ent_veh",
            "name": str(veh).strip(),
            "type": "VEHICLE",
            "context": "Transport vehicle used in alleged offence",
            "source_page": veh_pg,
            "confidence": 0.95,
            "status": "EXTRACTED"
        })

    # Place of occurrence
    place = extracted_dict.get("place_of_occurrence")
    if place:
        place_ann = annotations.get("place_of_occurrence") or {}
        place_pg = 1
        if isinstance(place_ann, dict) and place_ann.get("sources"):
            place_pg = place_ann["sources"][0].get("page_num", 1)
        else:
            place_pg = _find_page_citation(str(place), pages)

        entities.append({
            "id": "ent_place",
            "name": str(place).strip(),
            "type": "LOCATION",
            "context": "Specific place where the offence occurred",
            "source_page": place_pg,
            "confidence": 0.95,
            "status": "EXTRACTED"
        })

    # Station / District as jurisdiction location
    stn = extracted_dict.get("station") or extracted_dict.get("district")
    if stn and stn != place:
        entities.append({
            "id": "ent_loc",
            "name": str(stn).strip(),
            "type": "JURISDICTION",
            "context": "Police / Excise station or district jurisdiction",
            "source_page": _find_page_citation(str(stn), pages),
            "confidence": 0.98,
            "status": "EXTRACTED"
        })

    # Contraband / Seized Property
    contra = extracted_dict.get("contraband_type") or extracted_dict.get("seized_property_details")
    if contra:
        qty_str = f" ({extracted_dict.get('seized_quantity')} {extracted_dict.get('seized_unit', '')})".strip() if extracted_dict.get('seized_quantity') else ""
        entities.append({
            "id": "ent_contra",
            "name": f"{contra}{qty_str}",
            "type": "CONTRABAND",
            "context": "Contraband / property seized in this case",
            "source_page": _find_page_citation(str(contra), pages),
            "confidence": 0.94,
            "status": "EXTRACTED"
        })

    # Financial / Property Loss amount
    fin_amt = extracted_dict.get("property_loss_amount") or extracted_dict.get("financial_loss_amount")
    if fin_amt:
        entities.append({
            "id": "ent_fin",
            "name": f"Rs. {fin_amt}",
            "type": "FINANCIAL",
            "context": "Monetary value / property loss mentioned in FIR",
            "source_page": _find_page_citation(str(fin_amt), pages),
            "confidence": 0.90,
            "status": "EXTRACTED"
        })

    # Offence Date and Time
    off_date = extracted_dict.get("offence_date")
    if off_date:
        off_time = extracted_dict.get("offence_time")
        date_str = f"{off_date} {off_time}".strip() if off_time else str(off_date).strip()
        entities.append({
            "id": "ent_date_offence",
            "name": date_str,
            "type": "DATE_TIME",
            "context": "Date/Time of alleged incident/offence",
            "source_page": _find_page_citation(str(off_date), pages),
            "confidence": 0.96,
            "status": "EXTRACTED"
        })

    # Registration Date and Time
    reg_date = extracted_dict.get("registration_date")
    if reg_date:
        reg_time = extracted_dict.get("registration_time")
        rdate_str = f"{reg_date} {reg_time}".strip() if reg_time else str(reg_date).strip()
        entities.append({
            "id": "ent_date_reg",
            "name": rdate_str,
            "type": "DATE_TIME",
            "context": "FIR formal registration timestamp",
            "source_page": _find_page_citation(str(reg_date), pages),
            "confidence": 0.98,
            "status": "EXTRACTED"
        })

    # Evidence items / seized property articles
    ev_items = extracted_dict.get("evidence_collected") or extracted_dict.get("seized_property_details")
    if ev_items and ev_items != contra:
        entities.append({
            "id": "ent_ev_item",
            "name": str(ev_items).strip(),
            "type": "EVIDENCE",
            "context": "Physical evidence / recovered articles noted in FIR",
            "source_page": _find_page_citation(str(ev_items), pages),
            "confidence": 0.93,
            "status": "EXTRACTED"
        })

    # Digital identifiers / Phone number
    digi = extracted_dict.get("digital_identifiers") or extracted_dict.get("complainant_contact")
    if digi:
        entities.append({
            "id": "ent_digi",
            "name": str(digi).strip(),
            "type": "DIGITAL_ID",
            "context": "Digital identifier or contact number in record",
            "source_page": _find_page_citation(str(digi), pages),
            "confidence": 0.92,
            "status": "EXTRACTED"
        })

    # URLs and emails detected in full text
    email_matches = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', full_content)
    for idx, email in enumerate(set(email_matches), 1):
        if not any(e["name"] == email for e in entities):
            entities.append({
                "id": f"ent_email_{idx}",
                "name": email,
                "type": "DIGITAL_ID",
                "context": "Email address identified in document text",
                "source_page": _find_page_citation(email, pages),
                "confidence": 0.95,
                "status": "EXTRACTED"
            })

    url_matches = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', full_content)
    for idx, url in enumerate(set(url_matches), 1):
        if not any(e["name"] == url for e in entities):
            entities.append({
                "id": f"ent_url_{idx}",
                "name": url,
                "type": "DIGITAL_ID",
                "context": "Website / URL identified in record",
                "source_page": _find_page_citation(url, pages),
                "confidence": 0.95,
                "status": "EXTRACTED"
            })

    phone_matches = re.findall(r'(?:\+91[\-\s]?)?[6-9]\d{9}', full_content)
    for idx, ph in enumerate(set(phone_matches), 1):
        if not any(e["name"] == ph for e in entities):
            entities.append({
                "id": f"ent_ph_{idx}",
                "name": ph,
                "type": "PHONE",
                "context": "Contact phone number extracted from document",
                "source_page": _find_page_citation(ph, pages),
                "confidence": 0.92,
                "status": "EXTRACTED"
            })

    # Law Sections
    sec_list = extracted_dict.get("law_sections") or []
    if isinstance(sec_list, str):
        sec_list = [sec_list]
    for idx, sec in enumerate(sec_list, 1):
        if sec:
            entities.append({
                "id": f"ent_sec_{idx}",
                "name": str(sec).strip(),
                "type": "SECTION",
                "context": "Statutory / legal section invoked in this FIR",
                "source_page": _find_page_citation(str(sec), pages),
                "confidence": 0.97,
                "status": "EXTRACTED"
            })

    # Build Key Points
    key_points = []
    narrative_summary = (
        extracted_dict.get("brief_facts")
        or extracted_dict.get("incident_narrative")
        or extracted_dict.get("narrative_summary")
    )
    if narrative_summary:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(narrative_summary)) if len(s.strip()) > 10]
        for idx, s in enumerate(sentences[:6], 1):
            key_points.append({
                "id": f"kp_{idx}",
                "point": s,
                "source_page": _find_page_citation(s[:30], pages)
            })
    else:
        # Fallback key points from structured values
        kp_items = []
        if extracted_dict.get("offence_nature"):
            kp_items.append(f"Offence recorded as: {extracted_dict.get('offence_nature')}.")
        if extracted_dict.get("contraband_type") and extracted_dict.get("seized_quantity"):
            kp_items.append(
                f"Seized {extracted_dict.get('seized_quantity')} "
                f"{extracted_dict.get('seized_unit', '')} of {extracted_dict.get('contraband_type')}."
            )
        if extracted_dict.get("vehicle_details"):
            kp_items.append(f"Transport vehicle identified: {extracted_dict.get('vehicle_details')}.")
        if extracted_dict.get("place_of_occurrence"):
            kp_items.append(f"Place of occurrence: {extracted_dict.get('place_of_occurrence')}.")
        if extracted_dict.get("property_loss_amount"):
            kp_items.append(f"Property loss / value: Rs. {extracted_dict.get('property_loss_amount')}.")
        for idx, pt in enumerate(kp_items, 1):
            key_points.append({
                "id": f"kp_{idx}",
                "point": pt,
                "source_page": 1
            })

    # Quality warnings
    for p in pages:
        if p.is_unreadable:
            warnings.append(f"Page {p.physical_page_number} has low scan clarity or is unreadable.")
        elif p.ocr_confidence and p.ocr_confidence < 0.65:
            warnings.append(f"Page {p.physical_page_number} has low OCR confidence ({int(p.ocr_confidence * 100)}%).")

    # Document metadata block
    non_null_confs = [f.get("confidence") for f in structured_fields if f.get("confidence") is not None and f.get("value") is not None]
    avg_quality = round(sum(non_null_confs) / len(non_null_confs), 3) if non_null_confs else 0.95

    raw_summary_text = (
        extracted_dict.get("brief_facts")
        or extracted_dict.get("incident_narrative")
        or narrative_summary
        or (full_content[:500] + "..." if len(full_content) > 500 else full_content)
    )

    pages_content = [
        {
            "page_number": p.physical_page_number,
            "text": p.raw_text or "",
            "ocr_applied": p.ocr_applied,
            "ocr_confidence": p.ocr_confidence,
            "is_unreadable": p.is_unreadable
        }
        for p in pages
    ]


    document_metadata = {
        "original_filename": document.original_filename,
        "document_id": document.id,
        "case_id": document.case_id,
        "document_type": extracted_dict.get("document_type") or "First Information Report (FIR)",
        "upload_date": document.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if document.created_at else None,
        "extraction_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_pages": document.physical_page_count,
        "page_count": document.physical_page_count,
        "mime_type": document.mime_type,
        "file_format": (document.mime_type or "application/pdf").split("/")[-1].upper(),
        "file_size": f"{round(file_size_bytes / 1024, 1)} KB" if file_size_bytes else None,
        "file_size_bytes": file_size_bytes,
        "file_hash": document.file_hash,
        "ocr_status": document.ingestion_status or ("COMPLETED" if sarvam_job_id or full_content else "PENDING"),
        "ocr_applied": True if sarvam_job_id else any(p.ocr_applied for p in pages),
        "ocr_quality": avg_quality,
        "provider": provider,
        "model": "sarvam-doc-ai-v1" if provider == "SARVAM_AI" else "fir-vision-regex-v1",
        "sarvam_job_id": sarvam_job_id,
        "author": extracted_dict.get("complainant_name") or extracted_dict.get("investigating_officer") or extracted_dict.get("seizing_officer_name"),
        "document_date": (
            extracted_dict.get("registration_date")
            or extracted_dict.get("offence_date")
            or extracted_dict.get("information_received_date")
        ),
        "district": extracted_dict.get("district"),
        "station": extracted_dict.get("station"),
        "raw_text_summary": raw_summary_text,
    }

    return {
        "document_id": document.id,
        "case_id": document.case_id,
        "original_filename": document.original_filename,
        "config_id": config.id,
        "config_version": config.version,
        "sarvam_job_id": sarvam_job_id,
        "provider": provider,
        "file_hash": document.file_hash,
        "document_content": full_content,
        "pages_content": pages_content,
        "raw_text_summary": raw_summary_text,
        "document_metadata": document_metadata,
        "structured_fields": structured_fields,
        "entities": entities,
        "key_points": key_points,
        "warnings": warnings,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# ─────────────────────────────────────────────────────────────────────────────
# Existing Narrative & Voice Endpoints (Preserved 100%)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/narrative")
async def extract_from_narrative(
    req: NarrativeExtractionRequest,
    current_user: User = Depends(get_current_user)
):
    """Process typed case narrative into structured FIR fields using Gemini."""
    if not req.narrative or len(req.narrative.strip()) < 10:
        raise HTTPException(status_code=400, detail="Narrative text is too short for meaningful extraction.")

    extracted = gemini_service.extract_structured_case(
        raw_text=req.narrative,
        language_hint=req.language or "en"
    )
    return extracted


@router.post("/voice")
async def process_voice_intake(
    audio: UploadFile = File(...),
    language: str = Form("te"),
    current_user: User = Depends(get_current_user)
):
    """Voice capture transcription and structured extraction."""
    audio_bytes = await audio.read()
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Empty or corrupted audio recording received.")

    if language == "te":
        simulated_transcript = (
            "కర్నూలు టౌన్ స్టేషన్ పరిధిలో సుమారు 45 లీటర్ల నాటుసారాను ఆటోలో రవాణా చేస్తుండగా నిందితుడు రాము నాయుడును పట్టుకున్నాము. "
            "వాహనం నంబర్ AP21TY4567 ను స్వాధీనం చేసుకున్నాము."
        )
    elif language == "hi":
        simulated_transcript = (
            "कुरनूल टाउन स्टेशन सीमा में लगभग 45 लीटर कच्ची शराब ले जाते हुए अभियुक्त रामू नायडू को पकड़ा गया। "
            "वाहन संख्या AP21TY4567 जब्त किया गया।"
        )
    else:
        simulated_transcript = (
            "During vehicular inspection in Kurnool Town limits, accused Ramu Naidu was intercepted transporting "
            "45 litres of illicit distilled liquor in Auto AP21TY4567. Contraband and vehicle seized under panchanama."
        )

    extracted = gemini_service.extract_structured_case(
        raw_text=simulated_transcript,
        language_hint=language
    )

    return {
        "transcript": simulated_transcript,
        "language": language,
        "extracted_data": extracted,
        "requires_officer_review": True
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI Document Extraction Workspace API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_extraction_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get active extraction configuration (schema, instructions, and optional Sarvam config_id)."""
    stmt = select(ExtractionConfig).where(ExtractionConfig.is_active == True).order_by(desc(ExtractionConfig.version))
    res = await db.execute(stmt)
    cfg = res.scalars().first()

    if not cfg:
        # Create and return default config
        cfg = ExtractionConfig(
            id="cfg-default-fir",
            name="FIR Standard Extraction",
            version=1,
            schema_json=json.dumps(DEFAULT_FIR_SCHEMA),
            instructions=DEFAULT_INSTRUCTIONS,
            sarvam_config_id=None,
            is_active=True,
            created_by=current_user.id
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

    return {
        "id": cfg.id,
        "name": cfg.name,
        "version": cfg.version,
        "schema_json": cfg.schema_json,
        "instructions": cfg.instructions,
        "sarvam_config_id": cfg.sarvam_config_id,
        "is_active": cfg.is_active,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
    }


@router.put("/config")
async def update_extraction_config(
    req: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save updated extraction configuration schema, defensive instructions, and optional Sarvam config_id."""
    # Validate schema_json
    try:
        parsed_schema = json.loads(req.schema_json)
        if not isinstance(parsed_schema, list):
            raise ValueError("Schema must be a JSON array of field objects.")
        for item in parsed_schema:
            if not isinstance(item, dict) or "key" not in item or "label" not in item:
                raise ValueError("Each schema field must contain at least 'key' and 'label'.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {str(e)}")

    stmt = select(ExtractionConfig).where(ExtractionConfig.is_active == True).order_by(desc(ExtractionConfig.version))
    res = await db.execute(stmt)
    cfg = res.scalars().first()

    if cfg:
        cfg.version += 1
        cfg.name = req.name or cfg.name
        cfg.schema_json = req.schema_json
        cfg.instructions = req.instructions or cfg.instructions
        if req.sarvam_config_id is not None:
            cfg.sarvam_config_id = req.sarvam_config_id.strip() if req.sarvam_config_id.strip() else None
        cfg.created_by = current_user.id
    else:
        cfg = ExtractionConfig(
            id=generate_uuid(),
            name=req.name or "FIR Standard Extraction",
            version=1,
            schema_json=req.schema_json,
            instructions=req.instructions or DEFAULT_INSTRUCTIONS,
            sarvam_config_id=req.sarvam_config_id.strip() if req.sarvam_config_id and req.sarvam_config_id.strip() else None,
            is_active=True,
            created_by=current_user.id
        )
        db.add(cfg)

    await db.commit()
    await db.refresh(cfg)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="EXTRACTION_CONFIG_UPDATED",
        object_type="EXTRACTION_CONFIG",
        object_id=cfg.id,
        after_state={"version": cfg.version, "field_count": len(parsed_schema), "sarvam_config_id": cfg.sarvam_config_id}
    )

    return {
        "id": cfg.id,
        "name": cfg.name,
        "version": cfg.version,
        "schema_json": cfg.schema_json,
        "instructions": cfg.instructions,
        "sarvam_config_id": cfg.sarvam_config_id,
        "message": f"Extraction configuration version {cfg.version} saved successfully."
    }


@router.post("/config/validate")
async def validate_schema(req: SchemaValidateRequest):
    """Validate output schema JSON syntax and mandatory properties."""
    try:
        parsed = json.loads(req.schema_json)
        if not isinstance(parsed, list):
            return {"valid": False, "error": "Schema must be an array of field definitions."}
        if len(parsed) == 0:
            return {"valid": False, "error": "Schema cannot be empty."}
        keys = set()
        for idx, item in enumerate(parsed):
            if not isinstance(item, dict):
                return {"valid": False, "error": f"Item at index {idx} is not an object."}
            k = item.get("key")
            if not k or not isinstance(k, str) or not re.match(r"^[a-zA-Z0-9_]+$", k):
                return {"valid": False, "error": f"Field at index {idx} has invalid key '{k}'. Use letters, numbers, and underscores."}
            if k in keys:
                return {"valid": False, "error": f"Duplicate field key '{k}' found."}
            keys.add(k)
        return {"valid": True, "field_count": len(parsed), "message": "Schema definition is valid."}
    except Exception as e:
        return {"valid": False, "error": f"JSON syntax error: {str(e)}"}


@router.post("/run")
async def run_extraction(
    req: ExtractionRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute AI extraction on an uploaded document with real processing status."""
    # Fetch document
    from ...services.document_access import get_authorized_document
    document = await get_authorized_document(db, current_user, req.document_id)

    # Fetch pages
    p_stmt = select(DocumentPage).where(DocumentPage.document_id == req.document_id).order_by(DocumentPage.physical_page_number.asc())
    p_res = await db.execute(p_stmt)
    pages = p_res.scalars().all()

    # Fetch configuration
    if req.config_id:
        cfg_stmt = select(ExtractionConfig).where(ExtractionConfig.id == req.config_id)
    else:
        cfg_stmt = select(ExtractionConfig).where(ExtractionConfig.is_active == True).order_by(desc(ExtractionConfig.version))
    cfg_res = await db.execute(cfg_stmt)
    config = cfg_res.scalars().first()
    if not config:
        config = ExtractionConfig(
            id="cfg-default-fir",
            name="FIR Standard Extraction",
            version=1,
            schema_json=json.dumps(DEFAULT_FIR_SCHEMA),
            instructions=DEFAULT_INSTRUCTIONS,
            sarvam_config_id=None,
            is_active=True
        )

    # Perform extraction
    extracted_data = await _execute_extraction(document, pages, config, current_user.id)
    sarvam_job_id = extracted_data.get("sarvam_job_id")
    if sarvam_job_id:
        document.sarvam_job_id = sarvam_job_id

    # Save ExtractionRun record
    run = ExtractionRun(
        id=generate_uuid(),
        document_id=document.id,
        config_id=config.id,
        config_version=config.version,
        status="COMPLETED",
        raw_extracted_json=json.dumps(extracted_data),
        reviewed_extracted_json=json.dumps(extracted_data),
        case_id=document.case_id,
        sarvam_job_id=sarvam_job_id,
        created_by=current_user.id
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    extracted_data["run_id"] = run.id
    extracted_data["status"] = run.status
    extracted_data["case_id"] = run.case_id
    extracted_data["sarvam_job_id"] = run.sarvam_job_id

    return extracted_data


@router.get("/run/{run_id}")
async def get_extraction_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve extraction run results and officer review state."""
    stmt = select(ExtractionRun).where(ExtractionRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found.")

    # Fetch document info
    from ...services.document_access import get_authorized_document
    document = await get_authorized_document(db, current_user, run.document_id)

    data = json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")
    data["run_id"] = run.id
    data["document_id"] = run.document_id
    data["config_id"] = run.config_id
    data["config_version"] = run.config_version
    data["status"] = run.status
    data["case_id"] = run.case_id
    data["sarvam_job_id"] = run.sarvam_job_id or data.get("sarvam_job_id")
    if document:
        data["original_filename"] = document.original_filename
        data["mime_type"] = document.mime_type
        data["page_count"] = document.physical_page_count

    return data


@router.get("/document/{document_id}")
async def get_document_extraction(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the latest extraction run for a document, or run one automatically if none exists."""
    from ...services.document_access import get_authorized_document
    document = await get_authorized_document(db, current_user, document_id)

    # Find latest run
    run_stmt = select(ExtractionRun).where(ExtractionRun.document_id == document_id).order_by(desc(ExtractionRun.created_at)).limit(1)
    run_res = await db.execute(run_stmt)
    run = run_res.scalars().first()

    if not run:
        # Run extraction
        p_stmt = select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.physical_page_number.asc())
        p_res = await db.execute(p_stmt)
        pages = p_res.scalars().all()

        cfg_stmt = select(ExtractionConfig).where(ExtractionConfig.is_active == True).order_by(desc(ExtractionConfig.version))
        cfg_res = await db.execute(cfg_stmt)
        config = cfg_res.scalars().first()
        if not config:
            config = ExtractionConfig(
                id="cfg-default-fir",
                name="FIR Standard Extraction",
                version=1,
                schema_json=json.dumps(DEFAULT_FIR_SCHEMA),
                instructions=DEFAULT_INSTRUCTIONS,
                sarvam_config_id=None,
                is_active=True
            )

        extracted_data = await _execute_extraction(document, pages, config, current_user.id)
        sarvam_job_id = extracted_data.get("sarvam_job_id")
        if sarvam_job_id:
            document.sarvam_job_id = sarvam_job_id

        run = ExtractionRun(
            id=generate_uuid(),
            document_id=document.id,
            config_id=config.id,
            config_version=config.version,
            status="COMPLETED",
            raw_extracted_json=json.dumps(extracted_data),
            reviewed_extracted_json=json.dumps(extracted_data),
            case_id=document.case_id,
            sarvam_job_id=sarvam_job_id,
            created_by=current_user.id
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

    data = json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")
    data["run_id"] = run.id
    data["document_id"] = run.document_id
    data["config_id"] = run.config_id
    data["config_version"] = run.config_version
    data["status"] = run.status
    data["case_id"] = run.case_id
    data["sarvam_job_id"] = run.sarvam_job_id or data.get("sarvam_job_id")
    data["original_filename"] = document.original_filename
    data["mime_type"] = document.mime_type
    data["page_count"] = document.physical_page_count

    return data


@router.put("/run/{run_id}/review")
async def save_extraction_review(
    run_id: str,
    req: ReviewUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save officer-edited field values and review status (draft persistence)."""
    stmt = select(ExtractionRun).where(ExtractionRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found.")

    run.reviewed_extracted_json = json.dumps(req.reviewed_data)
    run.updated_at = datetime.utcnow()
    await db.commit()

    return {"message": "Draft review saved successfully.", "run_id": run.id}


@router.post("/run/{run_id}/confirm")
async def confirm_and_register_case(
    run_id: str,
    req: ConfirmCaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Officer confirms verified extraction data.
    Creates or updates the Case, links fields to CaseField, registers entities,
    and triggers automated classification into FIR folders.
    """
    stmt = select(ExtractionRun).where(ExtractionRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found.")

    from ...services.document_access import STATEWIDE_CATEGORIES, get_authorized_document
    source_doc = await get_authorized_document(db, current_user, run.document_id)
    if (source_doc.doc_category or "").upper() in STATEWIDE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="Laws, circulars, guides and reference documents cannot be registered as FIR evidence on a case.",
        )

    review_data = req.reviewed_data or json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")

    # 1. Permanently preserve reviewed draft before running validation checks
    run.reviewed_extracted_json = json.dumps(review_data)
    run.updated_at = datetime.utcnow()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        from ...services.case_validation import describe_db_error as _describe
        code, body = _describe(exc)
        logger.error(f"Saving reviewed draft failed for run {run_id}: {type(exc).__name__}")
        return JSONResponse(status_code=code, content=body)

    # 2. Extract structured fields and resolve canonical aliases
    raw_fields = {
        f["key"]: f.get("value")
        for f in review_data.get("structured_fields", [])
        if isinstance(f, dict) and "key" in f
    }
    # Also defensibly capture any top-level scalar keys in review_data
    for k, v in review_data.items():
        if k not in raw_fields and isinstance(v, (str, int, float)) and v is not None and str(v).strip():
            raw_fields[k] = v
    structured_fields = normalize_extraction_dict(raw_fields)

    # 3. Case-type awareness (Police FIR vs Excise FIR)
    case_type = str(structured_fields.get("case_type") or "").upper()
    offence_raw = structured_fields.get("offence_nature")
    offence_nature = str(offence_raw).strip() if offence_raw else ""
    offence_lower = offence_nature.lower()
    raw_sections = structured_fields.get("law_sections") or []
    sections_str = " ".join([str(s) for s in (raw_sections if isinstance(raw_sections, list) else [raw_sections])]).lower()
    acts_str = str(structured_fields.get("reported_offences_acts") or "").lower()

    station_str = str(structured_fields.get("station") or "").lower()
    is_explicit_excise_station = any(w in station_str for w in ["excise", "seb", "prohibition & excise", "prohibition and excise"])
    is_police_station = any(w in station_str for w in ["police", "p.s", "thana", "town station", "rural station", "traffic station"])

    is_excise = (
        case_type == "EXCISE"
        or (is_explicit_excise_station and not is_police_station)
    )

    doc_text = review_data.get("document_content") or ""

    # Detect candidate station and district from document text to assist officer correction
    cand_station = detect_station_from_text(doc_text)
    cand_district = detect_district_from_text(doc_text)

    # 4. Multi-field structured validation
    validation_report = []

    fir_raw = structured_fields.get("fir_number")
    if not fir_raw or not str(fir_raw).strip():
        validation_report.append({
            "field": "fir_number",
            "label": "FIR / Crime Number",
            "issue": "MISSING",
            "reason": "FIR/Crime Number is mandatory for legal case indexing and registration.",
            "correction_section": "FIR & Jurisdiction",
            "candidate_value": None
        })

    district_raw = structured_fields.get("district")
    if not district_raw or not str(district_raw).strip():
        validation_report.append({
            "field": "district",
            "label": "District",
            "issue": "MISSING",
            "reason": "Jurisdictional district establishes territorial legal competence under Criminal Procedure.",
            "correction_section": "FIR & Jurisdiction",
            "candidate_value": cand_district
        })

    station_raw = structured_fields.get("station")
    if not station_raw or not str(station_raw).strip():
        validation_report.append({
            "field": "station",
            "label": "Police / Excise Station",
            "issue": "MISSING",
            "reason": "Jurisdictional police or excise station is mandatory for station record ownership.",
            "correction_section": "FIR & Jurisdiction",
            "candidate_value": cand_station
        })

    if not offence_raw or not str(offence_raw).strip():
        validation_report.append({
            "field": "offence_nature",
            "label": "Offence Nature / Allegation",
            "issue": "MISSING",
            "reason": "Offence category or factual gist is required to classify the FIR.",
            "correction_section": "FIR & Jurisdiction",
            "candidate_value": None
        })

    # Conditionally check excise particulars if case is an Excise seizure/transport case
    if is_excise:
        contraband_raw = structured_fields.get("contraband_type")
        if not contraband_raw or not str(contraband_raw).strip():
            if any(w in offence_lower for w in ["seiz", "transport", "distill", "possess", "ndps", "liquor"]):
                validation_report.append({
                    "field": "contraband_type",
                    "label": "Contraband / Seized Property",
                    "issue": "MISSING_EXCISE_PARTICULAR",
                    "reason": "Excise FIR involving seizure or transport requires explicit contraband description (e.g. ID Liquor, Non-Duty-Paid Liquor, Ganja).",
                    "correction_section": "Seizure & Evidence",
                    "candidate_value": None
                })

    # Values must fit the case table's columns (PostgreSQL enforces lengths that SQLite ignores),
    # and the case must belong to the officer's jurisdiction
    from ...services.case_validation import column_length_issues, describe_db_error, jurisdiction_issue
    validation_report += column_length_issues(Case, {
        "fir_number": fir_raw, "district": district_raw, "station": station_raw,
        "contraband_type": structured_fields.get("contraband_type"),
        "seized_unit": structured_fields.get("seized_unit"),
        "vehicle_details": structured_fields.get("vehicle_details"),
    })
    if district_raw and station_raw:
        scope_issue = jurisdiction_issue(current_user, str(district_raw).strip(), str(station_raw).strip())
        if scope_issue:
            validation_report.append(scope_issue)

    if validation_report:
        labels = [f"{item['label']} ({item['field']})" for item in validation_report]
        missing = [item for item in validation_report if item["issue"].startswith("MISSING")]
        lead = "Missing required fields" if len(missing) == len(validation_report) else "Fields need correction"
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "code": "VALIDATION_FAILED",
                "detail": f"Registration failed: {lead}: {', '.join(labels)}. Please review and correct these fields before confirming.",
                "validation_report": validation_report,
                "missing_fields": [item["field"] for item in missing]
            }
        )

    fir_number = str(fir_raw).strip()
    district = str(district_raw).strip()
    station = str(station_raw).strip()
    offence_nature = str(offence_raw).strip()
    contraband_type = structured_fields.get("contraband_type")

    # Calculate registration year from extracted field or current year
    try:
        year_raw = structured_fields.get("year")
        year = int(year_raw) if year_raw else datetime.now().year
    except Exception:
        year = datetime.now().year
    
    qty_val = structured_fields.get("seized_quantity")
    try:
        seized_quantity = float(qty_val) if qty_val is not None else 0.0
    except Exception:
        seized_quantity = 0.0

    seized_unit = structured_fields.get("seized_unit") or ("Litres" if is_excise and contraband_type else None)
    vehicle_details = structured_fields.get("vehicle_details")
    io_name = structured_fields.get("investigating_officer") or structured_fields.get("complainant_details")
    # The officer name is derived, not a reviewed form field: use it only when it fits the column
    if io_name and len(str(io_name)) > (Case.__table__.c.seizing_officer_name.type.length or 10**6):
        io_name = None

    # Check if case exists or needs creation (idempotent registration: a retried confirmation
    # finds the case through the run or the FIR number instead of creating a second one)
    existing_case = None
    target_case_id = req.case_id or run.case_id
    if target_case_id:
        c_res = await db.execute(select(Case).where(Case.id == target_case_id))
        existing_case = c_res.scalar_one_or_none()

    if not existing_case:
        # Check by FIR number
        c_res = await db.execute(select(Case).where(Case.fir_number == fir_number))
        existing_case = c_res.scalar_one_or_none()

    if existing_case and not enforce_data_scope(current_user, existing_case.district, existing_case.station):
        # Never update (or reveal) a case outside the officer's jurisdiction
        return JSONResponse(status_code=409, content={
            "code": "DUPLICATE_FIR_NUMBER",
            "detail": f"FIR number '{fir_number}' is already registered in another jurisdiction. "
                      f"Correct the FIR number or ask that jurisdiction to attach this document.",
        })

    # Everything from here to the commit is one transaction: a failure rolls all of it back, so a
    # retried confirmation never finds a half-registered case
    try:
        if existing_case:
            # Update existing case, including an officer-corrected FIR number
            if fir_number and existing_case.fir_number != fir_number:
                clash_res = await db.execute(
                    select(Case.id).where(Case.fir_number == fir_number, Case.id != existing_case.id)
                )
                if clash_res.first():
                    raise HTTPException(
                        status_code=409,
                        detail=f"FIR number '{fir_number}' is already registered to another case. "
                               f"Correct the FIR number or open the existing case."
                    )
                existing_case.fir_number = fir_number
                existing_case.year = year
            existing_case.district = district
            existing_case.station = station
            existing_case.offence_nature = offence_nature
            if contraband_type:
                existing_case.contraband_type = contraband_type
            if seized_quantity:
                existing_case.seized_quantity = seized_quantity
            if seized_unit:
                existing_case.seized_unit = seized_unit
            if vehicle_details:
                existing_case.vehicle_details = vehicle_details
            if review_data.get("document_content"):
                existing_case.narrative = review_data.get("document_content")[:3000]
            case_obj = existing_case
        else:
            # Create new Case with appropriate officer designation
            default_rank = "Excise Sub-Inspector" if is_excise else "Sub-Inspector of Police"
            case_obj = Case(
                id=generate_uuid(),
                fir_number=fir_number,
                year=year,
                district=district,
                station=station,
                offence_nature=offence_nature,
                contraband_type=contraband_type,
                seized_quantity=seized_quantity,
                seized_unit=seized_unit,
                vehicle_details=vehicle_details,
                seizing_officer_name=io_name or current_user.full_name,
                seizing_officer_rank=current_user.designation or default_rank,
                narrative=review_data.get("document_content")[:3000] if review_data.get("document_content") else None,
                status="IN_REVIEW",
                created_by=current_user.id
            )
            db.add(case_obj)
            await db.flush()

        # Link document to case
        doc_res = await db.execute(select(Document).where(Document.id == run.document_id))
        doc_obj = doc_res.scalar_one_or_none()
        if doc_obj:
            doc_obj.case_id = case_obj.id

        run.case_id = case_obj.id
        run.reviewed_extracted_json = json.dumps(review_data)

        # Persist CaseFields
        for field in review_data.get("structured_fields", []):
            f_key = field.get("key")
            f_val = str(field.get("value")) if field.get("value") is not None else None
            if f_val and f_key:
                # Check if CaseField already exists
                cf_stmt = select(CaseField).where(CaseField.case_id == case_obj.id, CaseField.field_name == f_key)
                cf_res = await db.execute(cf_stmt)
                cf = cf_res.scalar_one_or_none()
                if cf:
                    cf.normalized_value = f_val
                    cf.human_override_value = f_val
                    cf.verification_status = "VERIFIED"
                else:
                    cf = CaseField(
                        id=generate_uuid(),
                        case_id=case_obj.id,
                        field_name=f_key,
                        original_value=f_val,
                        normalized_value=f_val,
                        source_doc_id=run.document_id,
                        extraction_method="AI_WORKSPACE_EXTRACTION",
                        confidence_score=1.0,
                        verification_status="VERIFIED"
                    )
                    db.add(cf)

        # Register Entities
        for ent in review_data.get("entities", []):
            ent_name = ent.get("name")
            ent_type = ent.get("type", "PERSON")
            if ent_name and ent_type in ["ACCUSED", "PERSON"]:
                e_stmt = select(Entity).where(Entity.canonical_name.ilike(ent_name.strip()))
                e_res = await db.execute(e_stmt)
                # Several entities can share a name; reuse the first rather than failing the registration
                entity = e_res.scalars().first()
                if not entity:
                    entity = Entity(
                        id=generate_uuid(),
                        canonical_name=ent_name.strip(),
                        entity_type="PERSON",
                        risk_score=0.25,
                        verification_status="CONFIRMED"
                    )
                    db.add(entity)
                    await db.flush()

                # Check mention
                m_stmt = select(EntityMention).where(EntityMention.case_id == case_obj.id, EntityMention.entity_id == entity.id)
                m_res = await db.execute(m_stmt)
                if not m_res.scalar_one_or_none():
                    db.add(EntityMention(
                        id=generate_uuid(),
                        entity_id=entity.id,
                        case_id=case_obj.id,
                        mention_text=ent_name.strip(),
                        role_in_case="ACCUSED",
                        source_doc_id=run.document_id,
                        page_number=ent.get("source_page", 1)
                    ))

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except SQLAlchemyError as exc:
        await db.rollback()
        code, body = describe_db_error(exc)
        logger.error(f"Case registration failed for run {run_id}: {type(exc).__name__}: {str(getattr(exc, 'orig', exc))[:200]}")
        return JSONResponse(status_code=code, content=body)

    case_id, case_fir, case_status = case_obj.id, case_obj.fir_number, case_obj.status
    warnings = []

    # Audit log (the case is already saved; a failed audit write is reported, not turned into an error)
    try:
        await log_audit_event(
            db=db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="EXTRACTION_CASE_CONFIRMED",
            object_type="CASE",
            object_id=case_id,
            after_state={"fir_number": case_fir, "run_id": run.id}
        )
    except Exception as exc:
        await db.rollback()
        logger.error(f"Audit record for confirmed case {case_id} failed: {type(exc).__name__}: {exc}")
        warnings.append("The case was saved, but its audit record could not be written. Inform the administrator.")

    # Post-intake intelligence workflow. Its failures never undo the registration; failed stages
    # are recorded per stage and can be retried from the intake page.
    try:
        await trigger_post_intake_workflow(case_id, db)
    except Exception as exc:
        await db.rollback()
        logger.warning(f"Post-intake workflow trigger error for case {case_id}: {exc}")
    from ...services.workflow import workflow_summary
    workflow = await workflow_summary(db, case_id)
    if workflow["status"] in ("FAILED", "NEEDS_REVIEW"):
        warnings.append("Some automated workflow stages did not complete. The case is registered; review or retry those stages.")

    return {
        "success": True,
        "confirmation_status": "CONFIRMED",
        "case_id": case_id,
        "fir_number": case_fir,
        "status": case_status,
        "workflow_status": workflow["status"],
        "workflow_stages": workflow["stages"],
        "warnings": warnings,
        "message": f"Case {case_fir} verified and registered successfully."
    }


@router.get("/run/{run_id}/export/{format}")
async def export_extraction_results(
    run_id: str,
    format: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export extraction results as:
    - 'xlsx': Excel multi-sheet spreadsheet
    - 'docx': Official Andhra Pradesh Government Word report
    - 'csv': RFC 4180 compliant CSV table
    - 'json': Complete indented JSON format
    """
    stmt = select(ExtractionRun).where(ExtractionRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Extraction run not found.")

    from ...services.document_access import get_authorized_document
    document = await get_authorized_document(db, current_user, run.document_id)

    data = json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")
    data["run_id"] = run.id
    data["document_id"] = run.document_id
    data["config_id"] = run.config_id
    data["config_version"] = run.config_version
    data["status"] = run.status
    if document:
        data["original_filename"] = document.original_filename

    clean_name = os.path.splitext(document.original_filename)[0] if document else "FIR_Extraction"
    clean_name = re.sub(r"[^\w\-_\. ]", "_", clean_name)

    fmt = format.lower().strip()
    if fmt == "xlsx":
        content = generate_xlsx_bytes(data)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{clean_name}_extraction.xlsx"
    elif fmt == "docx":
        content = generate_docx_bytes(data)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{clean_name}_extraction.docx"
    elif fmt == "csv":
        content = generate_csv_bytes(data)
        media_type = "text/csv; charset=utf-8"
        filename = f"{clean_name}_extraction.csv"
    elif fmt == "json":
        content = generate_json_bytes(data)
        media_type = "application/json; charset=utf-8"
        filename = f"{clean_name}_extraction.json"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Use xlsx, docx, csv, or json.")

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/document/{document_id}/file")
async def download_original_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download the original uploaded FIR document file."""
    from ...services.document_access import get_authorized_document
    from ...services.ingestion import materialize_document_file
    document = await get_authorized_document(db, current_user, document_id)

    path, is_temp = await materialize_document_file(document)
    if not path:
        raise HTTPException(status_code=404, detail="The original file for this document is not in storage.")
    if is_temp:
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        return Response(content=data, media_type=document.mime_type or "application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename=\"{document.original_filename}\""})
    return FileResponse(
        path=path,
        filename=document.original_filename,
        media_type=document.mime_type
    )
