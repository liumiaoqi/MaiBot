from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.common.database.database import get_db_session
from src.common.database.database_model import ChatSession, ModelUsage
from src.common.logger import get_logger
from src.services.statistics_service import get_dashboard_statistics, get_model_statistics, get_summary_statistics
from src.webui.dependencies import require_auth
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.base import ApiResponse
from src.webui.schemas.statistics import AgentStatisticsItem, AgentStatisticsResponse, DashboardData

from sqlalchemy import func
from sqlmodel import col, select

logger = get_logger("webui.statistics")

router = APIRouter(prefix="/statistics", tags=["statistics"], dependencies=[Depends(require_auth)])


@router.get("/dashboard", response_model=ApiResponse[DashboardData])
async def get_dashboard_data(hours: int = 24):
    """获取仪表盘统计数据。"""
    try:
        data = await get_dashboard_statistics(hours=hours)
        return ApiResponse(data=data)
    except AppError:
        raise
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取统计数据失败: {str(e)}") from e


@router.get("/summary", response_model=ApiResponse)
async def get_summary(hours: int = 24):
    """获取统计摘要。"""
    try:
        now = datetime.now()
        start_time = now - timedelta(hours=hours)
        data = await get_summary_statistics(start_time, now)
        return ApiResponse(data=data)
    except AppError:
        raise
    except Exception as e:
        logger.error(f"获取统计摘要失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取统计摘要失败: {str(e)}") from e


@router.get("/models", response_model=ApiResponse)
async def get_model_stats(hours: int = 24):
    """获取模型统计。"""
    try:
        now = datetime.now()
        start_time = now - timedelta(hours=hours)
        data = await get_model_statistics(start_time, now)
        return ApiResponse(data=data)
    except AppError:
        raise
    except Exception as e:
        logger.error(f"获取模型统计失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取模型统计失败: {str(e)}") from e


@router.get("/agents", response_model=ApiResponse[AgentStatisticsResponse])
async def get_agent_statistics(hours: int = 24):
    """按智能体维度聚合 LLM 调用统计。

    通过 ModelUsage.session_id 关联 ChatSession.agent_id 实现按智能体分组。
    """
    try:
        now = datetime.now()
        start_time = now - timedelta(hours=hours)

        with get_db_session(auto_commit=False) as session:
            session_agent_map: dict[str, str] = {}
            chat_sessions = session.exec(select(ChatSession)).all()
            for cs in chat_sessions:
                if cs.session_id and cs.agent_id:
                    session_agent_map[cs.session_id] = cs.agent_id

            statement = (
                select(
                    ModelUsage.session_id,
                    func.count().label("request_count"),
                    func.sum(col(ModelUsage.prompt_tokens)).label("total_input_tokens"),
                    func.sum(col(ModelUsage.completion_tokens)).label("total_output_tokens"),
                    func.sum(col(ModelUsage.cost)).label("total_cost"),
                    func.avg(col(ModelUsage.time_cost)).label("avg_response_time"),
                )
                .where(col(ModelUsage.timestamp) >= start_time, col(ModelUsage.timestamp) <= now)
                .group_by(col(ModelUsage.session_id))
            )
            rows = session.exec(statement).all()

        agent_data: dict[str, AgentStatisticsItem] = {}
        for row in rows:
            session_id, request_count, input_tokens, output_tokens, cost, avg_time = row
            agent_id = session_agent_map.get(session_id or "", session_id or "unknown")
            if agent_id not in agent_data:
                agent_data[agent_id] = AgentStatisticsItem(agent_id=agent_id)
            entry = agent_data[agent_id]
            entry.request_count += int(request_count or 0)
            entry.total_input_tokens += int(input_tokens or 0)
            entry.total_output_tokens += int(output_tokens or 0)
            entry.total_cost += float(cost or 0.0)
            if avg_time is not None:
                entry.avg_response_time = float(avg_time)

        return ApiResponse(data=AgentStatisticsResponse(
            hours=hours,
            agents=sorted(agent_data.values(), key=lambda a: a.request_count, reverse=True),
        ))
    except AppError:
        raise
    except Exception as e:
        logger.error(f"获取智能体统计失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取智能体统计失败: {str(e)}") from e


@router.get("/export")
async def export_statistics(hours: int = 24, format: str = "csv"):
    """导出 LLM 调用统计数据。"""
    try:
        now = datetime.now()
        start_time = now - timedelta(hours=hours)

        with get_db_session(auto_commit=False) as session:
            statement = (
                select(ModelUsage)
                .where(col(ModelUsage.timestamp) >= start_time, col(ModelUsage.timestamp) <= now)
                .order_by(col(ModelUsage.timestamp))
            )
            records = session.exec(statement).all()

        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["时间", "智能体", "模型", "输入Token", "输出Token", "费用", "延迟(秒)"])

        for record in records:
            writer.writerow([
                record.timestamp.isoformat() if record.timestamp else "",
                record.session_id or "",
                record.model_assign_name or record.model_name,
                record.prompt_tokens,
                record.completion_tokens,
                f"{record.cost:.6f}",
                f"{record.time_cost:.3f}",
            ])

        output.seek(0)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"llm_stats_{timestamp_str}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except AppError:
        raise
    except Exception as e:
        logger.error(f"导出统计数据失败: {e}")
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"导出统计数据失败: {str(e)}") from e
