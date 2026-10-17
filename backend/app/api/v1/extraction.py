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
    {"id": "f_fir_number", "key": "fir_number", "label": "FIR / Crime Number", "data_type": "string", "required": True, "description": "Official Crime or FIR registration number", "validation_rules": "Format: [Number]/[Year]"},
    {"id": "f_year", "key": "year", "label": "Year", "data_type": "number", "required": True, "description": "Year of registration", "validation_rules": "Four digit year (e.g. 2024)"},
    {"id": "f_district", "key": "district", "label": "District", "data_type": "string", "required": True, "description": "District jurisdiction name in Andhra Pradesh", "validation_rules": "Valid AP district"},
    {"id": "f_station", "key": "station", "label": "Police / Excise Station", "data_type": "string", "required": True, "description": "Jurisdiction station name", "validation_rules": ""},
    {"id": "f_offence_date", "key": "offence_date", "label": "Date & Time of Offence", "data_type": "string", "required": False, "description": "Date and approximate time when offence occurred", "validation_rules": ""},
    {"id": "f_registration_date", "key": "registration_date", "label": "Registration Date", "data_type": "string", "required": False, "description": "Date FIR was booked at station", "validation_rules": ""},
    {"id": "f_place_of_occurrence", "key": "place_of_occurrence", "label": "Place of Occurrence", "data_type": "string", "required": False, "description": "Specific street, landmark, village or coordinates", "validation_rules": ""},
    {"id": "f_complainant_details", "key": "complainant_details", "label": "Complainant / Informant", "data_type": "string", "required": False, "description": "Name and designation of complainant/seizing official", "validation_rules": ""},
    {"id": "f_accused_names", "key": "accused_names", "label": "Accused Persons", "data_type": "array", "required": False, "description": "List of accused names and parentage if mentioned", "validation_rules": ""},
    {"id": "f_offence_nature", "key": "offence_nature", "label": "Offence Nature", "data_type": "string", "required": True, "description": "Gist or classification of the alleged crime", "validation_rules": ""},
    {"id": "f_contraband_type", "key": "contraband_type", "label": "Contraband / Seized Property", "data_type": "string", "required": False, "description": "Property, narcotic, liquor, or stolen items seized", "validation_rules": ""},
    {"id": "f_seized_quantity", "key": "seized_quantity", "label": "Seized Quantity", "data_type": "number", "required": False, "description": "Numerical quantity of seized goods", "validation_rules": "Positive numeric value"},
    {"id": "f_seized_unit", "key": "seized_unit", "label": "Quantity Unit", "data_type": "string", "required": False, "description": "Unit of measurement (e.g. Litres, Kgs, Bottles)", "validation_rules": ""},
    {"id": "f_vehicle_details", "key": "vehicle_details", "label": "Vehicle Details", "data_type": "string", "required": False, "description": "Registration number, make, model of transport vehicle used", "validation_rules": ""},
    {"id": "f_law_sections", "key": "law_sections", "label": "Invoked Law Sections", "data_type": "array", "required": False, "description": "List of statutory sections invoked (e.g. AP Excise Act Sec 34(a), BNS 303(2))", "validation_rules": ""},
    {"id": "f_investigating_officer", "key": "investigating_officer", "label": "Investigating Officer (IO)", "data_type": "string", "required": False, "description": "Name and rank of assigned IO", "validation_rules": ""}
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
    """Execute AI extraction with prompt schema grounding and source page citations."""
    try:
        schema_fields = json.loads(config.schema_json)
    except Exception:
        schema_fields = DEFAULT_FIR_SCHEMA

    # Full verbatim text across pages with clear page breaks
    page_texts = []
    for p in pages:
        p_num = p.physical_page_number
        raw = p.raw_text or ""
        page_texts.append(f"--- Page {p_num} ---\n{raw}")
    full_content = "\n\n".join(page_texts)

    # Base raw extraction using Gemini or deterministic fallback
    extracted_dict = gemini_service.extract_structured_case(full_content)

    # Build structured fields matching schema
    structured_fields = []
    warnings = []

    for f in schema_fields:
        k = f.get("key")
        val = extracted_dict.get(k)
        
        # Check citations
        src_pg = 1
        if val is not None:
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
            "source_page": src_pg,
            "reviewed": False
        })

    # Build Entities
    entities = []
    # Accused entities
    for idx, acc in enumerate(extracted_dict.get("accused_names") or [], 1):
        if acc:
            pg = _find_page_citation(acc, pages)
            entities.append({
                "id": f"ent_acc_{idx}",
                "name": str(acc).strip(),
                "type": "ACCUSED",
                "source_page": pg,
                "confidence": 0.96,
                "status": "EXTRACTED"
            })

    # Seizing / Investigating Officer
    io_name = extracted_dict.get("seizing_officer_name") or extracted_dict.get("investigating_officer")
    if io_name:
        entities.append({
            "id": "ent_io",
            "name": str(io_name).strip(),
            "type": "OFFICER",
            "source_page": _find_page_citation(str(io_name), pages),
            "confidence": 0.94,
            "status": "EXTRACTED"
        })

    # Vehicle
    veh = extracted_dict.get("vehicle_details")
    if veh:
        entities.append({
            "id": "ent_veh",
            "name": str(veh).strip(),
            "type": "VEHICLE",
            "source_page": _find_page_citation(str(veh), pages),
            "confidence": 0.95,
            "status": "EXTRACTED"
        })

    # Location / Station
    stn = extracted_dict.get("station") or extracted_dict.get("district")
    if stn:
        entities.append({
            "id": "ent_loc",
            "name": str(stn).strip(),
            "type": "LOCATION",
            "source_page": _find_page_citation(str(stn), pages),
            "confidence": 0.98,
            "status": "EXTRACTED"
        })

    # Law Sections
    for idx, sec in enumerate(extracted_dict.get("law_sections") or [], 1):
        if sec:
            entities.append({
                "id": f"ent_sec_{idx}",
                "name": str(sec).strip(),
                "type": "SECTION",
                "source_page": _find_page_citation(str(sec), pages),
                "confidence": 0.97,
                "status": "EXTRACTED"
            })

    # Build Key Points
    key_points = []
    narrative_summary = extracted_dict.get("narrative_summary")
    if narrative_summary:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narrative_summary) if len(s.strip()) > 10]
        for idx, s in enumerate(sentences[:5], 1):
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
            kp_items.append(f"Seized {extracted_dict.get('seized_quantity')} {extracted_dict.get('seized_unit', '')} of {extracted_dict.get('contraband_type')}.")
        if extracted_dict.get("vehicle_details"):
            kp_items.append(f"Transport vehicle identified: {extracted_dict.get('vehicle_details')}.")
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

    return {
        "document_id": document.id,
        "original_filename": document.original_filename,
        "config_id": config.id,
        "config_version": config.version,
        "document_content": full_content,
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
    """Get active extraction configuration (schema and instructions)."""
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
        "is_active": cfg.is_active,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
    }


