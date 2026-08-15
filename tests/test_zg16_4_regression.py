"""ZG16-4 ASCII 看图功能回归测试 — 向后兼容性验证。

覆盖场景：开关关闭行为不变、有 vision 不触发、to_ascii 输出类型/无 ANSI、
AsciiImageCache 纯内存/key 用 emoji_hash、send_emoji 降级不请求 vision、
ImageComponent.content 写入 ASCII 后 binary_data 清空。
"""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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
from src.common.utils.utils_image import ImageUtils
from src.emoji_system.ascii_image_cache import AsciiImageCache
from src.maisaka.builtin_tool.send_emoji import (

    _is_ascii_fallback_enabled,
    _select_emoji_with_text_fallback,
)


# ── 测试夹具 ──────────────────────────────────────────────────────


def _make_png_bytes(size: tuple[int, int] = (100, 100)) -> bytes:
    """生成 PNG 图片字节。"""
    image = PILImage.new("RGB", size, color=(128, 128, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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


@pytest.fixture
def app_config_ascii_enabled():
    """注册 ASCII 开关开启的 AppConfigPort。"""
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port

    port = SimpleNamespace(
        get_enable_ascii_image=lambda: True,
        get_ascii_column_width=lambda: 48,
        get_ascii_main_color_count=lambda: 2,
        get_ascii_cache_max_size=lambda: 256,
        get_ascii_charset=lambda: "@%#*+=-:.",
    )
    set_app_config_port(port)
    # 重置 send_emoji 模块的全局缓存单例，避免跨测试污染
    import src.maisaka.builtin_tool.send_emoji as send_emoji_module

    original_cache = send_emoji_module._ascii_image_cache_instance
    send_emoji_module._ascii_image_cache_instance = None
    yield port
    send_emoji_module._ascii_image_cache_instance = original_cache
    reset_app_config_port()


def _make_session_message_with_image(image_bytes: bytes) -> SessionMessage:
    """构造含一张图片的 SessionMessage。"""
    from datetime import datetime

    message = SessionMessage(
        message_id="regression_msg_1",
        timestamp=datetime.now(),
        platform="test",
    )
    message.raw_message = MessageSequence([ImageComponent(binary_hash="reg_hash", binary_data=image_bytes)])
    message.message_info = SimpleNamespace(
        user_info=SimpleNamespace(user_id="u1", user_nickname="test", user_cardname=""),
        group_info=None,
        additional_config={},
    )
    message.session_id = "test_session"
    return message


# ── 回归测试用例 ──────────────────────────────────────────────────


class TestRegressionSwitchOff:
    """开关关闭行为不变。"""

    def test_switch_off_should_render_ascii_returns_false(self, app_config_ascii_disabled):
        """enable_ascii_image=false 时 _should_render_ascii 返回 False。"""
        assert _should_render_ascii(enable_visual_message=False) is False

    def test_switch_off_is_ascii_fallback_enabled_returns_false(self, app_config_ascii_disabled):
        """enable_ascii_image=false 时 _is_ascii_fallback_enabled 返回 False。"""
        assert _is_ascii_fallback_enabled() is False


class TestRegressionHasVision:
    """有 vision 不触发 ASCII 渲染。"""

    def test_has_vision_should_render_ascii_returns_false(self, app_config_ascii_enabled):
        """enable_visual_message=True 时 _should_render_ascii 返回 False。"""
        assert _should_render_ascii(enable_visual_message=True) is False


class TestRegressionToAsciiOutput:
    """to_ascii 输出类型与无 ANSI 控制字符。"""

    def test_to_ascii_returns_str_type(self):
        """to_ascii 输出为 str 类型。"""
        image_bytes = _make_png_bytes()
        result = ImageUtils.to_ascii(image_bytes)
        assert result is not None
        assert isinstance(result, str)

    def test_to_ascii_no_ansi_control_chars(self):
        """to_ascii 输出无 ANSI 控制字符。"""
        image_bytes = _make_png_bytes()
        result = ImageUtils.to_ascii(image_bytes)
        assert result is not None
        assert "\x1b" not in result
        assert "\033" not in result


class TestRegressionAsciiCacheInMemory:
    """AsciiImageCache 纯内存不落磁盘 + key 用 emoji_hash。"""

    def test_cache_is_pure_in_memory(self):
        """AsciiImageCache 纯内存不落磁盘。"""
        from collections import OrderedDict

        cache = AsciiImageCache(max_size=256)
        cache.put("h1", "text1")
        # 内部存储应为 OrderedDict（纯内存）
        assert isinstance(cache._cache, OrderedDict)
        # 不应有任何磁盘相关属性
        assert not hasattr(cache, "_file_path")
        assert not hasattr(cache, "_db_path")

    def test_cache_key_is_emoji_hash(self):
        """AsciiImageCache key 用 emoji_hash。"""
        cache = AsciiImageCache(max_size=256)
        emoji_hash = "file_hash_abc123"
        cache.put(emoji_hash, "ascii_text")
        # key 应为 emoji_hash 字符串
        assert emoji_hash in cache._cache
        keys = list(cache._cache.keys())
        assert all(isinstance(k, str) for k in keys)


class TestRegressionSendEmojiNoVision:
    """send_emoji 降级路径不请求 vision 能力。"""

    async def test_fallback_uses_text_generation_only(self, app_config_ascii_enabled, tmp_path: Path):
        """降级路径调用 run_sub_agent(capabilities=["text_generation"])。"""
        from src.common.data_models.image_data_model import MaiEmoji

        # 构造临时表情包
        image_bytes = _make_png_bytes()
        file_path = tmp_path / "reg_emoji.png"
        file_path.write_bytes(image_bytes)
        emoji = MaiEmoji(file_path)
        emoji.file_hash = "reg_hash"
        emoji.description = "回归测试表情"
        emoji.emotion = ["happy"]

        tool_ctx = MagicMock()
        tool_ctx.runtime.log_prefix = "[regression]"

        mock_response = SimpleNamespace(
            content='{"emoji_index": 1, "reason": "选择"}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="test_model",
            prompt_html_uri=None,
        )
        tool_ctx.runtime.run_sub_agent = AsyncMock(return_value=mock_response)

        await _select_emoji_with_text_fallback(tool_ctx, [emoji], "理由")

        call_kwargs = tool_ctx.runtime.run_sub_agent.call_args.kwargs
        assert call_kwargs.get("capabilities") == ["text_generation"]
        assert "vision" not in call_kwargs.get("capabilities", [])


class TestRegressionImageComponentClearBinary:
    """ImageComponent.content 写入 ASCII 后 binary_data 清空。"""

    async def test_content_set_and_binary_cleared(self, app_config_ascii_enabled):
        """ImageComponent.content 写入 ASCII 后 binary_data 清空。"""
        image_bytes = _make_png_bytes()
        message = _make_session_message_with_image(image_bytes)

        # 渲染前：binary_data 有内容，content 为空
        component_before = message.raw_message.components[0]
        assert len(component_before.binary_data) > 0
        assert component_before.content == ""

        await _render_ascii_for_image_components(message, enable_visual_message=False)

        # 渲染后：content 有 ASCII，binary_data 清空
        component_after = message.raw_message.components[0]
        assert len(component_after.content) > 0
        assert component_after.binary_data == b""