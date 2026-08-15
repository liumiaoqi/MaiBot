"""ZG16-4 ASCII 看图功能测试 — 图片接收链路触发判断。

覆盖场景：_should_render_ascii 触发条件、_render_ascii_for_image_components
含图消息渲染/有 vision 不变/开关关闭不变/渲染失败降级/批量部分失败。
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from PIL import Image as PILImage

from src.chat.message_receive.bot import (
    _render_ascii_for_image_components,
    _should_render_ascii,
)
from src.common.data_models.message_component_data_model import (
    ImageComponent,
    MessageSequence,
)
from src.common.data_models.session_message_data_model import SessionMessage


# ── 测试夹具 ──────────────────────────────────────────────────────


def _make_png_bytes(size: tuple[int, int] = (100, 100), color: tuple[int, int, int] = (128, 128, 128)) -> bytes:
    """生成 PNG 图片字节。"""
    image = PILImage.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def app_config_ascii_enabled():
    """注册 ASCII 开关开启的 AppConfigPort。"""
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port

    port = SimpleNamespace(
        get_enable_ascii_image=lambda: True,
        get_ascii_column_width=lambda: 48,
        get_ascii_main_color_count=lambda: 2,
        get_ascii_charset=lambda: "@%#*+=-:.",
    )
    set_app_config_port(port)
    yield port
    reset_app_config_port()


@pytest.fixture
def app_config_ascii_disabled():
    """注册 ASCII 开关关闭的 AppConfigPort。"""
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port

    port = SimpleNamespace(
        get_enable_ascii_image=lambda: False,
        get_ascii_column_width=lambda: 48,
        get_ascii_main_color_count=lambda: 2,
        get_ascii_charset=lambda: "@%#*+=-:.",
    )
    set_app_config_port(port)
    yield port
    reset_app_config_port()


def _make_session_message_with_image(image_bytes: bytes) -> SessionMessage:
    """构造含一张图片的 SessionMessage。"""
    from datetime import datetime

    message = SessionMessage(
        message_id="test_msg_1",
        timestamp=datetime.now(),
        platform="test",
    )
    message.raw_message = MessageSequence([ImageComponent(binary_hash="test_hash", binary_data=image_bytes)])
    message.message_info = SimpleNamespace(
        user_info=SimpleNamespace(user_id="u1", user_nickname="test", user_cardname=""),
        group_info=None,
        additional_config={},
    )
    message.session_id = "test_session"
    return message


def _make_session_message_with_multiple_images(image_bytes_list: list[bytes]) -> SessionMessage:
    """构造含多张图片的 SessionMessage。"""
    from datetime import datetime

    components = [ImageComponent(binary_hash=f"hash_{i}", binary_data=bytes_data) for i, bytes_data in enumerate(image_bytes_list)]
    message = SessionMessage(
        message_id="test_msg_multi",
        timestamp=datetime.now(),
        platform="test",
    )
    message.raw_message = MessageSequence(components)
    message.message_info = SimpleNamespace(
        user_info=SimpleNamespace(user_id="u1", user_nickname="test", user_cardname=""),
        group_info=None,
        additional_config={},
    )
    message.session_id = "test_session"
    return message


# ── 测试用例 ──────────────────────────────────────────────────────


class TestShouldRenderAscii:
    """_should_render_ascii 触发条件判断。"""

    def test_no_vision_and_ascii_enabled_returns_true(self, app_config_ascii_enabled):
        """无 vision + 开关开启 → True。"""
        # enable_visual_message=False 表示无 vision
        assert _should_render_ascii(enable_visual_message=False) is True

    def test_has_vision_returns_false(self, app_config_ascii_enabled):
        """有 vision → False（enable_visual_message=True）。"""
        assert _should_render_ascii(enable_visual_message=True) is False

    def test_ascii_disabled_returns_false(self, app_config_ascii_disabled):
        """开关关闭 → False。"""
        assert _should_render_ascii(enable_visual_message=False) is False


class TestRenderAsciiForImageComponents:
    """_render_ascii_for_image_components 条件性渲染。"""

    async def test_no_vision_enabled_renders_ascii(self, app_config_ascii_enabled):
        """无 vision + 开关开启 + 含图消息 → ImageComponent.content 为 ASCII 文本 + binary_data 为空。"""
        image_bytes = _make_png_bytes()
        message = _make_session_message_with_image(image_bytes)
        original_binary = message.raw_message.components[0].binary_data
        assert len(original_binary) > 0

        await _render_ascii_for_image_components(message, enable_visual_message=False)

        component = message.raw_message.components[0]
        # content 应为 ASCII 文本
        assert isinstance(component.content, str)
        assert len(component.content) > 0
        # binary_data 应被清空
        assert component.binary_data == b""

    async def test_has_vision_keeps_components_unchanged(self, app_config_ascii_enabled):
        """有 vision → 所有 ImageComponent 不变。"""
        image_bytes = _make_png_bytes()
        message = _make_session_message_with_image(image_bytes)
        original_content = message.raw_message.components[0].content
        original_binary = message.raw_message.components[0].binary_data

        await _render_ascii_for_image_components(message, enable_visual_message=True)

        component = message.raw_message.components[0]
        assert component.content == original_content
        assert component.binary_data == original_binary

    async def test_ascii_disabled_keeps_components_unchanged(self, app_config_ascii_disabled):
        """开关关闭 → 所有 ImageComponent 不变。"""
        image_bytes = _make_png_bytes()
        message = _make_session_message_with_image(image_bytes)
        original_content = message.raw_message.components[0].content
        original_binary = message.raw_message.components[0].binary_data

        await _render_ascii_for_image_components(message, enable_visual_message=False)

        component = message.raw_message.components[0]
        assert component.content == original_content
        assert component.binary_data == original_binary

    async def test_render_failure_keeps_placeholder_and_no_block(self, app_config_ascii_enabled):
        """渲染失败 → content 留空走既有占位 + 不阻断。"""
        image_bytes = _make_png_bytes()
        message = _make_session_message_with_image(image_bytes)
        original_content = message.raw_message.components[0].content

        # mock to_ascii 返回 None 模拟渲染失败
        with patch("src.chat.message_receive.bot.ImageUtils.to_ascii", return_value=None):
            # 不应抛异常
            await _render_ascii_for_image_components(message, enable_visual_message=False)

        component = message.raw_message.components[0]
        # content 应保持原值（留空走既有占位）
        assert component.content == original_content
        # binary_data 应保持不变（未被清空）
        assert component.binary_data == image_bytes

    async def test_batch_partial_failure(self, app_config_ascii_enabled):
        """多张图片部分渲染失败 → 成功的走 ASCII，失败的走占位。"""
        good_bytes = _make_png_bytes((100, 100), (128, 128, 128))
        bad_bytes = _make_png_bytes((200, 200), (64, 64, 64))
        message = _make_session_message_with_multiple_images([good_bytes, bad_bytes])

        # mock to_ascii：第一次成功，第二次失败
        call_count = [0]
        original_to_ascii = __import__("src.common.utils.utils_image", fromlist=["ImageUtils"]).ImageUtils.to_ascii

        def selective_to_ascii(image_bytes, *, column_width, charset, main_color_count):
            call_count[0] += 1
            if call_count[0] == 2:
                return None  # 第二次失败
            return original_to_ascii(image_bytes, column_width=column_width, charset=charset, main_color_count=main_color_count)

        with patch("src.chat.message_receive.bot.ImageUtils.to_ascii", side_effect=selective_to_ascii):
            await _render_ascii_for_image_components(message, enable_visual_message=False)

        components = message.raw_message.components
        # 第一张成功：content 有 ASCII，binary_data 清空
        assert len(components[0].content) > 0
        assert components[0].binary_data == b""
        # 第二张失败：content 保持原值，binary_data 保持不变
        assert components[1].binary_data == bad_bytes