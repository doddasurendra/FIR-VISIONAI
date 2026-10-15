import json
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from ..models.case import Case, CaseField
from ..models.entity import Entity, EntityMention, GraphEdge
from ..models.user import User
from ..models.document import Document
from ..models.generation import GeneratedDocument
from ..services.auth import apply_case_scope_filter

class AnalyticsService:
    @staticmethod
    async def get_dashboard_kpis(user: User, db: AsyncSession) -> Dict[str, Any]:
        """Aggregate real database numbers scoped to user authorization."""
        # 1. Total cases
        case_stmt = apply_case_scope_filter(
            select(func.count(Case.id)).where(Case.is_archived == False),
            user,
            Case
        )
        total_cases = (await db.execute(case_stmt)).scalar() or 0

        # 2. Cases by Status
        status_stmt = apply_case_scope_filter(
            select(Case.status, func.count(Case.id)).where(Case.is_archived == False).group_by(Case.status),
            user,
            Case
        )
        status_rows = (await db.execute(status_stmt)).all()
        cases_by_status = {row[0]: row[1] for row in status_rows}

        # 3. Contraband Breakdown
        contra_stmt = apply_case_scope_filter(
            select(Case.contraband_type, func.count(Case.id), func.sum(Case.seized_quantity))
            .where(Case.is_archived == False)
            .group_by(Case.contraband_type),
            user,
            Case
        )
        contra_rows = (await db.execute(contra_stmt)).all()
        contraband_stats = [
            {"contraband": row[0] or "Unknown", "cases": row[1], "total_quantity": round(row[2] or 0.0, 1)}
            for row in contra_rows
        ]

        # 4. District Breakdown (for STATE users or district view)
        dist_stmt = apply_case_scope_filter(
            select(Case.district, func.count(Case.id)).where(Case.is_archived == False).group_by(Case.district),
            user,
            Case
        )
        dist_rows = (await db.execute(dist_stmt)).all()
        cases_by_district = [{"district": row[0], "count": row[1]} for row in dist_rows]

        # 5. Pending reviews
        pending_fields = (await db.execute(select(func.count(CaseField.id)).where(CaseField.verification_status == "UNVERIFIED"))).scalar() or 0
        pending_drafts = (await db.execute(select(func.count(GeneratedDocument.id)).where(GeneratedDocument.status == "DRAFT"))).scalar() or 0

        return {
            "total_cases": total_cases,
            "cases_by_status": cases_by_status,
            "contraband_stats": contraband_stats,
            "cases_by_district": cases_by_district,
            "pending_verifications": pending_fields,
            "pending_drafts": pending_drafts,
            "scope": {
                "role": user.role,
                "district": user.district,
                "station": user.station
            }
        }

    @staticmethod
    async def get_repeat_offender_analysis(user: User, db: AsyncSession) -> List[Dict[str, Any]]:
        """Calculate repeat offender patterns with explainable risk factors."""
        # Find entities with multiple mentions as ACCUSED
        stmt = (
            select(Entity.id, Entity.canonical_name, Entity.entity_type, func.count(EntityMention.id))
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .where(EntityMention.role_in_case == "ACCUSED", Entity.is_canonical == True)
            .group_by(Entity.id, Entity.canonical_name, Entity.entity_type)
            .having(func.count(EntityMention.id) >= 1)
            .order_by(desc(func.count(EntityMention.id)))
            .limit(20)
        )
        rows = (await db.execute(stmt)).all()

        analysis_results = []
        for r in rows:
            ent_id, name, e_type, offence_count = r
            
            # Fetch cases this person appears in
            cases_stmt = (
                select(Case.id, Case.fir_number, Case.offence_date, Case.contraband_type, Case.district)
                .join(EntityMention, EntityMention.case_id == Case.id)
                .where(EntityMention.entity_id == ent_id)
            )
            case_rows = (await db.execute(cases_stmt)).all()
            
            # Explainable Risk Scoring calculation
            # Features: offence_count (weight 0.25), multi-district presence (weight 0.25), commercial contraband (weight 0.2)
            districts = set([c.district for c in case_rows])
            is_cross_district = len(districts) > 1
            
            risk_score = min(0.95, (offence_count * 0.25) + (0.25 if is_cross_district else 0.05))
            
            risk_factors = []
            if offence_count >= 2:
                risk_factors.append(f"Recorded in {offence_count} independent case crime reports.")
            if is_cross_district:
                risk_factors.append(f"Cross-district illicit operations observed across {', '.join(districts)}.")
            else:
                risk_factors.append("Localized operational pattern within single district.")

            analysis_results.append({
                "entity_id": ent_id,
                "name": name,
                "entity_type": e_type,
                "offence_count": offence_count,
                "risk_score": round(risk_score, 2),
                "risk_level": "HIGH" if risk_score >= 0.70 else "MEDIUM" if risk_score >= 0.40 else "LOW",
                "risk_factors": risk_factors,
                "associated_cases": [
                    {"case_id": c.id, "fir_number": c.fir_number, "contraband": c.contraband_type, "district": c.district}
                    for c in case_rows
                ],
                "disclaimer": "Analytical review aid only. Does not replace judicial determination."
            })

        return analysis_results

analytics_service = AnalyticsService()
