"""Dream 子智能体定时触发器。

管理 Dream 的定时派生逻辑：
- 自动触发：默认每7天（可通过 DreamConfig.interval_days 按智能体配置）
- 前置检查：项目年龄不足7天且无历史对话时跳过
- 最小间隔：两次派生之间至少 min_spawn_gap_seconds 秒
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from .dream import DreamAgent
from ..config.dream import DreamConfig
from ..lifecycle import SubAgentLifecycleManager
from ..models import SubAgentLifecycle, SubAgentSpec, SubAgentType, TriggerType
from ..scheduler import SubAgentScheduler

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 3600  # 每小时检查一次


class DreamTrigger:
    """Dream 子智能体定时触发器。

    在后台循环中定期检查是否需要派生 Dream 子智能体。
    """

    def __init__(
        self,
        scheduler: SubAgentScheduler,
        config: DreamConfig,
        memory_service: Any = None,
        message_repository: Any = None,
    ) -> None:
        self._scheduler = scheduler
        self._config = config
        self._memory_service = memory_service
        self._message_repository = message_repository
        self._last_spawn_time: dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动定时触发循环。"""
        if self._running:
            return
        if not self._config.enabled:
            logger.info("Dream 子智能体已禁用，不启动定时触发")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="dream_trigger")
        logger.info("Dream 定时触发器已启动，周期=%d天", self._config.interval_days)

    async def stop(self) -> None:
        """停止定时触发循环。"""
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Dream 定时触发器已停止")

    async def trigger_now(self, agent_id: str, session_id: str = "") -> Optional[str]:
        """手动触发 Dream 派生。

        Args:
            agent_id: 智能体ID。
            session_id: 会话ID。

        Returns:
            派生的子智能体ID，失败返回 None。
        """
        return await self._try_spawn(agent_id, session_id, trigger_type=TriggerType.MANUAL)

    async def _loop(self) -> None:
        """定时检查循环。"""
        while self._running:
            try:
                await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
                if not self._running:
                    break
                await self._check_and_spawn()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Dream 定时触发循环异常")
                await asyncio.sleep(60)

    async def _check_and_spawn(self) -> None:
        """检查所有智能体是否需要 Dream 派生。"""
        now = time.time()
        interval_seconds = self._config.interval_days * 86400

        for agent_id, last_time in list(self._last_spawn_time.items()):
            if now - last_time >= interval_seconds:
                await self._try_spawn(agent_id, trigger_type=TriggerType.AUTO)

    async def _try_spawn(
        self,
        agent_id: str,
        session_id: str = "",
        trigger_type: TriggerType = TriggerType.AUTO,
    ) -> Optional[str]:
        """尝试派生 Dream 子智能体。

        Args:
            agent_id: 智能体ID。
            session_id: 会话ID。
            trigger_type: 触发类型。

        Returns:
            派生的子智能体ID，失败返回 None。
        """
        now = time.time()
        last_time = self._last_spawn_time.get(agent_id, 0)

        if now - last_time < self._config.min_spawn_gap_seconds:
            logger.debug(
                "Dream 派生间隔不足: agent_id=%s 距上次=%.0fs",
                agent_id,
                now - last_time,
            )
            return None

        spec = SubAgentSpec(
            subagent_type=SubAgentType.DREAM,
            agent_id=agent_id,
            session_id=session_id,
            interactive=False,
            lifecycle=SubAgentLifecycle.PERSISTENT,
            trigger_type=trigger_type,
            trigger_reason=f"{'手动' if trigger_type == TriggerType.MANUAL else '定时'}触发 Dream 记忆巩固",
            config=self._config.model_dump(),
        )

        try:
            handle = await self._scheduler.spawn(spec)
            self._last_spawn_time[agent_id] = now
            logger.info(
                "Dream 子智能体已派生: id=%s agent_id=%s trigger=%s",
                handle.subagent_id,
                agent_id,
                trigger_type.value,
            )
            return handle.subagent_id
        except Exception as e:
            logger.warning("Dream 子智能体派生失败: agent_id=%s error=%s", agent_id, e)
            return None

    def record_spawn(self, agent_id: str) -> None:
        """记录派生时间（供外部调用）。"""
        self._last_spawn_time[agent_id] = time.time()