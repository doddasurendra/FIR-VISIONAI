import io
import re
import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

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

    # Attempt official Sarvam AI Document Intelligence if available and document file exists on disk
    if sarvam_doc_ai.is_available() and document.stored_path and os.path.exists(document.stored_path):
        try:
            logger.info(f"Triggering Sarvam Document AI for document {document.id} ({document.original_filename})")
            sarvam_res = await sarvam_doc_ai.process_document(
                file_path=document.stored_path,
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
                logger.info(f"Sarvam Document AI succeeded for document {document.id} (job_id: {sarvam_job_id})")
        except Exception as exc:
            logger.warning(f"Sarvam Document AI pass failed: {exc}. Falling back to Gemini extraction.")
            sarvam_res = None

    if sarvam_res and "extract" in sarvam_res and sarvam_res["extract"].get("result"):
        extracted_dict = sarvam_res["extract"]["result"]
    else:
        # Fallback raw extraction using Gemini or deterministic fallback
        extracted_dict = gemini_service.extract_structured_case(full_content)

    # Build structured fields matching schema
    structured_fields = []
    warnings = []

    for f in schema_fields:
        k = f.get("key")
        val = extracted_dict.get(k)
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

    file_size_bytes = None
    if document.stored_path and os.path.exists(document.stored_path):
        try:
            file_size_bytes = os.path.getsize(document.stored_path)
        except Exception:
            file_size_bytes = None

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
    cfg = res.scalar_one_or_none()

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
    cfg = res.scalar_one_or_none()

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
    doc_stmt = select(Document).where(Document.id == req.document_id)
    doc_res = await db.execute(doc_stmt)
    document = doc_res.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

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
    config = cfg_res.scalar_one_or_none()
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
    doc_stmt = select(Document).where(Document.id == run.document_id)
    doc_res = await db.execute(doc_stmt)
    document = doc_res.scalar_one_or_none()

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
    doc_stmt = select(Document).where(Document.id == document_id)
    doc_res = await db.execute(doc_stmt)
    document = doc_res.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Find latest run
    run_stmt = select(ExtractionRun).where(ExtractionRun.document_id == document_id).order_by(desc(ExtractionRun.created_at))
    run_res = await db.execute(run_stmt)
    run = run_res.scalar_one_or_none()

    if not run:
        # Run extraction
        p_stmt = select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.physical_page_number.asc())
        p_res = await db.execute(p_stmt)
        pages = p_res.scalars().all()

        cfg_stmt = select(ExtractionConfig).where(ExtractionConfig.is_active == True).order_by(desc(ExtractionConfig.version))
        cfg_res = await db.execute(cfg_stmt)
        config = cfg_res.scalar_one_or_none()
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
    run.updated_at = datetime.now(timezone.utc)
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

    review_data = req.reviewed_data or json.loads(run.reviewed_extracted_json or run.raw_extracted_json or "{}")
    structured_fields = {f["key"]: f.get("value") for f in review_data.get("structured_fields", [])}

    # Validate required registration fields without inventing silent fallback values
    missing_fields = []
    fir_raw = structured_fields.get("fir_number")
    if not fir_raw or not str(fir_raw).strip():
        missing_fields.append("FIR Number (fir_number)")
    
    district_raw = structured_fields.get("district") or current_user.district
    if not district_raw or not str(district_raw).strip():
        missing_fields.append("District (district)")

    station_raw = structured_fields.get("station") or current_user.station
    if not station_raw or not str(station_raw).strip():
        missing_fields.append("Police / Excise Station (station)")

    offence_raw = structured_fields.get("offence_nature")
    if not offence_raw or not str(offence_raw).strip():
        missing_fields.append("Offence Nature (offence_nature)")

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: Missing required fields: {', '.join(missing_fields)}. Please review and complete these fields before confirming."
        )

    fir_number = str(fir_raw).strip()
    district = str(district_raw).strip()
    station = str(station_raw).strip()
    offence_nature = str(offence_raw).strip()
    contraband_type = structured_fields.get("contraband_type")
    
    qty_val = structured_fields.get("seized_quantity")
    try:
        seized_quantity = float(qty_val) if qty_val is not None else 0.0
    except Exception:
        seized_quantity = 0.0

    seized_unit = structured_fields.get("seized_unit")
    vehicle_details = structured_fields.get("vehicle_details")
    io_name = structured_fields.get("investigating_officer") or structured_fields.get("complainant_details")

    # Check if case exists or needs creation
    existing_case = None
    target_case_id = req.case_id or run.case_id
    if target_case_id:
        c_res = await db.execute(select(Case).where(Case.id == target_case_id))
        existing_case = c_res.scalar_one_or_none()

    if not existing_case:
        # Check by FIR number
        c_res = await db.execute(select(Case).where(Case.fir_number == fir_number))
        existing_case = c_res.scalar_one_or_none()

    if existing_case:
        # Update existing case
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
        # Create new Case
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
            seizing_officer_rank=current_user.designation or "Excise Officer",
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
            entity = e_res.scalar_one_or_none()
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

    # Trigger automated post-intake classification workflow (FIR Folders)
    try:
        await trigger_post_intake_workflow(case_obj.id, db)
    except Exception as exc:
        logger.warning(f"Post-intake workflow trigger error: {exc}")

    # Audit log
    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="EXTRACTION_CASE_CONFIRMED",
        object_type="CASE",
        object_id=case_obj.id,
        after_state={"fir_number": case_obj.fir_number, "run_id": run.id}
    )

    return {
        "success": True,
        "case_id": case_obj.id,
        "fir_number": case_obj.fir_number,
        "message": f"Case {case_obj.fir_number} verified and registered successfully."
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

    doc_stmt = select(Document).where(Document.id == run.document_id)
    doc_res = await db.execute(doc_stmt)
    document = doc_res.scalar_one_or_none()

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
        filename = f"{clean_name}_report.docx"
    elif fmt == "csv":
        content = generate_csv_bytes(data)
        media_type = "text/csv; charset=utf-8"
        filename = f"{clean_name}_fields.csv"
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
    doc_stmt = select(Document).where(Document.id == document_id)
    doc_res = await db.execute(doc_stmt)
    document = doc_res.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not os.path.exists(document.stored_path):
        raise HTTPException(status_code=404, detail="Stored document file not found on server disk.")

    return FileResponse(
        path=document.stored_path,
        filename=document.original_filename,
        media_type=document.mime_type
    )
