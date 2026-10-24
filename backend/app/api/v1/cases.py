from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, Response
from typing import List, Optional
from datetime import datetime
import os
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc, func
from ...config import settings
from ...database import get_db
from ...models.user import User
from ...models.case import Case, CaseField
from ...models.entity import Entity, EntityMention, GraphEdge
from ...models.document import Document
from ...schemas.schemas import CaseCreate, CaseUpdate, CaseFieldOverride, IncidentLocationUpdate, IncidentLocationResponse, RegeocodeRequest
from ...services.auth import get_current_user, apply_case_scope_filter, enforce_data_scope
from ...services.audit import log_audit_event
from ...services.storage import storage_service
from ...services.pdf_pipeline import pdf_pipeline
from ...services.geocoder import geocoder_service
from .documents import _detect_mime_type

router = APIRouter(prefix="/cases", tags=["Case Management"])

@router.get("", include_in_schema=False)
@router.get("/")
async def list_cases(
    response: Response,
    district: Optional[str] = None,
    station: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    include_archived: bool = Query(False, description="Include archived/soft-deleted cases"),
    page: int = 1,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if status_filter == "ARCHIVED" or include_archived:
        query = select(Case).where(Case.is_archived == True)
    else:
        query = select(Case).where(Case.is_archived == False)
    query = apply_case_scope_filter(query, current_user, Case)

    if district:
        query = query.where(Case.district.ilike(district))
    if station:
        query = query.where(Case.station.ilike(station))
    if status_filter:
        query = query.where(Case.status == status_filter)
    if search:
        search_pattern = f"%{search}%"
        entity_case_ids_subquery = (
            select(EntityMention.case_id)
            .join(Entity, Entity.id == EntityMention.entity_id)
            .where(
                or_(
                    EntityMention.mention_text.ilike(search_pattern),
                    Entity.canonical_name.ilike(search_pattern),
                    Entity.aliases_json.ilike(search_pattern)
                )
            )
        )
        query = query.where(
            or_(
                Case.fir_number.ilike(search_pattern),
                Case.contraband_type.ilike(search_pattern),
                Case.offence_nature.ilike(search_pattern),
                Case.vehicle_details.ilike(search_pattern),
                Case.mandal.ilike(search_pattern),
                Case.village.ilike(search_pattern),
                Case.narrative.ilike(search_pattern),
                Case.id.in_(entity_case_ids_subquery)
            )
        )

    # Calculate total count before pagination
    count_stmt = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_stmt)).scalar() or 0
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    # Paginate and execute
    res = await db.execute(query.order_by(desc(Case.created_at)).offset((page - 1) * limit).limit(limit))
    cases = res.scalars().all()
    return cases

