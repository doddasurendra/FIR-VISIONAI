from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from ...database import get_db
from ...models.user import User
from ...models.folder import FIRFolder, CaseFolderAssignment
from ...models.case import Case
from ...models.entity import Entity, EntityMention
from ...services.auth import get_current_user
from ...services.audit import log_audit_event
import json

router = APIRouter(prefix="/folders", tags=["FIR Folders & Classification"])


def _apply_role_filter(stmt, folder_model, user: User):
    """Filter out restricted folders that the user's role cannot access."""
    if user.role == "STATE":
        return stmt  # STATE sees everything
    if user.role == "DISTRICT":
        return stmt.where(
            (folder_model.is_restricted == False) |
            (folder_model.required_role.in_(["DISTRICT", "STATION"]))
        )
    # STATION: cannot see restricted folders above STATION level
    return stmt.where(
        (folder_model.is_restricted == False) |
        (folder_model.required_role == "STATION")
    )


@router.get("", include_in_schema=False)
@router.get("/")
async def list_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all active FIR folder categories visible to the current user."""
    stmt = select(FIRFolder).where(FIRFolder.is_active == True)
    stmt = _apply_role_filter(stmt, FIRFolder, current_user)
    stmt = stmt.order_by(FIRFolder.sort_order, FIRFolder.name)
    res = await db.execute(stmt)
    folders = res.scalars().all()
    return [
        {
            "id": f.id, "name": f.name, "slug": f.slug,
            "description": f.description, "color_code": f.color_code,
            "icon_name": f.icon_name, "group_label": f.group_label,
            "is_restricted": f.is_restricted, "sort_order": f.sort_order,
        }
        for f in folders
    ]


@router.get("/counts")
async def get_folder_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get case counts per folder for the current user's authorized scope."""
    # Build base case scope
    case_stmt = select(Case.id)
    if current_user.role == "STATION":
        case_stmt = case_stmt.where(
            Case.district == current_user.district,
            Case.station == current_user.station,
        )
    elif current_user.role == "DISTRICT":
        case_stmt = case_stmt.where(Case.district == current_user.district)
    # STATE sees all

    authorized_case_ids_res = await db.execute(case_stmt)
    authorized_case_ids = [row[0] for row in authorized_case_ids_res.all()]

    if not authorized_case_ids:
        return {}

    # Count assignments per folder within authorized cases
    count_stmt = (
        select(
            CaseFolderAssignment.folder_id,
            func.count(CaseFolderAssignment.case_id.distinct()).label("cnt")
        )
        .where(CaseFolderAssignment.case_id.in_(authorized_case_ids))
        .group_by(CaseFolderAssignment.folder_id)
    )
    count_res = await db.execute(count_stmt)
    counts = {row.folder_id: row.cnt for row in count_res.all()}

    # Map folder_id → slug
    folder_res = await db.execute(select(FIRFolder.id, FIRFolder.slug))
    slug_map = {row.id: row.slug for row in folder_res.all()}

    return {slug_map.get(fid, fid): cnt for fid, cnt in counts.items()}


