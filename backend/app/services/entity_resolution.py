import json
import logging
import networkx as nx
from typing import Dict, Any, List, Optional, Tuple
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, update
from ..models.entity import Entity, EntityMention, GraphEdge
from ..models.case import Case
from ..models.user import User

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
    async def build_network_graph(user: User, db: AsyncSession) -> Dict[str, Any]:
        """
        Construct NetworkX graph, detect Louvain communities, and return
        clickable node and edge JSON for frontend visualization.
        """
        # Fetch canonical entities
        e_stmt = select(Entity).where(Entity.is_canonical == True)
        e_res = await db.execute(e_stmt)
        entities = e_res.scalars().all()
        entity_map = {e.id: e for e in entities}

        # Fetch graph edges
        edge_stmt = select(GraphEdge)
        edge_res = await db.execute(edge_stmt)
        edges = edge_res.scalars().all()

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
            "PERSON": "#3b82f6",     # Blue
            "VEHICLE": "#f59e0b",    # Amber
            "LOCATION": "#10b981",   # Emerald
            "ORGANIZATION": "#8b5cf6" # Purple
        }

        for e_id, ent in entity_map.items():
            degree = G.degree[e_id] if e_id in G else 0
            comm_id = community_assignment.get(e_id, 0)
            nodes_data.append({
                "id": ent.id,
                "label": ent.canonical_name,
                "title": f"Type: {ent.entity_type}\nAliases: {ent.aliases_json}\nObserved Cases: {degree}\nRisk: {round(ent.risk_score, 2)}",
                "entity_type": ent.entity_type,
                "value": max(10, degree * 8), # Node size based on observed case frequency
                "color": colors.get(ent.entity_type, "#6b7280"),
                "community_id": comm_id,
                "risk_score": ent.risk_score
            })

        edges_data = []
        for edge in edges:
            if edge.source_entity_id in entity_map and edge.target_entity_id in entity_map:
                edges_data.append({
                    "id": edge.id,
                    "from": edge.source_entity_id,
                    "to": edge.target_entity_id,
                    "label": edge.edge_type,
                    "title": f"Relationship: {edge.edge_type}\nCase ID: {edge.case_id}",
                    "case_id": edge.case_id,
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
            }
        }

entity_service = EntityResolutionService()
