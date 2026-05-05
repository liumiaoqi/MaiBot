from datetime import datetime
from pathlib import Path

import sys

from src.chat.message_receive.message import SessionMessage
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.message_adapter import build_message, get_message_kind, get_message_role, get_tool_call_id, get_tool_calls


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_build_message_returns_session_message_with_maisaka_metadata() -> None:
    timestamp = datetime.now()
    tool_call = ToolCall(
        call_id="call-1",
        func_name="reply",
        args={"message_id": "msg-1"},
    )
    raw_message = MessageSequence(components=[TextComponent(text="内部消息内容")])

    message = build_message(
        role="assistant",
        content="展示消息内容",
        message_kind="perception",
        source="assistant",
        tool_call_id="call-1",
        tool_calls=[tool_call],
        timestamp=timestamp,
        message_id="maisaka-msg-1",
        raw_message=raw_message,
        display_text="展示消息内容",
    )

    assert isinstance(message, SessionMessage)
    assert message.initialized is True
    assert message.message_id == "maisaka-msg-1"
    assert message.timestamp == timestamp
    assert message.processed_plain_text == "展示消息内容"
    assert message.raw_message is raw_message

    assert get_message_role(message) == "assistant"
    assert get_message_kind(message) == "perception"
    assert get_tool_call_id(message) == "call-1"

    restored_tool_calls = get_tool_calls(message)
    assert len(restored_tool_calls) == 1
    assert restored_tool_calls[0].call_id == "call-1"
    assert restored_tool_calls[0].func_name == "reply"
    assert restored_tool_calls[0].args == {"message_id": "msg-1"}
