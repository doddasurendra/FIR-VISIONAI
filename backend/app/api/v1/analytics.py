from fastapi import APIRouter, Depends
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
    """Real database-backed dashboard KPIs scoped to officer role."""
    data = await analytics_service.get_dashboard_kpis(user=current_user, db=db)
    return data

@router.get("/repeat-offenders")
async def get_repeat_offender_risk_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Explainable repeat offender risk patterns."""
    data = await analytics_service.get_repeat_offender_analysis(user=current_user, db=db)
    return data
