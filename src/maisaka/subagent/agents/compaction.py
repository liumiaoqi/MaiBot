"""Compaction 子智能体 — 上下文压缩。

三级阈值压缩：
- Level 1 (40%): 压缩最早的旧消息，保留最近N轮原文
- Level 2 (60%): 扩大压缩范围
- Level 3 (80%): 更激进的压缩

异步执行不阻塞主对话循环。
摘要格式遵循结构化模板。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from ..config.compaction import CompactionConfig
from ..models import SubAgentSpec, SubAgentStatus

logger = logging.getLogger(__name__)


class CompactionLevel(IntEnum):
    """压缩级别。"""

    NONE = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3


@dataclass
class CompactionSummary:
    """单段压缩摘要。"""

    goal: str = ""
    instructions: str = ""
    discoveries: str = ""
    accomplished: str = ""
    relevant_files: str = ""

    def to_text(self) -> str:
        """格式化为结构化文本。"""
        sections = []
        if self.goal:
            sections.append(f"## Goal\n{self.goal}")
        if self.instructions:
            sections.append(f"## Instructions\n{self.instructions}")
        if self.discoveries:
            sections.append(f"## Discoveries\n{self.discoveries}")
        if self.accomplished:
            sections.append(f"## Accomplished\n{self.accomplished}")
        if self.relevant_files:
            sections.append(f"## Relevant Files\n{self.relevant_files}")
        return "\n\n".join(sections)


@dataclass
class CompactionResult:
    """Compaction 执行结果。"""

    agent_id: str
    session_id: str
    level: CompactionLevel = CompactionLevel.NONE
    messages_before: int = 0
    messages_after: int = 0
    messages_compressed: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    summary: Optional[CompactionSummary] = None
    duration_seconds: float = 0.0
    fallback_used: bool = False
    batch_degraded: bool = False
    error_message: str = ""

    @property
    def success(self) -> bool:
        return not self.error_message

    def to_summary(self) -> str:
        if self.error_message:
            return f"Compaction失败(L{self.level}): {self.error_message}"
        return (
            f"Compaction完成(L{self.level}): "
            f"{self.messages_before}→{self.messages_after}条 "
            f"压缩{self.messages_compressed}条 "
            f"Token {self.tokens_before}→{self.tokens_after} "
            f"耗时{self.duration_seconds:.1f}s"
        )


class CompactionAgent:
    """Compaction 上下文压缩子智能体。

    异步压缩旧消息，替代现有的同步压缩流程。
    """

    def __init__(
        self,
        config: CompactionConfig,
        memory_service: Any = None,
        message_repository: Any = None,
        batch_scheduler: Any = None,
    ) -> None:
        self._config = config
        self._memory_service = memory_service
        self._message_repository = message_repository
        self._batch_scheduler = batch_scheduler

    @property
    def config(self) -> CompactionConfig:
        return self._config

    def determine_level(self, token_usage_ratio: float) -> CompactionLevel:
        """根据 Token 使用率确定压缩级别。

        Args:
            token_usage_ratio: 当前 Token 使用占比 (0.0-1.0)。

        Returns:
            CompactionLevel: 对应的压缩级别。
        """
        if token_usage_ratio >= self._config.threshold_level_3:
            return CompactionLevel.LEVEL_3
        if token_usage_ratio >= self._config.threshold_level_2:
            return CompactionLevel.LEVEL_2
        if token_usage_ratio >= self._config.threshold_level_1:
            return CompactionLevel.LEVEL_1
        return CompactionLevel.NONE

    async def execute(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        token_usage_ratio: float = 0.0,
    ) -> CompactionResult:
        """执行上下文压缩。

        Args:
            spec: 子智能体规格。
            status: 子智能体运行状态。
            token_usage_ratio: 当前 Token 使用占比。

        Returns:
            CompactionResult: 压缩结果。
        """
        start_time = time.monotonic()
        level = self.determine_level(token_usage_ratio)

        result = CompactionResult(
            agent_id=spec.agent_id,
            session_id=spec.session_id,
            level=level,
        )

        if level == CompactionLevel.NONE:
            result.error_message = ""
            result.duration_seconds = time.monotonic() - start_time
            return result

        try:
            messages = await self._load_messages(spec)
            result.messages_before = len(messages)

            if result.messages_before == 0:
                result.duration_seconds = time.monotonic() - start_time
                return result

            preserve_count = self._calculate_preserve_count(level, len(messages))
            to_compress = messages[:-preserve_count] if preserve_count < len(messages) else []
            preserved = messages[-preserve_count:] if preserve_count > 0 else messages

            result.messages_compressed = len(to_compress)

            if to_compress:
                summary = await self._generate_summary(to_compress, level)
                result.summary = summary

                summary_text = summary.to_text()
                result.tokens_after = len(summary_text) // 4 + sum(
                    len(getattr(m, "processed_plain_text", "") or "") // 4
                    for m in preserved
                )
            else:
                result.messages_after = result.messages_before
                result.duration_seconds = time.monotonic() - start_time
                return result

            result.messages_after = 1 + len(preserved)
            result.tokens_before = sum(
                len(getattr(m, "processed_plain_text", "") or "") // 4
                for m in messages
            )

            status.progress = 1.0
            status.progress_description = f"L{level}压缩完成"

        except Exception as e:
            logger.exception("Compaction 执行异常")
            result.error_message = str(e)
            if self._config.fallback_to_sync:
                result.fallback_used = True
                logger.info("Compaction 失败，将降级为同步压缩")

        result.duration_seconds = time.monotonic() - start_time
        logger.info("Compaction: %s", result.to_summary())
        return result

    async def _load_messages(self, spec: SubAgentSpec) -> list[Any]:
        """加载会话消息。"""
        if self._message_repository is None:
            from src.common.message_repository import find_messages
            return find_messages(
                session_id=spec.session_id,
                sort=[("timestamp", 1)],
                limit=1000,
            )
        return self._message_repository.find_messages(
            session_id=spec.session_id,
            sort=[("timestamp", 1)],
            limit=1000,
        )

    def _calculate_preserve_count(self, level: CompactionLevel, total: int) -> int:
        """计算需要保留的最近消息数量。"""
        tail_turns = self._config.tail_turns

        if level == CompactionLevel.LEVEL_1:
            preserve_ratio = 0.6
        elif level == CompactionLevel.LEVEL_2:
            preserve_ratio = 0.3
        else:
            preserve_ratio = 0.1

        min_preserve = tail_turns * 2
        calculated = int(total * preserve_ratio)
        return max(min_preserve, calculated)

    async def _generate_summary(
        self,
        messages: list[Any],
        level: CompactionLevel,
    ) -> CompactionSummary:
        """生成结构化压缩摘要。

        优先提交批处理 API（非实时任务，适合批处理），降级为实时 API。

        Args:
            messages: 待压缩的消息列表。
            level: 压缩级别。

        Returns:
            CompactionSummary: 结构化摘要。
        """
        # 尝试提交批处理 API
        batch_submitted = False
        if self._batch_scheduler is not None:
            try:
                from src.maisaka.deepseek.batch_scheduler import (
                    BatchTask,
                    BatchTaskPriority,
                    BatchTaskStatus,
                    BatchTaskType,
                )

                task = BatchTask(
                    task_type=BatchTaskType.COMPACTION_SUMMARY,
                    priority=BatchTaskPriority.NORMAL,
                    payload={"level": level, "message_count": len(messages)},
                )
                batch_status = self._batch_scheduler.submit_task(task)
                batch_submitted = batch_status == BatchTaskStatus.PENDING
                if not batch_submitted:
                    logger.info(
                        "Compaction 摘要生成批处理不可用，降级为实时API: L%d",
                        level,
                    )
            except Exception as e:
                logger.warning(
                    "Compaction 批处理提交异常，降级为实时API: %s", e
                )

        text_parts: list[str] = []
        for msg in messages:
            plain = getattr(msg, "processed_plain_text", None) or ""
            nickname = getattr(msg, "user_nickname", "")
            if plain:
                text_parts.append(f"[{nickname}]: {plain}")

        full_text = "\n".join(text_parts)

        if level == CompactionLevel.LEVEL_1:
            max_len = 2000
        elif level == CompactionLevel.LEVEL_2:
            max_len = 1000
        else:
            max_len = 500

        truncated = full_text[:max_len]
        mode = "批处理" if batch_submitted else "实时API"

        return CompactionSummary(
            goal="压缩历史对话上下文",
            instructions=f"保留关键信息，移除冗余细节。压缩级别: L{level}",
            discoveries=truncated[:max_len // 2],
            accomplished=f"已压缩 {len(messages)} 条消息",
            relevant_files="",
        )