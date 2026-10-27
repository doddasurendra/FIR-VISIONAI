from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import get_db
from ...models.user import User
from ...services.auth import get_current_user
from ...services.analytics import analytics_service

router = APIRouter(prefix="/analytics", tags=["Reports & Analytics"])

@router.get("/dashboard")
async def get_dashboard_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Real database-backed dashboard KPIs scoped to officer role with 60-second client cache."""
    data = await analytics_service.get_dashboard_kpis(user=current_user, db=db)
    return JSONResponse(content=data, headers={"Cache-Control": "private, max-age=60"})

@router.get("/repeat-offenders")
async def get_repeat_offender_risk_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Explainable repeat offender risk patterns."""
    data = await analytics_service.get_repeat_offender_analysis(user=current_user, db=db)
    return data

@router.get("/hotspots")
async def get_crime_hotspots(
    date_from: Optional[date] = Query(None, description="Incident date from (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Incident date to (YYYY-MM-DD)"),
    offence_type: Optional[str] = Query(None, max_length=500),
    contraband_type: Optional[str] = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Hotspot clusters from each case's geocoded incident location within the user's jurisdiction,
    every located incident, and the cases whose location is not yet verified.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date_from must be on or before date_to.")
    return await analytics_service.get_crime_hotspots(
        user=current_user, db=db, date_from=date_from, date_to=date_to,
        offence_type=offence_type or None, contraband_type=contraband_type or None)

@router.get("/risk-evaluation")
async def evaluate_risk_prediction_pipeline(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reproducible evaluation pipeline for repeat-offender risk prediction (>90% accuracy target)."""
    return await analytics_service.evaluate_risk_prediction_pipeline(user=current_user, db=db)

@router.get("/pilot-metrics")
async def get_pilot_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Operational readiness metrics for 60-day Proof of Concept across Kurnool, Guntur, and Vizag."""
    return await analytics_service.get_pilot_readiness_metrics(user=current_user, db=db)

