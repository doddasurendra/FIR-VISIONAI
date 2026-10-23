from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
import re
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, desc
from ...database import get_db
from ...models.user import User
from ...models.entity import Entity, EntityMention, GraphEdge
from ...models.case import Case
from ...models.document import Document
from ...schemas.schemas import EntityMergeRequest
from ...services.auth import get_current_user, enforce_data_scope, apply_case_scope_filter
from ...services.entity_resolution import entity_service
from ...services.audit import log_audit_event

router = APIRouter(prefix="/entities", tags=["Entity Resolution & Network Detection"])

# Alias without trailing slash to prevent 307 redirects
@router.get("", include_in_schema=False)
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
    case_id: Optional[str] = Query(None, description="Optional FIR case ID for single-case mode"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Interactive entity network graph with single-FIR inspection or cross-case intelligence.
    Supports Person, Vehicle, Location, Organization, and Phone entities.
    """
    graph_data = await entity_service.build_network_graph(user=current_user, db=db, case_id=case_id)
    return graph_data

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: Repeat Offender & Criminal Network Intelligence Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class MatchDecisionRequest(BaseModel):
    case_id: str
    entity_id: str
    decision: str  # "CONFIRM" | "REJECT" | "CORRECT"
    target_entity_id: Optional[str] = None
    corrected_name: Optional[str] = None
    corrected_attributes: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None

@router.post("/matches/decision")
async def record_match_decision(
    req: MatchDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Record officer verification decision (Confirm, Reject, or Correct) for proposed repeat
    offender match or entity relationship, ensuring human-in-the-loop sign-off and audit history.
    """
    stmt = select(Entity).where(Entity.id == req.entity_id)
    res = await db.execute(stmt)
    entity = res.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    action_type = "REPEAT_OFFENDER_MATCH_REVIEWED"
    if req.decision == "CONFIRM":
        entity.verification_status = "CONFIRMED"
        action_type = "REPEAT_OFFENDER_MATCH_CONFIRMED"
    elif req.decision == "REJECT":
        entity.verification_status = "REJECTED"
        action_type = "REPEAT_OFFENDER_MATCH_REJECTED"
    elif req.decision == "CORRECT":
        if req.corrected_name and req.corrected_name.strip():
            entity.canonical_name = req.corrected_name.strip()
        if req.corrected_attributes:
            attrs = json.loads(entity.attributes_json or "{}")
            attrs.update(req.corrected_attributes)
            entity.attributes_json = json.dumps(attrs)
        entity.verification_status = "CONFIRMED"
        action_type = "ENTITY_IDENTITY_CORRECTED"
    else:
        raise HTTPException(status_code=400, detail=f"Invalid decision '{req.decision}'. Must be CONFIRM, REJECT, or CORRECT.")

    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type=action_type,
        object_type="ENTITY",
        object_id=req.entity_id,
        after_state={
            "case_id": req.case_id,
            "decision": req.decision,
            "notes": req.notes,
            "canonical_name": entity.canonical_name,
            "verification_status": entity.verification_status
        }
    )

    return {
        "success": True,
        "message": f"Officer decision '{req.decision}' recorded successfully in audit log.",
        "entity_id": entity.id,
        "verification_status": entity.verification_status,
        "canonical_name": entity.canonical_name
    }

