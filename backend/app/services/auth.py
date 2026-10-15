from datetime import datetime, timedelta
from typing import Optional, List
import jwt
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..config import settings
from ..database import get_db
from ..models.user import User, RefreshToken

ph = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    # Add random jti so each token is unique even for same user within same second
    to_encode.update({"exp": expire, "type": "refresh", "jti": secrets.token_hex(16)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials: invalid token claims",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: authentication token has expired. Please refresh or log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: user account does not exist",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        approval_st = getattr(user, 'approval_status', 'INACTIVE')
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account access denied: status is '{approval_st}'. Administrator approval is required.",
        )
    return user

def enforce_data_scope(user: User, target_district: Optional[str], target_station: Optional[str]) -> bool:
    """
    Enforce hierarchical data visibility rules:
    - STATE role: Permitted across all districts & stations
    - DISTRICT role: Permitted only within assigned district
    - STATION role: Permitted only within assigned station
    """
    if user.role == "STATE":
        return True
    if user.role == "DISTRICT":
        return target_district is not None and user.district.lower() == target_district.lower()
    if user.role == "STATION":
        station_match = (
            user.station and target_station and user.station.lower() == target_station.lower()
        )
        district_match = target_district is not None and user.district.lower() == target_district.lower()
        return district_match and station_match
    return False

def apply_case_scope_filter(query, user: User, case_model):
    """Apply server-side SQLAlchemy filtering to guarantee role isolation."""
    if user.role == "STATE":
        return query
    if user.role == "DISTRICT":
        return query.where(case_model.district.ilike(user.district))
    if user.role == "STATION":
        return query.where(
            case_model.district.ilike(user.district),
            case_model.station.ilike(user.station)
        )
    return query.where(case_model.id == "unauthorized")
