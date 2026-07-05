"""行为意图引擎——智能体基于内在需求、情绪、对话上下文自主产生行为意图。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.inner_need import InnerNeed, InnerNeedEngine

logger = get_logger("agent_autonomy.behavior_intent")


@dataclass
class BehaviorIntent:
    """行为意图。"""

    intent_type: str = ""
    intent_strength: float = 0.0
    intent_source: str = ""
    source_description: str = ""

    def is_valid(self) -> bool:
        return self.intent_strength > 0 and bool(self.source_description)


class BaseIntentSource(ABC):
    """行为意图来源基类。"""

    @abstractmethod
    async def produce(
        self,
        agent_id: str,
        inner_needs: list[InnerNeed],
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
    ) -> list[BehaviorIntent]:
        """产生行为意图。"""
        ...


class InnerNeedIntentSource(BaseIntentSource):
    """内在需求→行为意图。"""

    async def produce(
        self,
        agent_id: str,
        inner_needs: list[InnerNeed],
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
    ) -> list[BehaviorIntent]:
        intents: list[BehaviorIntent] = []

        has_conversation = bool(conversation_context)

        for need in inner_needs:
            if need.need_type in ("companionship", "sharing", "night_chat", "boredom"):
                if has_conversation:
                    intents.append(BehaviorIntent(
                        intent_type="want_to_speak",
                        intent_strength=need.strength * 0.8,
                        intent_source="inner_need_driven",
                        source_description=need.description,
                    ))
            elif need.need_type in ("missing", "comfort"):
                if has_conversation:
                    intents.append(BehaviorIntent(
                        intent_type="want_to_interject",
                        intent_strength=need.strength * 0.6,
                        intent_source="inner_need_driven",
                        source_description=need.description,
                    ))

        return intents


class EmotionIntentSource(BaseIntentSource):
    """情绪→行为意图。"""

    async def produce(
        self,
        agent_id: str,
        inner_needs: list[InnerNeed],
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
    ) -> list[BehaviorIntent]:
        intents: list[BehaviorIntent] = []
        if emotion_state is None:
            return intents

        dominant = emotion_state.dominant_emotion
        intensity = emotion_state.get_dominant_intensity()

        if dominant in ("excited", "happy") and intensity >= 60:
            intents.append(BehaviorIntent(
                intent_type="want_to_speak",
                intent_strength=intensity * 0.7,
                intent_source="emotion_driven",
                source_description=f"情绪{dominant}(强度{intensity:.0f})驱动发言",
            ))

        return intents


class TopicRelevanceIntentSource(BaseIntentSource):
    """话题相关性→行为意图。"""

    async def produce(
        self,
        agent_id: str,
        inner_needs: list[InnerNeed],
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
    ) -> list[BehaviorIntent]:
        intents: list[BehaviorIntent] = []
        if not conversation_context:
            return intents

        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if not registry.has_agent(agent_id):
                return intents
            agent_config = registry.get_agent(agent_id)
            keywords = getattr(agent_config, "attention_keywords", [])
            if not keywords:
                return intents

            recent_text = ""
            for msg in conversation_context[-10:]:
                content = getattr(msg, "content", "") or ""
                recent_text += content.lower() + " "

            matched_keywords = [kw for kw in keywords if kw.lower() in recent_text]
            if matched_keywords:
                strength = min(30.0 + len(matched_keywords) * 15.0, 80.0)
                intents.append(BehaviorIntent(
                    intent_type="want_to_interject",
                    intent_strength=strength,
                    intent_source="topic_relevance_driven",
                    source_description=f"话题相关：{', '.join(matched_keywords)}",
                ))
        except Exception:
            pass

        return intents


class RelationshipIntentSource(BaseIntentSource):
    """关系→行为意图。"""

    async def produce(
        self,
        agent_id: str,
        inner_needs: list[InnerNeed],
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
    ) -> list[BehaviorIntent]:
        intents: list[BehaviorIntent] = []
        if not conversation_context:
            return intents

        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if not registry.has_agent(agent_id):
                return intents
            agent_config = registry.get_agent(agent_id)
            internal_rels = getattr(agent_config, "internal_relationships", [])
            if not internal_rels:
                return intents

            recent_text = ""
            for msg in conversation_context[-10:]:
                content = getattr(msg, "content", "") or ""
                recent_text += content.lower() + " "

            for rel in internal_rels:
                target_name = getattr(rel, "target_agent_id", "")
                if target_name and target_name.lower() in recent_text:
                    intents.append(BehaviorIntent(
                        intent_type="want_to_interject",
                        intent_strength=50.0,
                        intent_source="relationship_driven",
                        source_description=f"对话提及{target_name}，关系亲密",
                    ))
        except Exception:
            pass

        return intents


class InteractionSignalIntentSource(BaseIntentSource):
    """交互信号→行为意图。"""

    async def produce(
        self,
        agent_id: str,
        inner_needs: list[InnerNeed],
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
    ) -> list[BehaviorIntent]:
        intents: list[BehaviorIntent] = []
        if not interaction_signals:
            return intents

        try:
            from src.config.config import global_config

            bonus = global_config.agent_autonomy.interaction_signal_intent_bonus
        except Exception:
            bonus = 40.0

        for signal in interaction_signals:
            target_agent_id = getattr(signal, "target_agent_id", None)
            if target_agent_id == agent_id:
                trigger_reason = getattr(signal, "trigger_reason", "交互信号")
                intents.append(BehaviorIntent(
                    intent_type="want_to_interject",
                    intent_strength=bonus,
                    intent_source="interaction_signal_driven",
                    source_description=f"交互信号：{trigger_reason}",
                ))

        return intents


class BehaviorIntentEngine:
    """行为意图引擎——智能体自主产生行为意图的核心。

    支持动态注册意图类型和意图来源。
    """

    # 内置意图类型
    BUILTIN_INTENT_TYPES = {"want_to_speak", "want_to_interject"}

    def __init__(self, inner_need_engine: InnerNeedEngine) -> None:
        self._inner_need_engine = inner_need_engine
        self._sources: dict[str, BaseIntentSource] = {}
        self._intent_types: set[str] = set(self.BUILTIN_INTENT_TYPES)
        self._autonomy_logger = AutonomyLogger.get()

    def register_source(self, source_type: str, source: BaseIntentSource) -> None:
        """注册行为意图来源。"""
        self._sources[source_type] = source

    def register_intent_type(self, intent_type: str) -> None:
        """注册自定义意图类型。"""
        self._intent_types.add(intent_type)

    def get_registered_intent_types(self) -> set[str]:
        """获取所有已注册的意图类型。"""
        return set(self._intent_types)

    def is_valid_intent_type(self, intent_type: str) -> bool:
        """检查意图类型是否已注册。"""
        return intent_type in self._intent_types

    async def produce_intents(
        self,
        agent_id: str,
        emotion_state: Any | None = None,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
        intent_threshold: float = 0.0,
    ) -> list[BehaviorIntent]:
        """自主产生行为意图。"""
        inner_needs = await self._inner_need_engine.evaluate(
            agent_id=agent_id,
            emotion_state=emotion_state,
            memory_context=memory_context,
            time_context=time_context,
        )

        all_intents: list[BehaviorIntent] = []
        for source_type, source in self._sources.items():
            try:
                intents = await source.produce(
                    agent_id=agent_id,
                    inner_needs=inner_needs,
                    emotion_state=emotion_state,
                    conversation_context=conversation_context,
                    interaction_signals=interaction_signals,
                )
                all_intents.extend(intents)
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 行为意图产生异常: "
                    f"source={source_type} agent={agent_id} error={exc}"
                )

        # 过滤低强度意图
        valid_intents = [
            i for i in all_intents
            if i.is_valid() and i.intent_strength >= intent_threshold
        ]

        # 去重：同一 intent_type 只保留强度最高的
        best_by_type: dict[str, BehaviorIntent] = {}
        for intent in valid_intents:
            key = intent.intent_type
            if key not in best_by_type or intent.intent_strength > best_by_type[key].intent_strength:
                best_by_type[key] = intent

        result = sorted(best_by_type.values(), key=lambda i: i.intent_strength, reverse=True)

        for intent in result:
            logger.debug(
                f"[agent_autonomy] agent={agent_id} intent={intent.intent_type} "
                f"strength={intent.intent_strength:.1f} source={intent.intent_source}"
            )

        if result:
            intent_summary = ", ".join(
                f"{i.intent_type}({i.intent_strength:.1f})" for i in result[:3]
            )
            self._autonomy_logger.log(
                agent_id,
                AutonomyEventType.BEHAVIOR_INTENT,
                f"产生意图: {intent_summary}",
            )

        return result