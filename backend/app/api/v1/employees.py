from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database import get_db
from ...models.user import User
from ...schemas.schemas import UserCreate, UserResponse
from ...services.auth import get_current_user, hash_password
from ...services.audit import log_audit_event

router = APIRouter(prefix="/employees", tags=["Employee Management"])

@router.get("/", response_model=List[UserResponse])
async def list_employees(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(User)
    if current_user.role == "DISTRICT":
        stmt = stmt.where(User.district.ilike(current_user.district))
    elif current_user.role == "STATION":
        stmt = stmt.where(User.station.ilike(current_user.station))

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
        designation=req.designation or "Excise Sub-Inspector"
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
    return {"message": f"Employee is now {'active' if emp.is_active else 'deactivated'}"}
