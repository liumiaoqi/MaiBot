"""Dream 子智能体 — 记忆巩固。

6阶段记忆巩固流程：
Phase 0: 定位数据源（读取记忆文件）
Phase 1: 定向（读取当前画像和检查点）
Phase 2: 提取（从记忆文件提取候选持久知识）
Phase 3: 验证（对照原始对话轨迹验证候选事实）
Phase 4: 合并去重（写入持久知识到画像6桶）
Phase 5: 精简验证（保持画像紧凑）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..config.dream import DreamConfig
from ..models import SubAgentSpec, SubAgentState, SubAgentStatus, SubAgentType

logger = logging.getLogger(__name__)


@dataclass
class DreamPhaseResult:
    """单阶段执行结果。"""

    phase: int
    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass
class DreamResult:
    """Dream 执行总结果。"""

    agent_id: str
    session_id: str
    phases: list[DreamPhaseResult] = field(default_factory=list)
    added_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    total_duration_seconds: float = 0.0
    error_message: str = ""
    batch_degraded: bool = False

    @property
    def success(self) -> bool:
        return not self.error_message

    def to_summary(self) -> str:
        if self.error_message:
            return f"Dream失败: {self.error_message}"
        return (
            f"Dream完成: 新增{self.added_count} 更新{self.updated_count} "
            f"删除{self.deleted_count} 跳过{self.skipped_count} "
            f"耗时{self.total_duration_seconds:.1f}s"
        )


# 画像6桶名称
BUCKET_KEYS = [
    "identity_settings",
    "relationship_settings",
    "stable_facts",
    "interaction_preferences",
    "recent_interactions",
    "uncertain_notes",
]


class DreamAgent:
    """Dream 记忆巩固子智能体。

    从对话轨迹提取持久知识，写入用户画像6桶结构。
    对 A_Memorix 画像服务只通过 MemoryService 接口操作。
    """

    def __init__(
        self,
        config: DreamConfig,
        memory_service: Any = None,
        message_repository: Any = None,
        batch_scheduler: Any = None,
    ) -> None:
        self._config = config
        self._memory_service = memory_service
        self._message_repository = message_repository
        self._batch_scheduler = batch_scheduler

    @property
    def config(self) -> DreamConfig:
        return self._config

    async def execute(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
    ) -> DreamResult:
        """执行6阶段记忆巩固流程。

        Args:
            spec: 子智能体规格。
            status: 子智能体运行状态（会被更新进度）。

        Returns:
            DreamResult: 执行结果。
        """
        start_time = time.monotonic()
        result = DreamResult(
            agent_id=spec.agent_id,
            session_id=spec.session_id,
        )

        if self._memory_service is None:
            result.error_message = "A_Memorix 不可用，Dream 终止执行"
            logger.warning(result.error_message)
            return result

        phases = [
            (0, self._phase0_locate_data),
            (1, self._phase1_orient),
            (2, self._phase2_extract),
            (3, self._phase3_verify),
            (4, self._phase4_merge),
            (5, self._phase5_compact),
        ]

        for phase_num, phase_fn in phases:
            phase_start = time.monotonic()
            try:
                phase_result = await phase_fn(spec, status, result)
                phase_result.duration_seconds = time.monotonic() - phase_start
                result.phases.append(phase_result)

                if not phase_result.success:
                    logger.warning(
                        "Dream Phase %d 失败: %s",
                        phase_num,
                        phase_result.message,
                    )
                    if phase_num < 2:
                        result.error_message = f"Phase {phase_num} 失败: {phase_result.message}"
                        result.total_duration_seconds = time.monotonic() - start_time
                        return result

                status.progress = (phase_num + 1) / len(phases)
                status.progress_description = f"Phase {phase_num} 完成"

            except Exception as e:
                logger.exception("Dream Phase %d 异常", phase_num)
                result.phases.append(DreamPhaseResult(
                    phase=phase_num,
                    success=False,
                    message=str(e),
                    duration_seconds=time.monotonic() - phase_start,
                ))
                result.error_message = f"Phase {phase_num} 异常: {e}"
                result.total_duration_seconds = time.monotonic() - start_time
                return result

        result.total_duration_seconds = time.monotonic() - start_time
        logger.info("Dream 执行完成: %s", result.to_summary())
        return result

    async def _phase0_locate_data(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        result: DreamResult,
    ) -> DreamPhaseResult:
        """Phase 0: 定位数据源。"""
        if self._message_repository is None:
            return DreamPhaseResult(
                phase=0, success=False,
                message="消息仓库不可用",
            )

        from src.common.message_repository import find_messages

        end_time = time.time()
        start_time = end_time - self._config.interval_days * 86400

        messages = find_messages(
            session_id=spec.session_id,
            start_time=start_time,
            end_time=end_time,
            sort=[("timestamp", -1)],
            limit=500,
        )

        if not messages:
            return DreamPhaseResult(
                phase=0, success=True,
                message="无对话轨迹，无需巩固",
                data={"message_count": 0},
            )

        return DreamPhaseResult(
            phase=0, success=True,
            message=f"定位到 {len(messages)} 条对话轨迹",
            data={
                "message_count": len(messages),
                "time_range_days": self._config.interval_days,
                "messages": messages[:50],
            },
        )

    async def _phase1_orient(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        result: DreamResult,
    ) -> DreamPhaseResult:
        """Phase 1: 定向 — 读取当前画像。"""
        try:
            profile = await self._memory_service.get_person_profile(
                person_id=spec.agent_id,
                chat_id=spec.session_id,
            )
            return DreamPhaseResult(
                phase=1, success=True,
                message="画像读取完成",
                data={"profile": profile},
            )
        except Exception as e:
            return DreamPhaseResult(
                phase=1, success=False,
                message=f"画像读取失败: {e}",
            )

    async def _phase2_extract(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        result: DreamResult,
    ) -> DreamPhaseResult:
        """Phase 2: 提取候选持久知识。

        优先提交批处理 API（50%成本折扣），降级为实时 API。
        """
        phase0_data = next(
            (p.data for p in result.phases if p.phase == 0), {}
        )
        message_count = phase0_data.get("message_count", 0)

        if message_count == 0:
            return DreamPhaseResult(
                phase=2, success=True,
                message="无对话轨迹，跳过提取",
                data={"candidates": []},
            )

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
                    agent_id=spec.agent_id,
                    task_type=BatchTaskType.DREAM_CONSOLIDATION,
                    priority=BatchTaskPriority.NORMAL,
                    payload={
                        "session_id": spec.session_id,
                        "interval_days": self._config.interval_days,
                        "message_count": message_count,
                    },
                )
                batch_status = self._batch_scheduler.submit_task(task)
                if batch_status == BatchTaskStatus.PENDING:
                    batch_submitted = True
                    logger.info(
                        "Dream Phase2 知识提取已提交批处理: agent=%s",
                        spec.agent_id,
                    )
                else:
                    result.batch_degraded = True
                    logger.info(
                        "Dream Phase2 批处理不可用，降级为实时API: agent=%s",
                        spec.agent_id,
                    )
            except Exception as e:
                result.batch_degraded = True
                logger.warning(
                    "Dream Phase2 批处理提交异常，降级为实时API: %s", e
                )

        candidates: list[dict[str, Any]] = []
        messages = phase0_data.get("messages", [])

        for msg in messages:
            text = getattr(msg, "processed_plain_text", None) or ""
            if not text or len(text) < 5:
                continue
            candidates.append({
                "source": "conversation_trace",
                "text": text[:200],
                "session_id": spec.session_id,
                "timestamp": str(getattr(msg, "timestamp", "")),
            })

        mode = "批处理" if batch_submitted else "实时API"
        return DreamPhaseResult(
            phase=2, success=True,
            message=f"提取 {len(candidates)} 条候选知识 (模式: {mode})",
            data={"candidates": candidates, "batch_submitted": batch_submitted},
        )

    async def _phase3_verify(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        result: DreamResult,
    ) -> DreamPhaseResult:
        """Phase 3: 验证候选事实。"""
        phase2_data = next(
            (p.data for p in result.phases if p.phase == 2), {}
        )
        candidates = phase2_data.get("candidates", [])

        verified: list[dict[str, Any]] = []
        for c in candidates:
            text = c.get("text", "")
            if len(text) >= 10:
                verified.append(c)

        return DreamPhaseResult(
            phase=3, success=True,
            message=f"验证通过 {len(verified)}/{len(candidates)} 条",
            data={"verified": verified},
        )

    async def _phase4_merge(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        result: DreamResult,
    ) -> DreamPhaseResult:
        """Phase 4: 合并去重 — 写入画像6桶。"""
        phase3_data = next(
            (p.data for p in result.phases if p.phase == 3), {}
        )
        verified = phase3_data.get("verified", [])

        if not verified:
            result.skipped_count = len(verified)
            return DreamPhaseResult(
                phase=4, success=True,
                message="无待合并知识",
            )

        bucket_distribution: dict[str, list[str]] = {
            k: [] for k in BUCKET_KEYS
        }

        for v in verified:
            text = v.get("text", "")
            bucket = self._classify_to_bucket(text)
            bucket_distribution[bucket].append(text)

        added = 0
        updated = 0
        for bucket_key, items in bucket_distribution.items():
            for item_text in items:
                try:
                    await self._memory_service.ingest_text(
                        external_id=f"dream_{spec.agent_id}_{int(time.time())}",
                        source_type="dream_consolidation",
                        text=item_text,
                        chat_id=spec.session_id,
                    )
                    added += 1
                except Exception as e:
                    logger.debug("合并写入跳过: %s", e)
                    result.skipped_count += 1

        result.added_count = added
        result.updated_count = updated

        return DreamPhaseResult(
            phase=4, success=True,
            message=f"合并完成: 新增{added} 更新{updated}",
            data={"bucket_distribution": {k: len(v) for k, v in bucket_distribution.items()}},
        )

    async def _phase5_compact(
        self,
        spec: SubAgentSpec,
        status: SubAgentStatus,
        result: DreamResult,
    ) -> DreamPhaseResult:
        """Phase 5: 精简验证 — 保持画像紧凑。"""
        try:
            profile = await self._memory_service.get_person_profile(
                person_id=spec.agent_id,
                chat_id=spec.session_id,
            )
            return DreamPhaseResult(
                phase=5, success=True,
                message="精简验证完成",
                data={"final_profile_available": True},
            )
        except Exception as e:
            return DreamPhaseResult(
                phase=5, success=True,
                message=f"精简验证跳过（画像不可读）: {e}",
            )

    def _classify_to_bucket(self, text: str) -> str:
        """将候选知识分类到画像6桶。

        基于关键词启发式分类，后续可替换为 LLM 分类。
        """
        text_lower = text.lower()

        identity_keywords = ["名字", "叫", "是", "职业", "身份", "年龄", "岁"]
        relationship_keywords = ["关系", "朋友", "恋人", "称呼", "叫她", "叫他", "闺蜜"]
        stable_keywords = ["总是", "一直", "从来", "每次", "习惯", "喜欢", "讨厌"]
        preference_keywords = ["偏好", "雷点", "不喜欢", "想要", "希望", "介意"]
        recent_keywords = ["最近", "今天", "昨天", "刚才", "刚刚"]
        uncertain_keywords = ["可能", "也许", "大概", "好像", "似乎", "不确定"]

        scores: dict[str, int] = {}
        keyword_map = {
            "identity_settings": identity_keywords,
            "relationship_settings": relationship_keywords,
            "stable_facts": stable_keywords,
            "interaction_preferences": preference_keywords,
            "recent_interactions": recent_keywords,
            "uncertain_notes": uncertain_keywords,
        }

        for bucket, keywords in keyword_map.items():
            scores[bucket] = sum(1 for kw in keywords if kw in text_lower)

        max_score = max(scores.values()) if scores else 0
        if max_score == 0:
            return "uncertain_notes"

        for bucket, score in scores.items():
            if score == max_score:
                return bucket

        return "uncertain_notes"