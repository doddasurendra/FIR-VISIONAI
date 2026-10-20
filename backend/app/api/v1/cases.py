from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc
from ...database import get_db
from ...models.user import User
from ...models.case import Case, CaseField
from ...models.entity import Entity, EntityMention, GraphEdge
from ...models.document import Document
from ...schemas.schemas import CaseCreate, CaseUpdate, CaseFieldOverride
from ...services.auth import get_current_user, apply_case_scope_filter, enforce_data_scope
from ...services.audit import log_audit_event

router = APIRouter(prefix="/cases", tags=["Case Management"])

@router.get("/")
async def list_cases(
    district: Optional[str] = None,
    station: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    # Count total
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

    new_case = Case(
        fir_number=req.fir_number,
        year=req.year,
        district=target_dist,
        station=target_station or "Station",
        mandal=req.mandal,
        village=req.village,
        location_description=req.location_description,
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

    return new_case

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
