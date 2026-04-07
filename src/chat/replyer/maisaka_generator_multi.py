import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from src.chat.message_receive.chat_manager import BotChatSession
from src.chat.message_receive.message import SessionMessage
from src.cli.console import console
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.common.data_models.reply_generation_data_models import (
    GenerationMetrics,
    LLMCompletionResult,
    ReplyGenerationResult,
    build_reply_monitor_detail,
)
from src.common.logger import get_logger
from src.common.prompt_i18n import load_prompt
from src.config.config import global_config
from src.core.types import ActionInfo
from src.llm_models.payload_content.message import (
    ImageMessagePart,
    Message,
    MessageBuilder,
    RoleType,
    TextMessagePart,
)
from src.services.llm_service import LLMServiceClient

from src.maisaka.context_messages import (
    AssistantMessage,
    LLMContextMessage,
    ReferenceMessage,
    SessionBackedMessage,
    ToolResultMessage,
)
from src.maisaka.message_adapter import clone_message_sequence, parse_speaker_content
from src.maisaka.prompt_cli_renderer import PromptCLIVisualizer

from .maisaka_expression_selector import maisaka_expression_selector

logger = get_logger("replyer")


@dataclass
class MaisakaReplyContext:
    """Maisaka replyer 使用的回复上下文。"""

    expression_habits: str = ""
    selected_expression_ids: List[int] = field(default_factory=list)


