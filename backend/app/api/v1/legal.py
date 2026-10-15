from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db
from ...models.user import User
from ...models.legal import LegalCorpus, CaseLegalSection
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search verified legal corpus (Andhra Pradesh Excise Act, BNS, historical IPC)."""
    stmt = select(LegalCorpus).where(LegalCorpus.verification_status == "VERIFIED")
    if act_name:
        stmt = stmt.where(LegalCorpus.act_name.ilike(f"%{act_name}%"))
    if query:
        stmt = stmt.where(
            LegalCorpus.section_number.ilike(f"%{query}%") |
            LegalCorpus.section_title.ilike(f"%{query}%") |
            LegalCorpus.full_text.ilike(f"%{query}%")
        )
    res = await db.execute(stmt)
    return res.scalars().all()

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
