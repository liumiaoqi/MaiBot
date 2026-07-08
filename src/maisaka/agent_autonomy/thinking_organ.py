"""思维器官——以角色内部视角运行思考管道。

每个智能体拥有自己的 ThinkingOrgan 实例，
Orchestrator 只协调"谁在思考"，不关心"怎么思考"。
"""

from __future__ import annotations

import time

from src.common.logger import get_logger
from src.core.types import ThinkAction, ThinkContext, ThinkResult
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

logger = get_logger("agent_autonomy.thinking_organ")


class ThinkingOrgan:
    """思维器官——以角色内部视角运行 Planner。

    满足 src.core.protocols.ThinkingOrgan Protocol。
    """

    def __init__(self, agent_id: str, prompt_builder: EmbodiedPlannerPromptBuilder) -> None:
        self._agent_id = agent_id
        self._prompt_builder = prompt_builder
        self._autonomy_logger = AutonomyLogger.get()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_degraded(self) -> bool:
        return self._prompt_builder.is_degraded

    def build_system_prompt(self, tools_section: str = "") -> str:
        """构建角色化系统提示词。"""
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            "构建角色化系统提示词",
            level="debug",
        )
        return self._prompt_builder.build_system_prompt(tools_section)

    def build_personality_prompt(self) -> str:
        """构建角色化人格提示词。"""
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            "开始角色化思考",
        )
        return self._prompt_builder.build_personality_prompt()

    def get_prompt_template_name(self) -> str:
        """获取当前使用的提示词模板名。"""
        return self._prompt_builder.get_prompt_template_name()

    async def think(self, context: ThinkContext) -> ThinkResult:
        """执行一次思考——基于消息上下文产生回复。

        Args:
            context: 思考上下文（消息序列、情绪状态、记忆片段）

        Returns:
            ThinkResult（回复文本、工具调用、或不回复）
        """
        start_ms = time.time() * 1000
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            f"开始思考(trigger={context.trigger_reason})",
        )

        try:
            system_prompt = self.build_system_prompt()
            personality_prompt = self.build_personality_prompt()

            user_parts = []
            for msg in context.messages:
                if msg.plain_text:
                    prefix = f"[{msg.sender_name}] " if msg.sender_name else ""
                    user_parts.append(f"{prefix}{msg.plain_text}")

            context_parts = []
            if context.inner_voice_text:
                context_parts.append(f"内心声音：{context.inner_voice_text}")
            if context.emotion_state_text:
                context_parts.append(f"当前情绪：{context.emotion_state_text}")
            if context.relationship_text:
                context_parts.append(f"关系描述：{context.relationship_text}")
            if context.memory_snippets:
                context_parts.append("相关记忆：\n" + "\n".join(f"- {s}" for s in context.memory_snippets))
            if context.cohabitant_summary:
                context_parts.append(f"共居状态：{context.cohabitant_summary}")

            user_text = "\n".join(user_parts)
            if context_parts:
                user_text += "\n\n" + "\n".join(context_parts)

            if not user_text.strip():
                return ThinkResult(action=ThinkAction.SILENT, thinking_time_ms=int(time.time() * 1000 - start_ms))

            reply_text = await self._call_llm(system_prompt, personality_prompt, user_text)

            elapsed = int(time.time() * 1000 - start_ms)
            if not reply_text or not reply_text.strip():
                return ThinkResult(action=ThinkAction.SILENT, thinking_time_ms=elapsed)

            self._autonomy_logger.log(
                self._agent_id,
                AutonomyEventType.THINKING,
                f"思考完成({len(reply_text)}字, {elapsed}ms)",
            )
            return ThinkResult(
                action=ThinkAction.REPLY,
                text=reply_text.strip(),
                thinking_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = int(time.time() * 1000 - start_ms)
            logger.error(f"[thinking_organ] 思考异常: agent={self._agent_id} error={exc}")
            return ThinkResult(
                action=ThinkAction.ERROR,
                error_message=str(exc),
                thinking_time_ms=elapsed,
            )

    async def think_proactive(self, reason: str, context: ThinkContext) -> ThinkResult:
        """执行一次主动思考——无外部消息触发。

        Args:
            reason: 主动思考原因（inner_need / reminder / butler_interjection）
            context: 思考上下文

        Returns:
            ThinkResult
        """
        start_ms = time.time() * 1000
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            f"主动思考(reason={reason})",
        )

        try:
            system_prompt = self.build_system_prompt()
            personality_prompt = self.build_personality_prompt()

            context_parts = []
            if context.inner_voice_text:
                context_parts.append(f"内心声音：{context.inner_voice_text}")
            if context.emotion_state_text:
                context_parts.append(f"当前情绪：{context.emotion_state_text}")
            if context.relationship_text:
                context_parts.append(f"关系描述：{context.relationship_text}")
            if context.memory_snippets:
                context_parts.append("相关记忆：\n" + "\n".join(f"- {s}" for s in context.memory_snippets))
            if context.cohabitant_summary:
                context_parts.append(f"共居状态：{context.cohabitant_summary}")

            reason_map = {
                "inner_need": "你内心产生了想要说话的冲动",
                "reminder": "到了该提醒/关心的时候",
                "butler_interjection": "管家协调你插话",
            }
            reason_text = reason_map.get(reason, reason)
            user_text = f"[主动思考触发] {reason_text}"
            if context_parts:
                user_text += "\n\n" + "\n".join(context_parts)
            for msg in context.messages:
                if msg.plain_text:
                    prefix = f"[{msg.sender_name}] " if msg.sender_name else ""
                    user_text += f"\n{prefix}{msg.plain_text}"

            reply_text = await self._call_llm(system_prompt, personality_prompt, user_text)

            elapsed = int(time.time() * 1000 - start_ms)
            if not reply_text or not reply_text.strip():
                return ThinkResult(action=ThinkAction.SILENT, thinking_time_ms=elapsed)

            self._autonomy_logger.log(
                self._agent_id,
                AutonomyEventType.THINKING,
                f"主动思考完成({len(reply_text)}字, {elapsed}ms)",
            )
            return ThinkResult(
                action=ThinkAction.REPLY,
                text=reply_text.strip(),
                thinking_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = int(time.time() * 1000 - start_ms)
            logger.error(f"[thinking_organ] 主动思考异常: agent={self._agent_id} error={exc}")
            return ThinkResult(
                action=ThinkAction.ERROR,
                error_message=str(exc),
                thinking_time_ms=elapsed,
            )

    async def _call_llm(self, system_prompt: str, personality_prompt: str, user_text: str) -> str | None:
        """调用 LLM 产生回复。"""
        from src.llm_models.payload_content.message import MessageBuilder, RoleType
        from src.common.data_models.llm_service_data_models import LLMGenerationOptions
        from src.services.llm_service import LLMServiceClient

        client = LLMServiceClient(task_name="replyer", request_type="thinking_organ")

        messages = []
        messages.append(MessageBuilder().set_role(RoleType.System).add_text_part(system_prompt).build())
        if personality_prompt:
            messages.append(MessageBuilder().set_role(RoleType.System).add_text_part(personality_prompt).build())
        messages.append(MessageBuilder().set_role(RoleType.User).add_text_part(user_text).build())

        def message_factory(_client):
            return messages

        result = await client.generate_response_with_messages(
            message_factory=message_factory,
            options=LLMGenerationOptions(temperature=0.7),
        )
        return result.response
