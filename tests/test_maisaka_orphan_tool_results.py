from datetime import datetime

from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.chat_loop_service import MaisakaChatLoopService
from src.maisaka.context_messages import AssistantMessage, SessionBackedMessage, ToolResultMessage


def _build_user_message(text: str) -> SessionBackedMessage:
    return SessionBackedMessage(
        raw_message=MessageSequence([TextComponent(text)]),
        visible_text=text,
        timestamp=datetime.now(),
    )


def test_select_llm_context_messages_drops_orphan_tool_results_anywhere() -> None:
    assistant_message = AssistantMessage(
        content="",
        timestamp=datetime.now(),
        tool_calls=[ToolCall(call_id="call_1", func_name="wait", args={"seconds": 30})],
    )
    orphan_tool_message = ToolResultMessage(
        content="当前对话循环已暂停，等待新消息到来。",
        timestamp=datetime.now(),
        tool_call_id="orphan_call",
    )
    matched_tool_message = ToolResultMessage(
        content="等待 30 秒。",
        timestamp=datetime.now(),
        tool_call_id="call_1",
        tool_name="wait",
    )
    chat_history = [
        _build_user_message("第一条消息"),
        orphan_tool_message,
        assistant_message,
        matched_tool_message,
        _build_user_message("第二条消息"),
    ]

    selected_history, _ = MaisakaChatLoopService.select_llm_context_messages(
        chat_history,
        max_context_size=8,
    )

    assert orphan_tool_message not in selected_history
    assert assistant_message in selected_history
    assert matched_tool_message in selected_history