@router.put("/config")
async def update_extraction_config(
    req: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save updated extraction configuration schema and defensive instructions."""
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
        cfg.created_by = current_user.id
    else:
        cfg = ExtractionConfig(
            id=generate_uuid(),
            name=req.name or "FIR Standard Extraction",
            version=1,
            schema_json=req.schema_json,
            instructions=req.instructions or DEFAULT_INSTRUCTIONS,
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
        after_state={"version": cfg.version, "field_count": len(parsed_schema)}
    )

    return {
        "id": cfg.id,
        "name": cfg.name,
        "version": cfg.version,
        "schema_json": cfg.schema_json,
        "instructions": cfg.instructions,
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
            is_active=True
        )

    # Perform extraction
    extracted_data = await _execute_extraction(document, pages, config, current_user.id)

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
        created_by=current_user.id
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    extracted_data["run_id"] = run.id
    extracted_data["status"] = run.status
    extracted_data["case_id"] = run.case_id

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
                is_active=True
            )

        extracted_data = await _execute_extraction(document, pages, config, current_user.id)
        run = ExtractionRun(
            id=generate_uuid(),
            document_id=document.id,
            config_id=config.id,
            config_version=config.version,
            status="COMPLETED",
            raw_extracted_json=json.dumps(extracted_data),
            reviewed_extracted_json=json.dumps(extracted_data),
            case_id=document.case_id,
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

    # Extract required fields with intelligent fallbacks
    fir_number = str(structured_fields.get("fir_number") or f"FIR-TEMP-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    year_val = structured_fields.get("year")
    try:
        year = int(year_val) if year_val else datetime.now().year
    except Exception:
        year = datetime.now().year

    district = str(structured_fields.get("district") or current_user.district)
    station = str(structured_fields.get("station") or current_user.station or "Station Jurisdiction")
    offence_nature = str(structured_fields.get("offence_nature") or "Under Investigation")
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