class MaisakaReplyGenerator:
    """生成 Maisaka 的最终可见回复（多模态管线）。"""

    def __init__(
        self,
        chat_stream: Optional[BotChatSession] = None,
        request_type: str = "maisaka_replyer",
    ) -> None:
        self.chat_stream = chat_stream
        self.request_type = request_type
        self.express_model = LLMServiceClient(
            task_name="replyer",
            request_type=request_type,
        )
        self._personality_prompt = self._build_personality_prompt()

    def _build_personality_prompt(self) -> str:
        """构建 replyer 使用的人设提示。"""
        try:
            bot_name = global_config.bot.nickname
            alias_names = global_config.bot.alias_names
            bot_aliases = f"，也有人叫你{','.join(alias_names)}" if alias_names else ""

            prompt_personality = global_config.personality.personality
            if (
                hasattr(global_config.personality, "states")
                and global_config.personality.states
                and hasattr(global_config.personality, "state_probability")
                and global_config.personality.state_probability > 0
                and random.random() < global_config.personality.state_probability
            ):
                prompt_personality = random.choice(global_config.personality.states)

            return f"你的名字是{bot_name}{bot_aliases}，你{prompt_personality};"
        except Exception as exc:
            logger.warning(f"构建 Maisaka 人设提示词失败: {exc}")
            return "你的名字是麦麦，你是一个活泼可爱的 AI 助手。"

    @staticmethod
    def _normalize_content(content: str, limit: int = 500) -> str:
        normalized = " ".join((content or "").split())
        if len(normalized) > limit:
            return normalized[:limit] + "..."
        return normalized

    @staticmethod
    def _extract_visible_assistant_reply(message: AssistantMessage) -> str:
        del message
        return ""

    def _extract_guided_bot_reply(self, message: SessionBackedMessage) -> str:
        speaker_name, body = parse_speaker_content(message.processed_plain_text.strip())
        bot_nickname = global_config.bot.nickname.strip() or "Bot"
        if speaker_name == bot_nickname:
            return self._normalize_content(body.strip())
        return ""

    @staticmethod
    def _split_user_message_segments(raw_content: str) -> List[tuple[Optional[str], str]]:
        segments: List[tuple[Optional[str], str]] = []
        current_speaker: Optional[str] = None
        current_lines: List[str] = []

        for raw_line in raw_content.splitlines():
            speaker_name, content_body = parse_speaker_content(raw_line)
            if speaker_name is not None:
                if current_lines:
                    segments.append((current_speaker, "\n".join(current_lines)))
                current_speaker = speaker_name
                current_lines = [content_body]
                continue

            current_lines.append(raw_line)

        if current_lines:
            segments.append((current_speaker, "\n".join(current_lines)))

        return segments

    def _build_target_message_block(self, reply_message: Optional[SessionMessage]) -> str:
        if reply_message is None:
            return ""

        user_info = reply_message.message_info.user_info
        sender_name = user_info.user_cardname or user_info.user_nickname or user_info.user_id
        target_message_id = reply_message.message_id.strip() if reply_message.message_id else "未知"
        target_content = self._normalize_content((reply_message.processed_plain_text or "").strip(), limit=300)
        if not target_content:
            target_content = "[无可见文本内容]"

        return (
            "【本次回复目标】\n"
            f"- 目标消息ID：{target_message_id}\n"
            f"- 发送者：{sender_name}\n"
            f"- 消息内容：{target_content}\n"
            "- 你这次要回复的就是这条目标消息，请结合整段上下文理解，但不要把其他历史消息当成当前回复对象。"
        )

    def _build_system_prompt(
        self,
        reply_message: Optional[SessionMessage],
        reply_reason: str,
        expression_habits: str = "",
    ) -> str:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_message_block = self._build_target_message_block(reply_message)

        try:
            system_prompt = load_prompt(
                "maisaka_replyer",
                bot_name=global_config.bot.nickname,
                time_block=f"当前时间：{current_time}",
                identity=self._personality_prompt,
                reply_style=global_config.personality.reply_style,
            )
        except Exception:
            system_prompt = "你是一个友好的 AI 助手，请根据聊天记录自然回复。"

        sections: List[str] = []
        if expression_habits.strip():
            sections.append(expression_habits.strip())
        if target_message_block:
            sections.append(target_message_block)
        if reply_reason.strip():
            sections.append(f"【回复信息参考】\n{reply_reason}")
        if not sections:
            return system_prompt
        return f"{system_prompt}\n\n" + "\n\n".join(sections)

    def _build_reply_instruction(self) -> str:
        return "请自然地回复。不要输出多余说明、括号、at 或额外标记，只输出实际要发送的内容。"

    def _build_multimodal_user_message(
        self,
        message: SessionBackedMessage,
        default_user_name: str,
    ) -> Optional[Message]:
        speaker_name, _ = parse_speaker_content(message.processed_plain_text.strip())
        visible_speaker = speaker_name or default_user_name

        raw_message = clone_message_sequence(message.raw_message)
        if not raw_message.components:
            raw_message = MessageSequence([TextComponent(f"[{visible_speaker}]")])
        elif isinstance(raw_message.components[0], TextComponent):
            first_text = raw_message.components[0].text or ""
            raw_message.components[0] = TextComponent(f"[{visible_speaker}]{first_text}")
        else:
            raw_message.components.insert(0, TextComponent(f"[{visible_speaker}]"))

        multimodal_message = SessionBackedMessage(
            raw_message=raw_message,
            visible_text=f"[{visible_speaker}]{message.processed_plain_text}",
            timestamp=message.timestamp,
            message_id=message.message_id,
            original_message=message.original_message,
            source_kind=message.source_kind,
        )
        return multimodal_message.to_llm_message()

    def _build_history_messages(self, chat_history: List[LLMContextMessage]) -> List[Message]:
        bot_nickname = global_config.bot.nickname.strip() or "Bot"
        default_user_name = global_config.maisaka.cli_user_name.strip() or "User"
        messages: List[Message] = []

        for message in chat_history:
            if isinstance(message, (ReferenceMessage, ToolResultMessage)):
                continue

            if isinstance(message, SessionBackedMessage):
                guided_reply = self._extract_guided_bot_reply(message)
                if guided_reply:
                    messages.append(
                        MessageBuilder().set_role(RoleType.Assistant).add_text_content(guided_reply).build()
                    )
                    continue

                multimodal_message = self._build_multimodal_user_message(message, default_user_name)
                if multimodal_message is not None:
                    messages.append(multimodal_message)
                    continue

                for speaker_name, content_body in self._split_user_message_segments(message.processed_plain_text):
                    content = self._normalize_content(content_body)
                    if not content:
                        continue

                    visible_speaker = speaker_name or default_user_name
                    if visible_speaker == bot_nickname:
                        messages.append(
                            MessageBuilder().set_role(RoleType.Assistant).add_text_content(content).build()
                        )
                        continue

                    user_content = f"[{visible_speaker}]{content}"
                    messages.append(MessageBuilder().set_role(RoleType.User).add_text_content(user_content).build())
                continue

            if isinstance(message, AssistantMessage):
                visible_reply = self._extract_visible_assistant_reply(message)
                if visible_reply:
                    messages.append(
                        MessageBuilder().set_role(RoleType.Assistant).add_text_content(visible_reply).build()
                    )

        return messages

    def _build_request_messages(
        self,
        chat_history: List[LLMContextMessage],
        reply_message: Optional[SessionMessage],
        reply_reason: str,
        expression_habits: str = "",
    ) -> List[Message]:
        messages: List[Message] = []
        system_prompt = self._build_system_prompt(
            reply_message=reply_message,
            reply_reason=reply_reason,
            expression_habits=expression_habits,
        )
        instruction = self._build_reply_instruction()

        messages.append(MessageBuilder().set_role(RoleType.System).add_text_content(system_prompt).build())
        messages.extend(self._build_history_messages(chat_history))
        messages.append(MessageBuilder().set_role(RoleType.User).add_text_content(instruction).build())
        return messages

    @staticmethod
    def _build_request_prompt_preview(messages: List[Message]) -> str:
        preview_lines: List[str] = []
        for message in messages:
            role_name = message.role.value.capitalize()
            part_previews: List[str] = []
            for part in message.parts:
                if isinstance(part, TextMessagePart):
                    part_previews.append(part.text)
                    continue
                if isinstance(part, ImageMessagePart):
                    part_previews.append(f"[图片:{part.normalized_image_format}]")
            preview_lines.append(f"{role_name}: {''.join(part_previews)}")
        return "\n\n".join(preview_lines)

    def _resolve_session_id(self, stream_id: Optional[str]) -> str:
        if stream_id:
            return stream_id
        if self.chat_stream is not None:
            return self.chat_stream.session_id
        return ""

    async def _build_reply_context(
        self,
        chat_history: List[LLMContextMessage],
        reply_message: Optional[SessionMessage],
        reply_reason: str,
        stream_id: Optional[str],
        sub_agent_runner: Optional[Callable[[str], Awaitable[str]]],
    ) -> MaisakaReplyContext:
        session_id = self._resolve_session_id(stream_id)
        if not session_id:
            logger.warning("构建 Maisaka 回复上下文失败：缺少会话标识")
            return MaisakaReplyContext()

        if sub_agent_runner is None:
            logger.info("表达方式选择跳过：缺少子代理执行器")
            return MaisakaReplyContext()

        selection_result = await maisaka_expression_selector.select_for_reply(
            session_id=session_id,
            chat_history=chat_history,
            reply_message=reply_message,
            reply_reason=reply_reason,
            sub_agent_runner=sub_agent_runner,
        )
        return MaisakaReplyContext(
            expression_habits=selection_result.expression_habits,
            selected_expression_ids=selection_result.selected_expression_ids,
        )

    async def generate_reply_with_context(
        self,
        extra_info: str = "",
        reply_reason: str = "",
        available_actions: Optional[Dict[str, ActionInfo]] = None,
        chosen_actions: Optional[List[object]] = None,
        from_plugin: bool = True,
        stream_id: Optional[str] = None,
        reply_message: Optional[SessionMessage] = None,
        reply_time_point: Optional[float] = None,
        think_level: int = 1,
        unknown_words: Optional[List[str]] = None,
        log_reply: bool = True,
        chat_history: Optional[List[LLMContextMessage]] = None,
        expression_habits: str = "",
        selected_expression_ids: Optional[List[int]] = None,
        sub_agent_runner: Optional[Callable[[str], Awaitable[str]]] = None,
    ) -> Tuple[bool, ReplyGenerationResult]:

        def finalize(success_value: bool) -> Tuple[bool, ReplyGenerationResult]:
            result.monitor_detail = build_reply_monitor_detail(result)
            return success_value, result

        del available_actions
        del chosen_actions
        del extra_info
        del from_plugin
        del log_reply
        del reply_time_point
        del think_level
        del unknown_words

        result = ReplyGenerationResult()
        overall_started_at = time.perf_counter()
        if chat_history is None:
            result.error_message = "聊天历史为空"
            return finalize(False)

        logger.info(
            f"Maisaka 回复器开始生成: 流={stream_id} 原因={reply_reason!r} "
            f"历史条数={len(chat_history)} 目标ID={reply_message.message_id if reply_message else None}"
        )

        filtered_history = [
            message
            for message in chat_history
            if not isinstance(message, (ReferenceMessage, ToolResultMessage))
        ]

        if self.express_model is None:
            logger.error("回复模型未初始化")
            result.error_message = "回复模型尚未初始化"
            return finalize(False)

        try:
            reply_context = await self._build_reply_context(
                chat_history=filtered_history,
                reply_message=reply_message,
                reply_reason=reply_reason or "",
                stream_id=stream_id,
                sub_agent_runner=sub_agent_runner,
            )
        except Exception as exc:
            import traceback

            logger.error(f"构建回复上下文失败: {exc}\n{traceback.format_exc()}")
            result.error_message = f"构建回复上下文失败: {exc}"
            result.metrics = GenerationMetrics(
                overall_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
            )
            return finalize(False)

        merged_expression_habits = expression_habits.strip() or reply_context.expression_habits
        result.selected_expression_ids = (
            list(selected_expression_ids)
            if selected_expression_ids is not None
            else list(reply_context.selected_expression_ids)
        )

        logger.info(
            f"回复上下文完成: 流={stream_id} 已选表达={result.selected_expression_ids!r}"
        )

        prompt_started_at = time.perf_counter()
        try:
            request_messages = self._build_request_messages(
                chat_history=filtered_history,
                reply_message=reply_message,
                reply_reason=reply_reason or "",
                expression_habits=merged_expression_habits,
            )
        except Exception as exc:
            import traceback

            logger.error(f"构建提示词失败: {exc}\n{traceback.format_exc()}")
            result.error_message = f"构建提示词失败: {exc}"
            result.metrics = GenerationMetrics(
                overall_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
            )
            return finalize(False)

        prompt_ms = round((time.perf_counter() - prompt_started_at) * 1000, 2)
        prompt_preview = self._build_request_prompt_preview(request_messages)
        show_replyer_prompt = bool(getattr(global_config.debug, "show_replyer_prompt", False))
        show_replyer_reasoning = bool(getattr(global_config.debug, "show_replyer_reasoning", False))

        def message_factory(_client: object) -> List[Message]:
            return request_messages

        result.completion.request_prompt = prompt_preview
        preview_chat_id = self._resolve_session_id(stream_id)
        replyer_prompt_section: RenderableType | None = None
        if show_replyer_prompt:
            replyer_prompt_section = Panel(
                PromptCLIVisualizer.build_text_access_panel(
                    prompt_preview,
                    category="replyer",
                    chat_id=preview_chat_id,
                    request_kind="replyer",
                    subtitle=f"流ID: {preview_chat_id}",
                ),
                title="Reply Prompt",
                border_style="bright_yellow",
                padding=(0, 1),
            )

        llm_started_at = time.perf_counter()
        try:
            generation_result = await self.express_model.generate_response_with_messages(
                message_factory=message_factory
            )
        except Exception as exc:
            logger.exception("Maisaka 回复器调用失败")
            result.error_message = str(exc)
            result.metrics = GenerationMetrics(
                prompt_ms=prompt_ms,
                llm_ms=round((time.perf_counter() - llm_started_at) * 1000, 2),
                overall_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
            )
            return finalize(False)

        llm_ms = round((time.perf_counter() - llm_started_at) * 1000, 2)
        response_text = (generation_result.response or "").strip()
        result.success = bool(response_text)
        result.completion = LLMCompletionResult(
            request_prompt=prompt_preview,
            response_text=response_text,
            reasoning_text=generation_result.reasoning or "",
            model_name=generation_result.model_name or "",
            tool_calls=generation_result.tool_calls or [],
            prompt_tokens=generation_result.prompt_tokens,
            completion_tokens=generation_result.completion_tokens,
            total_tokens=generation_result.total_tokens,
        )
        result.metrics = GenerationMetrics(
            prompt_ms=prompt_ms,
            llm_ms=llm_ms,
            overall_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
            stage_logs=[
                f"prompt: {prompt_ms} ms",
                f"llm: {llm_ms} ms",
            ],
        )

        if show_replyer_reasoning and result.completion.reasoning_text:
            logger.info(f"Maisaka 回复器思考内容:\n{result.completion.reasoning_text}")

        if not result.success:
            result.error_message = "回复器返回了空内容"
            logger.warning("Maisaka 回复器返回了空内容")
            return finalize(False)

        logger.info(
            f"Maisaka 回复器生成成功: 文本={response_text!r} "
            f"总耗时ms={result.metrics.overall_ms} 已选表达={result.selected_expression_ids!r}"
        )
        if show_replyer_prompt or show_replyer_reasoning:
            summary_lines = [
                f"流ID: {preview_chat_id or 'unknown'}",
                f"耗时: {result.metrics.overall_ms} ms",
            ]
            if result.selected_expression_ids:
                summary_lines.append(f"表达编号: {result.selected_expression_ids!r}")

            renderables: List[RenderableType] = [Text("\n".join(summary_lines))]
            if replyer_prompt_section is not None:
                renderables.append(replyer_prompt_section)
            if show_replyer_reasoning and result.completion.reasoning_text:
                renderables.append(
                    Panel(
                        Text(result.completion.reasoning_text),
                        title="思考内容",
                        border_style="magenta",
                        padding=(0, 1),
                    )
                )
            renderables.append(
                Panel(
                    Text(response_text),
                    title="回复结果",
                    border_style="green",
                    padding=(0, 1),
                )
            )
            console.print(
                Panel(
                    Group(*renderables),
                    title="MaiSaka 回复器",
                    border_style="bright_yellow",
                    padding=(0, 1),
                )
            )
        result.text_fragments = [response_text]
        return finalize(True)
