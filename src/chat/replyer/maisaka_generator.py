from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import random
import time

from sqlmodel import select

from src.chat.message_receive.chat_manager import BotChatSession
from src.common.database.database import get_db_session
from src.common.database.database_model import Expression
from src.common.data_models.reply_generation_data_models import (
    GenerationMetrics,
    LLMCompletionResult,
    ReplyGenerationResult,
)
from src.common.logger import get_logger
from src.common.prompt_i18n import load_prompt
from src.common.utils.utils_session import SessionUtils
from src.config.config import global_config
from src.core.types import ActionInfo
from src.services.llm_service import LLMServiceClient

from src.chat.message_receive.message import SessionMessage
from src.maisaka.context_messages import AssistantMessage, LLMContextMessage, ReferenceMessage, SessionBackedMessage, ToolResultMessage
from src.maisaka.message_adapter import parse_speaker_content

logger = get_logger("replyer")


@dataclass
class MaisakaReplyContext:
    """Maisaka replyer 使用的回复上下文。"""

    expression_habits: str = ""
    selected_expression_ids: List[int] = field(default_factory=list)


@dataclass
class _ExpressionRecord:
    """表达方式的轻量记录。"""

    expression_id: Optional[int]
    situation: str
    style: str


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
        """构建 replyer 使用的人设描述。"""
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

    def _build_prompt(
        self,
        chat_history: List[LLMContextMessage],
        reply_message: Optional[SessionMessage],
        reply_reason: str,
        expression_habits: str = "",
    ) -> str:
        """构建 Maisaka replyer 提示词。"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_history = self._format_chat_history(chat_history)
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
        return f"System: {system_prompt}\n\nUser: {user_prompt}"

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
    ) -> MaisakaReplyContext:
        """在 replyer 内部构建表达习惯和黑话解释。"""
        session_id = self._resolve_session_id(stream_id)
        if not session_id:
            logger.warning("构建 Maisaka 回复上下文失败：缺少会话标识")
            return MaisakaReplyContext()

        expression_habits, selected_expression_ids = self._build_expression_habits(
            session_id=session_id,
            chat_history=chat_history,
            reply_message=reply_message,
            reply_reason=reply_reason,
        )
        return MaisakaReplyContext(
            expression_habits=expression_habits,
            selected_expression_ids=selected_expression_ids,
        )

    def _build_expression_habits(
        self,
        session_id: str,
        chat_history: List[LLMContextMessage],
        reply_message: Optional[SessionMessage],
        reply_reason: str,
    ) -> tuple[str, List[int]]:
        """查询并格式化适合当前会话的表达习惯。"""
        del chat_history
        del reply_message
        del reply_reason

        expression_records = self._load_expression_records(session_id)
        if not expression_records:
            return "", []

        lines: List[str] = []
        selected_ids: List[int] = []
        for expression in expression_records:
            if expression.expression_id is not None:
                selected_ids.append(expression.expression_id)
            lines.append(f"- 当{expression.situation}时，可以自然地用{expression.style}这种表达习惯。")

        block = "【表达习惯参考】\n" + "\n".join(lines)
        logger.info(
            f"已构建 Maisaka 表达习惯: 会话标识={session_id} "
            f"数量={len(selected_ids)} 表达编号={selected_ids!r}"
        )
        return block, selected_ids

    def _get_related_session_ids(self, session_id: str) -> List[str]:
        """根据表达互通组配置，解析当前会话可共享的会话 ID。"""
        related_session_ids = {session_id}
        expression_groups = global_config.expression.expression_groups

        for expression_group in expression_groups:
            target_items = expression_group.expression_groups
            group_session_ids: set[str] = set()
            contains_current_session = False

            for target_item in target_items:
                platform = target_item.platform.strip()
                item_id = target_item.item_id.strip()
                if not platform or not item_id:
                    continue

                rule_type = target_item.rule_type
                target_session_id = SessionUtils.calculate_session_id(
                    platform,
                    group_id=item_id if rule_type == "group" else None,
                    user_id=None if rule_type == "group" else item_id,
                )
                group_session_ids.add(target_session_id)
                if target_session_id == session_id:
                    contains_current_session = True

            if contains_current_session:
                related_session_ids.update(group_session_ids)

        return list(related_session_ids)

    def _load_expression_records(self, session_id: str) -> List[_ExpressionRecord]:
        """提取表达方式静态数据，避免 detached ORM 对象。"""
        related_session_ids = self._get_related_session_ids(session_id)

        with get_db_session(auto_commit=False) as session:
            base_query = select(Expression).where(Expression.rejected.is_(False))  # type: ignore[attr-defined]
            scoped_query = base_query.where(
                (Expression.session_id.in_(related_session_ids)) | (Expression.session_id.is_(None))  # type: ignore[attr-defined]
            ).order_by(Expression.count.desc(), Expression.last_active_time.desc())  # type: ignore[attr-defined]

            if global_config.expression.expression_checked_only:
                scoped_query = scoped_query.where(Expression.checked.is_(True))  # type: ignore[attr-defined]

            expressions = session.exec(scoped_query.limit(5)).all()

            return [
                _ExpressionRecord(
                    expression_id=expression.id,
                    situation=expression.situation,
                    style=expression.style,
                )
                for expression in expressions
            ]

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
    ) -> Tuple[bool, ReplyGenerationResult]:
        """结合上下文生成 Maisaka 的最终可见回复。"""
        del available_actions
        del chosen_actions
        del extra_info
        del from_plugin
        del log_reply
        del reply_time_point
        del think_level
        del unknown_words

        result = ReplyGenerationResult()
        if chat_history is None:
            result.error_message = "聊天历史为空"
            return False, result

        logger.info(
            f"Maisaka 回复器开始生成: 会话流标识={stream_id} 回复原因={reply_reason!r} "
            f"历史消息数={len(chat_history)} 目标消息编号="
            f"{reply_message.message_id if reply_message else None}"
        )

        filtered_history = [
            message
            for message in chat_history
            if not isinstance(message, (ReferenceMessage, ToolResultMessage))
        ]

        logger.debug(f"Maisaka 回复器过滤后历史消息数={len(filtered_history)}")

        # Validate that express_model is properly initialized
        if self.express_model is None:
            logger.error("Maisaka 回复器的回复模型未初始化")
            result.error_message = "回复模型尚未初始化"
            return False, result

        try:
            reply_context = await self._build_reply_context(
                chat_history=filtered_history,
                reply_message=reply_message,
                reply_reason=reply_reason or "",
                stream_id=stream_id,
            )
        except Exception as exc:
            import traceback
            logger.error(f"Maisaka 回复器构建回复上下文失败: {exc}\n{traceback.format_exc()}")
            result.error_message = f"构建回复上下文失败: {exc}"
            return False, result

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

        try:
            prompt = self._build_prompt(
                chat_history=filtered_history,
                reply_message=reply_message,
                reply_reason=reply_reason or "",
                expression_habits=merged_expression_habits,
            )
        except Exception as exc:
            import traceback
            logger.error(f"Maisaka 回复器构建提示词失败: {exc}\n{traceback.format_exc()}")
            result.error_message = f"构建提示词失败: {exc}"
            return False, result

        result.completion.request_prompt = prompt

        if global_config.debug.show_replyer_prompt:
            logger.info(f"\nMaisaka 回复器提示词：\n{prompt}\n")

        started_at = time.perf_counter()
        try:
            generation_result = await self.express_model.generate_response(prompt)
        except Exception as exc:
            logger.exception("Maisaka 回复器调用失败")
            result.error_message = str(exc)
            result.metrics = GenerationMetrics(
                overall_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            return False, result

        response_text = (generation_result.response or "").strip()
        result.success = bool(response_text)
        result.completion = LLMCompletionResult(
            request_prompt=prompt,
            response_text=response_text,
            reasoning_text=generation_result.reasoning or "",
            model_name=generation_result.model_name or "",
            tool_calls=generation_result.tool_calls or [],
        )
        result.metrics = GenerationMetrics(
            overall_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

        if global_config.debug.show_replyer_reasoning and result.completion.reasoning_text:
            logger.info(f"Maisaka 回复器思考内容：\n{result.completion.reasoning_text}")

        if not result.success:
            result.error_message = "回复器返回了空内容"
            logger.warning("Maisaka 回复器返回了空内容")
            return False, result

        logger.info(
            f"Maisaka 回复器生成成功: 回复文本={response_text!r} "
            f"总耗时毫秒={result.metrics.overall_ms} "
            f"已选表达编号={result.selected_expression_ids!r}"
        )
        result.text_fragments = [response_text]
        return True, result
