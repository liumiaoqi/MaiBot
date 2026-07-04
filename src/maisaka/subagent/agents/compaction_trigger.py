"""Compaction 子智能体触发器与上下文监控。

- ContextMonitor: 每轮对话后检查 token 使用量
- CompactionTrigger: 达到阈值时触发 Compaction 子智能体派生
- 降级路径: Compaction 不可用时回退到 mid_term.py 同步压缩
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .compaction import CompactionAgent, CompactionLevel, CompactionResult
from ..config.compaction import CompactionConfig
from ..models import SubAgentLifecycle, SubAgentSpec, SubAgentType, TriggerType
from ..scheduler import SubAgentScheduler

logger = logging.getLogger(__name__)


@dataclass
class ContextUsageSnapshot:
    """上下文使用量快照。"""

    total_tokens: int = 0
    max_tokens: int = 128000
    usage_ratio: float = 0.0
    message_count: int = 0
    session_id: str = ""
    agent_id: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def is_above_level1(self) -> bool:
        return self.usage_ratio >= 0.4

    @property
    def is_above_level2(self) -> bool:
        return self.usage_ratio >= 0.6

    @property
    def is_above_level3(self) -> bool:
        return self.usage_ratio >= 0.8


class ContextMonitor:
    """上下文使用量监控器。

    在每轮对话后检查 token 使用量，
    当达到 Compaction 阈值时触发 Compaction 子智能体派生。
    """

    def __init__(
        self,
        compaction_trigger: Optional[CompactionTrigger] = None,
    ) -> None:
        self._trigger = compaction_trigger
        self._last_snapshot: Optional[ContextUsageSnapshot] = None
        self._last_compaction_level = CompactionLevel.NONE

    @property
    def last_snapshot(self) -> Optional[ContextUsageSnapshot]:
        return self._last_snapshot

    async def check_and_trigger(
        self,
        total_tokens: int,
        max_tokens: int,
        message_count: int,
        session_id: str,
        agent_id: str,
    ) -> Optional[CompactionResult]:
        """检查上下文使用量并触发压缩。

        Args:
            total_tokens: 当前使用的 Token 数。
            max_tokens: 模型最大 Token 数。
            message_count: 当前消息数。
            session_id: 会话ID。
            agent_id: 智能体ID。

        Returns:
            CompactionResult 或 None（未触发）。
        """
        usage_ratio = total_tokens / max_tokens if max_tokens > 0 else 0.0

        snapshot = ContextUsageSnapshot(
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            usage_ratio=usage_ratio,
            message_count=message_count,
            session_id=session_id,
            agent_id=agent_id,
        )
        self._last_snapshot = snapshot

        if self._trigger is None:
            return None

        new_level = self._trigger.config_agent.determine_level(usage_ratio)
        if new_level <= self._last_compaction_level:
            return None

        self._last_compaction_level = new_level
        logger.info(
            "上下文使用率 %.1f%% 触发 L%d Compaction: session=%s agent=%s",
            usage_ratio * 100,
            new_level,
            session_id,
            agent_id,
        )

        return await self._trigger.trigger_compaction(
            agent_id=agent_id,
            session_id=session_id,
            token_usage_ratio=usage_ratio,
        )


class CompactionTrigger:
    """Compaction 子智能体触发器。

    管理异步 Compaction 派生和 mid_term.py 降级路径。
    """

    def __init__(
        self,
        scheduler: SubAgentScheduler,
        config: CompactionConfig,
        memory_service: Any = None,
        message_repository: Any = None,
        mid_term_builder: Any = None,
    ) -> None:
        self._scheduler = scheduler
        self._config = config
        self._memory_service = memory_service
        self._message_repository = message_repository
        self._mid_term_builder = mid_term_builder
        self._fallback_count: int = 0

    @property
    def config_agent(self) -> CompactionAgent:
        return CompactionAgent(
            config=self._config,
            memory_service=self._memory_service,
            message_repository=self._message_repository,
        )

    @property
    def fallback_count(self) -> int:
        return self._fallback_count

    async def trigger_compaction(
        self,
        agent_id: str,
        session_id: str,
        token_usage_ratio: float = 0.0,
    ) -> Optional[CompactionResult]:
        """触发 Compaction 压缩。

        优先异步派生子智能体；失败时降级到 mid_term.py 同步压缩。

        Args:
            agent_id: 智能体ID。
            session_id: 会话ID。
            token_usage_ratio: Token 使用占比。

        Returns:
            CompactionResult 或 None。
        """
        if not self._config.enabled:
            return await self._fallback_to_sync(agent_id, session_id, "Compaction 已禁用")

        spec = SubAgentSpec(
            subagent_type=SubAgentType.COMPACTION,
            agent_id=agent_id,
            session_id=session_id,
            interactive=False,
            lifecycle=SubAgentLifecycle.EPHEMERAL,
            trigger_type=TriggerType.AUTO,
            trigger_reason=f"上下文使用率 {token_usage_ratio:.0%} 触发压缩",
            config=self._config.model_dump(),
        )

        try:
            handle = await self._scheduler.spawn(spec)
            logger.info(
                "Compaction 子智能体已派生: id=%s agent=%s",
                handle.subagent_id,
                agent_id,
            )
            return CompactionResult(
                agent_id=agent_id,
                session_id=session_id,
                level=self.config_agent.determine_level(token_usage_ratio),
            )
        except Exception as e:
            logger.warning("Compaction 子智能体派生失败: %s", e)
            if self._config.fallback_to_sync:
                return await self._fallback_to_sync(agent_id, session_id, str(e))
            return CompactionResult(
                agent_id=agent_id,
                session_id=session_id,
                error_message=str(e),
            )

    async def _fallback_to_sync(
        self,
        agent_id: str,
        session_id: str,
        reason: str,
    ) -> CompactionResult:
        """降级到 mid_term.py 同步压缩。"""
        self._fallback_count += 1
        logger.info(
            "Compaction 降级到同步压缩: agent=%s session=%s reason=%s (累计降级%d次)",
            agent_id,
            session_id,
            reason,
            self._fallback_count,
        )

        if self._mid_term_builder is not None:
            try:
                from src.maisaka.memory.mid_term import build_mid_term_memory_message

                result = await build_mid_term_memory_message(session_id=session_id)
                return CompactionResult(
                    agent_id=agent_id,
                    session_id=session_id,
                    fallback_used=True,
                )
            except Exception as e:
                logger.warning("同步压缩也失败: %s", e)
                return CompactionResult(
                    agent_id=agent_id,
                    session_id=session_id,
                    fallback_used=True,
                    error_message=f"同步压缩失败: {e}",
                )

        return CompactionResult(
            agent_id=agent_id,
            session_id=session_id,
            fallback_used=True,
            error_message=f"降级到同步压缩: {reason}",
        )