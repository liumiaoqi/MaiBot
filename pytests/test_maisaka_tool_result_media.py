from base64 import b64encode
from datetime import datetime
from types import SimpleNamespace

import asyncio
import pytest

from src.common.data_models.message_component_data_model import ImageComponent, MessageSequence, TextComponent
from src.core.tooling import ToolContentItem, ToolExecutionResult
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.chat_history_visual_refresher import has_pending_image_recognition
from src.maisaka.chat_history_visual_refresher import refresh_chat_history_visual_placeholders
from src.maisaka.context_messages import SessionBackedMessage
from src.maisaka.reasoning_engine import MaisakaReasoningEngine


def _build_engine() -> MaisakaReasoningEngine:
    engine = MaisakaReasoningEngine.__new__(MaisakaReasoningEngine)
    engine._runtime = SimpleNamespace(_chat_history=[], log_prefix="[test]")
    return engine


@pytest.mark.asyncio
async def test_tool_result_image_is_registered_for_recognition(monkeypatch: pytest.MonkeyPatch) -> None:
    """tool result 返回的图片应进入 image_manager 识图链路。"""

    image_bytes = b"tool-image"
    engine = _build_engine()
    calls: list[dict[str, object]] = []

    async def fake_get_image_description(**kwargs):
        calls.append(kwargs)
        return ""

    monkeypatch.setattr(
        "src.chat.image_system.image_manager.image_manager.get_image_description",
        fake_get_image_description,
    )

    engine._append_tool_result_media_messages(
        ToolCall(call_id="call-1", func_name="tool_with_image"),
        ToolExecutionResult(
            tool_name="tool_with_image",
            success=True,
            content_items=[
                ToolContentItem(
                    content_type="image",
                    data=b64encode(image_bytes).decode("ascii"),
                    mime_type="image/png",
                    name="result.png",
                )
            ],
        ),
    )
    await asyncio.sleep(0)

    assert len(engine._runtime._chat_history) == 1
    image_component = engine._runtime._chat_history[0].raw_message.components[1]
    assert isinstance(image_component, ImageComponent)
    assert calls == [
        {
            "image_hash": image_component.binary_hash,
            "image_bytes": image_bytes,
            "wait_for_build": False,
        }
    ]


def test_tool_result_image_without_original_message_is_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """tool result media 没有 original_message，也应被 planner 等待逻辑扫描到。"""

    image_component = ImageComponent(binary_hash="", binary_data=b"tool-image")
    history_message = SessionBackedMessage(
        raw_message=MessageSequence([TextComponent("<tool_result_media />"), image_component]),
        visible_text="<tool_result_media />\n[图片]",
        timestamp=datetime.now(),
        message_id="tool_result:call-1:1",
        source_kind="tool_result_media",
    )
    monkeypatch.setattr("src.maisaka.chat_history_visual_refresher._is_vlm_task_configured", lambda: True)
    monkeypatch.setattr(
        "src.maisaka.chat_history_visual_refresher._is_image_description_pending",
        lambda image_hash: False,
    )
    monkeypatch.setattr(
        "src.maisaka.chat_history_visual_refresher._lookup_cached_image_description",
        lambda image_hash: "",
    )

    assert has_pending_image_recognition([history_message]) is True


@pytest.mark.asyncio
async def test_tool_result_image_without_original_message_refreshes_from_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """tool result media 没有 original_message，也应能从缓存描述回填 raw_message。"""

    image_component = ImageComponent(binary_hash="image-hash", content="", binary_data=b"")
    history_message = SessionBackedMessage(
        raw_message=MessageSequence([TextComponent("<tool_result_media />"), image_component]),
        visible_text="<tool_result_media />\n[图片]",
        timestamp=datetime.now(),
        message_id="tool_result:call-1:1",
        source_kind="tool_result_media",
    )
    monkeypatch.setattr(
        "src.maisaka.chat_history_visual_refresher._lookup_cached_image_description",
        lambda image_hash: "一张工具结果图",
    )

    refreshed_count = await refresh_chat_history_visual_placeholders(
        chat_history=[history_message],
        build_history_message=lambda message, source_kind: None,
        build_visible_text=lambda message, source_kind: "",
    )

    assert refreshed_count == 1
    assert image_component.content == "[图片：一张工具结果图]"
    assert "[图片：一张工具结果图]" in history_message.visible_text
