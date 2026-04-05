"""Maisaka 历史消息处理辅助工具。"""

from typing import TYPE_CHECKING

from src.common.data_models.message_component_data_model import MessageSequence, TextComponent

from .context_messages import AssistantMessage, LLMContextMessage, ToolResultMessage
from .message_adapter import build_visible_text_from_sequence, clone_message_sequence, format_speaker_content

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage


def build_prefixed_message_sequence(
    source_sequence: MessageSequence,
    planner_prefix: str,
) -> MessageSequence:
    """基于原始消息序列构造带规划器前缀的新序列。"""

    planner_components = clone_message_sequence(source_sequence).components
    if planner_components and isinstance(planner_components[0], TextComponent):
        planner_components[0].text = f"{planner_prefix}{planner_components[0].text}"
    else:
        planner_components.insert(0, TextComponent(planner_prefix))
    return MessageSequence(planner_components)


def build_session_message_visible_text(
    message: "SessionMessage",
    source_sequence: MessageSequence | None = None,
) -> str:
    """将真实会话消息转换为 Maisaka 可见文本。"""

    normalized_sequence = source_sequence if source_sequence is not None else message.raw_message
    user_info = message.message_info.user_info
    speaker_name = user_info.user_cardname or user_info.user_nickname or user_info.user_id
    visible_message_id = None if message.is_notify else message.message_id

    visible_sequence = MessageSequence([])
    visible_sequence.text(
        format_speaker_content(
            speaker_name,
            "",
            message.timestamp,
            visible_message_id,
        )
    )
    for component in clone_message_sequence(normalized_sequence).components:
        visible_sequence.components.append(component)
    return build_visible_text_from_sequence(visible_sequence).strip()


def drop_leading_orphan_tool_results(
    chat_history: list[LLMContextMessage],
) -> tuple[list[LLMContextMessage], int]:
    """移除历史前缀中缺少对应 tool_call 的工具结果消息。"""

    if not chat_history:
        return chat_history, 0

    available_tool_call_ids = {
        tool_call.call_id
        for message in chat_history
        if isinstance(message, AssistantMessage)
        for tool_call in message.tool_calls
        if tool_call.call_id
    }

    first_valid_index = 0
    while first_valid_index < len(chat_history):
        message = chat_history[first_valid_index]
        if not isinstance(message, ToolResultMessage):
            break
        if message.tool_call_id in available_tool_call_ids:
            break
        first_valid_index += 1

    if first_valid_index == 0:
        return chat_history, 0
    return chat_history[first_valid_index:], first_valid_index
