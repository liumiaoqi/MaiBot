"""交互引擎。

执行交互触发决策，原子化写入情绪变化、关系更新、记忆写入和事件持久化。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from src.maisaka.agent_interaction.effect_calculator import EffectCalculator
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.event_store import InteractionEventStore
from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
from src.maisaka.agent_interaction.models import InteractionEventCreate
from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation

logger = logging.getLogger(__name__)


@dataclass
class InteractionResult:
    """交互执行结果。"""

    success: bool = False
    event_id: str = ""
    emotion_effects: dict[str, dict[str, float]] = field(default_factory=dict)
    relationship_effect: float = 0.0
    memory_write_status: str = "skipped"
    echo_triggered: bool = False
    error: str = ""


class InteractionEngine:
    """交互引擎。

    核心流程：
    1. 调用 EffectCalculator 计算影响
    2. 若影响为空则返回失败
    3. 原子写入：双方情绪变化 + 关系更新 + 事件持久化
    4. 非阻塞：记忆写入（失败不回滚情绪和关系）
    """

    def __init__(
        self,
        emotion_registry: AgentEmotionManagerRegistry,
        relationship_manager: AgentRelationshipManager,
        event_store: InteractionEventStore,
        memory_adapter: AgentMemoryAdapter | None = None,
        echo_decay_ratio: float = 0.5,
        echo_max_depth: int = 3,
    ) -> None:
        self._emotion_registry = emotion_registry
        self._relationship_manager = relationship_manager
        self._event_store = event_store
        self._memory_adapter = memory_adapter
        self._effect_calculator = EffectCalculator(echo_decay_ratio=echo_decay_ratio)
        self._echo_max_depth = echo_max_depth
        self._echo_decay_ratio = echo_decay_ratio

    async def execute(self, evaluation: TriggerEvaluation) -> InteractionResult:
        """执行交互触发决策。"""
        if not evaluation.should_trigger:
            return InteractionResult(error="触发评估未通过")

        initiator_id = evaluation.initiator_agent_id
        target_id = evaluation.target_agent_id

        # 获取双方情绪状态
        initiator_state = self._emotion_registry.get_emotion_state(initiator_id)
        target_state = self._emotion_registry.get_emotion_state(target_id)

        # 获取关系类型
        rel = await self._relationship_manager.get_relationship(initiator_id, target_id)
        relationship_type = rel.relationship_type if rel else "friend"

        # 计算影响
        effect = self._effect_calculator.calculate(
            interaction_type=evaluation.interaction_type,
            relationship_type=relationship_type,
            initiator_emotion=initiator_state.dominant_emotion,
            target_emotion=target_state.dominant_emotion,
            echo_depth=evaluation.metadata.get("echo_depth", 0),
        )

        if effect.is_empty:
            return InteractionResult(error="影响计算结果为空，禁止零影响交互")

        # 原子写入
        try:
            # 写入发起方情绪变化
            for emotion_type, delta in effect.initiator_emotion_deltas.items():
                self._emotion_registry.apply_trigger(initiator_id, emotion_type, delta)

            # 写入目标方情绪变化
            for emotion_type, delta in effect.target_emotion_deltas.items():
                self._emotion_registry.apply_trigger(target_id, emotion_type, delta)

            # 更新关系分数
            await self._relationship_manager.update_relationship(
                initiator_id, target_id, effect.relationship_delta
            )

            # 非阻塞：写入交互记忆
            memory_status = "skipped"
            if self._memory_adapter is not None:
                memory_status = await self._write_memory(
                    initiator_id=initiator_id,
                    target_id=target_id,
                    evaluation=evaluation,
                    effect=effect,
                    emotion_effects={
                        "initiator": effect.initiator_emotion_deltas,
                        "target": effect.target_emotion_deltas,
                    },
                )

            # 持久化交互事件
            emotion_effects = {
                "initiator": effect.initiator_emotion_deltas,
                "target": effect.target_emotion_deltas,
            }
            event_data = InteractionEventCreate(
                initiator_agent_id=initiator_id,
                target_agent_id=target_id,
                interaction_type=evaluation.interaction_type,
                trigger_reason=evaluation.trigger_reason,
                emotion_effects=json.dumps(emotion_effects, ensure_ascii=False),
                relationship_effect=effect.relationship_delta,
                memory_write_status=memory_status,
                echo_depth=evaluation.metadata.get("echo_depth", 0),
                echo_parent_event_id=evaluation.metadata.get("echo_parent_event_id", ""),
                metadata=json.dumps(evaluation.metadata, ensure_ascii=False),
            )
            event_id = await self._event_store.save_event(event_data)

            result = InteractionResult(
                success=True,
                event_id=event_id,
                emotion_effects=emotion_effects,
                relationship_effect=effect.relationship_delta,
                memory_write_status=memory_status,
            )

            # 非阻塞：回声检测
            try:
                from src.maisaka.agent_interaction.echo_detector import EchoDetector
                detector = EchoDetector(
                    echo_max_depth=self._echo_max_depth,
                    echo_decay_ratio=self._echo_decay_ratio,
                )
                await detector.check_and_propagate(result, evaluation)
            except Exception as e:
                logger.debug("[agent_interaction] 回声检测异常，静默截断: %s", e)

            # 非阻塞：发布交互信号到自主性架构
            try:
                from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus, InteractionSignalEvent

                signal = InteractionSignalEvent(
                    initiator_agent_id=initiator_id,
                    target_agent_id=target_id,
                    interaction_type=evaluation.interaction_type,
                    trigger_reason=evaluation.trigger_reason,
                    emotion_effects=emotion_effects,
                    relationship_effect=effect.relationship_delta,
                    event_id=event_id,
                )
                AutonomyEventBus.get_instance().emit_sync("interaction_signal", signal)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error("[agent_interaction] 交互执行失败: %s", e)
            return InteractionResult(error=str(e))

    async def _write_memory(
        self,
        initiator_id: str,
        target_id: str,
        evaluation: TriggerEvaluation,
        effect: object,
        emotion_effects: dict,
    ) -> str:
        """非阻塞写入交互记忆，失败时降级为日志记录。"""
        try:
            content = evaluation.trigger_reason
            result = await self._memory_adapter.write_interaction_memory(
                event_id="pending",
                initiator_id=initiator_id,
                target_id=target_id,
                content=content,
                emotion_tag=effect.emotion_tag,
                interaction_type=evaluation.interaction_type,
                emotion_snapshot=json.dumps(emotion_effects, ensure_ascii=False),
                relationship_delta=effect.relationship_delta,
            )
            if result.success:
                return "success"
            logger.warning("[agent_interaction] 记忆写入失败: %s", result.detail)
            return "failed"
        except Exception as e:
            logger.warning("[agent_interaction] 记忆写入异常，降级为日志: %s", e)
            return "failed"

    async def execute_manual(
        self,
        initiator_id: str,
        target_id: str,
        interaction_type: str,
        reason: str,
    ) -> InteractionResult:
        """管理员手动触发交互。"""
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=1.0,
            initiator_agent_id=initiator_id,
            target_agent_id=target_id,
            interaction_type=interaction_type,
            trigger_reason=f"[手动触发] {reason}",
            metadata={"manual": True},
        )

        result = await self.execute(evaluation)

        if result.success:
            logger.info(
                "[agent_interaction] 手动触发: %s→%s type=%s reason=%s",
                initiator_id,
                target_id,
                interaction_type,
                reason[:80],
            )

        return result
