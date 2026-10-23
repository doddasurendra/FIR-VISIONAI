from fastapi import APIRouter, Depends
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Geographic and temporal crime hotspot clusters with coordinates and contraband metrics."""
    return await analytics_service.get_crime_hotspots(user=current_user, db=db)

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

