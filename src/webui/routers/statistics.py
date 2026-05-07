from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from src.common.logger import get_logger
from src.services.statistics_service import get_dashboard_statistics, get_model_statistics, get_summary_statistics
from src.webui.dependencies import require_auth
from src.webui.schemas.statistics import DashboardData

logger = get_logger("webui.statistics")

router = APIRouter(prefix="/statistics", tags=["statistics"], dependencies=[Depends(require_auth)])


@router.get("/dashboard", response_model=DashboardData)
async def get_dashboard_data(hours: int = 24) -> DashboardData:
    """获取仪表盘统计数据。"""
    try:
        return await get_dashboard_statistics(hours=hours)
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}") from e


@router.get("/summary")
async def get_summary(hours: int = 24):
    """获取统计摘要。"""
    try:
        now = datetime.now()
        start_time = now - timedelta(hours=hours)
        return await get_summary_statistics(start_time, now)
    except Exception as e:
        logger.error(f"获取统计摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/models")
async def get_model_stats(hours: int = 24):
    """获取模型统计。"""
    try:
        start_time = datetime.now() - timedelta(hours=hours)
        return await get_model_statistics(start_time)
    except Exception as e:
        logger.error(f"获取模型统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
