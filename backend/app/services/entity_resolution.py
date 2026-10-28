import json
import logging
import re
import networkx as nx
from typing import Dict, Any, List, Optional, Tuple
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, update
from ..models.entity import Entity, EntityMention, GraphEdge
from ..models.case import Case
from ..models.user import User
from .auth import apply_case_scope_filter, enforce_data_scope

logger = logging.getLogger(__name__)

PLACEHOLDER_NAMES = {"unknown", "unknown suspect", "unknown person", "unknown person(s)", "unknown persons",
                     "unknown accused", "unidentified", "not known", "n/a", "na", "nil", "none", "-", "—"}
LOCATION_TYPES = ("LOCATION", "JURISDICTION")


def is_placeholder(name: Optional[str]) -> bool:
    n = re.sub(r"\s+", " ", (name or "").strip().lower()).rstrip(".")
    return not n or n in PLACEHOLDER_NAMES or n.startswith("unknown ")


def _attrs(e: Entity) -> Dict[str, Any]:
    try:
        return json.loads(e.attributes_json or "{}") or {}
    except (TypeError, ValueError):
        return {}


def registration_of(*texts: Optional[str]) -> Optional[str]:
    """Normalised vehicle registration in any of the texts ('Hero Splendor AP 21 AB 1234' -> 'AP21AB1234')."""
    from .retrieval import id_tokens
    for t in texts:
        regs = [tok["norm"] for tok in id_tokens(t or "") if tok["kind"] == "VEHICLE"]
        if regs:
            return regs[0]
    return None


