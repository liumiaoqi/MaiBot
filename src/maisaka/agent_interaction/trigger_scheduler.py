"""交互触发器调度器。

综合多种触发信号计算触发概率，协调冷却控制，
选择最优触发决策并调用交互引擎执行。
"""

from __future__ import annotations

import logging

from src.maisaka.agent.config import AgentConfig

from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent_interaction.cooldown import InteractionCooldownManager, build_agent_pair_key
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.engine import InteractionEngine, InteractionResult
from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation, TriggerRegistry
from src.maisaka.time_awareness.service import TimeAwarenessService

logger = logging.getLogger(__name__)

# 综合触发权重
_EMOTION_WEIGHT = 0.4
_TIME_WEIGHT = 0.3
_RELATIONSHIP_WEIGHT = 0.3

# 触发阈值
_DEFAULT_TRIGGER_THRESHOLD = 0.5


class InteractionTrigger:
    """交互触发器调度器。

    核心方法 evaluate_all：
    1. 获取智能体情绪状态和关系网
    2. 遍历所有已注册触发器
    3. 综合触发概率 = 情绪权重×情绪概率 + 时间权重×时间概率 + 关系权重×关系概率
    4. 选择综合概率最高的触发结果
    5. 检查冷却状态
    6. 冷却通过则返回触发决策
    """

    def __init__(
        self,
        emotion_registry: AgentEmotionManagerRegistry,
        relationship_manager: AgentRelationshipManager,
        engine: InteractionEngine,
        cooldown_manager: InteractionCooldownManager,
        trigger_registry: TriggerRegistry | None = None,
        trigger_threshold: float = _DEFAULT_TRIGGER_THRESHOLD,
    ) -> None:
        self._emotion_registry = emotion_registry
        self._relationship_manager = relationship_manager
        self._engine = engine
        self._cooldown_manager = cooldown_manager
        self._trigger_registry = trigger_registry or TriggerRegistry()
        self._trigger_threshold = trigger_threshold
        self._config_registry = AgentConfigRegistry.get_instance()
        self._time_service = TimeAwarenessService()

    @property
    def registry(self) -> TriggerRegistry:
        return self._trigger_registry

    async def evaluate_all(self, agent_id: str) -> TriggerEvaluation | None:
        """综合评估所有触发器，返回最优触发决策。"""
        config = self._config_registry.get_agent(agent_id)
        emotion_state = self._emotion_registry.get_emotion_state(agent_id)

        # 获取关系列表
        relationships = await self._get_relationships(agent_id, config)

        # 构建时间上下文
        time_ctx = self._time_service.get_time_context(config)
        time_context = {
            "time_period": time_ctx.time_period,
            "active_coefficient": time_ctx.active_coefficient,
        }

        # 遍历所有触发器评估
        evaluations: list[tuple[str, TriggerEvaluation]] = []
        for trigger_type, trigger in self._trigger_registry.all_triggers():
            evaluation = await trigger.evaluate(
                agent_id=agent_id,
                emotion_state=emotion_state,
                relationships=relationships,
                time_context=time_context,
            )
            evaluations.append((trigger_type, evaluation))

        if not evaluations:
            return None

        # 分类计算综合概率
        emotion_prob = 0.0
        time_prob = 0.0
        other_prob = 0.0
        best_evaluation: TriggerEvaluation | None = None
        best_combined = 0.0

        for trigger_type, evaluation in evaluations:
            if not evaluation.should_trigger:
                continue

            prob = evaluation.trigger_probability

            if trigger_type == "emotion_driven":
                emotion_prob = max(emotion_prob, prob)
            elif trigger_type == "time_awareness":
                time_prob = max(time_prob, prob)
            else:
                other_prob = max(other_prob, prob)

            combined = _EMOTION_WEIGHT * emotion_prob + _TIME_WEIGHT * time_prob + _RELATIONSHIP_WEIGHT * max(other_prob, prob)

            if combined > best_combined:
                best_combined = combined
                best_evaluation = evaluation

        if best_evaluation is None or best_combined < self._trigger_threshold:
            return None

        # 检查冷却
        pair_key = build_agent_pair_key(agent_id, best_evaluation.target_agent_id)
        can_trigger = await self._cooldown_manager.can_trigger(pair_key)
        if not can_trigger:
            logger.debug(
                "[agent_interaction] %s→%s 冷却中，跳过触发",
                agent_id,
                best_evaluation.target_agent_id,
            )
            return None

        return best_evaluation

    async def try_trigger(self, agent_id: str) -> InteractionResult | None:
        """尝试触发交互。"""
        evaluation = await self.evaluate_all(agent_id)
        if evaluation is None:
            return None

        result = await self._engine.execute(evaluation)

        if result.success:
            pair_key = build_agent_pair_key(agent_id, evaluation.target_agent_id)
            await self._cooldown_manager.record_interaction(pair_key)

        return result

    async def _get_relationships(self, agent_id: str, config: AgentConfig):
        """获取智能体关系列表，优先从数据库获取动态关系。"""
        relationships = []
        for rel in config.internal_relationships:
            db_rel = await self._relationship_manager.get_relationship(
                agent_id, rel.target_agent_id
            )
            if db_rel is not None:
                relationships.append(db_rel)
        return relationships