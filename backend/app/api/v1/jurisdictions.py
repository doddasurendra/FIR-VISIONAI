from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db
from ...models.user import User
from ...services.auth import get_optional_current_user
from ...services.jurisdiction import (
    get_all_districts,
    get_stations_for_district,
    get_jurisdiction_summary,
    validate_jurisdiction,
    match_location_to_jurisdiction,
    detect_exact_station
)

router = APIRouter(prefix="/jurisdictions", tags=["Jurisdiction Master Data"])

@router.get("/districts", response_model=List[str])
async def list_districts():
    """List all 26 official Andhra Pradesh districts."""
    return get_all_districts()

@router.get("/stations", response_model=List[str])
async def list_stations(district: str = Query(..., description="District name in Andhra Pradesh")):
    """List verified Excise Stations for a specific Andhra Pradesh district."""
    stations = get_stations_for_district(district)
    if not stations:
        raise HTTPException(
            status_code=404,
            detail=f"District '{district}' not recognized in Andhra Pradesh master data."
        )
    return stations

@router.get("/summary", response_model=Dict[str, Any])
async def jurisdiction_summary():
    """Return statewide coverage statistics (all 26 districts & stations)."""
    return get_jurisdiction_summary()

@router.get("/reverse-geocode", response_model=Dict[str, Any])
async def reverse_geocode_location(
    latitude: float = Query(..., ge=-90, le=90, description="WGS84 latitude coordinate from browser Geolocation"),
    longitude: float = Query(..., ge=-180, le=180, description="WGS84 longitude coordinate from browser Geolocation"),
    accuracy: Optional[float] = Query(None, description="GPS accuracy in meters"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Reverse-geocodes browser/device coordinates to the nearest authorized Andhra Pradesh
    excise station using verified station coordinates, Haversine spatial calculations,
    and authenticated officer role-based boundaries.
    """
    return await detect_exact_station(
        lat=latitude,
        lon=longitude,
        accuracy=accuracy,
        user=current_user,
        db=db
    )

@router.get("/detect-station", response_model=Dict[str, Any])
async def detect_station_location(
    latitude: float = Query(..., ge=-90, le=90, description="WGS84 latitude coordinate from browser Geolocation"),
    longitude: float = Query(..., ge=-180, le=180, description="WGS84 longitude coordinate from browser Geolocation"),
    accuracy: Optional[float] = Query(None, description="GPS accuracy in meters"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """
    Dedicated endpoint for high-precision station detection against verified station registry.
    """
    return await detect_exact_station(
        lat=latitude,
        lon=longitude,
        accuracy=accuracy,
        user=current_user,
        db=db
    )

