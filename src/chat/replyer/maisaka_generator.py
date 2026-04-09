from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

import random
import time

from rich.panel import Panel

from src.chat.message_receive.chat_manager import BotChatSession
from src.chat.message_receive.message import SessionMessage
from src.chat.utils.utils import get_chat_type_and_target_info
from src.cli.console import console
from src.common.data_models.reply_generation_data_models import (
    GenerationMetrics,
    LLMCompletionResult,
    ReplyGenerationResult,
    build_reply_monitor_detail,
)
from src.common.logger import get_logger
from src.common.prompt_i18n import load_prompt
from src.common.utils.utils_session import SessionUtils
from src.config.config import global_config
from src.core.types import ActionInfo
from src.llm_models.payload_content.message import Message, MessageBuilder, RoleType
from src.services.llm_service import LLMServiceClient

from src.maisaka.context_messages import (
    AssistantMessage,
    LLMContextMessage,
    ReferenceMessage,
    SessionBackedMessage,
    ToolResultMessage,
)
from src.maisaka.message_adapter import parse_speaker_content
from src.maisaka.prompt_cli_renderer import PromptCLIVisualizer
from src.plugin_runtime.hook_payloads import serialize_prompt_messages

from .maisaka_expression_selector import maisaka_expression_selector

logger = get_logger("replyer")


@dataclass
class MaisakaReplyContext:
    """Maisaka replyer 使用的回复上下文。"""

    expression_habits: str = ""
    selected_expression_ids: List[int] = field(default_factory=list)


