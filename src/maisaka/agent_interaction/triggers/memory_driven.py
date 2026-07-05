"""记忆驱动触发器。

基于交互记忆的正面/负面加成、重逢需求、续聊约定等
驱动智能体间的交互触发。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import BaseTrigger, TriggerEvaluation

logger = logging.getLogger(__name__)

# 默认配置值
_POSITIVE_BONUS = 0.2
_NEGATIVE_PENALTY = 0.3
_RECONCILE_BONUS = 0.15
_REUNION_PROBABILITY = 0.15
_REUNION_THRESHOLD_HOURS = 24


class MemoryDrivenTrigger(BaseTrigger):
    """记忆驱动触发器。

    触发逻辑：
    1. 检索与各智能体的交互记忆
    2. 正面记忆 +20% 触发概率
    3. 负面记忆 -30% 触发概率，"想和好"类型 +15%
    4. 超过24小时无交互产生"想念"需求
    5. "续聊"类型引用上次交互内容
    """

    def __init__(
        self,
        memory_adapter: AgentMemoryAdapter,
        positive_bonus: float = _POSITIVE_BONUS,
        negative_penalty: float = _NEGATIVE_PENALTY,
        reconcile_bonus: float = _RECONCILE_BONUS,
        reunion_probability: float = _REUNION_PROBABILITY,
        reunion_threshold_hours: int = _REUNION_THRESHOLD_HOURS,
    ) -> None:
        self._memory_adapter = memory_adapter
        self._positive_bonus = positive_bonus
        self._negative_penalty = negative_penalty
        self._reconcile_bonus = reconcile_bonus
        self._reunion_probability = reunion_probability
        self._reunion_threshold_hours = reunion_threshold_hours

    async def evaluate(
        self,
        agent_id: str,
        emotion_state: EmotionState,
        relationships: list[AgentInteractionRelationshipRead],
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> TriggerEvaluation:
        best_target = ""
        best_prob = 0.0
        best_reason = ""

        for rel in relationships:
            prob = 0.0
            memory_desc = ""

            mention = min(rel.score / 300.0, 1.0) if rel.score > 0 else 0.1

            # 检索交互记忆
            try:
                result = await self._memory_adapter.search_interaction_memory(
                    agent_id, rel.target_agent_id, limit=5
                )
                if result.success and result.hits:
                    # 分析记忆中的情绪标签
                    positive_count = 0
                    negative_count = 0
                    has_reconcile = False
                    has_continuation = False

                    for hit in result.hits:
                        tags = hit.metadata.get("tags", [])
                        if isinstance(tags, str):
                            tags = [tags]
                        if "positive" in tags:
                            positive_count += 1
                        if "negative" in tags:
                            negative_count += 1
                        # 检测"想和好"类型
                        content_lower = hit.content.lower()
                        if any(kw in content_lower for kw in ["和好", "和解", "重归于好", "reconcile"]):
                            has_reconcile = True
                        # 检测"续聊"约定
                        if any(kw in content_lower for kw in ["再聊", "下次", "继续", "续聊"]):
                            has_continuation = True

                    # 计算概率
                    base_prob = mention * 0.5
                    prob = base_prob
                    prob += positive_count * self._positive_bonus
                    prob -= negative_count * self._negative_penalty
                    if has_reconcile:
                        prob += self._reconcile_bonus
                        memory_desc = "想和好的念头"
                    if has_continuation:
                        prob += 0.1
                        memory_desc = memory_desc or "上次约定再聊"

                    prob = max(0.0, prob)

                else:
                    # 无交互记忆，检查是否超过重逢阈值
                    prob = self._check_reunion(agent_id, rel, mention)
                    if prob > 0:
                        memory_desc = "好久没互动了"

            except Exception as e:
                logger.debug("[agent_interaction] 记忆检索失败: %s", e)
                prob = mention * 0.3

            if prob > best_prob:
                best_prob = prob
                best_target = rel.target_agent_id
                best_reason = memory_desc or "交互记忆"

        if best_prob < 0.3 or not best_target:
            return TriggerEvaluation(
                initiator_agent_id=agent_id, interaction_type="memory_driven"
            )

        reason = f"记忆驱动：{agent_id}基于与{best_target}的{best_reason}发起交互"

        return TriggerEvaluation(
            should_trigger=True,
            trigger_probability=best_prob,
            initiator_agent_id=agent_id,
            target_agent_id=best_target,
            interaction_type="memory_driven",
            trigger_reason=reason,
            metadata={"memory_desc": best_reason},
        )

    def _check_reunion(
        self, agent_id: str, rel: AgentInteractionRelationshipRead, mention: float
    ) -> float:
        """检查是否超过重逢阈值，产生想念需求。"""
        if rel.last_interaction_at is None:
            return self._reunion_probability * mention

        now = time.time()
        hours_since = (now - rel.last_interaction_at.timestamp()) / 3600.0

        if hours_since >= self._reunion_threshold_hours:
            return self._reunion_probability * mention

        return 0.0