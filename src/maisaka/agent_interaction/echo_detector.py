"""回声检测器。

当交互导致情绪剧烈变化时，向关联智能体传播回声信号。
回声链最大深度3层，每层影响量衰减，环路检测截断。
"""

from __future__ import annotations

import asyncio
import logging


from src.maisaka.agent_interaction.engine import InteractionResult
from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation

logger = logging.getLogger(__name__)

_ECHO_EMOTION_THRESHOLD = 20.0
_ECHO_TIMEOUT_SECONDS = 30


class EchoDetector:
    """回声检测器。

    核心逻辑：
    1. 检查交互结果中是否有单一情绪变化量 > 20
    2. 检查回声深度 < echo_max_depth
    3. 检查传播链中无重复智能体（环路检测）
    4. 通过检查后构建回声触发决策
    """

    def __init__(
        self,
        echo_max_depth: int = 3,
        echo_decay_ratio: float = 0.5,
    ) -> None:
        self._max_depth = echo_max_depth
        self._decay_ratio = echo_decay_ratio

    async def check_and_propagate(
        self,
        result: InteractionResult,
        evaluation: TriggerEvaluation,
    ) -> None:
        """检查交互结果是否产生回声，并传播。"""
        if not result.success:
            return

        # 检查是否有情绪变化超过阈值
        has_echo = False
        for effect_dict in result.emotion_effects.values():
            for delta in effect_dict.values():
                if abs(delta) > _ECHO_EMOTION_THRESHOLD:
                    has_echo = True
                    break
            if has_echo:
                break

        if not has_echo:
            return

        # 检查回声深度
        current_depth = evaluation.metadata.get("echo_depth", 0)
        if current_depth >= self._max_depth:
            logger.debug(
                "[agent_interaction] 回声深度 %d 达到上限 %d，截断",
                current_depth,
                self._max_depth,
            )
            return

        # 构建传播链
        chain = evaluation.metadata.get("echo_chain", [])
        if isinstance(chain, str):
            chain = []
        chain = list(chain)
        chain.append(evaluation.initiator_agent_id)

        # 环路检测
        if self._detect_loop(chain, evaluation.target_agent_id):
            logger.debug(
                "[agent_interaction] 回声环路检测: %s 已在链中",
                evaluation.target_agent_id,
            )
            return

        # 构建回声触发决策
        echo_evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=evaluation.trigger_probability * self._decay_ratio,
            initiator_agent_id=evaluation.target_agent_id,
            target_agent_id=evaluation.initiator_agent_id,
            interaction_type=evaluation.interaction_type,
            trigger_reason=f"交互回声：{evaluation.trigger_reason}",
            metadata={
                "echo_depth": current_depth + 1,
                "echo_parent_event_id": result.event_id,
                "echo_chain": chain + [evaluation.target_agent_id],
                "original_evaluation": {
                    "initiator": evaluation.initiator_agent_id,
                    "target": evaluation.target_agent_id,
                    "type": evaluation.interaction_type,
                },
            },
        )

        # 超时保护
        try:
            await asyncio.wait_for(
                self._propagate_echo(echo_evaluation),
                timeout=_ECHO_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[agent_interaction] 回声传播超时，强制截断")
        except Exception as e:
            logger.warning("[agent_interaction] 回声传播异常，静默截断: %s", e)

    async def _propagate_echo(self, evaluation: TriggerEvaluation) -> None:
        """传播回声信号（延迟导入避免循环依赖）。"""
        from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
        from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
        from src.maisaka.agent_interaction.event_store import InteractionEventStore
        from src.maisaka.agent_interaction.engine import InteractionEngine

        emotion_registry = AgentEmotionManagerRegistry()
        relationship_manager = AgentRelationshipManager()
        event_store = InteractionEventStore()
        engine = InteractionEngine(
            emotion_registry=emotion_registry,
            relationship_manager=relationship_manager,
            event_store=event_store,
        )

        echo_result = await engine.execute(evaluation)
        if echo_result.success:
            logger.info(
                "[agent_interaction] 回声传播成功: depth=%d %s→%s",
                evaluation.metadata.get("echo_depth", 0),
                evaluation.initiator_agent_id,
                evaluation.target_agent_id,
            )

    @staticmethod
    def _detect_loop(chain: list[str], new_agent_id: str) -> bool:
        """检查传播链中是否已存在新智能体。"""
        return new_agent_id in chain