class MaisakaReplyGenerator:
    """生成 Maisaka 的最终可见回复。"""

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
    def _format_message_time(message: LLMContextMessage) -> str:
        return message.timestamp.strftime("%H:%M:%S")

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
        """按说话人拆分用户消息。"""
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

    def _format_chat_history(self, messages: List[LLMContextMessage]) -> str:
        """格式化 replyer 使用的可见聊天记录。"""
        bot_nickname = global_config.bot.nickname.strip() or "Bot"
        parts: List[str] = []

        for message in messages:
            timestamp = self._format_message_time(message)

            if isinstance(message, (ReferenceMessage, ToolResultMessage)):
                continue

            if isinstance(message, SessionBackedMessage):
                guided_reply = self._extract_guided_bot_reply(message)
                if guided_reply:
                    parts.append(f"{timestamp} {bot_nickname}(you): {guided_reply}")
                    continue

                raw_content = message.processed_plain_text
                for speaker_name, content_body in self._split_user_message_segments(raw_content):
                    content = self._normalize_content(content_body)
                    if not content:
                        continue
                    visible_speaker = speaker_name or global_config.maisaka.cli_user_name.strip() or "User"
                    parts.append(f"{timestamp} {visible_speaker}: {content}")
                continue

            if isinstance(message, AssistantMessage):
                visible_reply = self._extract_visible_assistant_reply(message)
                if visible_reply:
                    parts.append(f"{timestamp} {bot_nickname}(you): {visible_reply}")

        return "\n".join(parts)

    def _build_target_message_block(self, reply_message: Optional[SessionMessage]) -> str:
        """构建当前需要回复的目标消息摘要。"""
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
            "- 你这次要回复的就是这条目标消息，请结合整段上下文理解，但不要误把其他历史消息当成当前回复对象。"
        )

    @staticmethod
    def _get_chat_prompt_for_chat(chat_id: str, is_group_chat: Optional[bool]) -> str:
        """根据聊天流 ID 获取匹配的额外 prompt。"""
        if not global_config.chat.chat_prompts:
            return ""

        for chat_prompt_item in global_config.chat.chat_prompts:
            if hasattr(chat_prompt_item, "platform"):
                platform = str(chat_prompt_item.platform or "").strip()
                item_id = str(chat_prompt_item.item_id or "").strip()
                rule_type = str(chat_prompt_item.rule_type or "").strip()
                prompt_content = str(chat_prompt_item.prompt or "").strip()
            elif isinstance(chat_prompt_item, str):
                parts = chat_prompt_item.split(":", 3)
                if len(parts) != 4:
                    continue

                platform, item_id, rule_type, prompt_content = parts
                platform = platform.strip()
                item_id = item_id.strip()
                rule_type = rule_type.strip()
                prompt_content = prompt_content.strip()
            else:
                continue

            if not platform or not item_id or not prompt_content:
                continue

            if rule_type == "group":
                config_is_group = True
                config_chat_id = SessionUtils.calculate_session_id(platform, group_id=item_id)
            elif rule_type == "private":
                config_is_group = False
                config_chat_id = SessionUtils.calculate_session_id(platform, user_id=item_id)
            else:
                continue

            if config_is_group != is_group_chat:
                continue
            if config_chat_id == chat_id:
                return prompt_content

        return ""

    def _build_group_chat_attention_block(self, session_id: str) -> str:
        """构建当前聊天场景下的额外注意事项块。"""
        if not session_id:
            return ""

        try:
            is_group_chat, _ = get_chat_type_and_target_info(session_id)
        except Exception:
            is_group_chat = None

        prompt_lines: List[str] = []

        if is_group_chat is True:
            if group_chat_prompt := global_config.chat.group_chat_prompt.strip():
                prompt_lines.append(f"通用注意事项：\n{group_chat_prompt}")
        elif is_group_chat is False:
            if private_chat_prompt := global_config.chat.private_chat_prompts.strip():
                prompt_lines.append(f"通用注意事项：\n{private_chat_prompt}")

        if chat_prompt := self._get_chat_prompt_for_chat(session_id, is_group_chat).strip():
            prompt_lines.append(f"当前聊天额外注意事项：\n{chat_prompt}")

        if not prompt_lines:
            return ""

        return "在该聊天中的注意事项：\n" + "\n\n".join(prompt_lines) + "\n"

    def _build_request_messages(
        self,
        chat_history: List[LLMContextMessage],
        reply_message: Optional[SessionMessage],
        reply_reason: str,
        expression_habits: str = "",
        stream_id: Optional[str] = None,
    ) -> List[Message]:
        """构建 Maisaka replyer 请求消息列表。"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_history = self._format_chat_history(chat_history)
        target_message_block = self._build_target_message_block(reply_message)
        session_id = self._resolve_session_id(stream_id)

        try:
            system_prompt = load_prompt(
                "maisaka_replyer",
                bot_name=global_config.bot.nickname,
                group_chat_attention_block=self._build_group_chat_attention_block(session_id),
                time_block=f"当前时间：{current_time}",
                identity=self._personality_prompt,
                reply_style=global_config.personality.reply_style,
            )
        except Exception:
            system_prompt = "你是一个友好的 AI 助手，请根据聊天记录自然回复。"

        extra_sections: List[str] = []
        if expression_habits.strip():
            extra_sections.append(expression_habits.strip())

        user_sections = [
            f"当前时间：{current_time}",
            f"【聊天记录】\n{formatted_history}",
        ]
        if target_message_block:
            user_sections.append(target_message_block)
        if extra_sections:
            user_sections.append("\n\n".join(extra_sections))
        user_sections.append(f"【回复信息参考】\n{reply_reason}")
        user_sections.append("现在，你说：")

        user_prompt = "\n\n".join(user_sections)
        return [
            MessageBuilder().set_role(RoleType.System).add_text_content(system_prompt).build(),
            MessageBuilder().set_role(RoleType.User).add_text_content(user_prompt).build(),
        ]

    def _resolve_session_id(self, stream_id: Optional[str]) -> str:
        """解析当前回复使用的会话 ID。"""
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
        """构建回复上下文：表达习惯和已选表达 ID。"""
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
        """结合上下文生成 Maisaka 的最终可见回复。"""

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
            f"Maisaka 回复器开始生成: 会话流标识={stream_id} 回复原因={reply_reason!r} "
            f"历史消息数={len(chat_history)} 目标消息编号={reply_message.message_id if reply_message else None}"
        )

        filtered_history = [
            message
            for message in chat_history
            if not isinstance(message, (ReferenceMessage, ToolResultMessage))
        ]
        logger.debug(f"Maisaka 回复器过滤后历史消息数={len(filtered_history)}")

        if self.express_model is None:
            logger.error("Maisaka 回复器的回复模型未初始化")
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

            logger.error(f"Maisaka 回复器构建回复上下文失败: {exc}\n{traceback.format_exc()}")
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
            f"Maisaka 回复上下文构建完成: 会话流标识={stream_id} "
            f"已选表达编号={result.selected_expression_ids!r}"
        )

        prompt_started_at = time.perf_counter()
        try:
            request_messages = self._build_request_messages(
                chat_history=filtered_history,
                reply_message=reply_message,
                reply_reason=reply_reason or "",
                expression_habits=merged_expression_habits,
                stream_id=stream_id,
            )
        except Exception as exc:
            import traceback

            logger.error(f"Maisaka 回复器构建提示词失败: {exc}\n{traceback.format_exc()}")
            result.error_message = f"构建提示词失败: {exc}"
            result.metrics = GenerationMetrics(
                overall_ms=round((time.perf_counter() - overall_started_at) * 1000, 2),
            )
            return finalize(False)

        prompt_ms = round((time.perf_counter() - prompt_started_at) * 1000, 2)
        request_prompt = PromptCLIVisualizer._build_prompt_dump_text(request_messages)
        result.completion.request_prompt = request_prompt
        result.request_messages = serialize_prompt_messages(request_messages)
        show_replyer_prompt = bool(getattr(global_config.debug, "show_replyer_prompt", False))
        show_replyer_reasoning = bool(getattr(global_config.debug, "show_replyer_reasoning", False))
        preview_chat_id = self._resolve_session_id(stream_id) or "unknown"

        if show_replyer_prompt:
            console.print(
                Panel(
                    PromptCLIVisualizer.build_prompt_access_panel(
                        request_messages,
                        category="replyer",
                        chat_id=preview_chat_id,
                        request_kind="replyer",
                        selection_reason=f"ID: {preview_chat_id}",
                        image_display_mode="path_link" if global_config.maisaka.show_image_path else "legacy",
                    ),
                    title="Maisaka Replyer Prompt",
                    border_style="bright_yellow",
                    padding=(0, 1),
                )
            )

        def message_factory(_client: object) -> List[Message]:
            return request_messages

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
            request_prompt=request_prompt,
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
            f"Maisaka 回复器生成成功: 回复文本={response_text!r} "
            f"总耗时毫秒={result.metrics.overall_ms} "
            f"已选表达编号={result.selected_expression_ids!r}"
        )
        result.text_fragments = [response_text]
        return finalize(True)
