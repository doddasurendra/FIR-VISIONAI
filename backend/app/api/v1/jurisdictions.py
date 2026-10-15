from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from ...services.jurisdiction import (
    get_all_districts,
    get_stations_for_district,
    get_jurisdiction_summary,
    validate_jurisdiction
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