@router.get("/stage6-intelligence")
async def get_stage6_intelligence_query(
    case_id: Optional[str] = Query(None, description="FIR Case ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _build_stage6_intelligence(case_id=case_id, db=db, current_user=current_user)

@router.get("/case/{case_id}/stage6-intelligence")
async def get_stage6_intelligence_path(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _build_stage6_intelligence(case_id=case_id, db=db, current_user=current_user)

async def _build_stage6_intelligence(
    case_id: Optional[str],
    db: AsyncSession,
    current_user: User
):
    """
    Stage 6: Repeat Offender & Criminal Network Intelligence.
    Provides structured entity identification across people, places, vehicles, phones, organizations,
    and seized items, plus explainable cross-case repeat-appearance links with provenance citations.
    """
    # 1. Fetch authorized cases scope
    auth_cases_stmt = apply_case_scope_filter(
        select(Case.id, Case.fir_number, Case.district, Case.station, Case.offence_date, Case.registration_date)
        .where(Case.is_archived == False),
        current_user,
        Case
    )
    auth_cases_res = await db.execute(auth_cases_stmt)
    authorized_cases = auth_cases_res.all()
    auth_case_ids = set([c.id for c in authorized_cases])
    case_meta_lookup = {
        c.id: {
            "id": c.id,
            "fir_number": c.fir_number,
            "district": c.district,
            "station": c.station,
            "offence_date": c.offence_date.isoformat() if c.offence_date else None,
            "registration_date": c.registration_date.isoformat() if c.registration_date else None,
        }
        for c in authorized_cases
    }

    # If no case_id specified, find the most recent authorized case or return jurisdiction overview
    target_case_id = case_id
    if not target_case_id and authorized_cases:
        target_case_id = authorized_cases[0].id

    if not target_case_id:
        return {
            "case_id": None,
            "fir_number": None,
            "status": "INSUFFICIENT_DATA",
            "insufficient_data": True,
            "message": "Insufficient authorized case data to identify relationships. Please register or upload an FIR first.",
            "identified_entities": {"PERSON": [], "LOCATION": [], "VEHICLE": [], "PHONE": [], "ORGANIZATION": [], "PROPERTY": []},
            "repeat_appearances": [],
            "graph_data": {"nodes": [], "edges": []},
            "stats": {"total_entities": 0, "repeat_appearances_count": 0, "network_connections": 0, "authorized_cases_count": 0}
        }

    # Verify jurisdiction
    c_stmt = select(Case).where(Case.id == target_case_id)
    c_res = await db.execute(c_stmt)
    case_obj = c_res.scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Target FIR Case not found.")
    if not enforce_data_scope(current_user, case_obj.district, case_obj.station):
        raise HTTPException(status_code=403, detail="Access denied: Case is outside your authorized jurisdiction.")

    # 2. Query all mentions in this case
    mentions_stmt = (
        select(EntityMention, Entity, Document)
        .join(Entity, Entity.id == EntityMention.entity_id)
        .outerjoin(Document, Document.id == EntityMention.source_doc_id)
        .where(EntityMention.case_id == target_case_id)
    )
    m_res = await db.execute(mentions_stmt)
    case_mentions = m_res.all()

    # Fallback to case document if mention source_doc_id was null
    case_doc_stmt = select(Document).where(Document.case_id == target_case_id).limit(1)
    case_doc_res = await db.execute(case_doc_stmt)
    fallback_doc = case_doc_res.scalar_one_or_none()

    # Group identified entities
    entities_by_type: Dict[str, List[Dict[str, Any]]] = {
        "PERSON": [],
        "LOCATION": [],
        "VEHICLE": [],
        "PHONE": [],
        "ORGANIZATION": [],
        "PROPERTY": []
    }

    seen_entity_ids = set()
    this_case_entities = []

    for mention, entity, doc in case_mentions:
        if entity.id in seen_entity_ids:
            continue
        seen_entity_ids.add(entity.id)
        this_case_entities.append((mention, entity, doc))

        # Privacy masking: Mask phone numbers for station officers unless statewide
        display_name = entity.canonical_name
        is_phone = entity.entity_type in ("PHONE", "PHONE_NUMBER")
        if is_phone and current_user.role not in ("STATE", "DISTRICT"):
            display_name = re.sub(r'(\d{5})\d{5}', r'\1*****', display_name)

        doc_name = (doc.original_filename if doc else (fallback_doc.original_filename if fallback_doc else "FIR_Document.pdf"))
        page_num = mention.page_number or 1

        entity_entry = {
            "entity_id": entity.id,
            "canonical_name": display_name,
            "raw_name": entity.canonical_name,
            "entity_type": entity.entity_type,
            "aliases": json.loads(entity.aliases_json or "[]"),
            "attributes": json.loads(entity.attributes_json or "{}"),
            "role_in_case": mention.role_in_case,
            "risk_score": round(entity.risk_score or 0.0, 2),
            "verification_status": entity.verification_status,
            "source_doc_name": doc_name,
            "source_page": page_num,
            "citation": f"{doc_name} • Page {page_num}"
        }

        group_key = entity.entity_type
        if group_key in ("PHONE_NUMBER",):
            group_key = "PHONE"
        elif group_key in ("CONTRABAND", "ITEM"):
            group_key = "PROPERTY"

        if group_key not in entities_by_type:
            entities_by_type[group_key] = []
        entities_by_type[group_key].append(entity_entry)

    # 3. Find Cross-Case Repeat Appearances & Matches across authorized cases
    repeat_appearances = []
    connected_case_ids = set()

    for mention, entity, doc in this_case_entities:
        # Query other mentions of this exact entity in authorized cases
        other_m_stmt = (
            select(EntityMention, Case, Document)
            .join(Case, Case.id == EntityMention.case_id)
            .outerjoin(Document, Document.id == EntityMention.source_doc_id)
            .where(
                EntityMention.entity_id == entity.id,
                EntityMention.case_id != target_case_id,
                EntityMention.case_id.in_(auth_case_ids)
            )
        )
        other_res = await db.execute(other_m_stmt)
        other_rows = other_res.all()

        if other_rows:
            # Exact Match / Confirmed Repeat Appearance
            related_cases_list = []
            for om, oc, od in other_rows:
                connected_case_ids.add(oc.id)
                o_doc_name = od.original_filename if od else "FIR_Record.pdf"
                related_cases_list.append({
                    "case_id": oc.id,
                    "fir_number": oc.fir_number,
                    "district": oc.district,
                    "station": oc.station,
                    "role_in_case": om.role_in_case,
                    "date": oc.offence_date.isoformat() if oc.offence_date else (oc.registration_date.isoformat() if oc.registration_date else None),
                    "source_doc_name": o_doc_name,
                    "source_page": om.page_number or 1,
                    "citation": f"{oc.fir_number} ({o_doc_name} • Page {om.page_number or 1})"
                })

            match_label = "Confirmed Identifier" if entity.verification_status == "CONFIRMED" else "Potential Repeat Appearance"
            match_type = "CONFIRMED_MATCH" if entity.verification_status == "CONFIRMED" else "POTENTIAL_REPEAT_APPEARANCE"

            repeat_appearances.append({
                "entity_id": entity.id,
                "canonical_name": entity.canonical_name,
                "entity_type": entity.entity_type,
                "match_label": match_label,
                "match_type": match_type,
                "confidence_score": 1.0 if entity.verification_status == "CONFIRMED" else 0.92,
                "matching_attributes": {
                    "matched_identifier": entity.canonical_name,
                    "shared_type": entity.entity_type,
                    "jurisdiction_verified": True
                },
                "appearance_count": len(related_cases_list) + 1,
                "related_cases": related_cases_list,
                "source_evidence": {
                    "doc_name": doc.original_filename if doc else (fallback_doc.original_filename if fallback_doc else "FIR_Evidence.pdf"),
                    "page_number": mention.page_number or 1,
                    "mention_role": mention.role_in_case
                },
                "verification_status": entity.verification_status,
                "advisory_notice": "Advisory Only: This link indicates recorded cross-case appearances in authorized records. It does not establish guilt and requires independent officer verification."
            })

    # 4. Fuzzy / Attribute Matching for Person / Vehicle to detect possible entity matches (Anti-False-Match protected)
    all_auth_entities_stmt = (
        select(Entity, EntityMention.case_id, EntityMention.page_number, Case.fir_number, Case.district, Case.station, Case.offence_date)
        .join(EntityMention, EntityMention.entity_id == Entity.id)
        .join(Case, Case.id == EntityMention.case_id)
        .where(
            Entity.is_canonical == True,
            EntityMention.case_id.in_(auth_case_ids),
            EntityMention.case_id != target_case_id
        )
    )
    all_auth_entities_res = await db.execute(all_auth_entities_stmt)
    candidate_pool = all_auth_entities_res.all()

    for mention, entity, doc in this_case_entities:
        if entity.id in [r["entity_id"] for r in repeat_appearances]:
            continue  # Already caught as exact match

        for cand_ent, cand_case_id, cand_page, cand_fir, cand_dist, cand_station, cand_date in candidate_pool:
            if cand_ent.entity_type != entity.entity_type:
                continue

            sim = fuzz.token_sort_ratio(entity.canonical_name.lower(), cand_ent.canonical_name.lower()) / 100.0

            # Vehicle registration match
            is_veh_match = False
            if entity.entity_type == "VEHICLE":
                try:
                    a1 = json.loads(entity.attributes_json or "{}").get("registration_number", "").replace(" ", "").upper()
                    a2 = json.loads(cand_ent.attributes_json or "{}").get("registration_number", "").replace(" ", "").upper()
                    if a1 and a2 and a1 == a2:
                        is_veh_match = True
                        sim = 0.99
                except Exception:
                    pass

            if sim >= 0.75 or is_veh_match:
                connected_case_ids.add(cand_case_id)
                match_label = "Possible Entity Match" if sim < 0.88 else "Potential Repeat Appearance"
                match_type = "POSSIBLE_ENTITY_MATCH" if sim < 0.88 else "POTENTIAL_REPEAT_APPEARANCE"

                repeat_appearances.append({
                    "entity_id": entity.id,
                    "target_entity_id": cand_ent.id,
                    "canonical_name": entity.canonical_name,
                    "target_name": cand_ent.canonical_name,
                    "entity_type": entity.entity_type,
                    "match_label": match_label,
                    "match_type": match_type,
                    "confidence_score": round(sim, 2),
                    "matching_attributes": {
                        "name_similarity": f"{int(sim * 100)}%",
                        "compared_with": cand_ent.canonical_name,
                        "shared_type": entity.entity_type
                    },
                    "appearance_count": 2,
                    "related_cases": [{
                        "case_id": cand_case_id,
                        "fir_number": cand_fir,
                        "district": cand_dist,
                        "station": cand_station,
                        "role_in_case": "RECORDED_LEAD",
                        "date": cand_date.isoformat() if cand_date else None,
                        "source_doc_name": "FIR_Record.pdf",
                        "source_page": cand_page or 1,
                        "citation": f"{cand_fir} (Page {cand_page or 1})"
                    }],
                    "source_evidence": {
                        "doc_name": doc.original_filename if doc else (fallback_doc.original_filename if fallback_doc else "FIR_Evidence.pdf"),
                        "page_number": mention.page_number or 1,
                        "mention_role": mention.role_in_case
                    },
                    "verification_status": entity.verification_status,
                    "advisory_notice": "Advisory Only: Proposed match based on lexical/attribute similarity. Protect against false identity merge: Officer verification required before official linkage."
                })
                break

    # 5. Build Sub-Graph for vis-network
    sub_nodes = []
    sub_edges = []
    node_ids = set()

    # Case Node
    case_node_id = f"case_{case_obj.id}"
    sub_nodes.append({
        "id": case_node_id,
        "label": f"FIR: {case_obj.fir_number}",
        "title": f"Current FIR: {case_obj.fir_number}\nStation: {case_obj.station}",
        "entity_type": "CASE",
        "color": "#0f5132",
        "value": 24,
        "shape": "box"
    })
    node_ids.add(case_node_id)

    # Color palette
    type_colors = {
        "PERSON": "#3b82f6",
        "VEHICLE": "#f59e0b",
        "LOCATION": "#10b981",
        "ORGANIZATION": "#8b5cf6",
        "PHONE": "#06b6d4",
        "PROPERTY": "#ec4899"
    }

    for mention, entity, _ in this_case_entities:
        if entity.id not in node_ids:
            is_repeat = any(r["entity_id"] == entity.id for r in repeat_appearances)
            sub_nodes.append({
                "id": entity.id,
                "label": entity.canonical_name,
                "title": f"Type: {entity.entity_type}\nName: {entity.canonical_name}\nStatus: {entity.verification_status}",
                "entity_type": entity.entity_type,
                "color": "#dc2626" if is_repeat else type_colors.get(entity.entity_type, "#6b7280"),
                "value": 18 if is_repeat else 12,
                "is_repeat": is_repeat
            })
            node_ids.add(entity.id)

        sub_edges.append({
            "id": f"edge_case_{entity.id}",
            "from": case_node_id,
            "to": entity.id,
            "label": mention.role_in_case,
            "color": {"color": "#cbd5e1"}
        })

    # Add related case nodes and edges for repeat entities
    for rep in repeat_appearances:
        for rc in rep["related_cases"]:
            rc_node_id = f"case_{rc['case_id']}"
            if rc_node_id not in node_ids:
                sub_nodes.append({
                    "id": rc_node_id,
                    "label": f"Prior FIR: {rc['fir_number']}",
                    "title": f"Prior FIR: {rc['fir_number']}\nDate: {rc['date']}\nStation: {rc['station']}",
                    "entity_type": "RELATED_CASE",
                    "color": "#64748b",
                    "value": 16,
                    "shape": "box"
                })
                node_ids.add(rc_node_id)

            sub_edges.append({
                "id": f"edge_{rep['entity_id']}_{rc_node_id}",
                "from": rep["entity_id"],
                "to": rc_node_id,
                "label": "REPEAT_APPEARANCE",
                "color": {"color": "#ef4444", "highlight": "#b91c1c"}
            })

    # Insufficient Data Check
    insufficient_data = len(authorized_cases) < 2 or (len(this_case_entities) == 0)
    msg = None
    if insufficient_data:
        msg = "Insufficient authorized case data to identify relationships. More authorized records needed."
    elif len(repeat_appearances) == 0:
        msg = f"Analyzed {len(this_case_entities)} case entities against {len(authorized_cases)} authorized FIRs. No repeat offenders or cross-case criminal network patterns identified."
    else:
        msg = f"Identified {len(repeat_appearances)} potential repeat appearance(s) across {len(connected_case_ids)} connected cases in authorized jurisdiction."

    return {
        "case_id": case_obj.id,
        "fir_number": case_obj.fir_number,
        "district": case_obj.district,
        "station": case_obj.station,
        "status": "COMPLETED",
        "insufficient_data": insufficient_data,
        "message": msg,
        "identified_entities": entities_by_type,
        "repeat_appearances": repeat_appearances,
        "graph_data": {
            "nodes": sub_nodes,
            "edges": sub_edges
        },
        "stats": {
            "total_entities": len(this_case_entities),
            "repeat_appearances_count": len(repeat_appearances),
            "connected_cases_count": len(connected_case_ids),
            "authorized_cases_count": len(authorized_cases)
        }
    }

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
