"""巩固调度器 — 调度 Distill 任务。

Dream 由 M1 的 DreamTrigger 定时调度管理，此处仅管理 Distill。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .distill import DistillAgent
from .knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationTask:
    """巩固任务记录。"""

    agent_id: str
    task_type: str = "distill"
    status: str = "pending"
    started_at: float = 0.0
    completed_at: float = 0.0
    assets_extracted: int = 0
    error_message: str = ""


class ConsolidationScheduler:
    """巩固调度器，管理 Distill 任务的调度和执行。

    调度策略：
      - 按智能体逐一调度，避免并发冲突
      - 最小间隔 1 小时，避免频繁执行
      - 支持手动触发
    """

    MIN_INTERVAL_SECONDS = 3600

    def __init__(
        self,
        knowledge_store: Optional[KnowledgeStore] = None,
        memory_service: Any = None,
        relationship_manager: Any = None,
    ) -> None:
        self._knowledge_store = knowledge_store or KnowledgeStore()
        self._memory_service = memory_service
        self._relationship_manager = relationship_manager
        self._last_run: dict[str, float] = {}
        self._history: list[ConsolidationTask] = []

    def should_run(self, agent_id: str) -> bool:
        """判断是否应该为指定智能体执行 Distill。"""
        last = self._last_run.get(agent_id, 0)
        return (time.time() - last) >= self.MIN_INTERVAL_SECONDS

    async def run_distill(
        self,
        agent_id: str,
        window_days: int = 30,
        force: bool = False,
    ) -> ConsolidationTask:
        """为指定智能体执行 Distill 巩固。

        Args:
            agent_id: 目标智能体ID。
            window_days: 扫描窗口天数。
            force: 是否强制执行（忽略最小间隔）。

        Returns:
            ConsolidationTask: 任务执行记录。
        """
        task = ConsolidationTask(agent_id=agent_id)

        if not force and not self.should_run(agent_id):
            task.status = "skipped"
            task.error_message = "距离上次执行不足1小时"
            logger.debug("Distill 跳过: agent=%s (间隔不足)", agent_id)
            return task

        task.status = "running"
        task.started_at = time.time()

        try:
            distill = DistillAgent(
                knowledge_store=self._knowledge_store,
                memory_service=self._memory_service,
                relationship_manager=self._relationship_manager,
            )

            result = await distill.execute(
                agent_id=agent_id,
                window_days=window_days,
            )

            task.assets_extracted = len([a for a in result.assets if a.is_valid()])
            task.status = "success" if result.success else "failed"
            task.error_message = result.error_message

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            logger.exception("Distill 调度执行异常: agent=%s", agent_id)

        task.completed_at = time.time()
        self._last_run[agent_id] = time.time()
        self._history.append(task)

        logger.info(
            "Distill 调度完成: agent=%s status=%s assets=%d",
            agent_id,
            task.status,
            task.assets_extracted,
        )
        return task

    async def run_all_agents(
        self,
        window_days: int = 30,
        force: bool = False,
    ) -> list[ConsolidationTask]:
        """为所有智能体执行 Distill 巩固。"""
        tasks: list[ConsolidationTask] = []

        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry.get_instance()
            agents = registry.list_agents()

            for agent_config in agents:
                task = await self.run_distill(
                    agent_id=agent_config.agent_id,
                    window_days=window_days,
                    force=force,
                )
                tasks.append(task)

        except Exception as e:
            logger.error("Distill 全量调度失败: %s", e)

        return tasks

    def get_history(self, agent_id: Optional[str] = None) -> list[ConsolidationTask]:
        """获取调度历史。"""
        if agent_id is None:
            return list(self._history)
        return [t for t in self._history if t.agent_id == agent_id]