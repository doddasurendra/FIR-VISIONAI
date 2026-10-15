from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db
from ...models.user import User
from ...schemas.schemas import UserCreate, UserResponse, PasswordResetRequest, ApprovalDecisionRequest
from ...services.auth import get_current_user, hash_password
from ...services.audit import log_audit_event
from ...services.jurisdiction import validate_jurisdiction

router = APIRouter(prefix="/employees", tags=["Employee Management"])

@router.get("/", response_model=List[UserResponse])
async def list_employees(
    approval_status: Optional[str] = Query(None, description="Filter by approval status: APPROVED, PENDING_APPROVAL, REJECTED"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(User)
    if current_user.role == "DISTRICT":
        stmt = stmt.where(User.district.ilike(current_user.district))
    elif current_user.role == "STATION":
        stmt = stmt.where(User.station.ilike(current_user.station))

    if approval_status:
        stmt = stmt.where(User.approval_status == approval_status.upper())

    stmt = stmt.order_by(User.created_at.desc())
    res = await db.execute(stmt)
    users = res.scalars().all()
    return users

@router.post("/", response_model=UserResponse)
async def create_employee(
    req: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only STATE or DISTRICT can create employees
    if current_user.role not in ["STATE", "DISTRICT"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You lack authorization to create department employees."
        )

    # Prevent role elevation: DISTRICT user cannot create STATE admin
    if current_user.role == "DISTRICT" and req.role in ["STATE", "DISTRICT"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="District administrators can only create station officers within their district."
        )

    # Validate jurisdiction
    if not validate_jurisdiction(req.district, req.station if req.role == "STATION" else None):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid jurisdiction: District '{req.district}' or Station '{req.station}' not recognized in Andhra Pradesh master data."
        )

    # Check username duplicate
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_emp = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        role=req.role,
        district=req.district if current_user.role == "STATE" else current_user.district,
        station=req.station,
        badge_number=req.badge_number,
        designation=req.designation or "Excise Sub-Inspector",
        department=req.department or "AP Prohibition & Excise Department",
        approval_status="APPROVED",
        is_active=True
    )
    db.add(new_emp)
    await db.commit()
    await db.refresh(new_emp)

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="EMPLOYEE_CREATED",
        object_type="USER",
        object_id=new_emp.id,
        after_state={"username": new_emp.username, "role": new_emp.role, "district": new_emp.district}
    )

    return new_emp

@router.post("/{employee_id}/approve")
async def approve_registration(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Administrator workflow: Approve a pending self-registration request."""
    if current_user.role not in ["STATE", "DISTRICT"]:
        raise HTTPException(status_code=403, detail="Unauthorized to approve accounts.")

    stmt = select(User).where(User.id == employee_id)
    res = await db.execute(stmt)
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Scope check: District admin can only approve within their district
    if current_user.role == "DISTRICT" and emp.district.lower() != current_user.district.lower():
        raise HTTPException(status_code=403, detail="District administrators can only approve officers in their own district.")

    emp.is_active = True
    emp.approval_status = "APPROVED"
    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="ACCOUNT_APPROVED",
        object_type="USER",
        object_id=emp.id,
        after_state={"username": emp.username, "approval_status": "APPROVED", "is_active": True}
    )

    return {"success": True, "message": f"Account for '{emp.username}' ({emp.role}) approved and activated successfully."}

@router.post("/{employee_id}/reject")
async def reject_registration(
    employee_id: str,
    req: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Administrator workflow: Reject a pending self-registration request."""
    if current_user.role not in ["STATE", "DISTRICT"]:
        raise HTTPException(status_code=403, detail="Unauthorized to reject accounts.")

    stmt = select(User).where(User.id == employee_id)
    res = await db.execute(stmt)
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    emp.is_active = False
    emp.approval_status = "REJECTED"
    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="ACCOUNT_REJECTED",
        object_type="USER",
        object_id=emp.id,
        after_state={"username": emp.username, "approval_status": "REJECTED", "reason": req.reason}
    )

    return {"success": True, "message": f"Account registration for '{emp.username}' has been rejected."}

@router.post("/{employee_id}/reset-password")
async def reset_employee_password(
    employee_id: str,
    req: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Administrator workflow: Reset an employee's password securely."""
    if current_user.role not in ["STATE", "DISTRICT"]:
        raise HTTPException(status_code=403, detail="Unauthorized to reset passwords.")

    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    stmt = select(User).where(User.id == employee_id)
    res = await db.execute(stmt)
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if current_user.role == "DISTRICT" and emp.district.lower() != current_user.district.lower():
        raise HTTPException(status_code=403, detail="Cannot reset passwords outside your assigned district.")

    emp.password_hash = hash_password(req.new_password)
    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="PASSWORD_RESET_BY_ADMIN",
        object_type="USER",
        object_id=emp.id,
        after_state={"username": emp.username, "action": "password_reset"}
    )

    return {"success": True, "message": f"Password for '{emp.username}' reset successfully."}

@router.put("/{employee_id}/toggle-status")
async def toggle_employee_status(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role not in ["STATE", "DISTRICT"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    stmt = select(User).where(User.id == employee_id)
    res = await db.execute(stmt)
    emp = res.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    if current_user.role == "DISTRICT" and emp.district.lower() != current_user.district.lower():
        raise HTTPException(status_code=403, detail="Cannot alter status outside your district.")

    emp.is_active = not emp.is_active
    await db.commit()

    await log_audit_event(
        db=db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action_type="EMPLOYEE_STATUS_TOGGLED",
        object_type="USER",
        object_id=emp.id,
        after_state={"is_active": emp.is_active}
    )
    return {"message": f"Employee '{emp.username}' is now {'active' if emp.is_active else 'deactivated'}"}
