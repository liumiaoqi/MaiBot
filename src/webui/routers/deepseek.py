"""DeepSeek 优化面板 API 路由"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.common.logger import get_logger
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.deepseek.batch_scheduler import BatchScheduler, BatchTaskStatus
from src.maisaka.deepseek.budget import TokenBudgetManager
from src.maisaka.deepseek.cost_tracker import CostTracker
from src.maisaka.deepseek.prefix_cache import PrefixCacheManager
from src.webui.dependencies import require_auth

logger = get_logger("webui.deepseek")

router = APIRouter(
    prefix="/deepseek", tags=["DeepSeek"], dependencies=[Depends(require_auth)]
)


def _get_registry() -> AgentConfigRegistry:
    return AgentConfigRegistry()


def _get_budget_manager() -> TokenBudgetManager:
    return TokenBudgetManager()


def _get_prefix_cache_manager() -> PrefixCacheManager:
    return PrefixCacheManager()


def _get_batch_scheduler() -> BatchScheduler:
    return BatchScheduler()


def _get_cost_tracker() -> CostTracker:
    return CostTracker()


class TokenBudgetSegment(BaseModel):
    segment: str = Field(description="段名")
    ratio: float = Field(description="占比")
    token_limit: int = Field(description="Token上限")


class TokenBudgetResponse(BaseModel):
    agent_id: str
    model_context_window: int = 128000
    segments: List[TokenBudgetSegment] = Field(default_factory=list)


class CacheStatsResponse(BaseModel):
    agent_id: str
    hit_tokens: int = 0
    miss_tokens: int = 0
    hit_rate: float = 0.0
    prefix_cache_enabled: bool = True


class BatchTaskSummary(BaseModel):
    task_id: str
    agent_id: str
    task_type: str
    status: str
    priority: str
    degraded_to_realtime: bool = False
    created_at: float = 0.0


class BatchOverviewResponse(BaseModel):
    api_available: bool = True
    pending_count: int = 0
    degraded_count: int = 0
    recent_tasks: List[BatchTaskSummary] = Field(default_factory=list)


class AgentCostResponse(BaseModel):
    agent_id: str
    total_cost: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_hit_tokens: int = 0


class MonthlyReportResponse(BaseModel):
    by_agent: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    by_task_type: Dict[str, Dict[str, float]] = Field(default_factory=dict)


class DeepSeekOverviewResponse(BaseModel):
    total_agents: int = 0
    agents_with_budget: int = 0
    agents_with_cache: int = 0
    batch_api_available: bool = True
    total_cost_30d: float = 0.0
    avg_cache_hit_rate: float = 0.0


@router.get("/overview", response_model=DeepSeekOverviewResponse)
async def get_deepseek_overview():
    """获取 DeepSeek 优化全局概览。"""
    registry = _get_registry()
    agents = registry.list_agents()
    budget_mgr = _get_budget_manager()
    cache_mgr = _get_prefix_cache_manager()
    batch_sched = _get_batch_scheduler()
    cost_tracker = _get_cost_tracker()

    total_cost = 0.0
    total_hit_rate = 0.0
    agents_with_cache = 0

    for agent_config in agents:
        aid = agent_config.agent_id
        agent_cost = cost_tracker.get_agent_cost(aid, period_days=30)
        total_cost += agent_cost.get("total_cost", 0.0)

        stats = cache_mgr.get_cache_stats(aid)
        hit_rate = stats.get("hit_rate", 0.0)
        if isinstance(hit_rate, (int, float)) and hit_rate > 0:
            total_hit_rate += hit_rate
            agents_with_cache += 1

    avg_hit_rate = total_hit_rate / max(agents_with_cache, 1)

    return DeepSeekOverviewResponse(
        total_agents=len(agents),
        agents_with_budget=len(agents),
        agents_with_cache=agents_with_cache,
        batch_api_available=batch_sched._batch_api_available,
        total_cost_30d=round(total_cost, 4),
        avg_cache_hit_rate=round(avg_hit_rate, 4),
    )


@router.get("/budget/{agent_id}", response_model=TokenBudgetResponse)
async def get_agent_budget(agent_id: str):
    """获取指定智能体的 Token 预算分配。"""
    budget_mgr = _get_budget_manager()
    allocation = budget_mgr.get_budget(agent_id)

    segment_names = [
        "identity", "anti_mechanization", "internal_relationships",
        "emotion_state", "relationship", "profile", "mid_term",
        "heuristic", "cross_chat", "history", "reserved",
    ]

    segments = []
    for name in segment_names:
        ratio = getattr(allocation, name, 0.0)
        token_limit = allocation.get_token_limit(name, 128000)
        segments.append(TokenBudgetSegment(
            segment=name, ratio=round(ratio, 4), token_limit=token_limit,
        ))

    return TokenBudgetResponse(agent_id=agent_id, segments=segments)


@router.get("/cache/{agent_id}", response_model=CacheStatsResponse)
async def get_agent_cache_stats(agent_id: str):
    """获取指定智能体的前缀缓存统计。"""
    cache_mgr = _get_prefix_cache_manager()
    stats = cache_mgr.get_cache_stats(agent_id)
    enabled = cache_mgr.is_prefix_cache_enabled(agent_id)

    return CacheStatsResponse(
        agent_id=agent_id,
        hit_tokens=int(stats.get("hit_tokens", 0)),
        miss_tokens=int(stats.get("miss_tokens", 0)),
        hit_rate=float(stats.get("hit_rate", 0.0)),
        prefix_cache_enabled=enabled,
    )


@router.get("/batch/overview", response_model=BatchOverviewResponse)
async def get_batch_overview():
    """获取批处理任务概览。"""
    batch_sched = _get_batch_scheduler()

    recent_tasks = []
    for task in batch_sched._pending_tasks[-20:]:
        recent_tasks.append(BatchTaskSummary(
            task_id=task.task_id,
            agent_id=task.agent_id,
            task_type=task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type),
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            priority=task.priority.value if hasattr(task.priority, "value") else str(task.priority),
            degraded_to_realtime=task.degraded_to_realtime,
            created_at=task.created_at,
        ))

    for task in batch_sched._completed_tasks[-20:]:
        recent_tasks.append(BatchTaskSummary(
            task_id=task.task_id,
            agent_id=task.agent_id,
            task_type=task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type),
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            priority=task.priority.value if hasattr(task.priority, "value") else str(task.priority),
            degraded_to_realtime=task.degraded_to_realtime,
            created_at=task.created_at,
        ))

    degraded_count = sum(
        1 for t in batch_sched._completed_tasks if t.degraded_to_realtime
    )

    return BatchOverviewResponse(
        api_available=batch_sched._batch_api_available,
        pending_count=batch_sched.get_pending_count(),
        degraded_count=degraded_count,
        recent_tasks=recent_tasks,
    )


@router.get("/cost/{agent_id}", response_model=AgentCostResponse)
async def get_agent_cost(agent_id: str, period_days: int = 30):
    """获取指定智能体的成本统计。"""
    cost_tracker = _get_cost_tracker()
    data = cost_tracker.get_agent_cost(agent_id, period_days=period_days)

    return AgentCostResponse(
        agent_id=agent_id,
        total_cost=round(data.get("total_cost", 0.0), 6),
        total_input_tokens=int(data.get("total_input_tokens", 0)),
        total_output_tokens=int(data.get("total_output_tokens", 0)),
        total_cache_hit_tokens=int(data.get("total_cache_hit_tokens", 0)),
    )


@router.get("/cost/report", response_model=MonthlyReportResponse)
async def get_monthly_cost_report():
    """获取月度成本报告。"""
    cost_tracker = _get_cost_tracker()
    report = cost_tracker.get_monthly_report()

    return MonthlyReportResponse(
        by_agent=report.get("by_agent", {}),
        by_task_type=report.get("by_task_type", {}),
    )