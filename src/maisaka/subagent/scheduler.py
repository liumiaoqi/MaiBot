"""子智能体调度器。

提供 spawn / cancel / get_status 方法。
- 并发限制：每智能体最多3个子智能体同时运行。
- 排队等待：超过5秒则放弃本次派生。
- 级联取消：取消父级智能体时所有子智能体同时被取消。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .interactive_gate import InteractiveGate
from .lifecycle import SubAgentLifecycleManager
from .models import (
    SubAgentHandle,
    SubAgentSpec,
    SubAgentState,
    SubAgentStatus,
    SubAgentType,
)
from .registry import SubAgentRegistry

logger = logging.getLogger(__name__)

MAX_CONCURRENT_PER_AGENT = 3
SPAWN_TIMEOUT_SECONDS = 5.0


class SpawnTimeoutError(Exception):
    """派生超时错误。"""


class ConcurrencyLimitExceededError(Exception):
    """并发限制超出错误。"""


class SubAgentScheduler:
    """子智能体调度器。

    组合 Registry / InteractiveGate / LifecycleManager，
    提供 spawn / cancel / get_status 统一接口。
    """

    def __init__(
        self,
        registry: Optional[SubAgentRegistry] = None,
        gate: Optional[InteractiveGate] = None,
        lifecycle_manager: Optional[SubAgentLifecycleManager] = None,
        max_concurrent: int = MAX_CONCURRENT_PER_AGENT,
        spawn_timeout: float = SPAWN_TIMEOUT_SECONDS,
    ) -> None:
        self._registry = registry or SubAgentRegistry()
        self._gate = gate or InteractiveGate()
        self._lifecycle = lifecycle_manager or SubAgentLifecycleManager()
        self._max_concurrent = max_concurrent
        self._spawn_timeout = spawn_timeout
        self._spawn_events: dict[str, asyncio.Event] = {}

    @property
    def registry(self) -> SubAgentRegistry:
        return self._registry

    @property
    def gate(self) -> InteractiveGate:
        return self._gate

    @property
    def lifecycle(self) -> SubAgentLifecycleManager:
        return self._lifecycle

    def _count_active(self, agent_id: str) -> int:
        """统计指定智能体当前活跃的子智能体数量。"""
        return len([
            s for s in self._lifecycle.list_by_agent(agent_id)
            if not s.is_terminal
        ])

    async def spawn(self, spec: SubAgentSpec) -> SubAgentHandle:
        """派生子智能体。

        Args:
            spec: 子智能体规格。

        Returns:
            SubAgentHandle: 子智能体句柄。

        Raises:
            SpawnTimeoutError: 排队等待超过 spawn_timeout 秒。
            ConcurrencyLimitExceededError: 超过并发限制且无排队空间。
            ValueError: 子智能体类型未注册。
        """
        if not self._registry.is_registered(spec.subagent_type):
            raise ValueError(
                f"子智能体类型 '{spec.subagent_type.value}' 未注册"
            )

        deadline = time.monotonic() + self._spawn_timeout

        while True:
            active_count = self._count_active(spec.agent_id)
            if active_count < self._max_concurrent:
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SpawnTimeoutError(
                    f"智能体 {spec.agent_id} 子智能体派生超时 "
                    f"（活跃数={active_count}，上限={self._max_concurrent}）"
                )

            wait_time = min(remaining, 0.5)
            await asyncio.sleep(wait_time)

        status = self._lifecycle.create(spec)
        self._lifecycle.start(status.subagent_id)

        logger.info(
            "子智能体派生成功: id=%s type=%s agent_id=%s",
            status.subagent_id,
            spec.subagent_type.value,
            spec.agent_id,
        )
        return SubAgentHandle.from_status(status)

    async def cancel(self, agent_id: str) -> list[str]:
        """级联取消指定智能体的所有活跃子智能体。

        Args:
            agent_id: 父级智能体ID。

        Returns:
            被取消的子智能体ID列表。
        """
        cancelled_ids: list[str] = []
        active = [
            s for s in self._lifecycle.list_by_agent(agent_id)
            if not s.is_terminal
        ]
        for status in active:
            self._lifecycle.cancel(status.subagent_id)
            cancelled_ids.append(status.subagent_id)
            logger.info(
                "级联取消子智能体: id=%s agent_id=%s",
                status.subagent_id,
                agent_id,
            )
        return cancelled_ids

    def get_status(self, subagent_id: str) -> Optional[SubAgentStatus]:
        """获取子智能体运行状态。"""
        return self._lifecycle.get_status(subagent_id)

    def list_active_by_agent(self, agent_id: str) -> list[SubAgentStatus]:
        """列出指定智能体的所有活跃子智能体。"""
        return [
            s for s in self._lifecycle.list_by_agent(agent_id)
            if not s.is_terminal
        ]

    def list_all_by_agent(self, agent_id: str) -> list[SubAgentStatus]:
        """列出指定智能体的所有子智能体（含终态）。"""
        return self._lifecycle.list_by_agent(agent_id)