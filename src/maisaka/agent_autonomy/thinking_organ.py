"""思维器官——以角色内部视角运行思考管道。

每个智能体拥有自己的 ThinkingOrgan 实例，
Orchestrator 只协调"谁在思考"，不关心"怎么思考"。
"""

from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Any, Callable

from src.common.logger import get_logger
from src.core.types import ThinkAction, ThinkContext, ThinkResult
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

logger = get_logger("agent_autonomy.thinking_organ")

MAX_INTERNAL_ROUNDS = 10
SIMILARITY_THRESHOLD = 0.9


class ThinkingOrgan:
    """思维器官——以角色内部视角运行 Planner。

    满足 src.core.protocols.ThinkingOrgan Protocol。

    两种运行模式：
    1. 完整模式（chat_loop_service + tool_registry 注入）：支持工具循环、上下文管理
    2. 简化模式（无注入）：仅支持单次 LLM 调用，用于插话/提醒等轻量场景
    """

    def __init__(
        self,
        agent_id: str,
        prompt_builder: EmbodiedPlannerPromptBuilder,
        chat_loop_service: Any | None = None,
        tool_registry: Any | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._prompt_builder = prompt_builder
        self._chat_loop_service = chat_loop_service
        self._tool_registry = tool_registry
        self._autonomy_logger = AutonomyLogger.get()
        self._discovered_tools: list[str] = []
        self._last_reasoning_content: str = ""
        self._chat_history: list[Any] = []

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_degraded(self) -> bool:
        return self._prompt_builder.is_degraded

    @property
    def has_full_capabilities(self) -> bool:
        """是否具备完整能力（工具循环 + 上下文管理）。"""
        return self._chat_loop_service is not None and self._tool_registry is not None

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
        """执行一次思考——基于消息上下文产生回复。"""
        start_ms = time.time() * 1000
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            f"开始思考(trigger={context.trigger_reason})",
        )

        try:
            if self.has_full_capabilities:
                result = await self._think_with_tools(context, request_kind="planner")
                result.thinking_time_ms = int(time.time() * 1000 - start_ms)
                return result
            return await self._think_simple(context)
        except Exception as exc:
            elapsed = int(time.time() * 1000 - start_ms)
            logger.error(f"[thinking_organ] 思考异常: agent={self._agent_id} error={exc}")
            return ThinkResult(
                action=ThinkAction.ERROR,
                error_message=str(exc),
                thinking_time_ms=elapsed,
            )

    async def think_proactive(self, reason: str, context: ThinkContext) -> ThinkResult:
        """执行一次主动思考——无外部消息触发。"""
        start_ms = time.time() * 1000
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            f"主动思考(reason={reason})",
        )

        try:
            if self.has_full_capabilities:
                result = await self._think_with_tools(context, request_kind="proactive", reason=reason)
                result.thinking_time_ms = int(time.time() * 1000 - start_ms)
                return result
            return await self._think_proactive_simple(reason, context)
        except Exception as exc:
            elapsed = int(time.time() * 1000 - start_ms)
            logger.error(f"[thinking_organ] 主动思考异常: agent={self._agent_id} error={exc}")
            return ThinkResult(
                action=ThinkAction.ERROR,
                error_message=str(exc),
                thinking_time_ms=elapsed,
            )

    # ========================================================================
    # 完整模式：工具循环
    # ========================================================================

    async def _think_with_tools(
        self,
        context: ThinkContext,
        *,
        request_kind: str = "planner",
        reason: str | None = None,
    ) -> ThinkResult:
        """工具循环核心 — 多轮 LLM 调用 + 工具执行。"""
        from src.core.tooling import ToolInvocation, ToolExecutionContext, ToolAvailabilityContext

        total_tool_calls = 0
        rounds = 0

        tool_definitions = await self._build_tool_definitions(context)
        injected_messages = self._build_injected_messages(context)

        for round_idx in range(MAX_INTERNAL_ROUNDS):
            rounds = round_idx + 1

            try:
                response = await self._chat_loop_service.chat_loop_step(
                    chat_history=self._chat_history,
                    injected_user_messages=injected_messages or None,
                    request_kind=request_kind,
                    tool_definitions=tool_definitions if tool_definitions else None,
                )
            except Exception as exc:
                logger.error(f"[thinking_organ] LLM 调用失败: agent={self._agent_id} round={round_idx} error={exc}")
                return ThinkResult(
                    action=ThinkAction.ERROR,
                    error_message=str(exc),
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )

            reasoning_content = getattr(response, "reasoning", "") or getattr(response, "content", "") or ""

            if self._should_replace_reasoning(reasoning_content):
                reasoning_content = "我应该根据我上面思考的内容进行反思..."
            self._last_reasoning_content = reasoning_content

            if response.raw_message is not None:
                self._chat_history.append(response.raw_message)

            if not response.tool_calls:
                content = (response.content or "").strip()
                action = ThinkAction.REPLY if content else ThinkAction.SILENT
                self._autonomy_logger.log(
                    self._agent_id,
                    AutonomyEventType.THINKING,
                    f"思考完成(无工具调用, {rounds}轮, {total_tool_calls}次工具, action={action.value})",
                )
                return ThinkResult(
                    action=action,
                    text=content,
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )

            total_tool_calls += len(response.tool_calls)

            should_pause, pause_tool_name, _summaries = await self._handle_tool_calls(
                response.tool_calls,
                reasoning_content,
                context,
            )

            if should_pause:
                if pause_tool_name == "wait":
                    wait_secs = 60.0
                    for tc in response.tool_calls:
                        if tc.func_name == "wait" and isinstance(tc.args, dict):
                            wait_secs = float(tc.args.get("seconds", tc.args.get("duration", 60)))
                    self._autonomy_logger.log(
                        self._agent_id,
                        AutonomyEventType.THINKING,
                        f"等待工具暂停: {wait_secs}s",
                    )
                    return ThinkResult(
                        action=ThinkAction.WAIT,
                        tool_calls_count=total_tool_calls,
                        rounds=rounds,
                        wait_seconds=wait_secs,
                    )
                self._autonomy_logger.log(
                    self._agent_id,
                    AutonomyEventType.THINKING,
                    f"工具暂停: {pause_tool_name}",
                )
                return ThinkResult(
                    action=ThinkAction.SILENT,
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )

            injected_messages = []

        logger.warning(f"[thinking_organ] 工具循环达到上限: agent={self._agent_id} rounds={rounds}")
        return ThinkResult(
            action=ThinkAction.SILENT,
            tool_calls_count=total_tool_calls,
            rounds=rounds,
        )

    async def _handle_tool_calls(
        self,
        tool_calls: list[Any],
        latest_thought: str,
        context: ThinkContext,
    ) -> tuple[bool, str, list[str]]:
        """执行工具调用。返回 (should_pause, pause_tool_name, summaries)。"""
        from src.core.tooling import ToolInvocation, ToolExecutionContext, ToolAvailabilityContext

        if self._tool_registry is None:
            return False, "", []

        summaries: list[str] = []
        availability_context = ToolAvailabilityContext(
            session_id=context.session_id,
            stream_id=context.session_id,
            is_group_chat=context.is_group_chat,
        )
        tool_specs = await self._tool_registry.list_tools(availability_context)
        tool_spec_map = {spec.name: spec for spec in tool_specs}

        for tool_call in tool_calls:
            invocation = ToolInvocation(
                tool_name=tool_call.func_name,
                arguments=dict(tool_call.args or {}),
                call_id=tool_call.call_id,
                session_id=context.session_id,
                stream_id=context.session_id,
                reasoning=latest_thought,
            )

            execution_context = ToolExecutionContext(
                session_id=context.session_id,
                stream_id=context.session_id,
                reasoning=latest_thought,
                is_group_chat=context.is_group_chat,
            )

            tool_started_at = time.time()
            try:
                result = await self._tool_registry.invoke(invocation, execution_context)
            except Exception as exc:
                from src.core.tooling import ToolExecutionResult
                result = ToolExecutionResult(
                    tool_name=invocation.tool_name,
                    success=False,
                    error_message=str(exc),
                )

            tool_duration_ms = (time.time() - tool_started_at) * 1000

            history_content = result.get_history_content() if hasattr(result, "get_history_content") else (result.content or result.error_message)
            if history_content:
                summaries.append(f"[{invocation.tool_name}] {history_content[:200]}")

            if bool(result.metadata.get("wait_rest", False)):
                return True, "wait_rest", summaries
            if bool(result.metadata.get("pause_execution", False)):
                return True, invocation.tool_name, summaries

        return False, "", summaries

    async def _build_tool_definitions(self, context: ThinkContext) -> list[dict[str, Any]]:
        """构建工具定义 — visible/deferred 分离。"""
        if self._tool_registry is None:
            return []

        from src.core.tooling import ToolAvailabilityContext

        availability_context = ToolAvailabilityContext(
            session_id=context.session_id,
            stream_id=context.session_id,
            is_group_chat=context.is_group_chat,
        )
        tool_specs = await self._tool_registry.list_tools(availability_context)

        visible: list[Any] = []
        deferred: list[Any] = []

        for spec in tool_specs:
            visibility = str(spec.metadata.get("visibility", "") or "").strip().lower()
            if spec.provider_name == "maisaka_builtin":
                from src.maisaka.builtin_tool import get_builtin_tool_visibility, is_builtin_tool_in_action_stage
                if not is_builtin_tool_in_action_stage(spec):
                    continue
                bv = get_builtin_tool_visibility(spec)
                if bv == "visible":
                    visible.append(spec)
                elif bv == "deferred":
                    deferred.append(spec)
                continue
            if visibility == "visible":
                visible.append(spec)
                continue
            deferred.append(spec)

        discovered_names = set(context.discovered_tools) | set(self._discovered_tools)
        discovered_specs = [s for s in deferred if s.name in discovered_names]
        all_visible = [*visible, *discovered_specs]

        self._discovered_tools = list(set(self._discovered_tools) | discovered_names)

        return [spec.to_llm_definition() for spec in all_visible if hasattr(spec, "to_llm_definition")]

    def _build_injected_messages(self, context: ThinkContext) -> list[str]:
        """构建上下文注入消息。"""
        parts: list[str] = []

        if context.inner_voice_text:
            parts.append(f"内心声音：{context.inner_voice_text}")
        if context.emotion_state_text:
            parts.append(f"当前情绪：{context.emotion_state_text}")
        if context.relationship_text:
            parts.append(f"关系描述：{context.relationship_text}")
        if context.memory_snippets:
            parts.append("相关记忆：\n" + "\n".join(f"- {s}" for s in context.memory_snippets))
        if context.cohabitant_summary:
            parts.append(f"共居状态：{context.cohabitant_summary}")

        return parts

    def _should_replace_reasoning(self, content: str) -> bool:
        """思考相似度检测 — 防止死循环。"""
        if not content or not self._last_reasoning_content:
            return False
        ratio = SequenceMatcher(None, self._last_reasoning_content, content).ratio()
        return ratio > SIMILARITY_THRESHOLD

    # ========================================================================
    # 简化模式：单次 LLM 调用（插话/提醒 fallback）
    # ========================================================================

    async def _think_simple(self, context: ThinkContext) -> ThinkResult:
        """简化模式思考 — 无工具循环。"""
        start_ms = time.time() * 1000

        system_prompt = self.build_system_prompt()
        personality_prompt = self.build_personality_prompt()

        user_parts = []
        for msg in context.messages:
            if msg.plain_text:
                prefix = f"[{msg.sender_name}] " if msg.sender_name else ""
                user_parts.append(f"{prefix}{msg.plain_text}")

        context_parts = self._build_injected_messages(context)

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

    async def _think_proactive_simple(self, reason: str, context: ThinkContext) -> ThinkResult:
        """简化模式主动思考 — 无工具循环。"""
        start_ms = time.time() * 1000

        system_prompt = self.build_system_prompt()
        personality_prompt = self.build_personality_prompt()

        context_parts = self._build_injected_messages(context)

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

    async def _call_llm(self, system_prompt: str, personality_prompt: str, user_text: str) -> str | None:
        """调用 LLM 产生回复（简化模式）。"""
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
