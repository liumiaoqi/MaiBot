from datetime import datetime
from types import SimpleNamespace

from src.chat.message_receive.message import SessionMessage
from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import MessageSequence, ReplyComponent, TextComponent
from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext


def _build_sent_message() -> SessionMessage:
    message = SessionMessage(
        message_id="real-message-id",
        timestamp=datetime(2026, 4, 5, 12, 0, 0),
        platform="qq",
    )
    message.message_info = MessageInfo(
        user_info=UserInfo(
            user_id="bot-qq",
            user_nickname="MaiSaka",
            user_cardname=None,
        ),
        group_info=None,
        additional_config={},
    )
    message.raw_message = MessageSequence(
        [
            ReplyComponent(target_message_id="m123"),
            TextComponent(text="你好"),
        ]
    )
    message.session_id = "test-session"
    message.initialized = True
    return message


def test_append_sent_message_to_chat_history_keeps_message_id() -> None:
    runtime = SimpleNamespace(_chat_history=[])
    engine = SimpleNamespace(_get_runtime_manager=lambda: None)
    tool_ctx = BuiltinToolRuntimeContext(engine=engine, runtime=runtime)

    tool_ctx.append_sent_message_to_chat_history(_build_sent_message())

    assert len(runtime._chat_history) == 1
    history_message = runtime._chat_history[0]
    assert history_message.message_id == "real-message-id"
    assert "[msg_id]real-message-id\n" in history_message.raw_message.components[0].text
    assert "[msg_id:real-message-id]" in history_message.visible_text