@router.get("/persons/single-fir")
async def get_single_fir_persons(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List PERSON entities linked to exactly 1 case in user's authorized scope."""
    return await _get_persons_by_fir_count(db, current_user, min_fir=1, max_fir=1,
                                            skip=skip, limit=limit, search=search)


@router.get("/persons/multiple-fir")
async def get_multiple_fir_persons(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List PERSON entities linked to 2+ cases in user's authorized scope."""
    return await _get_persons_by_fir_count(db, current_user, min_fir=2, max_fir=None,
                                            skip=skip, limit=limit, search=search)


async def _get_persons_by_fir_count(
    db: AsyncSession,
    user: User,
    min_fir: int,
    max_fir: Optional[int],
    skip: int,
    limit: int,
    search: Optional[str],
):
    # Authorized case IDs
    case_stmt = select(Case.id)
    if user.role == "STATION":
        case_stmt = case_stmt.where(Case.district == user.district, Case.station == user.station)
    elif user.role == "DISTRICT":
        case_stmt = case_stmt.where(Case.district == user.district)

    case_res = await db.execute(case_stmt)
    authorized_ids = [row[0] for row in case_res.all()]

    if not authorized_ids:
        return {"persons": [], "total": 0}

    # Entity mention counts per PERSON entity within authorized cases
    mention_stmt = (
        select(
            EntityMention.entity_id,
            func.count(EntityMention.case_id.distinct()).label("case_count")
        )
        .where(
            EntityMention.case_id.in_(authorized_ids),
        )
        .group_by(EntityMention.entity_id)
    )
    if max_fir is None:
        mention_stmt = mention_stmt.having(func.count(EntityMention.case_id.distinct()) >= min_fir)
    else:
        mention_stmt = mention_stmt.having(
            func.count(EntityMention.case_id.distinct()) >= min_fir,
            func.count(EntityMention.case_id.distinct()) <= max_fir,
        )

    mention_res = await db.execute(mention_stmt)
    entity_counts = {row.entity_id: row.case_count for row in mention_res.all()}

    if not entity_counts:
        return {"persons": [], "total": 0}

    # Fetch entity details, filter by PERSON type
    entity_stmt = (
        select(Entity)
        .where(
            Entity.id.in_(list(entity_counts.keys())),
            Entity.entity_type == "PERSON",
            Entity.is_canonical == True,
        )
    )
    if search:
        entity_stmt = entity_stmt.where(Entity.canonical_name.ilike(f"%{search}%"))

    total_res = await db.execute(
        select(func.count()).select_from(entity_stmt.subquery())
    )
    total = total_res.scalar() or 0

    entity_stmt = entity_stmt.offset(skip).limit(limit)
    entity_res = await db.execute(entity_stmt)
    entities = entity_res.scalars().all()

    persons = []
    for ent in entities:
        attrs = json.loads(ent.attributes_json or "{}")
        persons.append({
            "id": ent.id,
            "canonical_name": ent.canonical_name,
            "aliases": json.loads(ent.aliases_json or "[]"),
            "risk_score": ent.risk_score,
            "verification_status": ent.verification_status,
            "case_count": entity_counts.get(ent.id, 0),
            "attributes": attrs,
        })

    return {"persons": persons, "total": total}


@router.get("/{folder_slug}/cases")
async def get_folder_cases(
    folder_slug: str,
    skip: int = 0,
    limit: int = 30,
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List cases assigned to a specific FIR folder, scoped to user's jurisdiction."""
    folder_res = await db.execute(
        select(FIRFolder).where(FIRFolder.slug == folder_slug, FIRFolder.is_active == True)
    )
    folder = folder_res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder '{folder_slug}' not found")

    # Role check for restricted folders
    if folder.is_restricted and folder.required_role:
        role_order = {"STATION": 1, "DISTRICT": 2, "STATE": 3}
        if role_order.get(current_user.role, 0) < role_order.get(folder.required_role, 0):
            raise HTTPException(status_code=403, detail="Insufficient role to access this folder")

    # Get case IDs in this folder
    assignment_res = await db.execute(
        select(CaseFolderAssignment.case_id).where(
            CaseFolderAssignment.folder_id == folder.id
        )
    )
    case_ids = [row[0] for row in assignment_res.all()]
    if not case_ids:
        return {"folder": {"name": folder.name, "slug": folder.slug}, "cases": [], "total": 0}

    # Apply jurisdiction scope
    stmt = select(Case).where(Case.id.in_(case_ids))
    if current_user.role == "STATION":
        stmt = stmt.where(Case.district == current_user.district, Case.station == current_user.station)
    elif current_user.role == "DISTRICT":
        stmt = stmt.where(Case.district == current_user.district)

    if status:
        stmt = stmt.where(Case.status == status.upper())
    if search:
        stmt = stmt.where(
            (Case.fir_number.ilike(f"%{search}%")) |
            (Case.offence_nature.ilike(f"%{search}%")) |
            (Case.narrative.ilike(f"%{search}%"))
        )

    total_res = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_res.scalar() or 0

    stmt = stmt.order_by(Case.registration_date.desc()).offset(skip).limit(limit)
    case_res = await db.execute(stmt)
    cases = case_res.scalars().all()

    return {
        "folder": {
            "id": folder.id, "name": folder.name, "slug": folder.slug,
            "description": folder.description, "color_code": folder.color_code,
            "icon_name": folder.icon_name,
        },
        "cases": [
            {
                "id": c.id, "fir_number": c.fir_number, "year": c.year,
                "district": c.district, "station": c.station,
                "offence_nature": c.offence_nature, "status": c.status,
                "registration_date": c.registration_date.isoformat() if c.registration_date else None,
                "classification_confidence": c.classification_confidence,
                "classification_status": c.classification_status,
            }
            for c in cases
        ],
        "total": total,
    }


@router.post("/{folder_slug}/cases/{case_id}")
async def assign_case_to_folder(
    folder_slug: str,
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually assign a case to a folder (officer override)."""
    folder_res = await db.execute(
        select(FIRFolder).where(FIRFolder.slug == folder_slug)
    )
    folder = folder_res.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder '{folder_slug}' not found")

    case_res = await db.execute(select(Case).where(Case.id == case_id))
    case = case_res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Check for existing assignment to this folder
    existing_res = await db.execute(
        select(CaseFolderAssignment).where(
            CaseFolderAssignment.case_id == case_id,
            CaseFolderAssignment.folder_id == folder.id,
        )
    )
    if existing_res.scalar_one_or_none():
        return {"message": "Case already assigned to this folder"}

    from ...models.base import generate_uuid
    assignment = CaseFolderAssignment(
        id=generate_uuid(),
        case_id=case_id,
        folder_id=folder.id,
        assigned_by=current_user.id,
        is_primary=False,
        confidence_score=1.0,
        assignment_source="MANUAL",
    )
    db.add(assignment)

    # Update case classification status
    case.classification_status = "MANUAL_OVERRIDE"
    case.classification_source = "MANUAL"

    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="CASE_FOLDER_ASSIGNED",
        object_type="CASE",
        object_id=case_id,
        after_state={"folder_slug": folder_slug, "source": "MANUAL"},
    )

    return {"message": f"Case assigned to folder '{folder.name}'"}


@router.get("/workflow/{case_id}")
async def get_workflow_status(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get workflow execution stages for a case."""
    from ...models.folder import WorkflowExecution
    res = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.case_id == case_id)
        .order_by(WorkflowExecution.created_at)
    )
    stages = res.scalars().all()
    return [
        {
            "stage": s.stage, "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "error_message": s.error_message,
            "result_summary": s.result_summary,
        }
        for s in stages
    ]


@router.post("/workflow/{case_id}/retry")
async def retry_workflow(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retry failed post-intake workflow stages for a case."""
    from ...services.workflow import trigger_post_intake_workflow
    await trigger_post_intake_workflow(case_id, db)
    return {"message": "Workflow restarted successfully", "case_id": case_id}

