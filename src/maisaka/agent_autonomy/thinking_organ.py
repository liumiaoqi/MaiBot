"""思维器官——以角色内部视角运行思考管道。

每个智能体拥有自己的 ThinkingOrgan 实例，
Orchestrator 只协调"谁在思考"，不关心"怎么思考"。

思考-行动分离：content = 内心独白（永远不发给用户），reply 工具调用 = 对外回复。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from src.common.logger import get_logger
from src.config.config import global_config
from src.core.types import CycleStatus, SilenceReason, ThinkAction, ThinkContext, ThinkCycleLog, ThinkResult
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

logger = get_logger("agent_autonomy.thinking_organ")

MAX_INTERNAL_ROUNDS = 10
SIMILARITY_THRESHOLD = 0.9


@dataclass(slots=True)
class ToolCycleResult:
    """_handle_tool_calls 的返回值——替代原有 4 元组。"""

    should_pause: bool = False
    pause_tool_name: str = ""
    summaries: list[str] = field(default_factory=list)
    monitor_results: list[dict[str, Any]] = field(default_factory=list)
    reply_detected: bool = False
    reply_text: str = ""
    reply_failed: bool = False


class ThinkingOrgan:
    """思维器官——以角色内部视角运行 Planner。

    满足 src.core.protocols.ThinkingOrgan Protocol。

    所有思考路径统一走工具循环（_think_with_tools），content = 内心独白不发给用户，
    回复必须通过 reply 工具调用。简化模式已废除。
    """

    def __init__(
        self,
        agent_id: str,
        prompt_builder: EmbodiedPlannerPromptBuilder,
        chat_loop_service: Any | None = None,
        tool_registry: Any | None = None,
        chat_loop_adapter: Any | None = None,
    ) -> None:
        if chat_loop_service is None:
            raise ValueError(
                f"ThinkingOrgan(agent={agent_id}) 需要 chat_loop_service，"
                f"简化模式已废除，所有思考路径必须走工具循环"
            )
        if tool_registry is None:
            raise ValueError(
                f"ThinkingOrgan(agent={agent_id}) 需要 tool_registry，"
                f"简化模式已废除，所有思考路径必须走工具循环"
            )
        self._agent_id = agent_id
        self._prompt_builder = prompt_builder
        self._chat_loop_service = chat_loop_service
        self._tool_registry = tool_registry
        self._chat_loop_adapter = chat_loop_adapter
        self._autonomy_logger = AutonomyLogger.get()
        self._discovered_tools: list[str] = []
        self._last_reasoning_content: str = ""

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
        """执行一次思考——基于消息上下文产生回复。"""
        start_ms = time.time() * 1000
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            f"开始思考(trigger={context.trigger_reason})",
        )

        try:
            result = await self._think_with_tools(context, request_kind="planner")
            result.thinking_time_ms = int(time.time() * 1000 - start_ms)
            return result
        except Exception as exc:
            elapsed = int(time.time() * 1000 - start_ms)
            logger.error(f"[thinking_organ] 思考异常: agent={self._agent_id} error={exc}")
            return ThinkResult(
                action=ThinkAction.ERROR,
                error_message=str(exc),
                silence_reason=SilenceReason.ERROR,
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
            result = await self._think_with_tools(context, request_kind="planner", reason=reason)
            result.thinking_time_ms = int(time.time() * 1000 - start_ms)
            return result
        except Exception as exc:
            elapsed = int(time.time() * 1000 - start_ms)
            logger.error(f"[thinking_organ] 主动思考异常: agent={self._agent_id} error={exc}")
            return ThinkResult(
                action=ThinkAction.ERROR,
                error_message=str(exc),
                silence_reason=SilenceReason.ERROR,
                thinking_time_ms=elapsed,
            )

    # ========================================================================
    # 完整模式：工具循环
    # ========================================================================

    def _get_chat_history(self) -> list[Any]:
        """获取当前对话历史——优先从 adapter 获取 runtime 的实时历史。"""
        if self._chat_loop_adapter is not None:
            return self._chat_loop_adapter.chat_history
        return []

    async def _think_with_tools(
        self,
        context: ThinkContext,
        *,
        request_kind: str = "planner",
        reason: str | None = None,
    ) -> ThinkResult:
        """工具循环核心 — 多轮 LLM 调用 + 工具执行。

        思考-行动分离：content = 内心独白（不发给用户），reply 工具调用 = 对外回复。
        """

        total_tool_calls = 0
        rounds = 0
        tool_monitor_results: list[dict[str, Any]] = []
        time_records: dict[str, float] = {}
        last_response = None
        cycle_started_at = time.time()
        tool_calls_made: list[str] = []
        tool_errors: list[str] = []
        has_tool_failure = False

        tool_definitions = await self._build_tool_definitions(context)
        injected_messages = self._build_injected_messages(context)

        for round_idx in range(MAX_INTERNAL_ROUNDS):
            rounds = round_idx + 1
            round_started_at = time.time()

            logger.info(
                f"[thinking_organ] 开始思考: agent={self._agent_id} "
                f"第{rounds}轮 消息数={len(self._get_chat_history())} "
                f"开始时间={round_started_at:.3f}"
            )

            try:
                response = await self._chat_loop_service.chat_loop_step(
                    chat_history=self._get_chat_history(),
                    injected_user_messages=injected_messages or None,
                    request_kind=request_kind,
                    tool_definitions=tool_definitions if tool_definitions else None,
                    system_prompt=self.build_system_prompt(),
                )
            except Exception as exc:
                logger.error(f"[thinking_organ] LLM 调用失败: agent={self._agent_id} round={round_idx} error={exc}")
                elapsed_ms = int((time.time() - cycle_started_at) * 1000)
                result = ThinkResult(
                    action=ThinkAction.ERROR,
                    error_message=str(exc),
                    silence_reason=SilenceReason.ERROR,
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )
                self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms, str(exc))
                return result

            last_response = response

            time_records["planner"] = time.time() - cycle_started_at

            self._save_prompt_preview(response, context, request_kind, round_idx)

            reasoning_content = getattr(response, "reasoning", "") or getattr(response, "content", "") or ""

            if self._should_replace_reasoning(reasoning_content):
                logger.info(
                    f"[thinking_organ] 当前思考与上一轮过于相似，已替换为重新思考提示: "
                    f"agent={self._agent_id} round={rounds}"
                )
                reasoning_content = "我应该根据我上面思考的内容进行反思..."
            self._last_reasoning_content = reasoning_content

            content = (response.content or "").strip()

            # 思考-行动分离核心：无 tool_calls 时 content 永远不作为回复
            if not response.tool_calls:
                silence_reason = self._determine_silence_reason(
                    has_tool_failure=has_tool_failure,
                    has_content=bool(content),
                    reached_max_cycles=False,
                )
                thought_summary = content[:100] if content else ""
                self._autonomy_logger.log(
                    self._agent_id,
                    AutonomyEventType.THINKING,
                    f"思考完成(无工具调用, {rounds}轮, {total_tool_calls}次工具, "
                    f"silence_reason={silence_reason.value})",
                )
                await self._emit_finalized(
                    response=response,
                    context=context,
                    tool_monitor_results=tool_monitor_results,
                    time_records=time_records,
                    end_reason="silent",
                    rounds=rounds,
                    total_tool_calls=total_tool_calls,
                )
                elapsed_ms = int((time.time() - cycle_started_at) * 1000)
                result = ThinkResult(
                    action=ThinkAction.SILENT,
                    silence_reason=silence_reason,
                    thought_summary=thought_summary,
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )
                self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms)
                return result

            total_tool_calls += len(response.tool_calls)

            for _, tc in enumerate(response.tool_calls, 1):
                logger.info(
                    f"[thinking_organ] [推理中工具调用] 第{rounds}轮: "
                    f"工具={tc.func_name} 调用ID={tc.call_id} "
                    f"agent={self._agent_id}"
                )

            cycle_result = await self._handle_tool_calls(
                response.tool_calls,
                reasoning_content,
                context,
            )
            tool_monitor_results.extend(cycle_result.monitor_results)
            tool_calls_made.extend(tc.func_name for tc in response.tool_calls)
            if cycle_result.reply_failed:
                tool_errors.append("reply: 执行失败")
                has_tool_failure = True
            time_records["tool_calls"] = sum(
                r.get("duration_ms", 0) for r in tool_monitor_results
            ) / 1000

            # reply 工具调用成功 → 返回 REPLY
            if cycle_result.reply_detected and not cycle_result.reply_failed:
                thought_summary = content[:100] if content else ""
                self._autonomy_logger.log(
                    self._agent_id,
                    AutonomyEventType.THINKING,
                    f"思考完成(reply工具调用, {rounds}轮, {total_tool_calls}次工具)",
                )
                await self._emit_finalized(
                    response=response,
                    context=context,
                    tool_monitor_results=tool_monitor_results,
                    time_records=time_records,
                    end_reason="reply",
                    rounds=rounds,
                    total_tool_calls=total_tool_calls,
                )
                elapsed_ms = int((time.time() - cycle_started_at) * 1000)
                result = ThinkResult(
                    action=ThinkAction.REPLY,
                    text=cycle_result.reply_text,
                    reply_sent=True,
                    thought_summary=thought_summary,
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )
                self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms)
                return result

            # reply 工具调用失败 → 立即返回 SILENT，不继续循环
            if cycle_result.reply_detected and cycle_result.reply_failed:
                logger.warning(
                    f"[thinking_organ] reply 工具调用失败: agent={self._agent_id} round={rounds}"
                )
                await self._emit_finalized(
                    response=response,
                    context=context,
                    tool_monitor_results=tool_monitor_results,
                    time_records=time_records,
                    end_reason="tool_failed",
                    rounds=rounds,
                    total_tool_calls=total_tool_calls,
                )
                elapsed_ms = int((time.time() - cycle_started_at) * 1000)
                result = ThinkResult(
                    action=ThinkAction.SILENT,
                    silence_reason=SilenceReason.TOOL_FAILED,
                    thought_summary=content[:100] if content else "",
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )
                self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms, "reply工具执行失败")
                return result

            if cycle_result.should_pause:
                if cycle_result.pause_tool_name == "wait":
                    wait_secs = 60.0
                    for tc in response.tool_calls:
                        if tc.func_name == "wait" and isinstance(tc.args, dict):
                            wait_secs = float(tc.args.get("seconds", tc.args.get("duration", 60)))
                    self._autonomy_logger.log(
                        self._agent_id,
                        AutonomyEventType.THINKING,
                        f"等待工具暂停: {wait_secs}s",
                    )
                    await self._emit_finalized(
                        response=response,
                        context=context,
                        tool_monitor_results=tool_monitor_results,
                        time_records=time_records,
                        end_reason="wait",
                        rounds=rounds,
                        total_tool_calls=total_tool_calls,
                    )
                    elapsed_ms = int((time.time() - cycle_started_at) * 1000)
                    result = ThinkResult(
                        action=ThinkAction.WAIT,
                        tool_calls_count=total_tool_calls,
                        rounds=rounds,
                        wait_seconds=wait_secs,
                    )
                    self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms)
                    return result
                self._autonomy_logger.log(
                    self._agent_id,
                    AutonomyEventType.THINKING,
                    f"工具暂停: {cycle_result.pause_tool_name}",
                )
                await self._emit_finalized(
                    response=response,
                    context=context,
                    tool_monitor_results=tool_monitor_results,
                    time_records=time_records,
                    end_reason="pause",
                    rounds=rounds,
                    total_tool_calls=total_tool_calls,
                )
                elapsed_ms = int((time.time() - cycle_started_at) * 1000)
                result = ThinkResult(
                    action=ThinkAction.SILENT,
                    tool_calls_count=total_tool_calls,
                    rounds=rounds,
                )
                self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms)
                return result

            injected_messages = []

        logger.warning(f"[thinking_organ] 工具循环达到上限: agent={self._agent_id} rounds={rounds}")
        await self._emit_finalized(
            response=last_response,
            context=context,
            tool_monitor_results=tool_monitor_results,
            time_records=time_records,
            end_reason="max_rounds",
            rounds=rounds,
            total_tool_calls=total_tool_calls,
        )
        elapsed_ms = int((time.time() - cycle_started_at) * 1000)
        result = ThinkResult(
            action=ThinkAction.SILENT,
            silence_reason=SilenceReason.MAX_CYCLES,
            thought_summary=content[:100] if content else "",
            tool_calls_count=total_tool_calls,
            rounds=rounds,
        )
        self._log_cycle(context, result, rounds, tool_calls_made, tool_errors, elapsed_ms)
        return result

    async def _handle_tool_calls(
        self,
        tool_calls: list[Any],
        latest_thought: str,
        context: ThinkContext,
    ) -> ToolCycleResult:
        """执行工具调用。返回 ToolCycleResult（含 reply 检测信息）。"""
        from src.core.tooling import ToolInvocation, ToolExecutionContext, ToolAvailabilityContext
        from src.maisaka.display.display_utils import format_tool_call_for_display
        from src.maisaka.utils.tool_record_payload import normalize_tool_record_value

        if self._tool_registry is None:
            return ToolCycleResult()

        summaries: list[str] = []
        monitor_results: list[dict[str, Any]] = []
        reply_detected = False
        reply_text = ""
        reply_failed = False
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

            # reply 工具调用检测
            if tool_call.func_name == "reply":
                reply_detected = True
                if result.success:
                    structured = result.structured_content if hasattr(result, "structured_content") else None
                    if isinstance(structured, dict) and "reply_text" in structured:
                        reply_text = str(structured["reply_text"])
                    elif result.content:
                        reply_text = result.content
                else:
                    reply_failed = True
                    logger.warning(
                        f"[thinking_organ] reply 工具调用失败详情: agent={self._agent_id} "
                        f"error={result.error_message[:200] if result.error_message else 'unknown'} "
                        f"content={result.content[:200] if result.content else 'N/A'}"
                    )

            history_content = result.get_history_content() if hasattr(result, "get_history_content") else (result.content or result.error_message)
            if history_content:
                summaries.append(f"[{invocation.tool_name}] {history_content[:200]}")

            normalized_tool_call = format_tool_call_for_display(tool_call)
            tool_call_source = str(normalized_tool_call.get("source") or "").strip()
            tool_call_source_label = str(normalized_tool_call.get("source_label") or "").strip()
            tool_spec = tool_spec_map.get(tool_call.func_name)
            monitor_result: dict[str, Any] = {
                "tool_call_id": tool_call.call_id,
                "tool_name": tool_call.func_name,
                "tool_title": tool_spec.title.strip() if tool_spec is not None and tool_spec.title.strip() else "",
                "tool_args": normalize_tool_record_value(invocation.arguments if isinstance(invocation.arguments, dict) else {}),
                "tool_call_source": tool_call_source,
                "tool_call_source_label": tool_call_source_label,
                "success": result.success,
                "duration_ms": round(tool_duration_ms, 2),
                "summary": summaries[-1] if summaries else "",
            }
            monitor_detail = result.metadata.get("monitor_detail")
            if monitor_detail is not None:
                monitor_result["detail"] = normalize_tool_record_value(monitor_detail)
            monitor_card = result.metadata.get("monitor_card")
            if monitor_card is not None:
                monitor_result["card"] = normalize_tool_record_value(monitor_card)
            prompt_html_uri = str(result.metadata.get("prompt_html_uri") or "").strip()
            if prompt_html_uri:
                monitor_result["prompt_html_uri"] = prompt_html_uri
            monitor_results.append(monitor_result)

            if bool(result.metadata.get("wait_rest", False)):
                return ToolCycleResult(
                    should_pause=True,
                    pause_tool_name="wait_rest",
                    summaries=summaries,
                    monitor_results=monitor_results,
                    reply_detected=reply_detected,
                    reply_text=reply_text,
                    reply_failed=reply_failed,
                )
            if bool(result.metadata.get("pause_execution", False)):
                return ToolCycleResult(
                    should_pause=True,
                    pause_tool_name=invocation.tool_name,
                    summaries=summaries,
                    monitor_results=monitor_results,
                    reply_detected=reply_detected,
                    reply_text=reply_text,
                    reply_failed=reply_failed,
                )

        return ToolCycleResult(
            summaries=summaries,
            monitor_results=monitor_results,
            reply_detected=reply_detected,
            reply_text=reply_text,
            reply_failed=reply_failed,
        )

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

    def _determine_silence_reason(
        self,
        *,
        has_tool_failure: bool,
        has_content: bool,
        reached_max_cycles: bool,
    ) -> SilenceReason:
        """判定沉默原因 — 优先级：tool_failed > intentional > no_content > max_cycles。"""
        if has_tool_failure:
            return SilenceReason.TOOL_FAILED
        if has_content:
            return SilenceReason.INTENTIONAL
        if reached_max_cycles:
            return SilenceReason.MAX_CYCLES
        return SilenceReason.NO_CONTENT

    def _log_cycle(
        self,
        context: ThinkContext,
        result: ThinkResult,
        cycle_count: int,
        tool_calls_made: list[str],
        tool_errors: list[str],
        elapsed_ms: int,
        error_detail: str = "",
    ) -> None:
        """输出思考循环结构化日志 — 失败不影响 ThinkResult 返回。"""
        try:
            if result.action == ThinkAction.REPLY:
                status = CycleStatus.COMPLETED_REPLY
            elif result.action == ThinkAction.ERROR:
                status = CycleStatus.ERROR
            elif result.action == ThinkAction.WAIT:
                status = CycleStatus.COMPLETED_SILENT
            else:
                status = CycleStatus.COMPLETED_SILENT

            cycle_log = ThinkCycleLog(
                agent_id=self._agent_id,
                session_name=context.session_id,
                trigger=context.trigger_reason,
                status=status,
                silence_reason=result.silence_reason,
                thought_summary=result.thought_summary,
                action_summary=result.action.value,
                reply_text=result.text if result.action == ThinkAction.REPLY else "",
                cycle_count=cycle_count,
                tool_calls_made=tool_calls_made,
                tool_errors=tool_errors,
                elapsed_ms=elapsed_ms,
                error_detail=error_detail,
            )
            logger.info(cycle_log.to_log_line())
        except Exception as exc:
            logger.debug(f"[thinking_organ] 日志输出失败: agent={self._agent_id} error={exc}")

    # ========================================================================
    # 监控事件 + 结构化日志
    # ========================================================================

    async def _emit_finalized(
        self,
        *,
        response: Any,
        context: ThinkContext,
        tool_monitor_results: list[dict[str, Any]],
        time_records: dict[str, float],
        end_reason: str,
        rounds: int,
        total_tool_calls: int,
    ) -> None:
        """广播 planner.finalized 事件，让 WebUI 实时监控面板显示思考结果。"""
        try:
            from src.maisaka.monitor.events import emit_planner_finalized

            await emit_planner_finalized(
                session_id=context.session_id,
                cycle_id=rounds,
                planner_request_messages=response.request_messages if response is not None else None,
                planner_selected_history_count=response.selected_history_count if response is not None else None,
                planner_tool_count=response.tool_count if response is not None else None,
                planner_content=response.content if response is not None else None,
                planner_tool_calls=response.tool_calls if response is not None else None,
                planner_prompt_tokens=response.prompt_tokens if response is not None else None,
                planner_completion_tokens=response.completion_tokens if response is not None else None,
                planner_total_tokens=response.total_tokens if response is not None else None,
                planner_duration_ms=response.duration_ms if response is not None else None,
                planner_prompt_html_uri=response.prompt_html_uri if response is not None else None,
                tools=tool_monitor_results,
                time_records=time_records,
                agent_state="thinking_organ",
                planner_interrupted=False,
                end_reason=end_reason,
                end_detail=f"rounds={rounds} tool_calls={total_tool_calls}",
            )
        except Exception as exc:
            logger.debug(f"[thinking_organ] 监控事件广播失败: agent={self._agent_id} error={exc}")

    def _save_prompt_preview(
        self,
        response: Any,
        context: ThinkContext,
        request_kind: str,
        round_idx: int,
    ) -> None:
        """保存结构化 prompt 预览到 logs/maisaka_prompt/。"""
        if not global_config.debug.show_maisaka_thinking:
            return

        try:
            from src.maisaka.display.prompt_cli_renderer import PromptCLIVisualizer
            from src.cli.console import console
            from rich.panel import Panel

            if response is None or not hasattr(response, "request_messages"):
                return

            prompt_access_panel = PromptCLIVisualizer.build_prompt_access_panel(
                response.request_messages,
                category="planner",
                chat_id=context.session_id,
                request_kind=request_kind,
                selection_reason=(
                    f"智能体: {self._agent_id}\n"
                    f"会话ID: {context.session_id}\n"
                    f"模型: {response.model_name or '未知'}\n"
                    f"构建消息数: {response.built_message_count}\n"
                    f"选中历史数: {response.selected_history_count}\n"
                    f"轮次: {round_idx + 1}"
                ),
                output_content=response.content or "",
                output_tool_calls=response.tool_calls if response.tool_calls else None,
                metadata={
                    "model_name": response.model_name,
                    "duration_ms": response.duration_ms,
                    "prompt_tokens": response.prompt_tokens,
                    "completion_tokens": response.completion_tokens,
                    "total_tokens": response.total_tokens,
                    "agent_id": self._agent_id,
                    "round": round_idx + 1,
                },
            )
            console.print(
                Panel(
                    prompt_access_panel,
                    title=f"[thinking_organ] {self._agent_id} 第{round_idx + 1}轮请求预览",
                    border_style="green",
                    padding=(0, 1),
                )
            )
        except Exception as exc:
            logger.debug(f"[thinking_organ] Prompt预览保存失败: agent={self._agent_id} error={exc}")

