from base64 import b64decode
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.common.data_models.message_component_data_model import ImageComponent, MessageSequence, TextComponent
from src.llm_models.payload_content.message import ImageMessagePart, RoleType
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.context_messages import (
    AssistantMessage,
    SessionBackedMessage,
    ToolResultMessage,
    build_full_complex_message_content_from_sequence,
    contains_complex_message,
)
from src.maisaka.chat_loop_service import MaisakaChatLoopService
from src.maisaka.history_post_processor import process_chat_history_after_cycle
from src.maisaka.mid_term_memory import (
    MidTermMemorySummaryModel,
    _build_summary_prompt_messages,
    _select_summary_source_messages,
    _should_enable_visual_summary,
    build_mid_term_memory_complex_message,
    insert_mid_term_memory_message,
    is_mid_term_memory_message,
)

PNG_BYTES = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _user_message(content: str) -> SessionBackedMessage:
    return SessionBackedMessage(
        raw_message=MessageSequence([TextComponent(content)]),
        visible_text=content,
        timestamp=datetime.now(),
    )


def _image_message(content: str = "") -> SessionBackedMessage:
    visible_text = content or "[图片，识别中.....]"
    return SessionBackedMessage(
        raw_message=MessageSequence(
            [ImageComponent(binary_hash="", binary_data=PNG_BYTES, content=content)]
        ),
        visible_text=visible_text,
        timestamp=datetime.now(),
    )


def _assistant_message(content: str, tool_calls: list[ToolCall] | None = None) -> AssistantMessage:
    return AssistantMessage(
        content=content,
        timestamp=datetime.now(),
        tool_calls=tool_calls or [],
    )


def _mid_term_summary(brief: str) -> SessionBackedMessage:
    return build_mid_term_memory_complex_message(
        MidTermMemorySummaryModel(
            long_summary=f"{brief} 的完整摘要",
            brief=brief,
            keywords=[brief],
        ),
        time_range="2026-05-21 10:00:00 ~ 2026-05-21 10:05:00",
        participants=["用户A"],
        source_messages=[_user_message(brief)],
    )


def test_context_optimization_keeps_latest_three_assistant_messages() -> None:
    chat_history = []
    for index in range(5):
        chat_history.append(_user_message(f"用户消息 {index}"))
        chat_history.append(_assistant_message(f"assistant {index}"))

    result = process_chat_history_after_cycle(
        chat_history,
        max_context_size=100,
        enable_context_optimization=True,
    )

    assistant_contents = [
        message.content
        for message in result.history
        if isinstance(message, AssistantMessage)
    ]
    user_contents = [
        message.visible_text
        for message in result.history
        if isinstance(message, SessionBackedMessage)
    ]

    assert assistant_contents == ["assistant 2", "assistant 3", "assistant 4"]
    assert user_contents == [f"用户消息 {index}" for index in range(5)]
    assert result.removed_count == 2
    assert result.remaining_context_count == 8


def test_context_optimization_disabled_keeps_assistant_messages() -> None:
    chat_history = [_assistant_message(f"assistant {index}") for index in range(5)]

    result = process_chat_history_after_cycle(
        chat_history,
        max_context_size=100,
        enable_context_optimization=False,
    )

    assistant_contents = [
        message.content
        for message in result.history
        if isinstance(message, AssistantMessage)
    ]

    assert assistant_contents == [f"assistant {index}" for index in range(5)]
    assert result.removed_count == 0


def test_context_optimization_preserves_trimmed_assistant_tool_content_as_user_message() -> None:
    removed_tool_call = ToolCall(call_id="removed-call", func_name="query_memory", args={"query": "旧记忆"})
    kept_tool_call = ToolCall(call_id="kept-call", func_name="reply", args={})
    chat_history = [
        _assistant_message("assistant 0", [removed_tool_call]),
        ToolResultMessage(
            content="旧工具结果",
            timestamp=datetime.now(),
            tool_call_id="removed-call",
            tool_name="query_memory",
        ),
        _assistant_message("assistant 1"),
        _assistant_message("assistant 2"),
        _assistant_message("assistant 3", [kept_tool_call]),
        ToolResultMessage(
            content="新工具结果",
            timestamp=datetime.now(),
            tool_call_id="kept-call",
            tool_name="reply",
        ),
    ]

    result = process_chat_history_after_cycle(
        chat_history,
        max_context_size=100,
        enable_context_optimization=True,
    )

    tool_results = [
        message.content
        for message in result.history
        if isinstance(message, ToolResultMessage)
    ]
    folded_tool_messages = [
        message.visible_text
        for message in result.history
        if isinstance(message, SessionBackedMessage) and message.source_kind == "optimized_tool_history"
    ]

    assert tool_results == ["新工具结果"]
    assert len(folded_tool_messages) == 1
    assert "removed-call" in folded_tool_messages[0]
    assert "query_memory" in folded_tool_messages[0]
    assert "旧记忆" in folded_tool_messages[0]
    assert "旧工具结果" in folded_tool_messages[0]
    assert result.removed_count == 1


