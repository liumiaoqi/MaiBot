"""ZG-N5 压缩升级——idle-task 排他协调器。

对标 dsh index.ts:368 compactNow + agent.runMaintenance。
手动压缩仅空闲时运行，运行中让出不阻塞消息。
自动压缩跳过 idle-task 协调器，直接执行。
"""

import asyncio
from typing import Awaitable, Callable

from .types import AbortSignal, CompactionResult, IdleStateUnqueryableError


class IdleTaskCoordinator:
    """idle-task 排他协调器——空闲判定 + 预留接纳 + 让出。"""

    def __init__(self, vitality_manager: object) -> None:
        self._vitality_manager = vitality_manager
        self._admission_reserved: set[str] = set()
        self._admission_lock = asyncio.Lock()

    def is_idle(self, agent_id: str) -> bool:
        """查询 agent 空闲（委托 vitality_manager.is_agent_idle）。"""
        try:
            return self._vitality_manager.is_agent_idle(agent_id)
        except Exception as exc:
            raise IdleStateUnqueryableError(f"空闲状态查询失败: {exc}") from exc

    async def request_manual_compact(
        self,
        agent_id: str,
        compact_fn: Callable[[AbortSignal], Awaitable[CompactionResult]],
        signal: AbortSignal,
    ) -> CompactionResult:
        """协调手动压缩——空闲判定 + 预留接纳 + 让出。

        Args:
            agent_id: 智能体标识
            compact_fn: 压缩执行函数（接受 AbortSignal）
            signal: 取消信号

        Returns:
            压缩结果

        Raises:
            ManualCompactionError: 非空闲时拒绝
            IdleStateUnqueryableError: 空闲状态查询失败
        """
        from .types import ManualCompactionError

        if not self.is_idle(agent_id):
            raise ManualCompactionError("busy", "agent 非空闲，手动压缩拒绝")

        async with self._admission_lock:
            self._admission_reserved.add(agent_id)
        try:
            result = await compact_fn(signal)
            return result
        finally:
            async with self._admission_lock:
                self._admission_reserved.discard(agent_id)

    def has_admission_reserved(self, agent_id: str) -> bool:
        """检查 agent 是否持有空闲接纳预留。"""
        return agent_id in self._admission_reserved

    async def release_admission(self, agent_id: str) -> None:
        """释放空闲接纳预留。"""
        async with self._admission_lock:
            self._admission_reserved.discard(agent_id)