def _phone_digits(value: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else None


class EntityResolutionService:
    @staticmethod
    def compute_similarity(e1: Entity, e2: Entity, districts: Optional[Dict[str, set]] = None) -> float:
        """
        Similarity of two entities of the same type:
        - VEHICLE: 1.0 only when the normalised registration numbers are equal, otherwise 0.0
          ("Hero Splendor AP21AB1234" and "Hero Splendor AP31AB9988" are different vehicles).
        - PHONE: 1.0 only for the same number.
        - LOCATION / JURISDICTION: compared only within the same district.
        - PERSON: fuzzy name similarity, boosted when phone or address also match; placeholders never match.
        districts: entity id -> districts of the cases mentioning it (and its own district attribute).
        """
        if e1.entity_type != e2.entity_type:
            return 0.0
        a1, a2 = _attrs(e1), _attrs(e2)

        if e1.entity_type == "VEHICLE":
            r1 = registration_of(a1.get("registration_number"), e1.canonical_name)
            r2 = registration_of(a2.get("registration_number"), e2.canonical_name)
            return 1.0 if r1 and r1 == r2 else 0.0

        if e1.entity_type in ("PHONE", "PHONE_NUMBER"):
            p1, p2 = _phone_digits(e1.canonical_name), _phone_digits(e2.canonical_name)
            return 1.0 if p1 and p1 == p2 else 0.0

        name_sim = fuzz.token_sort_ratio(e1.canonical_name.lower(), e2.canonical_name.lower()) / 100.0

        if e1.entity_type in LOCATION_TYPES:
            d1 = {d.lower() for d in (districts or {}).get(e1.id, set())} | ({a1["district"].lower()} if a1.get("district") else set())
            d2 = {d.lower() for d in (districts or {}).get(e2.id, set())} | ({a2["district"].lower()} if a2.get("district") else set())
            if d1 and d2 and not (d1 & d2):
                return 0.0
            return name_sim

        if e1.entity_type == "PERSON":
            if is_placeholder(e1.canonical_name) or is_placeholder(e2.canonical_name):
                return 0.0
            boost = 0.0
            if _phone_digits(a1.get("phone")) and _phone_digits(a1.get("phone")) == _phone_digits(a2.get("phone")):
                boost += 0.15
            if a1.get("address") and a2.get("address") and \
                    fuzz.token_set_ratio(str(a1["address"]).lower(), str(a2["address"]).lower()) >= 85:
                boost += 0.10
            return min(1.0, name_sim + boost)

        return name_sim

    @staticmethod
    async def find_review_candidates(db: AsyncSession, user: Optional[User] = None) -> List[Dict[str, Any]]:
        """Candidate duplicate pairs for human review (similarity 0.70-0.98), within the user's jurisdiction."""
        mention_stmt = (select(EntityMention.entity_id, Case.district)
                        .join(Case, Case.id == EntityMention.case_id).where(Case.is_archived == False))  # noqa: E712
        if user is not None:
            mention_stmt = apply_case_scope_filter(mention_stmt, user, Case)
        districts: Dict[str, set] = {}
        for eid, district in (await db.execute(mention_stmt)).all():
            districts.setdefault(eid, set()).add(district or "")
        stmt = select(Entity).where(Entity.is_canonical == True, Entity.id.in_(list(districts)))  # noqa: E712
        res = await db.execute(stmt)
        entities = [e for e in res.scalars().all() if not is_placeholder(e.canonical_name)]
        districts = {k: {d for d in v if d} for k, v in districts.items()}

        candidates = []
        n = len(entities)
        for i in range(n):
            for j in range(i + 1, n):
                e1 = entities[i]
                e2 = entities[j]
                if e1.entity_type != e2.entity_type:
                    continue

                sim = EntityResolutionService.compute_similarity(e1, e2, districts)
                if 0.70 <= sim <= 0.98:
                    candidates.append({
                        "pair_id": f"{e1.id}_{e2.id}",
                        "entity_1": {
                            "id": e1.id,
                            "name": e1.canonical_name,
                            "type": e1.entity_type,
                            "risk_score": e1.risk_score,
                            "attributes": json.loads(e1.attributes_json or "{}")
                        },
                        "entity_2": {
                            "id": e2.id,
                            "name": e2.canonical_name,
                            "type": e2.entity_type,
                            "risk_score": e2.risk_score,
                            "attributes": json.loads(e2.attributes_json or "{}")
                        },
                        "similarity_score": round(sim, 2),
                        "status": "PENDING_REVIEW"
                    })
        return candidates

    @staticmethod
    async def merge_entities(
        primary_id: str,
        secondary_id: str,
        officer_id: str,
        db: AsyncSession
    ) -> bool:
        """Merge secondary entity into primary canonical entity and redirect edges."""
        if primary_id == secondary_id:
            return False

        p_stmt = select(Entity).where(Entity.id == primary_id)
        s_stmt = select(Entity).where(Entity.id == secondary_id)
        
        p_res = await db.execute(p_stmt)
        s_res = await db.execute(s_stmt)
        
        primary = p_res.scalar_one_or_none()
        secondary = s_res.scalar_one_or_none()
        
        if not primary or not secondary:
            return False

        # 1. Update aliases on primary
        aliases = json.loads(primary.aliases_json or "[]")
        if secondary.canonical_name not in aliases:
            aliases.append(secondary.canonical_name)
        primary.aliases_json = json.dumps(aliases)

        # 2. Redirect secondary entity mentions
        await db.execute(
            update(EntityMention).where(EntityMention.entity_id == secondary_id).values(entity_id=primary_id)
        )

        # 3. Redirect graph edges
        await db.execute(
            update(GraphEdge).where(GraphEdge.source_entity_id == secondary_id).values(source_entity_id=primary_id)
        )
        await db.execute(
            update(GraphEdge).where(GraphEdge.target_entity_id == secondary_id).values(target_entity_id=primary_id)
        )

        # 4. Mark secondary as merged
        secondary.is_canonical = False
        secondary.merged_into_id = primary_id
        secondary.verification_status = "MERGED"

        await db.commit()
        return True

    @staticmethod
    async def build_network_graph(user: User, db: AsyncSession, case_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Construct NetworkX graph, detect Louvain communities, and return
        clickable node and edge JSON for frontend visualization.
        Supports single-case mode (case_id provided) and cross-case intelligence mode.
        """
        # Fetch authorized cases list for dropdown selection
        all_cases_stmt = apply_case_scope_filter(
            select(Case.id, Case.fir_number, Case.district, Case.station, Case.status, Case.vehicle_details)
            .where(Case.is_archived == False).order_by(Case.registration_date.desc()),
            user,
            Case
        )
        all_cases_res = await db.execute(all_cases_stmt)
        case_rows = all_cases_res.all()
        available_cases = [
            {"id": row[0], "fir_number": row[1], "district": row[2], "station": row[3], "status": row[4]}
            for row in case_rows
        ]
        vehicle_text = {row[0]: row[5] for row in case_rows}
        authorized_case_ids = [c["id"] for c in available_cases]
        case_lookup = {c["id"]: c["fir_number"] for c in available_cases}

        # Handle Single-Case Mode vs Cross-Case Mode
        selected_case_meta = None
        if case_id:
            c_stmt = select(Case).where(Case.id == case_id)
            c_res = await db.execute(c_stmt)
            target_case = c_res.scalar_one_or_none()
            if not target_case or not enforce_data_scope(user, target_case.district, target_case.station):
                return {
                    "nodes": [],
                    "edges": [],
                    "communities": [],
                    "stats": {"total_entities": 0, "total_relationships": 0, "communities_detected": 0},
                    "available_cases": available_cases,
                    "selected_case": None
                }
            authorized_case_ids = [case_id]
            selected_case_meta = {
                "id": target_case.id,
                "fir_number": target_case.fir_number,
                "district": target_case.district,
                "station": target_case.station,
                "status": target_case.status,
            }
            case_lookup[target_case.id] = target_case.fir_number
            vehicle_text[target_case.id] = target_case.vehicle_details

        if not authorized_case_ids:
            return {
                "nodes": [],
                "edges": [],
                "communities": [],
                "stats": {"total_entities": 0, "total_relationships": 0, "communities_detected": 0},
                "available_cases": available_cases,
                "selected_case": selected_case_meta
            }

        # Query mentions strictly in authorized cases (or single case)
        m_stmt = select(EntityMention.entity_id).where(EntityMention.case_id.in_(authorized_case_ids)).distinct()
        m_res = await db.execute(m_stmt)
        authorized_entity_ids = set([row[0] for row in m_res.all()])

        if not authorized_entity_ids:
            return {
                "nodes": [],
                "edges": [],
                "communities": [],
                "stats": {"total_entities": 0, "total_relationships": 0, "communities_detected": 0},
                "available_cases": available_cases,
                "selected_case": selected_case_meta
            }

        e_stmt = select(Entity).where(Entity.is_canonical == True, Entity.id.in_(authorized_entity_ids))
        if case_id:
            edge_stmt = select(GraphEdge).where(GraphEdge.case_id == case_id)
        else:
            edge_stmt = select(GraphEdge).where(
                or_(
                    GraphEdge.case_id.in_(authorized_case_ids),
                    and_(GraphEdge.source_entity_id.in_(authorized_entity_ids), GraphEdge.target_entity_id.in_(authorized_entity_ids))
                )
            )

        e_res = await db.execute(e_stmt)
        # Placeholder names ("Unknown Suspect", "N/A") are not people and are left out of the network
        entities = [e for e in e_res.scalars().all() if not is_placeholder(e.canonical_name)]
        entity_map = {e.id: e for e in entities}

        edge_res = await db.execute(edge_stmt)
        edges = edge_res.scalars().all()

        # Query all source cases and mentions for these entities
        m_cases_stmt = (
            select(EntityMention.entity_id, Case.id, Case.fir_number, Case.district, Case.station, EntityMention.role_in_case,
                   Case.status)
            .join(Case, Case.id == EntityMention.case_id)
            .where(EntityMention.entity_id.in_(list(entity_map.keys())), EntityMention.case_id.in_(authorized_case_ids))
        )
        m_cases_res = await db.execute(m_cases_stmt)
        entity_source_cases: Dict[str, List[Dict[str, Any]]] = {}
        for eid, cid, f_num, dist, stn, role, case_status in m_cases_res.all():
            if eid not in entity_source_cases:
                entity_source_cases[eid] = []
            entity_source_cases[eid].append({
                "case_id": cid,
                "fir_number": f_num,
                "district": dist,
                "station": stn,
                "role_in_case": role,
                "case_status": case_status,
                "is_draft": case_status == "DRAFT",
            })

        # Vehicles: every authorised case whose vehicle field carries the same normalised registration is
        # linked to that vehicle, drafts included (tagged), even when no entity mention was recorded for it
        case_info = {c["id"]: c for c in available_cases}
        if selected_case_meta:
            case_info[selected_case_meta["id"]] = selected_case_meta
        reg_cases: Dict[str, List[str]] = {}
        for cid in authorized_case_ids:
            reg = registration_of(vehicle_text.get(cid))
            if reg:
                reg_cases.setdefault(reg, []).append(cid)
        if reg_cases:
            vehicle_rows = (await db.execute(
                select(Entity).where(Entity.entity_type == "VEHICLE", Entity.is_canonical == True))).scalars().all()  # noqa: E712
            by_reg = {}
            for v in vehicle_rows:
                reg = registration_of(_attrs(v).get("registration_number"), v.canonical_name)
                if reg and reg in reg_cases:
                    by_reg.setdefault(reg, v)
            from types import SimpleNamespace
            for reg, cids in reg_cases.items():
                ent = by_reg.get(reg)
                if ent is None:
                    if not case_id and len(cids) < 2:
                        continue  # a vehicle seen in one case only adds nothing to the cross-case network
                    ent = SimpleNamespace(id=f"vehicle:{reg}", canonical_name=reg, entity_type="VEHICLE",
                                          risk_score=0.0, attributes_json=json.dumps({"registration_number": reg}))
                entity_map.setdefault(ent.id, ent)
                listed = {sc["case_id"] for sc in entity_source_cases.get(ent.id, [])}
                for cid in cids:
                    if cid in listed:
                        continue
                    info = case_info.get(cid, {})
                    entity_source_cases.setdefault(ent.id, []).append({
                        "case_id": cid,
                        "fir_number": info.get("fir_number"),
                        "district": info.get("district"),
                        "station": info.get("station"),
                        "role_in_case": "VEHICLE_USED",
                        "case_status": info.get("status"),
                        "is_draft": info.get("status") == "DRAFT",
                        "linked_by": "VEHICLE_REGISTRATION",
                    })

        # Build NetworkX graph
        G = nx.Graph()
        for e_id, ent in entity_map.items():
            G.add_node(e_id, label=ent.canonical_name, type=ent.entity_type, risk=ent.risk_score)

        for edge in edges:
            if edge.source_entity_id in entity_map and edge.target_entity_id in entity_map:
                G.add_edge(edge.source_entity_id, edge.target_entity_id, weight=edge.weight, edge_type=edge.edge_type)

        # Louvain community detection
        communities = []
        community_assignment = {}
        if len(G.nodes) > 1 and len(G.edges) > 0:
            try:
                raw_comm = nx.algorithms.community.louvain_communities(G, seed=42)
                for c_idx, comm in enumerate(raw_comm):
                    for node_id in comm:
                        community_assignment[node_id] = c_idx
                    communities.append({
                        "community_id": c_idx,
                        "size": len(comm),
                        "label": f"Analytical Network Lead #{c_idx + 1}"
                    })
            except Exception as ex:
                logger.warning(f"Community detection fallback: {ex}")

        # Format nodes for vis-network
        nodes_data = []
        colors = {
            "PERSON": "#3b82f6",       # Blue
            "VEHICLE": "#f59e0b",      # Amber
            "LOCATION": "#10b981",     # Emerald
            "ORGANIZATION": "#8b5cf6", # Purple
            "PHONE": "#06b6d4",        # Cyan
            "PHONE_NUMBER": "#06b6d4"  # Cyan
        }

        for e_id, ent in entity_map.items():
            degree = G.degree[e_id] if e_id in G else 0
            comm_id = community_assignment.get(e_id, 0)
            source_cases = entity_source_cases.get(e_id, [])
            fir_list_str = ", ".join(f"{sc['fir_number']}{' (draft)' if sc.get('is_draft') else ''}"
                                     for sc in source_cases) if source_cases else "Direct Lead"

            display_name = ent.canonical_name
            # Mask phone numbers for station officers without elevated statewide clearance
            if ent.entity_type in ("PHONE", "PHONE_NUMBER") and user.role not in ("STATE", "DISTRICT"):
                attrs = json.loads(ent.attributes_json or "{}")
                display_name = attrs.get("masked", re.sub(r'(\d{5})\d{5}', r'\1*****', ent.canonical_name))

            nodes_data.append({
                "id": ent.id,
                "label": display_name,
                "title": f"Type: {ent.entity_type}\nName: {display_name}\nSource Cases: {fir_list_str}\nObserved Connections: {degree}\nRisk Score: {round(ent.risk_score, 2)}",
                "entity_type": ent.entity_type,
                "value": max(12, degree * 8),
                "color": colors.get(ent.entity_type, "#6b7280"),
                "community_id": comm_id,
                "risk_score": ent.risk_score,
                "source_cases": source_cases,
                "case_count": len(source_cases)
            })

        edges_data = []
        for edge in edges:
            if edge.source_entity_id in entity_map and edge.target_entity_id in entity_map:
                source_fir = case_lookup.get(edge.case_id, "")
                edges_data.append({
                    "id": edge.id,
                    "from": edge.source_entity_id,
                    "to": edge.target_entity_id,
                    "label": edge.edge_type,
                    "title": f"Relationship: {edge.edge_type}\nSource Case: {source_fir or edge.case_id}",
                    "case_id": edge.case_id,
                    "fir_number": source_fir,
                    "color": {"color": "#94a3b8"}
                })

        return {
            "nodes": nodes_data,
            "edges": edges_data,
            "communities": communities,
            "stats": {
                "total_entities": len(nodes_data),
                "total_relationships": len(edges_data),
                "communities_detected": len(communities)
            },
            "available_cases": available_cases,
            "selected_case": selected_case_meta
        }

entity_service = EntityResolutionService()
