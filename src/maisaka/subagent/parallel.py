"""子智能体自由线程协同模块。

确保子智能体在自由线程模式下可并行运行：
- 不同智能体的子智能体可在不同线程上并行执行
- 使用线程安全的数据结构
- 不引入 GIL 依赖的全局可变状态
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from .models import SubAgentSpec, SubAgentState, SubAgentStatus, SubAgentType

logger = logging.getLogger(__name__)


class ThreadSafeStatusStore:
    """线程安全的子智能体状态存储。

    使用 threading.Lock 保护内部字典，
    确保自由线程模式下的数据安全。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._instances: dict[str, SubAgentStatus] = {}

    def put(self, status: SubAgentStatus) -> None:
        with self._lock:
            self._instances[status.subagent_id] = status

    def get(self, subagent_id: str) -> Optional[SubAgentStatus]:
        with self._lock:
            return self._instances.get(subagent_id)

    def remove(self, subagent_id: str) -> Optional[SubAgentStatus]:
        with self._lock:
            return self._instances.pop(subagent_id, None)

    def list_by_agent(self, agent_id: str) -> list[SubAgentStatus]:
        with self._lock:
            return [s for s in self._instances.values() if s.spec.agent_id == agent_id]

    def list_active(self) -> list[SubAgentStatus]:
        with self._lock:
            return [s for s in self._instances.values() if not s.is_terminal]

    def count_active_by_agent(self, agent_id: str) -> int:
        with self._lock:
            return sum(
                1 for s in self._instances.values()
                if s.spec.agent_id == agent_id and not s.is_terminal
            )

    def update_state(self, subagent_id: str, new_state: SubAgentState) -> bool:
        with self._lock:
            status = self._instances.get(subagent_id)
            if status is None:
                return False
            status.state = new_state
            return True


class ParallelSubAgentExecutor:
    """并行子智能体执行器。

    在自由线程模式下，不同智能体的子智能体
    可在独立的 asyncio.Task 中并行执行。
    """

    def __init__(self, max_parallel: int = 10) -> None:
        self._max_parallel = max_parallel
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._status_store = ThreadSafeStatusStore()

    @property
    def status_store(self) -> ThreadSafeStatusStore:
        return self._status_store

    async def execute_parallel(
        self,
        specs: list[SubAgentSpec],
        executor_fn: Any,
    ) -> list[Any]:
        """并行执行多个子智能体。

        Args:
            specs: 子智能体规格列表。
            executor_fn: 异步执行函数 (spec) -> result。

        Returns:
            执行结果列表。
        """
        semaphore = asyncio.Semaphore(self._max_parallel)

        async def _run_with_semaphore(spec: SubAgentSpec) -> Any:
            async with semaphore:
                return await executor_fn(spec)

        tasks = [
            asyncio.create_task(_run_with_semaphore(spec), name=f"subagent_{spec.agent_id}_{spec.subagent_type.value}")
            for spec in specs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results: list[Any] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "子智能体并行执行异常: agent=%s type=%s error=%s",
                    specs[i].agent_id,
                    specs[i].subagent_type.value,
                    result,
                )
                final_results.append(None)
            else:
                final_results.append(result)

        return final_results

    @property
    def active_task_count(self) -> int:
        return sum(1 for t in self._active_tasks.values() if not t.done())