def test_context_optimization_keeps_tool_result_media_after_tool_history_is_folded() -> None:
    removed_tool_call = ToolCall(call_id="removed-call", func_name="image_tool", args={"prompt": "cat"})
    tool_result_content = "\n".join(
        [
            "image ready",
            "<tool_result_media_list>",
            '  <media msg_id="tool_result:removed-call:1" type="image" mime="image/png" />',
            "</tool_result_media_list>",
        ]
    )
    media_message = SessionBackedMessage(
        raw_message=MessageSequence(
            [
                TextComponent('<tool_result_media msg_id="tool_result:removed-call:1" />'),
                ImageComponent(binary_hash="", binary_data=b"image-bytes"),
            ]
        ),
        visible_text='<tool_result_media msg_id="tool_result:removed-call:1" />\n[图片]',
        timestamp=datetime.now(),
        message_id="tool_result:removed-call:1",
        source_kind="tool_result_media",
    )
    chat_history = [
        _assistant_message("", [removed_tool_call]),
        ToolResultMessage(
            content=tool_result_content,
            timestamp=datetime.now(),
            tool_call_id="removed-call",
            tool_name="image_tool",
        ),
        media_message,
        _assistant_message("assistant 1"),
        _assistant_message("assistant 2"),
        _assistant_message("assistant 3"),
    ]

    result = process_chat_history_after_cycle(
        chat_history,
        max_context_size=100,
        enable_context_optimization=True,
    )

    tool_results = [message for message in result.history if isinstance(message, ToolResultMessage)]
    folded_tool_messages = [
        message
        for message in result.history
        if isinstance(message, SessionBackedMessage) and message.source_kind == "optimized_tool_history"
    ]
    media_messages = [
        message
        for message in result.history
        if isinstance(message, SessionBackedMessage) and message.source_kind == "tool_result_media"
    ]

    assert tool_results == []
    assert len(folded_tool_messages) == 1
    assert "removed-call" in folded_tool_messages[0].visible_text
    assert media_messages == [media_message]
    assert any(isinstance(component, ImageComponent) for component in media_messages[0].raw_message.components)


@pytest.mark.parametrize("tool_name", ["continue", "finish", "no_action", "reply", "wait"])
def test_context_optimization_drops_trimmed_control_tools_without_folding(tool_name: str) -> None:
    control_tool_call = ToolCall(call_id=f"{tool_name}-call", func_name=tool_name, args={})
    chat_history = [
        _assistant_message("assistant 0", [control_tool_call]),
        ToolResultMessage(
            content=f"{tool_name} 工具结果",
            timestamp=datetime.now(),
            tool_call_id=f"{tool_name}-call",
            tool_name=tool_name,
        ),
        _assistant_message("assistant 1"),
        _assistant_message("assistant 2"),
        _assistant_message("assistant 3"),
    ]

    result = process_chat_history_after_cycle(
        chat_history,
        max_context_size=100,
        enable_context_optimization=True,
    )

    folded_tool_messages = [
        message
        for message in result.history
        if isinstance(message, SessionBackedMessage) and message.source_kind == "optimized_tool_history"
    ]
    tool_results = [message for message in result.history if isinstance(message, ToolResultMessage)]

    assert folded_tool_messages == []
    assert tool_results == []


def test_trim_keeps_mid_term_memory_and_removes_old_normal_messages() -> None:
    summary_message = _mid_term_summary("旧摘要")
    chat_history = [
        summary_message,
        *[_user_message(f"用户消息 {index}") for index in range(8)],
    ]

    result = process_chat_history_after_cycle(
        chat_history,
        max_context_size=3,
        enable_context_optimization=False,
    )

    assert result.history[0] is summary_message
    assert [message.visible_text for message in result.history[1:]] == [
        "用户消息 6",
        "用户消息 7",
    ]
    assert [message.visible_text for message in result.removed_messages] == [
        "用户消息 0",
        "用户消息 1",
        "用户消息 2",
        "用户消息 3",
        "用户消息 4",
        "用户消息 5",
    ]


