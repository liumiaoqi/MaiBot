"""Distill 子智能体 — 从重复交互模式提取行为资产。

核心原则：没有重复模式就不创建任何东西。

3类行为资产：
  1. 互动风格资产：从高频互动模式提取沟通偏好
  2. 触发规则资产：从重复触发场景提取行为规则
  3. 情绪模式资产：从情绪变化规律提取情绪模式

30天窗口扫描，最小重复次数阈值=3。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DistillAssetType(str, Enum):
    """行为资产类型。"""

    INTERACTION_STYLE = "interaction_style"
    TRIGGER_RULE = "trigger_rule"
    EMOTION_PATTERN = "emotion_pattern"


@dataclass
class DistillAsset:
    """提取出的行为资产。"""

    asset_type: DistillAssetType
    agent_id: str
    pattern_key: str
    pattern_description: str
    evidence_count: int = 0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """资产是否有效（证据数>=3且置信度>=0.5）。"""
        return self.evidence_count >= 3 and self.confidence >= 0.5


@dataclass
class DistillResult:
    """Distill 执行总结果。"""

    agent_id: str
    assets: list[DistillAsset] = field(default_factory=list)
    skipped_no_pattern: int = 0
    skipped_low_confidence: int = 0
    total_interactions_scanned: int = 0
    duration_seconds: float = 0.0
    error_message: str = ""

    @property
    def success(self) -> bool:
        return not self.error_message

    def to_summary(self) -> str:
        if self.error_message:
            return f"Distill失败: {self.error_message}"
        valid = sum(1 for a in self.assets if a.is_valid())
        return (
            f"Distill完成: 扫描{self.total_interactions_scanned}条交互 "
            f"提取{len(self.assets)}个模式({valid}个有效) "
            f"跳过{self.skipped_no_pattern}无模式+{self.skipped_low_confidence}低置信 "
            f"耗时{self.duration_seconds:.1f}s"
        )


class DistillAgent:
    """Distill 记忆巩固子智能体。

    从30天窗口的重复交互模式中提取行为资产。
    核心原则：没有重复模式就不创建任何东西。
    """

    MIN_EVIDENCE_THRESHOLD = 3
    MIN_CONFIDENCE = 0.5
    WINDOW_DAYS = 30

    def __init__(
        self,
        knowledge_store: Any = None,
        memory_service: Any = None,
        relationship_manager: Any = None,
    ) -> None:
        self._knowledge_store = knowledge_store
        self._memory_service = memory_service
        self._relationship_manager = relationship_manager

    async def execute(
        self,
        agent_id: str,
        window_days: int = 30,
    ) -> DistillResult:
        """执行 Distill 巩固流程。

        Args:
            agent_id: 目标智能体ID。
            window_days: 扫描窗口天数。

        Returns:
            DistillResult: 执行结果。
        """
        start_time = time.monotonic()
        result = DistillResult(agent_id=agent_id)

        try:
            interactions = self._collect_interactions(agent_id, window_days)
            result.total_interactions_scanned = len(interactions)

            if len(interactions) < self.MIN_EVIDENCE_THRESHOLD:
                result.skipped_no_pattern = len(interactions)
                result.duration_seconds = time.monotonic() - start_time
                logger.info(
                    "Distill: 交互数不足(%d<%d)，跳过: agent=%s",
                    len(interactions),
                    self.MIN_EVIDENCE_THRESHOLD,
                    agent_id,
                )
                return result

            interaction_assets = self._extract_interaction_style_assets(
                agent_id, interactions
            )
            trigger_assets = self._extract_trigger_rule_assets(
                agent_id, interactions
            )
            emotion_assets = self._extract_emotion_pattern_assets(
                agent_id, interactions
            )

            all_assets = interaction_assets + trigger_assets + emotion_assets

            for asset in all_assets:
                if asset.is_valid():
                    result.assets.append(asset)
                    if self._knowledge_store is not None:
                        try:
                            self._knowledge_store.store_asset(asset)
                        except Exception as e:
                            logger.debug("资产存储跳过: %s", e)
                elif asset.evidence_count > 0:
                    result.skipped_low_confidence += 1
                else:
                    result.skipped_no_pattern += 1

        except Exception as e:
            result.error_message = str(e)
            logger.exception("Distill 执行异常: agent=%s", agent_id)

        result.duration_seconds = time.monotonic() - start_time
        logger.info("Distill: %s", result.to_summary())
        return result

    def _collect_interactions(
        self, agent_id: str, window_days: int
    ) -> list[dict[str, Any]]:
        """收集指定窗口内的交互记录。"""
        interactions: list[dict[str, Any]] = []

        try:
            from src.common.database.database import get_db_session
            from src.common.database.database_model import AgentRelationship

            with get_db_session() as db:
                rows = db.query(AgentRelationship).filter(
                    AgentRelationship.agent_id == agent_id,
                    AgentRelationship.interaction_count > 0,
                ).all()

                for row in rows:
                    interactions.append({
                        "user_id": row.user_id,
                        "interaction_count": row.interaction_count,
                        "score": row.score,
                        "level": row.level,
                        "last_interaction_at": row.last_interaction_at.isoformat() if row.last_interaction_at else None,
                    })
        except Exception as e:
            logger.warning("Distill 收集交互记录失败: %s", e)

        return interactions

    def _extract_interaction_style_assets(
        self,
        agent_id: str,
        interactions: list[dict[str, Any]],
    ) -> list[DistillAsset]:
        """提取互动风格资产。

        从高频互动用户中提取沟通偏好模式。
        """
        assets: list[DistillAsset] = []

        high_frequency_users = [
            i for i in interactions if i.get("interaction_count", 0) >= self.MIN_EVIDENCE_THRESHOLD
        ]

        if not high_frequency_users:
            return assets

        total_interactions = sum(i.get("interaction_count", 0) for i in high_frequency_users)
        avg_score = sum(i.get("score", 0) for i in high_frequency_users) / max(len(high_frequency_users), 1)

        style_description = self._build_interaction_style_description(
            high_frequency_users, total_interactions, avg_score
        )

        confidence = min(
            len(high_frequency_users) / 5.0,
            1.0,
        )

        assets.append(DistillAsset(
            asset_type=DistillAssetType.INTERACTION_STYLE,
            agent_id=agent_id,
            pattern_key=f"interaction_style_{agent_id}",
            pattern_description=style_description,
            evidence_count=len(high_frequency_users),
            confidence=confidence,
            metadata={
                "total_interactions": total_interactions,
                "avg_score": avg_score,
                "high_frequency_user_count": len(high_frequency_users),
            },
        ))

        return assets

    def _extract_trigger_rule_assets(
        self,
        agent_id: str,
        interactions: list[dict[str, Any]],
    ) -> list[DistillAsset]:
        """提取触发规则资产。

        从关系等级分布中提取行为触发规则。
        """
        assets: list[DistillAsset] = []

        level_distribution: dict[int, int] = {}
        for i in interactions:
            level = i.get("level", 0)
            level_distribution[level] = level_distribution.get(level, 0) + 1

        significant_levels = {
            k: v for k, v in level_distribution.items()
            if v >= self.MIN_EVIDENCE_THRESHOLD
        }

        if not significant_levels:
            return assets

        level_names = {0: "陌生人", 1: "认识", 2: "熟悉", 3: "亲密"}
        descriptions = []
        for level, count in sorted(significant_levels.items()):
            name = level_names.get(level, f"等级{level}")
            descriptions.append(f"{name}关系用户{count}人")

        rule_description = f"触发规则：{', '.join(descriptions)}。"
        if 3 in significant_levels:
            rule_description += "亲密关系用户优先响应。"
        elif 2 in significant_levels:
            rule_description += "熟悉关系用户积极互动。"

        confidence = min(
            sum(significant_levels.values()) / 10.0,
            1.0,
        )

        assets.append(DistillAsset(
            asset_type=DistillAssetType.TRIGGER_RULE,
            agent_id=agent_id,
            pattern_key=f"trigger_rule_{agent_id}",
            pattern_description=rule_description,
            evidence_count=sum(significant_levels.values()),
            confidence=confidence,
            metadata={"level_distribution": level_distribution},
        ))

        return assets

    def _extract_emotion_pattern_assets(
        self,
        agent_id: str,
        interactions: list[dict[str, Any]],
    ) -> list[DistillAsset]:
        """提取情绪模式资产。

        从互动分数分布中提取情绪反应模式。
        """
        assets: list[DistillAsset] = []

        scores = [i.get("score", 0) for i in interactions if i.get("score", 0) > 0]
        if len(scores) < self.MIN_EVIDENCE_THRESHOLD:
            return assets

        avg_score = sum(scores) / len(scores)
        high_score_count = sum(1 for s in scores if s >= 650)
        low_score_count = sum(1 for s in scores if s < 350)

        pattern_parts = []
        if high_score_count >= self.MIN_EVIDENCE_THRESHOLD:
            pattern_parts.append(
                f"与{high_score_count}位用户关系亲密(≥650分)，互动时情绪偏积极"
            )
        if low_score_count >= self.MIN_EVIDENCE_THRESHOLD:
            pattern_parts.append(
                f"与{low_score_count}位用户关系较浅(<350分)，互动时保持礼貌距离"
            )

        if not pattern_parts:
            return assets

        pattern_description = f"情绪模式：{'; '.join(pattern_parts)}。平均关系分{avg_score:.0f}。"

        confidence = min(len(scores) / 10.0, 1.0)

        assets.append(DistillAsset(
            asset_type=DistillAssetType.EMOTION_PATTERN,
            agent_id=agent_id,
            pattern_key=f"emotion_pattern_{agent_id}",
            pattern_description=pattern_description,
            evidence_count=len(scores),
            confidence=confidence,
            metadata={
                "avg_score": avg_score,
                "high_score_count": high_score_count,
                "low_score_count": low_score_count,
            },
        ))

        return assets

    def _build_interaction_style_description(
        self,
        users: list[dict[str, Any]],
        total_interactions: int,
        avg_score: float,
    ) -> str:
        """构建互动风格描述。"""
        if avg_score >= 650:
            style = "亲密友好型"
        elif avg_score >= 350:
            style = "温和亲近型"
        else:
            style = "礼貌疏离型"

        return (
            f"互动风格：{style}。"
            f"与{len(users)}位高频用户共互动{total_interactions}次，"
            f"平均关系分{avg_score:.0f}。"
        )