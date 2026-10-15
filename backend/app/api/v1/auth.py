from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from ...database import get_db
from ...models.user import User, RefreshToken
from ...schemas.schemas import LoginRequest, TokenResponse
from ...services.auth import verify_password, create_access_token, create_refresh_token, get_current_user
from ...services.audit import log_audit_event

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.username == req.username, User.is_active == True)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    user.last_login = datetime.utcnow()
    access_token = create_access_token({"sub": user.id, "role": user.role, "district": user.district})
    refresh_token = create_refresh_token({"sub": user.id})

    # Store refresh token
    ref_model = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.add(ref_model)
    await db.commit()

    # Log audit event
    await log_audit_event(
        db=db,
        actor_id=user.id,
        actor_username=user.username,
        action_type="USER_LOGIN",
        object_type="USER",
        object_id=user.id,
        after_state={"role": user.role, "district": user.district, "station": user.station}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "district": user.district,
            "station": user.station,
            "badge_number": user.badge_number,
            "designation": user.designation
        }
    }

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "district": current_user.district,
        "station": current_user.station,
        "badge_number": current_user.badge_number,
        "designation": current_user.designation
    }
