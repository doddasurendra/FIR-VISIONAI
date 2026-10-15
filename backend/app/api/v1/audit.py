from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from ...database import get_db
from ...models.user import User
from ...models.audit import AuditLog
from ...services.auth import get_current_user
from ...services.audit import verify_audit_chain

router = APIRouter(prefix="/audit", tags=["Audit Trail & Evidence Integrity"])

@router.get("/")
async def list_audit_logs(
    action_type: str = Query(None),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(AuditLog).order_by(desc(AuditLog.id))
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    res = await db.execute(stmt.limit(limit))
    return res.scalars().all()

@router.get("/verify-integrity")
async def verify_chain_integrity(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Section 15: Verify cryptographic integrity of the SHA-256 tamper-evident hash chain.
    """
    is_valid, count, error_msg = await verify_audit_chain(db)
    return {
        "is_chain_intact": is_valid,
        "verified_entries_count": count,
        "verification_status": "SECURE_AND_VERIFIED" if is_valid else "CORRUPTED_OR_TAMPERED",
        "error_details": error_msg,
        "algorithm": "SHA-256 Recursive Hash Chaining",
        "verified_by_actor": current_user.username
    }