def test_mid_term_memory_summary_source_filters_assistant_messages() -> None:
    user_message = _user_message("用户信息")
    assistant_message = _assistant_message("assistant 信息")
    empty_user_message = _user_message("")
    tool_message = ToolResultMessage(
        content="工具结果",
        timestamp=datetime.now(),
        tool_call_id="tool-call",
        tool_name="search",
    )

    selected_messages = _select_summary_source_messages(
        [assistant_message, tool_message, user_message, empty_user_message],
    )

    assert selected_messages == [user_message]


def test_mid_term_memory_summary_prompt_uses_multi_messages() -> None:
    first_message = _user_message("用户消息 1")
    second_message = _user_message("用户消息 2")

    prompt_messages = _build_summary_prompt_messages(
        [first_message, second_message],
        instruction_prompt="系统指令",
    )

    assert [message.role for message in prompt_messages] == [
        RoleType.System,
        RoleType.User,
        RoleType.User,
    ]
    assert prompt_messages[0].get_text_content() == "系统指令"
    assert prompt_messages[1].get_text_content() == "用户消息 1"
    assert prompt_messages[2].get_text_content() == "用户消息 2"


def test_mid_term_memory_summary_prompt_uses_text_fallback_without_visual_model() -> None:
    prompt_messages = _build_summary_prompt_messages(
        [_image_message()],
        instruction_prompt="系统指令",
        enable_visual_message=False,
    )

    assert len(prompt_messages) == 2
    assert prompt_messages[1].get_text_content() == "[图片，识别中.....]"
    assert not any(isinstance(part, ImageMessagePart) for part in prompt_messages[1].parts)


def test_mid_term_memory_summary_prompt_attaches_image_for_visual_model() -> None:
    prompt_messages = _build_summary_prompt_messages(
        [_image_message()],
        instruction_prompt="系统指令",
        enable_visual_message=True,
    )

    assert len(prompt_messages) == 2
    assert prompt_messages[1].get_text_content() == ""
    assert any(isinstance(part, ImageMessagePart) for part in prompt_messages[1].parts)


def test_mid_term_memory_visual_summary_follows_model_capability() -> None:
    assert _should_enable_visual_summary(SimpleNamespace(visual=True)) is True
    assert _should_enable_visual_summary(SimpleNamespace(visual=False)) is False
    assert _should_enable_visual_summary(None) is False


def test_insert_mid_term_memory_message_after_previous_summary_and_limits_count() -> None:
    first_summary = _mid_term_summary("摘要1")
    second_summary = _mid_term_summary("摘要2")
    third_summary = _mid_term_summary("摘要3")
    latest_user_message = _user_message("最新消息")

    history = insert_mid_term_memory_message(
        [first_summary, second_summary, latest_user_message],
        third_summary,
        max_summary_count=2,
    )

    assert history == [second_summary, third_summary, latest_user_message]
    assert [is_mid_term_memory_message(message) for message in history] == [True, True, False]


def test_mid_term_memory_message_is_expandable_complex_message() -> None:
    summary_message = _mid_term_summary("摘要")

    assert contains_complex_message(summary_message.raw_message) is True
    assert summary_message.message_id is not None
    assert summary_message.message_id.startswith("mtm:")
    assert 'user="' not in summary_message.prompt_text
    assert "可以选择使用 view_complex_message 查看这段聊天记录的完整信息，获取关键信息和细节信息。" in summary_message.prompt_text

    full_text = build_full_complex_message_content_from_sequence(summary_message.raw_message)

    assert "【聊天记录摘要】" in full_text
    assert "long_summary:" in full_text
    assert "摘要 的完整摘要" in full_text


def test_context_selection_pins_mid_term_memory_message_outside_recent_window() -> None:
    summary_message = _mid_term_summary("置顶摘要")
    chat_history = [
        summary_message,
        *[_user_message(f"用户消息 {index}") for index in range(30)],
    ]

    selected_history, selection_reason = MaisakaChatLoopService.select_llm_context_messages(
        chat_history,
        enable_visual_message=False,
        request_kind="planner",
        max_context_size=5,
    )

    assert selected_history[0] is summary_message
    assert [message.visible_text for message in selected_history[1:]] == [
        f"用户消息 {index}" for index in range(20, 30)
    ]
    assert "中期摘要 1 条" in selection_reason
