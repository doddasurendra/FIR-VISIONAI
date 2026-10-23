from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ...database import get_db
from ...models.user import User
from ...models.legal import LegalCorpus, CaseLegalSection
from ...models.document import Document
from ...schemas.schemas import OfficerLegalDecisionRequest
from ...services.auth import get_current_user
from ...services.legal_service import legal_service
from ...services.audit import log_audit_event

router = APIRouter(prefix="/legal", tags=["Legal Section Assistance"])

@router.get("/recommend/{case_id}")
async def recommend_sections_for_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Section 27: Case Facts -> Candidate Sections Recommendation Workflow."""
    result = await legal_service.recommend_sections_for_case(
        case_id=case_id,
        user=current_user,
        db=db
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@router.get("/search")
async def search_legal_corpus(
    query: Optional[str] = None,
    act_name: Optional[str] = None,
    category: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    status: Optional[str] = None,   # ACTIVE | HISTORICAL | ALL
    section_number: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search verified legal corpus with advanced filters.
    Supports category, jurisdiction, status (ACTIVE/HISTORICAL), and section number filters.
    """
    stmt = select(LegalCorpus).where(LegalCorpus.verification_status == "VERIFIED")

    if act_name:
        stmt = stmt.where(LegalCorpus.act_name.ilike(f"%{act_name}%"))
    if category:
        stmt = stmt.where(LegalCorpus.category == category)
    if jurisdiction:
        stmt = stmt.where(LegalCorpus.jurisdiction.ilike(f"%{jurisdiction}%"))
    if section_number:
        stmt = stmt.where(LegalCorpus.section_number.ilike(f"%{section_number}%"))

    # Status filter: ACTIVE = no repeal_date, HISTORICAL = has repeal_date
    if status == "ACTIVE":
        stmt = stmt.where(LegalCorpus.repeal_date == None)
    elif status == "HISTORICAL":
        stmt = stmt.where(LegalCorpus.repeal_date != None)

    if query:
        stmt = stmt.where(
            LegalCorpus.section_number.ilike(f"%{query}%") |
            LegalCorpus.section_title.ilike(f"%{query}%") |
            LegalCorpus.full_text.ilike(f"%{query}%") |
            LegalCorpus.act_name.ilike(f"%{query}%")
        )

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_res = await db.execute(count_stmt)
    total = count_res.scalar() or 0

    stmt = stmt.order_by(LegalCorpus.act_name, LegalCorpus.section_number).offset(skip).limit(limit)
    res = await db.execute(stmt)
    sections = res.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "results": [
            {
                "id": s.id,
                "act_name": s.act_name,
                "section_number": s.section_number,
                "section_title": s.section_title,
                "full_text": s.full_text,
                "explanation": s.explanation,
                "essential_ingredients_json": s.essential_ingredients_json,
                "penalty_text": s.penalty_text,
                "effective_date": s.effective_date,
                "repeal_date": s.repeal_date,
                "version": s.version,
                "jurisdiction": s.jurisdiction,
                "source_url": s.source_url,
                "source_gazette": s.source_gazette,
                "verification_status": s.verification_status,
                "document_id": s.document_id,
                "category": s.category,
                "is_historical": bool(s.repeal_date),
            }
            for s in sections
        ]
    }

