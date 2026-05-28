from datetime import datetime
from types import SimpleNamespace

import asyncio
import pytest

from src.chat.message_receive.message import SessionMessage
from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import (
    AtComponent,
    EmojiComponent,
    ImageComponent,
    MessageSequence,
    ReplyComponent,
    TextComponent,
)
from src.config.config import global_config
from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext
from src.maisaka.runtime import MaisakaHeartFlowChatting


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
    history_text = history_message.raw_message.components[0].text
    assert '<message msg_id="real-message-id"' in history_text
    assert 'quote="m123"' in history_text
    assert 'time="12:00:00"' in history_text
    assert 'user="MaiSaka"' in history_text
    assert "[msg_id:real-message-id]" in history_message.visible_text


@pytest.mark.asyncio
async def test_append_sent_image_message_schedules_image_recognition(monkeypatch: pytest.MonkeyPatch) -> None:
    """bot 自己发送的图片进入 Maisaka 历史时，也应触发后台识图。"""

    image_bytes = b"sent-image"
    message = _build_sent_message()
    message.raw_message = MessageSequence([ImageComponent(binary_hash="", binary_data=image_bytes)])
    runtime = MaisakaHeartFlowChatting.__new__(MaisakaHeartFlowChatting)
    runtime._chat_history = []
    runtime.log_prefix = "[test]"
    runtime._emit_monitor_message_sent = lambda **_kwargs: None

    calls: list[dict[str, object]] = []

    async def fake_get_image_description(**kwargs):
        calls.append(kwargs)
        return ""

    monkeypatch.setattr(
        "src.chat.image_system.image_manager.image_manager.get_image_description",
        fake_get_image_description,
    )

    assert runtime.append_sent_message_to_chat_history(message) is True
    await asyncio.sleep(0)

    assert len(runtime._chat_history) == 1
    assert calls == [
        {
            "image_hash": message.raw_message.components[0].binary_hash,
            "image_bytes": image_bytes,
            "wait_for_build": False,
        }
    ]


@pytest.mark.asyncio
async def test_post_process_reply_message_sequences_parses_formatted_output(monkeypatch) -> None:
    monkeypatch.setattr(global_config.chat, "enable_replyer_format_output", True)
    monkeypatch.setattr(
        "src.maisaka.builtin_tool.context.process_llm_response",
        lambda text: [text.strip()] if text.strip() else [],
    )

    target_message = SimpleNamespace(
        message_info=SimpleNamespace(
            user_info=SimpleNamespace(
                user_id="target-user",
                user_nickname="目标昵称",
                user_cardname="群名片",
            )
        )
    )
    image_message = SimpleNamespace(
        raw_message=MessageSequence(
            [
                ImageComponent(
                    binary_hash="",
                    binary_data=b"image-bytes",
                    content="[图片: 原图]",
                )
            ]
        )
    )
    runtime = SimpleNamespace(
        _chat_history=[SimpleNamespace(original_message=target_message)],
        find_source_message_by_id=lambda message_id: image_message if message_id == "image-msg" else None,
    )
    engine = SimpleNamespace(_get_runtime_manager=lambda: None)
    tool_ctx = BuiltinToolRuntimeContext(engine=engine, runtime=runtime)

    fake_emoji = SimpleNamespace(file_hash="emoji-hash", description="开心")

    async def fake_get_emoji_for_emotion(label: str):
        assert label == "开心"
        return fake_emoji

    monkeypatch.setattr("src.emoji_system.emoji_manager.emoji_manager.get_emoji_by_hash", lambda _label: None)
    monkeypatch.setattr(
        "src.emoji_system.emoji_manager.emoji_manager.get_emoji_for_emotion",
        fake_get_emoji_for_emotion,
    )

    sequences = await tool_ctx.post_process_reply_message_sequences_async(
        "<at>群名片</at><text>就这个群</text><emoji>开心</emoji>"
        '<image msg_id="image-msg" index="0">配图</image>'
    )

    assert len(sequences) == 1
    components = sequences[0].components
    assert isinstance(components[0], AtComponent)
    assert components[0].target_user_id == "target-user"
    assert isinstance(components[1], TextComponent)
    assert components[1].text == " 就这个群"
    assert isinstance(components[2], EmojiComponent)
    assert components[2].binary_hash == "emoji-hash"
    assert components[2].content == "[表情包: 开心]"
    assert isinstance(components[3], ImageComponent)
    assert components[3].binary_data == b"image-bytes"
    assert components[3].content == "[图片: 配图]"


def test_runtime_finds_source_message_from_history() -> None:
    target_message = _build_sent_message()
    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime._chat_history = [
        SimpleNamespace(message_id="other-message-id", original_message=SimpleNamespace()),
        SimpleNamespace(message_id="real-message-id", original_message=target_message),
    ]

    assert runtime.find_source_message_by_id("real-message-id") is target_message
    assert runtime.find_source_message_by_id("missing-message-id") is None