@router.get("/{case_id}")
async def get_case_detail(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied to case outside your permitted jurisdiction scope.")

    # Fetch fields
    f_stmt = select(CaseField).where(CaseField.case_id == case_id)
    f_res = await db.execute(f_stmt)
    fields = f_res.scalars().all()

    # Fetch documents
    d_stmt = select(Document).where(Document.case_id == case_id)
    d_res = await db.execute(d_stmt)
    docs = d_res.scalars().all()

    # Fetch accused/witness entity mentions
    m_stmt = (
        select(EntityMention, Entity)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .where(EntityMention.case_id == case_id)
    )
    m_res = await db.execute(m_stmt)
    mentions_data = [{"mention": m[0], "entity": m[1]} for m in m_res.all()]

    return {
        "case": case,
        "fields": fields,
        "documents": docs,
        "entities": mentions_data
    }

@router.get("/{case_id}/location", response_model=IncidentLocationResponse)
async def get_incident_location(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    # If coordinates are missing but place or mandal or district exists, resolve on the fly
    if case.incident_latitude is None or case.incident_longitude is None:
        raw_loc = case.incident_place_raw or case.location_description or f"{case.village or ''}, {case.mandal or ''}, {case.district}"
        geo = await geocoder_service.geocode_incident_location(
            raw_place=raw_loc,
            village=case.incident_village or case.village,
            mandal=case.incident_mandal or case.mandal,
            district=case.district
        )
        case.incident_place_raw = case.incident_place_raw or raw_loc
        case.incident_latitude = geo.get("latitude")
        case.incident_longitude = geo.get("longitude")
        case.incident_location_normalized = geo.get("display_name")
        case.incident_location_geocoder_status = geo.get("status", "APPROXIMATE")
        case.incident_location_confidence = geo.get("confidence", 0.7)
        await db.commit()
        await db.refresh(case)

    return IncidentLocationResponse(
        case_id=case.id,
        fir_number=case.fir_number,
        station=case.station,
        district=case.district,
        incident_place_raw=case.incident_place_raw or case.location_description,
        incident_location_normalized=case.incident_location_normalized or case.location_description or f"{case.village or ''}, {case.mandal or ''}, {case.district}",
        incident_village=case.incident_village or case.village,
        incident_mandal=case.incident_mandal or case.mandal,
        incident_district=case.incident_district or case.district,
        incident_state=case.incident_state or "Andhra Pradesh",
        incident_pincode=case.incident_pincode,
        incident_landmark=case.incident_landmark,
        incident_latitude=case.incident_latitude,
        incident_longitude=case.incident_longitude,
        incident_location_confidence=case.incident_location_confidence or 0.8,
        incident_location_source_doc_id=case.incident_location_source_doc_id,
        incident_location_source_page=case.incident_location_source_page or 1,
        incident_location_evidence_passage=case.incident_location_evidence_passage or f"Place of occurrence recorded in FIR: {case.incident_place_raw or case.location_description or case.village or case.station}",
        incident_location_geocoder_status=case.incident_location_geocoder_status or "APPROXIMATE",
        incident_location_verified=bool(case.incident_location_verified),
        incident_location_verified_by=case.incident_location_verified_by,
        incident_location_verified_at=case.incident_location_verified_at
    )

@router.put("/{case_id}/location")
async def update_incident_location(
    case_id: str,
    req: IncidentLocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    before_state = {
        "normalized": case.incident_location_normalized,
        "lat": case.incident_latitude,
        "lng": case.incident_longitude,
        "verified": case.incident_location_verified
    }

    # Retain original FIR evidence verbatim; update normalized fields
    if req.incident_location_normalized is not None:
        case.incident_location_normalized = req.incident_location_normalized
    if req.incident_latitude is not None:
        case.incident_latitude = req.incident_latitude
    if req.incident_longitude is not None:
        case.incident_longitude = req.incident_longitude
    if req.incident_village is not None:
        case.incident_village = req.incident_village
    if req.incident_mandal is not None:
        case.incident_mandal = req.incident_mandal
    if req.incident_district is not None:
        case.incident_district = req.incident_district
    if req.incident_landmark is not None:
        case.incident_landmark = req.incident_landmark
    if req.incident_pincode is not None:
        case.incident_pincode = req.incident_pincode
    if req.incident_location_geocoder_status is not None:
        case.incident_location_geocoder_status = req.incident_location_geocoder_status

    if req.incident_location_verified is True:
        case.incident_location_verified = True
        case.incident_location_verified_by = current_user.id
        case.incident_location_verified_at = datetime.utcnow()
        case.incident_location_geocoder_status = "MANUAL_CONFIRMED"

    if case.incident_location_normalized:
        case.location_description = case.incident_location_normalized

    await db.commit()
    await db.refresh(case)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="INCIDENT_LOCATION_VERIFIED" if req.incident_location_verified else "INCIDENT_LOCATION_EDITED",
        object_type="CASE",
        object_id=case.id,
        before_state=before_state,
        after_state={
            "normalized": case.incident_location_normalized,
            "lat": case.incident_latitude,
            "lng": case.incident_longitude,
            "status": case.incident_location_geocoder_status,
            "verified": case.incident_location_verified
        }
    )

    return IncidentLocationResponse(
        case_id=case.id,
        fir_number=case.fir_number,
        station=case.station,
        district=case.district,
        incident_place_raw=case.incident_place_raw or case.location_description,
        incident_location_normalized=case.incident_location_normalized or case.location_description or f"{case.village or ''}, {case.mandal or ''}, {case.district or ''}",
        incident_village=case.incident_village or case.village,
        incident_mandal=case.incident_mandal or case.mandal,
        incident_district=case.incident_district or case.district,
        incident_state=case.incident_state or "Andhra Pradesh",
        incident_pincode=case.incident_pincode,
        incident_landmark=case.incident_landmark,
        incident_latitude=case.incident_latitude,
        incident_longitude=case.incident_longitude,
        incident_location_confidence=case.incident_location_confidence or 1.0,
        incident_location_source_doc_id=case.incident_location_source_doc_id,
        incident_location_source_page=case.incident_location_source_page,
        incident_location_evidence_passage=case.incident_location_evidence_passage,
        incident_location_geocoder_status=case.incident_location_geocoder_status or "MANUAL_CONFIRMED",
        incident_location_verified=case.incident_location_verified or False,
        incident_location_verified_by=case.incident_location_verified_by,
        incident_location_verified_at=case.incident_location_verified_at,
        directions_url=geocoder_service.get_directions_url(case.incident_latitude, case.incident_longitude),
        is_approximate=(case.incident_location_geocoder_status == "APPROXIMATE"),
        display_address=case.incident_location_normalized or f"{case.incident_place_raw}, {case.district}"
    )

@router.post("/{case_id}/location/geocode", response_model=IncidentLocationResponse)
async def trigger_regeocode(
    case_id: str,
    req: Optional[RegeocodeRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    custom_addr = req.custom_address if req else None
    target_addr = custom_addr or case.incident_location_normalized or case.incident_place_raw or case.location_description
    geo = await geocoder_service.geocode_incident_location(
        raw_place=target_addr,
        village=case.incident_village or case.village,
        mandal=case.incident_mandal or case.mandal,
        district=case.district
    )

    case.incident_latitude = geo.get("latitude")
    case.incident_longitude = geo.get("longitude")
    case.incident_location_normalized = geo.get("display_name")
    case.incident_location_geocoder_status = geo.get("status")
    case.incident_location_confidence = geo.get("confidence")
    await db.commit()
    await db.refresh(case)

    return IncidentLocationResponse(
        case_id=case.id,
        fir_number=case.fir_number,
        station=case.station,
        district=case.district,
        incident_place_raw=case.incident_place_raw or case.location_description,
        incident_location_normalized=case.incident_location_normalized or case.location_description or f"{case.village or ''}, {case.mandal or ''}, {case.district or ''}",
        incident_village=case.incident_village or case.village,
        incident_mandal=case.incident_mandal or case.mandal,
        incident_district=case.incident_district or case.district,
        incident_state=case.incident_state or "Andhra Pradesh",
        incident_pincode=case.incident_pincode,
        incident_landmark=case.incident_landmark,
        incident_latitude=case.incident_latitude,
        incident_longitude=case.incident_longitude,
        incident_location_confidence=case.incident_location_confidence or 0.7,
        incident_location_source_doc_id=case.incident_location_source_doc_id,
        incident_location_source_page=case.incident_location_source_page,
        incident_location_evidence_passage=case.incident_location_evidence_passage,
        incident_location_geocoder_status=case.incident_location_geocoder_status or "APPROXIMATE",
        incident_location_verified=case.incident_location_verified or False,
        incident_location_verified_by=case.incident_location_verified_by,
        incident_location_verified_at=case.incident_location_verified_at,
        directions_url=geocoder_service.get_directions_url(case.incident_latitude, case.incident_longitude),
        is_approximate=(case.incident_location_geocoder_status == "APPROXIMATE"),
        display_address=case.incident_location_normalized or f"{case.incident_place_raw}, {case.district}"
    )

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_case(
    req: CaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify user station/district scope
    target_dist = req.district if current_user.role == "STATE" else current_user.district
    target_station = req.station if current_user.role in ["STATE", "DISTRICT"] else current_user.station

    # Duplicate FIR check
    dup = await db.execute(select(Case).where(Case.fir_number == req.fir_number))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An FIR with this registration number already exists.")

    raw_loc = req.location_description or f"{req.village or ''}, {req.mandal or ''}, {target_dist}"
    geo = await geocoder_service.geocode_incident_location(
        raw_place=raw_loc,
        village=req.village,
        mandal=req.mandal,
        district=target_dist
    )

    new_case = Case(
        fir_number=req.fir_number,
        year=req.year,
        district=target_dist,
        station=target_station or "Station",
        mandal=req.mandal,
        village=req.village,
        location_description=geo.get("display_name") or req.location_description,
        incident_place_raw=raw_loc,
        incident_location_normalized=geo.get("display_name") or raw_loc,
        incident_village=req.village,
        incident_mandal=req.mandal,
        incident_district=target_dist,
        incident_latitude=geo.get("latitude"),
        incident_longitude=geo.get("longitude"),
        incident_location_confidence=geo.get("confidence", 0.8),
        incident_location_geocoder_status=geo.get("status", "APPROXIMATE"),
        incident_location_evidence_passage=f"Location specified during FIR case intake: {raw_loc}",
        offence_nature=req.offence_nature,
        contraband_type=req.contraband_type,
        seized_quantity=req.seized_quantity,
        seized_unit=req.seized_unit,
        vehicle_details=req.vehicle_details,
        seizing_officer_name=req.seizing_officer_name or current_user.full_name,
        seizing_officer_rank=req.seizing_officer_rank or current_user.designation,
        narrative=req.narrative,
        status="IN_REVIEW", # Initially DRAFT or IN_REVIEW, not automatically approved
        created_by=current_user.id
    )
    db.add(new_case)
    await db.flush()

    # Link uploaded evidence documents to this persistent case
    primary_doc_id = None
    if getattr(req, "document_ids", None):
        for doc_id in req.document_ids:
            d_res = await db.execute(select(Document).where(Document.id == doc_id))
            d_obj = d_res.scalar_one_or_none()
            if d_obj:
                d_obj.case_id = new_case.id
                if not primary_doc_id:
                    primary_doc_id = d_obj.id

    # Add default case fields with provenance
    default_fields = [
        ("contraband_type", req.contraband_type),
        ("seized_quantity", str(req.seized_quantity) if req.seized_quantity else None),
        ("seized_unit", req.seized_unit),
        ("vehicle_details", req.vehicle_details),
        ("seizing_officer", req.seizing_officer_name or current_user.full_name)
    ]
    for fn, fv in default_fields:
        if fv:
            cf = CaseField(
                case_id=new_case.id,
                field_name=fn,
                original_value=fv,
                normalized_value=fv,
                source_doc_id=primary_doc_id,
                extraction_method="DOCUMENT_EXTRACTION" if primary_doc_id else "MANUAL_INPUT",
                confidence_score=1.0,
                verification_status="UNVERIFIED"
            )
            db.add(cf)

    # Process accused entities
    for name in req.accused_names or []:
        ent_stmt = select(Entity).where(Entity.canonical_name.ilike(name.strip()))
        ent_res = await db.execute(ent_stmt)
        ent = ent_res.scalar_one_or_none()
        if not ent:
            ent = Entity(
                canonical_name=name.strip(),
                entity_type="PERSON",
                aliases_json="[]",
                attributes_json="{}",
                risk_score=0.20
            )
            db.add(ent)
            await db.flush()

        mention = EntityMention(
            entity_id=ent.id,
            case_id=new_case.id,
            mention_text=name.strip(),
            role_in_case="ACCUSED"
        )
        db.add(mention)

    await db.commit()
    await db.refresh(new_case)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_CREATED",
        object_type="CASE",
        object_id=new_case.id,
        after_state={"fir_number": new_case.fir_number, "district": new_case.district, "contraband": new_case.contraband_type}
    )

    # Automatically trigger post-intake intelligence & classification workflow
    try:
        from ...services.workflow import trigger_post_intake_workflow
        await trigger_post_intake_workflow(new_case.id, db)
    except Exception as exc:
        pass

    return {
        "id": new_case.id,
        "fir_number": new_case.fir_number,
        "year": new_case.year,
        "district": new_case.district,
        "station": new_case.station,
        "offence_nature": new_case.offence_nature,
        "status": new_case.status,
        "registration_date": new_case.registration_date.isoformat() if new_case.registration_date else None
    }

@router.put("/{case_id}")
async def update_case(
    case_id: str,
    req: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    before_state = {"offence_nature": case.offence_nature, "contraband": case.contraband_type, "status": case.status}

    if req.offence_nature: case.offence_nature = req.offence_nature
    if req.contraband_type: case.contraband_type = req.contraband_type
    if req.seized_quantity is not None: case.seized_quantity = req.seized_quantity
    if req.seized_unit: case.seized_unit = req.seized_unit
    if req.vehicle_details: case.vehicle_details = req.vehicle_details
    if req.narrative: case.narrative = req.narrative
    if req.status: case.status = req.status

    await db.commit()
    await db.refresh(case)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_UPDATED",
        object_type="CASE",
        object_id=case.id,
        before_state=before_state,
        after_state={"offence_nature": case.offence_nature, "contraband": case.contraband_type, "status": case.status}
    )

    return case

@router.post("/{case_id}/fields/{field_id}/override")
async def override_case_field(
    case_id: str,
    field_id: str,
    req: CaseFieldOverride,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(CaseField).where(CaseField.id == field_id, CaseField.case_id == case_id)
    res = await db.execute(stmt)
    field = res.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Case field not found")

    before_val = field.human_override_value or field.original_value
    field.human_override_value = req.human_override_value
    field.verification_status = req.verification_status
    field.verified_by = current_user.id
    field.verified_at = datetime.utcnow()

    await db.commit()
    await db.refresh(field)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="FIELD_VERIFIED_OVERRIDE",
        object_type="CASE_FIELD",
        object_id=field.id,
        before_state={"field": field.field_name, "value": before_val},
        after_state={"field": field.field_name, "value": req.human_override_value, "status": req.verification_status}
    )

    return field

@router.delete("/{case_id}")
async def soft_delete_case(
    case_id: str,
    reason: str = Query("Departmental record archival", description="Mandatory reason for case archival"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    # Soft delete / archival
    case.is_archived = True
    case.archived_reason = reason
    case.archived_by = current_user.id
    case.status = "ARCHIVED"

    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_SOFT_DELETED",
        object_type="CASE",
        object_id=case.id,
        after_state={"reason": reason, "status": "ARCHIVED"}
    )

    return {"message": "Case safely archived. Source evidence and previous records preserved."}


@router.post("/{case_id}/restore")
async def restore_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Restore an archived / soft-deleted FIR case to active status."""
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    case.is_archived = False
    case.status = "DRAFT"
    case.archived_reason = None
    case.archived_by = None
    case.archived_at = None
    case.deleted_at = None
    case.deletion_reason = None
    case.deleted_by = None

    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_RESTORED",
        object_type="CASE",
        object_id=case.id,
        after_state={"status": "DRAFT", "is_archived": False}
    )

    return {"message": f"Case '{case.fir_number}' successfully restored to active records."}


@router.post("/{case_id}/replace-document")
async def replace_case_document(
    case_id: str,
    file: UploadFile = File(...),
    reason: str = Form(..., description="Mandatory reason for document replacement"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Replace an incorrectly uploaded FIR document for an existing case.
    Preserves the previous document in the audit archive, links the replacement,
    re-triggers extraction and classification, invalidates old RAG caches,
    and flags the case for officer re-review.
    """
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Replacement file is empty (0 bytes).")

    detected_mime = _detect_mime_type(file.filename, file_bytes)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Find existing active document for this case
    doc_stmt = (
        select(Document)
        .where(Document.case_id == case_id, Document.is_archived == False)
        .order_by(desc(Document.created_at))
    )
    doc_res = await db.execute(doc_stmt)
    old_doc = doc_res.scalars().first()

    # Upload replacement to storage
    storage_meta = await storage_service.upload_file(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=detected_mime
    )

    local_path = storage_meta["stored_path"]
    if storage_meta["storage_type"] == "SUPABASE":
        temp_dir = os.path.join(settings.EVIDENCE_DIR, "cloud_cache")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"{file_hash[:8]}_{file.filename}")
        with open(local_path, "wb") as f:
            f.write(file_bytes)

    # Process new document through pipeline
    new_doc = await pdf_pipeline.process_document(
        file_path=local_path,
        original_filename=file.filename,
        mime_type=detected_mime,
        user_id=current_user.id,
        db=db,
        case_id=case_id
    )

    # Soft-archive previous document
    if old_doc:
        old_doc.is_archived = True
        old_doc.archived_at = datetime.utcnow()
        old_doc.archived_by = current_user.id
        old_doc.archive_reason = f"Replaced by '{file.filename}': {reason}"
        old_doc.replaced_by_id = new_doc.id
        new_doc.replaces_id = old_doc.id

        # Invalidate RAG cache for old document
        from ...services.rag_engine import rag_engine
        rag_engine.invalidate_cache(old_doc.id)

    # Case requires officer re-verification due to document replacement
    case.status = "IN_REVIEW"

    await db.commit()

    # Trigger workflow to re-classify, re-extract entities and refresh intelligence
    try:
        from ...services.workflow import trigger_post_intake_workflow
        await trigger_post_intake_workflow(case_id, db)
    except Exception as exc:
        logger.warning(f"Workflow execution on document replacement failed: {exc}")

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_DOCUMENT_REPLACED",
        object_type="CASE",
        object_id=case_id,
        after_state={
            "old_doc_id": old_doc.id if old_doc else None,
            "new_doc_id": new_doc.id,
            "filename": file.filename,
            "reason": reason,
            "status": "IN_REVIEW",
            "requires_re_review": True
        }
    )

    return {
        "message": f"Document successfully replaced with '{file.filename}'. Workflow re-triggered. Case marked for re-review.",
        "case_status": case.status,
        "new_document_id": new_doc.id,
        "old_document_id": old_doc.id if old_doc else None,
        "requires_re_review": True
    }


@router.post("/bulk-archive")
async def bulk_archive_cases(
    case_ids: List[str] = Form(...),
    reason: str = Form(..., description="Mandatory reason for bulk archival"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Bulk soft-archive cases within authorized jurisdiction."""
    if current_user.role not in ("DISTRICT", "STATE"):
        raise HTTPException(status_code=403, detail="Bulk archival requires DISTRICT or STATE level authorization.")

    archived_count = 0
    for cid in case_ids:
        stmt = select(Case).where(Case.id == cid)
        res = await db.execute(stmt)
        c = res.scalar_one_or_none()
        if c and enforce_data_scope(current_user, c.district, c.station):
            c.is_archived = True
            c.status = "ARCHIVED"
            c.archived_reason = reason
            c.archived_by = current_user.id
            c.archived_at = datetime.utcnow()
            archived_count += 1

            await log_audit_event(
                db=db,
                actor_id=current_user.id,
                actor_username=current_user.username,
                action_type="CASE_BULK_ARCHIVED",
                object_type="CASE",
                object_id=c.id,
                after_state={"reason": reason}
            )

    await db.commit()
    return {"message": f"Successfully archived {archived_count} cases.", "archived_count": archived_count}


@router.post("/{case_id}/approve")
async def approve_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Officially approve and finalize an FIR case after officer verification."""
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied")

    case.status = "APPROVED"
    await db.commit()
    await db.refresh(case)

    # Update workflow execution stage for ADMIN
    try:
        from ...services.workflow import _upsert_workflow_stage
        await _upsert_workflow_stage(
            db, case_id, "ADMIN", "COMPLETED",
            result_summary="Case officially approved and finalized by authorized officer."
        )
    except Exception:
        pass

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_APPROVED",
        object_type="CASE",
        object_id=case.id,
        after_state={"status": "APPROVED", "fir_number": case.fir_number}
    )

    return {"message": "Case successfully verified, approved, and finalized.", "case": case}


@router.get("/{case_id}/export/{format}")
async def export_case_record(
    case_id: str,
    format: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export verified FIR case record in xlsx, docx, pdf, csv, or json.
    Strictly scoped to user jurisdiction, includes provenance, fields, entities and workflow status.
    """
    from fastapi.responses import Response

    fmt = format.lower().strip()
    if fmt not in ("xlsx", "docx", "pdf", "csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{format}'. Supported formats: xlsx, docx, pdf, csv, json."
        )

    # 1. Fetch case with strict jurisdiction check
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case record not found.")

    if not enforce_data_scope(current_user, case.district, case.station):
        raise HTTPException(status_code=403, detail="Access denied to case outside your permitted jurisdiction scope.")

    # 2. Fetch all related case fields strictly for this case_id
    f_stmt = select(CaseField).where(CaseField.case_id == case_id).order_by(CaseField.field_name)
    f_res = await db.execute(f_stmt)
    fields = [
        {
            "field_name": f.field_name,
            "original_value": f.original_value,
            "normalized_value": f.normalized_value,
            "human_override_value": f.human_override_value,
            "verification_status": f.verification_status,
            "page_number": f.page_number,
            "confidence_score": f.confidence_score
        }
        for f in f_res.scalars().all()
    ]

    # 3. Fetch entities strictly for this case_id
    m_stmt = (
        select(EntityMention, Entity)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .where(EntityMention.case_id == case_id)
    )
    m_res = await db.execute(m_stmt)
    entities = [
        {
            "mention": {
                "role_in_case": m[0].role_in_case,
                "mention_text": m[0].mention_text,
                "page_number": m[0].page_number
            },
            "entity": {
                "id": m[1].id,
                "canonical_name": m[1].canonical_name,
                "entity_type": m[1].entity_type,
                "verification_status": m[1].verification_status,
                "risk_score": m[1].risk_score
            }
        }
        for m in m_res.all()
    ]

    # 4. Fetch documents strictly for this case_id
    d_stmt = select(Document).where(Document.case_id == case_id)
    d_res = await db.execute(d_stmt)
    documents = [
        {
            "id": d.id,
            "original_filename": d.original_filename,
            "mime_type": d.mime_type,
            "file_hash_sha256": getattr(d, "file_hash", getattr(d, "file_hash_sha256", "")),
            "physical_page_count": d.physical_page_count,
            "created_at": d.created_at.isoformat() if d.created_at else None
        }
        for d in d_res.scalars().all()
    ]

    # 5. Fetch workflow executions strictly for this case_id
    from ...models.folder import WorkflowExecution
    w_stmt = select(WorkflowExecution).where(WorkflowExecution.case_id == case_id).order_by(WorkflowExecution.created_at)
    w_res = await db.execute(w_stmt)
    workflow = [
        {
            "stage": w.stage,
            "status": w.status,
            "started_at": w.started_at.isoformat() if w.started_at else None,
            "completed_at": w.completed_at.isoformat() if w.completed_at else None,
            "result_summary": w.result_summary,
            "error_message": w.error_message
        }
        for w in w_res.scalars().all()
    ]

    case_dict = {
        "id": case.id,
        "fir_number": case.fir_number,
        "year": case.year,
        "district": case.district,
        "station": case.station,
        "status": case.status,
        "classification_status": getattr(case, "classification_status", "PENDING"),
        "offence_category": case.offence_category,
        "offence_nature": case.offence_nature,
        "contraband_type": case.contraband_type,
        "seized_quantity": case.seized_quantity,
        "seized_unit": case.seized_unit,
        "vehicle_details": case.vehicle_details,
        "seizing_officer_name": case.seizing_officer_name,
        "seizing_officer_rank": case.seizing_officer_rank,
        "registration_date": case.registration_date.isoformat() if case.registration_date else None,
        "narrative": case.narrative,
        "created_at": case.created_at.isoformat() if case.created_at else None
    }

    export_data = {
        "case": case_dict,
        "fields": fields,
        "entities": entities,
        "documents": documents,
        "workflow": workflow
    }

    from ...services.case_export import (
        generate_case_xlsx,
        generate_case_docx,
        generate_case_csv,
        generate_case_json,
        generate_case_pdf
    )

    clean_fir = (case.fir_number or "FIR_Record").replace("/", "_").replace("\\", "_")
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{clean_fir}_{timestamp_str}.{fmt}"

    try:
        if fmt == "xlsx":
            content = generate_case_xlsx(export_data)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "docx":
            content = generate_case_docx(export_data)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif fmt == "pdf":
            content = generate_case_pdf(export_data)
            media_type = "application/pdf"
        elif fmt == "csv":
            content = generate_case_csv(export_data)
            media_type = "text/csv; charset=utf-8"
        elif fmt == "json":
            content = generate_case_json(export_data)
            media_type = "application/json; charset=utf-8"
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate {fmt.upper()} export: {str(exc)}")

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_EXPORTED",
        object_type="CASE",
        object_id=case.id,
        after_state={"format": fmt, "filename": filename}
    )

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

