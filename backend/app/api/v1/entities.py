from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db
from ...models.user import User
from ...models.entity import Entity, EntityMention
from ...models.case import Case
from ...schemas.schemas import EntityMergeRequest
from ...services.auth import get_current_user
from ...services.entity_resolution import entity_service
from ...services.audit import log_audit_event

router = APIRouter(prefix="/entities", tags=["Entity Resolution & Network Detection"])

@router.get("/")
async def list_entities(
    entity_type: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Entity).where(Entity.is_canonical == True)
    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)
    if search:
        stmt = stmt.where(Entity.canonical_name.ilike(f"%{search}%"))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/review-queue")
async def get_entity_review_queue(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Component 4: Review queue for candidate duplicate entities."""
    candidates = await entity_service.find_review_candidates(db=db)
    return candidates

@router.post("/merge")
async def merge_entities(
    req: EntityMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Merge duplicate entities and update graph edges."""
    success = await entity_service.merge_entities(
        primary_id=req.primary_entity_id,
        secondary_id=req.secondary_entity_id,
        officer_id=current_user.id,
        db=db
    )
    if not success:
        raise HTTPException(status_code=400, detail="Entity merge could not be completed.")

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="ENTITY_MERGE_CONFIRMED",
        object_type="ENTITY",
        object_id=req.primary_entity_id,
        after_state={"merged_entity_id": req.secondary_entity_id}
    )

    return {"message": "Entities successfully merged into canonical profile. Associated case edges updated."}

@router.get("/network-graph")
async def get_network_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Interactive entity network graph with Louvain community detection."""
    graph_data = await entity_service.build_network_graph(user=current_user, db=db)
    return graph_data

@router.get("/{entity_id}")
async def get_entity_profile(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Entity).where(Entity.id == entity_id)
    res = await db.execute(stmt)
    ent = res.scalar_one_or_none()
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Fetch mentions
    m_stmt = (
        select(EntityMention, Case)
        .join(Case, Case.id == EntityMention.case_id)
        .where(EntityMention.entity_id == entity_id)
    )
    m_res = await db.execute(m_stmt)
    linked_cases = [{"mention": m[0], "case": m[1]} for m in m_res.all()]

    return {
        "entity": ent,
        "linked_cases": linked_cases
    }
