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

class EntityResolutionService:
    @staticmethod
    def compute_similarity(e1: Entity, e2: Entity) -> float:
        """Calculate hybrid similarity using name token ratio and attribute matching."""
        if e1.entity_type != e2.entity_type:
            return 0.0

        # RapidFuzz token sort ratio
        name_sim = fuzz.token_sort_ratio(e1.canonical_name.lower(), e2.canonical_name.lower()) / 100.0

        # Attribute overlap (e.g. vehicle registration number, phone, address)
        try:
            attr1 = json.loads(e1.attributes_json or "{}")
            attr2 = json.loads(e2.attributes_json or "{}")
            
            # Exact match on vehicle registration
            if e1.entity_type == "VEHICLE":
                reg1 = attr1.get("registration_number", "").replace(" ", "").upper()
                reg2 = attr2.get("registration_number", "").replace(" ", "").upper()
                if reg1 and reg2 and reg1 == reg2:
                    return 1.0

            # Exact match on phone or aadhaar
            if attr1.get("phone") and attr2.get("phone") and attr1.get("phone") == attr2.get("phone"):
                return 0.98

        except Exception:
            pass

        return name_sim

    @staticmethod
    async def find_review_candidates(db: AsyncSession) -> List[Dict[str, Any]]:
        """Find candidate pairs that need human review (score between 0.75 and 0.92)."""
        stmt = select(Entity).where(Entity.is_canonical == True)
        res = await db.execute(stmt)
        entities = res.scalars().all()

        candidates = []
        n = len(entities)
        for i in range(n):
            for j in range(i + 1, n):
                e1 = entities[i]
                e2 = entities[j]
                if e1.entity_type != e2.entity_type:
                    continue

                sim = EntityResolutionService.compute_similarity(e1, e2)
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
            select(Case.id, Case.fir_number, Case.district, Case.station).where(Case.is_archived == False).order_by(Case.registration_date.desc()),
            user,
            Case
        )
        all_cases_res = await db.execute(all_cases_stmt)
        available_cases = [
            {"id": row[0], "fir_number": row[1], "district": row[2], "station": row[3]}
            for row in all_cases_res.all()
        ]
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
                "station": target_case.station
            }
            case_lookup[target_case.id] = target_case.fir_number

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
        entities = e_res.scalars().all()
        entity_map = {e.id: e for e in entities}

        edge_res = await db.execute(edge_stmt)
        edges = edge_res.scalars().all()

        # Query all source cases and mentions for these entities
        m_cases_stmt = (
            select(EntityMention.entity_id, Case.id, Case.fir_number, Case.district, Case.station, EntityMention.role_in_case)
            .join(Case, Case.id == EntityMention.case_id)
            .where(EntityMention.entity_id.in_(list(entity_map.keys())), EntityMention.case_id.in_(authorized_case_ids))
        )
        m_cases_res = await db.execute(m_cases_stmt)
        entity_source_cases: Dict[str, List[Dict[str, Any]]] = {}
        for eid, cid, f_num, dist, stn, role in m_cases_res.all():
            if eid not in entity_source_cases:
                entity_source_cases[eid] = []
            entity_source_cases[eid].append({
                "case_id": cid,
                "fir_number": f_num,
                "district": dist,
                "station": stn,
                "role_in_case": role
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
            fir_list_str = ", ".join(sc["fir_number"] for sc in source_cases) if source_cases else "Direct Lead"

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
