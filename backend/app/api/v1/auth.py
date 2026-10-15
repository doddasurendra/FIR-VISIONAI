from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import jwt
from ...config import settings
from ...database import get_db
from ...models.user import User, RefreshToken
from ...schemas.schemas import LoginRequest, TokenResponse, UserRegisterRequest, RefreshTokenRequest
from ...services.auth import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    get_current_user
)
from ...services.audit import log_audit_event
from ...services.jurisdiction import validate_jurisdiction

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    # 1. Fetch user by username (regardless of is_active to provide explicit error messages)
    stmt = select(User).where(User.username == req.username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect officer username or password."
        )

    # 2. Check active & approval status
    if not user.is_active:
        approval_st = getattr(user, "approval_status", "PENDING_APPROVAL")
        if approval_st == "PENDING_APPROVAL":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your registration request is pending administrative review. An authorized administrator must approve your account."
            )
        elif approval_st == "REJECTED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account registration was rejected by the administrator. Please contact your excise district nodal officer."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is currently deactivated. Please contact your department administrator."
            )

    user.last_login = datetime.utcnow()
    access_token = create_access_token({"sub": user.id, "role": user.role, "district": user.district})
    refresh_token = create_refresh_token({"sub": user.id})

    # Store refresh token
    ref_model = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
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
            "designation": user.designation,
            "department": getattr(user, "department", "AP Prohibition & Excise Department"),
            "approval_status": getattr(user, "approval_status", "APPROVED")
        }
    }

@router.post("/register")
async def register(req: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Self-Registration Endpoint with Strict Role Governance.
    - Password matching & strength validation
    - Duplicate username & email prevention
    - Andhra Pradesh official jurisdiction validation
    - Security rule: STATION accounts are approved for development testing;
      DISTRICT and STATE accounts are created with PENDING_APPROVAL status.
    """
    # 1. Validation: Passwords match
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    # 2. Validation: Username duplicate
    stmt = select(User).where(User.username == req.username)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Username '{req.username}' is already registered.")

    # 3. Validation: Email duplicate
    stmt = select(User).where(User.email == req.email)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Email address '{req.email}' is already registered.")

    # 4. Validation: Jurisdiction check against official Andhra Pradesh master data
    clean_role = req.role.upper().strip()
    if clean_role not in ["STATION", "DISTRICT", "STATE"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be STATION, DISTRICT, or STATE.")

    if clean_role in ["STATION", "DISTRICT"]:
        if not validate_jurisdiction(req.district, req.station if clean_role == "STATION" else None):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid jurisdiction: District '{req.district}' or Station '{req.station}' is not recognized in Andhra Pradesh master data."
            )

    # 5. Security Rule: Self-registration privileges
    # Ordinary/Self-registration must not automatically grant unrestricted district or state privileges.
    if clean_role == "STATION":
        is_active = True
        approval_status = "APPROVED"
        msg = "Account created and activated successfully. You can now sign in with your credentials."
    else:
        # Privileged roles require administrative approval
        is_active = False
        approval_status = "PENDING_APPROVAL"
        msg = f"Registration submitted for {clean_role} role. Your account is pending administrator review and approval."

    new_user = User(
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        password_hash=hash_password(req.password),
        role=clean_role,
        district=req.district if clean_role != "STATE" else "Amaravati Headquarters",
        station=req.station if clean_role == "STATION" else None,
        badge_number=req.badge_number,
        designation=req.designation or "Excise Sub-Inspector",
        department=req.department or "AP Prohibition & Excise Department",
        approval_status=approval_status,
        is_active=is_active
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Log audit event
    await log_audit_event(
        db=db,
        actor_id=new_user.id,
        actor_username=new_user.username,
        action_type="USER_REGISTERED",
        object_type="USER",
        object_id=new_user.id,
        after_state={
            "username": new_user.username,
            "role": new_user.role,
            "district": new_user.district,
            "station": new_user.station,
            "approval_status": approval_status
        }
    )

    return {
        "success": True,
        "message": msg,
        "user_id": new_user.id,
        "username": new_user.username,
        "role": new_user.role,
        "approval_status": approval_status,
        "is_active": is_active
    }

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token using stored refresh token with rotation."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not refresh token: invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "refresh":
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    # Verify refresh token in database
    stmt = select(RefreshToken).where(
        RefreshToken.token == req.refresh_token,
        RefreshToken.is_revoked == False
    )
    res = await db.execute(stmt)
    db_token = res.scalar_one_or_none()
    if not db_token or db_token.expires_at < datetime.utcnow():
        raise credentials_exception

    # Fetch user
    u_stmt = select(User).where(User.id == user_id, User.is_active == True)
    u_res = await db.execute(u_stmt)
    user = u_res.scalar_one_or_none()
    if not user:
        raise credentials_exception

    # Issue new access token and rotated refresh token
    new_access = create_access_token({"sub": user.id, "role": user.role, "district": user.district})
    new_refresh = create_refresh_token({"sub": user.id})

    # Revoke old token & store new one
    db_token.is_revoked = True
    new_ref_model = RefreshToken(
        user_id=user.id,
        token=new_refresh,
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(new_ref_model)
    await db.commit()

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
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
            "designation": user.designation,
            "department": getattr(user, "department", "AP Prohibition & Excise Department"),
            "approval_status": getattr(user, "approval_status", "APPROVED")
        }
    }

@router.post("/forgot-password")
async def forgot_password(data: dict, db: AsyncSession = Depends(get_db)):
    """Development / Demonstration password assistance endpoint."""
    username = data.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    stmt = select(User).where(User.username == username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        return {
            "success": True,
            "message": "If an account exists for this username, password reset instructions have been dispatched."
        }

    # In development mode, provide clear self-service or admin reset guidance
    return {
        "success": True,
        "message": f"Password reset instructions for officer '{username}' have been queued. In development mode, administrators can also reset this account directly from the Employee Management console, or you can use the documented development credentials."
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
        "designation": current_user.designation,
        "department": getattr(current_user, "department", "AP Prohibition & Excise Department"),
        "approval_status": getattr(current_user, "approval_status", "APPROVED")
    }
