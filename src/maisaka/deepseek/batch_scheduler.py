"""DeepSeek 批处理任务调度器。

将非实时性 LLM 任务提交到 DeepSeek 批处理 API（50%成本折扣）。
批处理不可用时自动降级为实时 API。
禁止将实时性要求高的任务提交到批处理 API。
"""

from __future__ import annotations

import time
from enum import Enum


from pydantic import BaseModel, Field

from src.common.logger import get_logger

logger = get_logger("maisaka_deepseek_batch")


class BatchTaskPriority(str, Enum):
    """批处理任务优先级。"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class BatchTaskType(str, Enum):
    """批处理任务类型。"""

    DREAM_CONSOLIDATION = "dream_consolidation"
    COMPACTION_SUMMARY = "compaction_summary"
    PROFILE_UPDATE = "profile_update"
    EMOTION_ANALYSIS = "emotion_analysis"


class BatchTaskStatus(str, Enum):
    """批处理任务状态。"""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"


class BatchTask(BaseModel):
    """批处理任务。"""

    task_id: str = Field(default="", description="任务ID")
    agent_id: str = Field(default="", description="智能体ID")
    task_type: BatchTaskType = Field(default=BatchTaskType.DREAM_CONSOLIDATION, description="任务类型")
    priority: BatchTaskPriority = Field(default=BatchTaskPriority.NORMAL, description="优先级")
    status: BatchTaskStatus = Field(default=BatchTaskStatus.PENDING, description="状态")
    payload: dict = Field(default_factory=dict, description="任务载荷")
    created_at: float = Field(default=0.0, description="创建时间戳")
    submitted_at: float = Field(default=0.0, description="提交时间戳")
    completed_at: float = Field(default=0.0, description="完成时间戳")
    error_message: str = Field(default="", description="错误信息")
    degraded_to_realtime: bool = Field(default=False, description="是否降级为实时API")


_REALTIME_ONLY_TASKS: set[BatchTaskType] = set()


class BatchScheduler:
    """DeepSeek 批处理任务调度器。"""

    MAX_PENDING_TASKS = 100

    def __init__(self) -> None:
        self._pending_tasks: list[BatchTask] = []
        self._completed_tasks: list[BatchTask] = []
        self._batch_api_available: bool = True

    def submit_task(self, task: BatchTask) -> BatchTaskStatus:
        """提交批处理任务。"""
        if task.task_type in _REALTIME_ONLY_TASKS:
            logger.info(f"任务 {task.task_id} 为实时任务，跳过批处理")
            task.status = BatchTaskStatus.DEGRADED
            task.degraded_to_realtime = True
            return BatchTaskStatus.DEGRADED

        if not self._is_batch_enabled(task.agent_id):
            task.status = BatchTaskStatus.DEGRADED
            task.degraded_to_realtime = True
            logger.info(f"智能体 {task.agent_id} 批处理未启用，降级为实时API")
            return BatchTaskStatus.DEGRADED

        if not self._batch_api_available:
            task.status = BatchTaskStatus.DEGRADED
            task.degraded_to_realtime = True
            logger.info("批处理API不可用，降级为实时API")
            return BatchTaskStatus.DEGRADED

        if len(self._pending_tasks) >= self.MAX_PENDING_TASKS:
            task.status = BatchTaskStatus.DEGRADED
            task.degraded_to_realtime = True
            logger.warning("批处理队列已满，降级为实时API")
            return BatchTaskStatus.DEGRADED

        task.created_at = time.time()
        task.status = BatchTaskStatus.PENDING
        self._pending_tasks.append(task)
        return BatchTaskStatus.PENDING

    def mark_batch_api_unavailable(self) -> None:
        """标记批处理 API 不可用。"""
        self._batch_api_available = False
        logger.warning("DeepSeek 批处理 API 标记为不可用，后续任务将降级为实时API")

    def mark_batch_api_available(self) -> None:
        """标记批处理 API 可用。"""
        self._batch_api_available = True
        logger.info("DeepSeek 批处理 API 恢复可用")

    def get_pending_count(self) -> int:
        """获取待处理任务数。"""
        return len(self._pending_tasks)

    def get_degraded_count(self, agent_id: str) -> int:
        """获取指定智能体的降级任务数。"""
        return sum(
            1
            for t in self._completed_tasks
            if t.agent_id == agent_id and t.degraded_to_realtime
        )

    @staticmethod
    def _is_batch_enabled(agent_id: str) -> bool:
        """检查智能体是否启用批处理。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry.get_instance()
            if registry.has_agent(agent_id):
                return registry.get_agent(agent_id).deepseek.batch_api_enabled
        except Exception:
            pass
        return True