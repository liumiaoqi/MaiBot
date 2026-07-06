"""内心独白引擎。

基于智能体性格+情绪+记忆生成内心独白内容，
写入微小自我情绪影响，持久化独白事件。
内心独白不触发任何外部行为。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass


from src.common.database.database import get_db_session
from src.common.database.database_model import InnerMonologueEvent as MonologueTable
from src.maisaka.agent.config import AgentConfig
from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
from src.maisaka.agent_interaction.monologue_trigger import MonologueTrigger

logger = logging.getLogger(__name__)


def _generate_monologue_id(agent_id: str) -> str:
    ts = format(int(time.time()), "x")
    return f"im:{agent_id}:{ts}"


# 情绪→内心独白模板
_EMOTION_TEMPLATES: dict[str, str] = {
    "lonely": "{name}默默地想着……好安静，要是有人在就好了",
    "happy": "{name}默默地想着……今天心情不错",
    "sad": "{name}默默地想着……心里有点堵",
    "anxious": "{name}默默地想着……总觉得有什么不对",
    "angry": "{name}默默地想着……真让人火大",
    "excited": "{name}默默地想着……好兴奋！",
    "calm": "{name}默默地想着……",
}

# 自我情绪影响量（微小变化+2~5）
_SELF_EMOTION_EFFECTS: dict[str, float] = {
    "lonely": 3.0,
    "happy": 2.0,
    "sad": 4.0,
    "anxious": 3.5,
    "angry": 4.0,
    "excited": 2.5,
    "calm": 1.0,
}


@dataclass
class MonologueResult:
    """内心独白执行结果。"""

    success: bool = False
    monologue_id: str = ""
    content: str = ""
    self_emotion_effect: dict[str, float] | None = None
    error: str = ""


class MonologueEngine:
    """内心独白引擎。

    核心流程：
    1. 获取情绪状态和智能体配置
    2. 生成内心独白内容（LLM优先，模板降级）
    3. 写入微小自我情绪影响
    4. 持久化独白事件
    """

    def __init__(
        self,
        emotion_registry: AgentEmotionManagerRegistry,
        monologue_trigger: MonologueTrigger,
        memory_adapter: AgentMemoryAdapter | None = None,
    ) -> None:
        self._emotion_registry = emotion_registry
        self._monologue_trigger = monologue_trigger
        self._memory_adapter = memory_adapter
        self._config_registry = AgentConfigRegistry.get_instance()

    async def execute(self, agent_id: str) -> MonologueResult:
        """执行内心独白。"""
        # 获取情绪状态
        emotion_state = self._emotion_registry.get_emotion_state(agent_id)
        idle_minutes = self._monologue_trigger.get_idle_minutes(agent_id)

        if not self._monologue_trigger.should_trigger(agent_id, idle_minutes, emotion_state):
            return MonologueResult()

        # 获取智能体配置
        try:
            config = self._config_registry.get_agent(agent_id)
        except Exception:
            return MonologueResult(error=f"无法获取智能体配置: {agent_id}")

        # 生成内心独白内容
        content = await self._generate_content(agent_id, config, emotion_state)

        # 计算自我情绪影响
        dominant = emotion_state.dominant_emotion
        effect_delta = _SELF_EMOTION_EFFECTS.get(dominant, 2.0)
        self_effect = {dominant: effect_delta}

        # 写入情绪变化
        self._emotion_registry.apply_trigger(agent_id, dominant, effect_delta)

        # 持久化独白事件
        monologue_id = _generate_monologue_id(agent_id)
        emotion_snapshot = json.dumps(emotion_state.emotions, ensure_ascii=False)

        try:
            row = MonologueTable(
                monologue_id=monologue_id,
                agent_id=agent_id,
                emotion_snapshot=emotion_snapshot,
                content=content[:1000],
                self_emotion_effect=json.dumps(self_effect, ensure_ascii=False),
            )
            with get_db_session() as session:
                session.add(row)
                session.commit()
        except Exception as e:
            logger.error("[agent_interaction] 内心独白持久化失败: %s", e)
            return MonologueResult(error=str(e))

        # 记录独白触发
        self._monologue_trigger.record_monologue(agent_id)

        logger.info(
            "[agent_interaction] 内心独白: %s emotion=%s content=%s",
            agent_id,
            dominant,
            content[:60],
        )

        return MonologueResult(
            success=True,
            monologue_id=monologue_id,
            content=content,
            self_emotion_effect=self_effect,
        )

    async def _generate_content(
        self, agent_id: str, config: AgentConfig, emotion_state: EmotionState
    ) -> str:
        """生成内心独白内容。"""
        dominant = emotion_state.dominant_emotion

        display_name = config.display_name or agent_id

        # 尝试从记忆中获取上下文
        memory_context = ""
        if self._memory_adapter is not None:
            try:
                result = await self._memory_adapter.search_interaction_memory(
                    agent_id, agent_id, query="最近的感受", limit=3
                )
                if result.success and result.hits:
                    memory_context = result.hits[0].content[:100]
            except Exception:
                pass

        # 使用模板生成（LLM生成可后续扩展）
        template = _EMOTION_TEMPLATES.get(dominant, _EMOTION_TEMPLATES["calm"])
        content = template.format(name=display_name)

        if memory_context:
            content = f"{content}（想起了{memory_context[:50]}）"

        return content