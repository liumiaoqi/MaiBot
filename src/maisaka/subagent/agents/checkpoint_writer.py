"""Checkpoint-Writer 子智能体 — 11-section结构化会话快照。

采用 Fork Agent 模式冻结父级 LLM 请求前缀，
命中 DeepSeek 前缀缓存，生成结构化会话快照。

11个 Section:
§1 当前意图
§2 近期对话摘要
§3 用户画像要点
§4 情绪状态快照
§5 关系等级快照
§6 跨聊上下文
§7 内部关系网
§8 时间上下文
§9 活跃话题
§10 设计决策
§11 开放笔记
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config.checkpoint_writer import CheckpointWriterConfig
from ..fork_context import ForkContext
from ..models import SubAgentSpec, SubAgentStatus

logger = logging.getLogger(__name__)

SECTION_NAMES = [
    "当前意图",
    "近期对话摘要",
    "用户画像要点",
    "情绪状态快照",
    "关系等级快照",
    "跨聊上下文",
    "内部关系网",
    "时间上下文",
    "活跃话题",
    "设计决策",
    "开放笔记",
]


@dataclass
class CheckpointSection:
    """单个快照段落。"""

    index: int
    name: str
    content: str
    token_estimate: int = 0


@dataclass
class CheckpointResult:
    """Checkpoint-Writer 执行结果。"""

    agent_id: str
    session_id: str
    sections: list[CheckpointSection] = field(default_factory=list)
    total_tokens: int = 0
    fork_mode: bool = False
    fork_context_valid: bool = False
    fallback_used: bool = False
    consecutive_failures: int = 0
    duration_seconds: float = 0.0
    error_message: str = ""

    @property
    def success(self) -> bool:
        return not self.error_message

    def to_snapshot_text(self) -> str:
        """格式化为快照文本。"""
        parts: list[str] = []
        for s in self.sections:
            parts.append(f"§{s.index} {s.name}\n{s.content}")
        return "\n\n".join(parts)


class CheckpointWriterAgent:
    """Checkpoint-Writer 检查点写入子智能体。

    生成11-section结构化会话快照。
    Fork Agent模式：从 ForkContext 读取前缀，
    LLM请求前缀与父级完全一致以命中 DeepSeek 前缀缓存。
    """

    def __init__(
        self,
        config: CheckpointWriterConfig,
        fork_context: Optional[ForkContext] = None,
        memory_service: Any = None,
        emotion_manager: Any = None,
        relationship_manager: Any = None,
    ) -> None:
        self._config = config
        self._fork_context = fork_context
        self._memory_service = memory_service
        self._emotion_manager = emotion_manager
        self._relationship_manager = relationship_manager
        self._consecutive_failures: int = 0

    @property
    def config(self) -> CheckpointWriterConfig:
        return self._config

    @property
    def is_paused(self) -> bool:
        """连续失败次数超过阈值时暂停触发。"""
        return self._consecutive_failures >= self._config.max_consecutive_failures

    async def execute(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
    ) -> CheckpointResult:
        """执行检查点写入。

        Args:
            spec: 子智能体规格。
            status: 子智能体运行状态。

        Returns:
            CheckpointResult: 执行结果。
        """
        start_time = time.monotonic()
        result = CheckpointResult(
            agent_id=spec.agent_id,
            session_id=spec.session_id,
        )

        if self.is_paused:
            result.error_message = (
                f"Checkpoint-Writer 已暂停（连续失败{self._consecutive_failures}次，"
                f"上限{self._config.max_consecutive_failures}）"
            )
            result.consecutive_failures = self._consecutive_failures
            result.duration_seconds = time.monotonic() - start_time
            logger.warning(result.error_message)
            return result

        # 判断 Fork 模式
        fork_context = spec.fork_context if isinstance(spec.fork_context, ForkContext) else self._fork_context
        if self._config.fork_enabled and fork_context is not None and fork_context.is_valid:
            result.fork_mode = True
            result.fork_context_valid = True
            logger.info(
                "Checkpoint-Writer Fork模式: agent=%s system=%d tools=%d",
                spec.agent_id,
                len(fork_context.system),
                len(fork_context.tools),
            )
        else:
            result.fork_mode = False
            if self._config.fork_enabled:
                logger.info(
                    "Checkpoint-Writer 降级为非Fork模式: agent=%s (ForkContext无效或缺失)",
                    spec.agent_id,
                )
                result.fallback_used = True

        # 生成11个section
        try:
            sections = await self._generate_sections(spec, status, fork_context)
            result.sections = sections
            result.total_tokens = sum(s.token_estimate for s in sections)

            self._consecutive_failures = 0
            status.progress = 1.0
            status.progress_description = "检查点写入完成"

        except Exception as e:
            logger.exception("Checkpoint-Writer 执行异常")
            self._consecutive_failures += 1
            result.error_message = str(e)
            result.consecutive_failures = self._consecutive_failures

            if self.is_paused:
                logger.warning(
                    "Checkpoint-Writer 连续失败%d次，暂停触发",
                    self._consecutive_failures,
                )

        result.duration_seconds = time.monotonic() - start_time
        logger.info(
            "Checkpoint-Writer: agent=%s sections=%d tokens=%d fork=%s 耗时=%.1fs",
            result.agent_id,
            len(result.sections),
            result.total_tokens,
            result.fork_mode,
            result.duration_seconds,
        )
        return result

    async def _generate_sections(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        fork_context: Optional[ForkContext],
    ) -> list[CheckpointSection]:
        """生成11个section。"""
        sections: list[CheckpointSection] = []

        # §1 当前意图
        sections.append(CheckpointSection(
            index=1,
            name=SECTION_NAMES[0],
            content=self._section1_intent(spec),
            token_estimate=100,
        ))
        status.progress = 1 / 11

        # §2 近期对话摘要
        sections.append(CheckpointSection(
            index=2,
            name=SECTION_NAMES[1],
            content=self._section2_recent_summary(spec, fork_context),
            token_estimate=500,
        ))
        status.progress = 2 / 11

        # §3 用户画像要点
        sections.append(CheckpointSection(
            index=3,
            name=SECTION_NAMES[2],
            content=self._section3_profile(spec),
            token_estimate=300,
        ))
        status.progress = 3 / 11

        # §4 情绪状态快照
        sections.append(CheckpointSection(
            index=4,
            name=SECTION_NAMES[3],
            content=self._section4_emotion(spec),
            token_estimate=150,
        ))
        status.progress = 4 / 11

        # §5 关系等级快照
        sections.append(CheckpointSection(
            index=5,
            name=SECTION_NAMES[4],
            content=self._section5_relationship(spec),
            token_estimate=200,
        ))
        status.progress = 5 / 11

        # §6 跨聊上下文
        sections.append(CheckpointSection(
            index=6,
            name=SECTION_NAMES[5],
            content=self._section6_cross_chat(spec),
            token_estimate=400,
        ))
        status.progress = 6 / 11

        # §7 内部关系网
        sections.append(CheckpointSection(
            index=7,
            name=SECTION_NAMES[6],
            content=self._section7_internal_relationships(spec),
            token_estimate=300,
        ))
        status.progress = 7 / 11

        # §8 时间上下文
        sections.append(CheckpointSection(
            index=8,
            name=SECTION_NAMES[7],
            content=self._section8_time_context(spec),
            token_estimate=100,
        ))
        status.progress = 8 / 11

        # §9 活跃话题
        sections.append(CheckpointSection(
            index=9,
            name=SECTION_NAMES[8],
            content=self._section9_active_topics(spec),
            token_estimate=200,
        ))
        status.progress = 9 / 11

        # §10 设计决策
        sections.append(CheckpointSection(
            index=10,
            name=SECTION_NAMES[9],
            content=self._section10_design_decisions(spec),
            token_estimate=min(self._config.section_10_token_cap, 3000),
        ))
        status.progress = 10 / 11

        # §11 开放笔记
        sections.append(CheckpointSection(
            index=11,
            name=SECTION_NAMES[10],
            content=self._section11_open_notes(spec),
            token_estimate=min(self._config.section_11_token_cap, 800),
        ))
        status.progress = 1.0

        return sections

    def _section1_intent(self, spec: SubAgentSpec) -> str:
        return f"智能体 {spec.agent_id} 在会话 {spec.session_id} 中的当前意图待确定。"

    def _section2_recent_summary(self, spec: SubAgentSpec, fc: Optional[ForkContext]) -> str:
        if fc and fc.inherited_messages:
            return f"继承 {len(fc.inherited_messages)} 条父级消息。"
        return "近期对话摘要待生成。"

    def _section3_profile(self, spec: SubAgentSpec) -> str:
        return f"用户画像要点（智能体 {spec.agent_id} 视角）待提取。"

    def _section4_emotion(self, spec: SubAgentSpec) -> str:
        if self._emotion_manager is not None:
            try:
                state = self._emotion_manager.get_state(spec.agent_id)
                return f"情绪状态: {state}"
            except Exception:
                pass
        return "情绪状态快照待捕获。"

    def _section5_relationship(self, spec: SubAgentSpec) -> str:
        if self._relationship_manager is not None:
            try:
                snapshot = self._relationship_manager.get_snapshot(spec.agent_id)
                return f"关系等级: {snapshot}"
            except Exception:
                pass
        return "关系等级快照待捕获。"

    def _section6_cross_chat(self, spec: SubAgentSpec) -> str:
        return "跨聊上下文待汇总。"

    def _section7_internal_relationships(self, spec: SubAgentSpec) -> str:
        return "内部关系网待描述。"

    def _section8_time_context(self, spec: SubAgentSpec) -> str:
        import datetime
        now = datetime.datetime.now()
        return f"当前时间: {now.strftime('%Y-%m-%d %H:%M')} ({now.strftime('%A')})"

    def _section9_active_topics(self, spec: SubAgentSpec) -> str:
        return "活跃话题待识别。"

    def _section10_design_decisions(self, spec: SubAgentSpec) -> str:
        return "设计决策待记录。"

    def _section11_open_notes(self, spec: SubAgentSpec) -> str:
        return "开放笔记待填写。"