@router.get("/acts")
async def list_acts(
    category: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all Acts indexed in LegalCorpus with section counts, effective date, category, and jurisdiction.
    Groups LegalCorpus records by act_name.
    """
    stmt = select(
        LegalCorpus.act_name,
        LegalCorpus.category,
        LegalCorpus.jurisdiction,
        LegalCorpus.effective_date,
        LegalCorpus.repeal_date,
        LegalCorpus.version,
        LegalCorpus.source_url,
        LegalCorpus.document_id,
        func.count(LegalCorpus.id).label("section_count")
    ).where(LegalCorpus.verification_status == "VERIFIED")

    if category:
        stmt = stmt.where(LegalCorpus.category == category)
    if jurisdiction:
        stmt = stmt.where(LegalCorpus.jurisdiction.ilike(f"%{jurisdiction}%"))

    stmt = stmt.group_by(
        LegalCorpus.act_name, LegalCorpus.category, LegalCorpus.jurisdiction,
        LegalCorpus.effective_date, LegalCorpus.repeal_date, LegalCorpus.version,
        LegalCorpus.source_url, LegalCorpus.document_id
    ).order_by(LegalCorpus.category, LegalCorpus.act_name)

    res = await db.execute(stmt)
    rows = res.all()

    acts = []
    for r in rows:
        # Try to get document title
        doc_title = None
        if r.document_id:
            doc_res = await db.execute(
                select(Document.document_title, Document.version_date).where(Document.id == r.document_id)
            )
            doc_row = doc_res.first()
            if doc_row:
                doc_title = doc_row.document_title

        acts.append({
            "act_name": r.act_name,
            "document_title": doc_title or r.act_name,
            "category": r.category,
            "jurisdiction": r.jurisdiction,
            "effective_date": r.effective_date,
            "repeal_date": r.repeal_date,
            "version": r.version,
            "source_url": r.source_url,
            "document_id": r.document_id,
            "section_count": r.section_count,
            "is_historical": bool(r.repeal_date),
        })

    return {"acts": acts, "total": len(acts)}

@router.get("/acts/sections")
async def get_act_sections(
    act_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch all indexed sections for a given Act."""
    stmt = select(LegalCorpus).where(
        LegalCorpus.act_name.ilike(f"%{act_name}%"),
        LegalCorpus.verification_status == "VERIFIED"
    ).order_by(LegalCorpus.section_number)
    res = await db.execute(stmt)
    sections = res.scalars().all()

    if not sections:
        raise HTTPException(status_code=404, detail=f"No sections found for Act: {act_name}")

    return {
        "act_name": sections[0].act_name if sections else act_name,
        "total": len(sections),
        "sections": [
            {
                "id": s.id,
                "section_number": s.section_number,
                "section_title": s.section_title,
                "full_text": s.full_text,
                "explanation": s.explanation,
                "essential_ingredients_json": s.essential_ingredients_json,
                "penalty_text": s.penalty_text,
                "effective_date": s.effective_date,
                "repeal_date": s.repeal_date,
                "jurisdiction": s.jurisdiction,
                "source_url": s.source_url,
                "source_gazette": s.source_gazette,
                "category": s.category,
                "is_historical": bool(s.repeal_date),
            }
            for s in sections
        ]
    }

@router.get("/stats")
async def get_legal_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Summary statistics: total sections, acts, by category."""
    total_res = await db.execute(select(func.count(LegalCorpus.id)).where(LegalCorpus.verification_status == "VERIFIED"))
    total = total_res.scalar() or 0

    by_cat_res = await db.execute(
        select(LegalCorpus.category, func.count(LegalCorpus.id).label("cnt"))
        .where(LegalCorpus.verification_status == "VERIFIED")
        .group_by(LegalCorpus.category)
        .order_by(LegalCorpus.category)
    )
    by_category = {r.category: r.cnt for r in by_cat_res.all()}

    acts_res = await db.execute(
        select(func.count(func.distinct(LegalCorpus.act_name)))
        .where(LegalCorpus.verification_status == "VERIFIED")
    )
    total_acts = acts_res.scalar() or 0

    historical_res = await db.execute(
        select(func.count(LegalCorpus.id)).where(
            LegalCorpus.verification_status == "VERIFIED",
            LegalCorpus.repeal_date != None
        )
    )
    historical = historical_res.scalar() or 0

    return {
        "total_sections": total,
        "total_acts": total_acts,
        "active_sections": total - historical,
        "historical_sections": historical,
        "by_category": by_category,
    }

@router.post("/decision")
async def record_officer_legal_decision(
    req: OfficerLegalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save officer's accepted or rejected decision for a legal section with reason."""
    try:
        record = await legal_service.record_officer_decision(
            case_id=req.case_id,
            legal_corpus_id=req.legal_corpus_id,
            decision=req.decision,
            reason=req.reason or "Reviewed by officer",
            user=current_user,
            db=db
        )

        await log_audit_event(
            db=db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action_type="LEGAL_SECTION_DECISION",
            object_type="CASE_LEGAL_SECTION",
            object_id=record.id,
            after_state={
                "case_id": req.case_id,
                "section": f"{record.act_name} {record.section_number}",
                "decision": req.decision,
                "reason": req.reason
            }
        )

        return record
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/case/{case_id}/sections")
async def get_case_sections(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(CaseLegalSection).where(CaseLegalSection.case_id == case_id)
    res = await db.execute(stmt)
    return res.scalars().all()
