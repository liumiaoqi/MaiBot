"""ZG16-4 ASCII 看图功能测试 — send_emoji ASCII 降级路径。

覆盖场景：_is_ascii_fallback_enabled 开关、_build_emoji_text_candidate_prompt 拼接、
降级不触发、无可用表情包、无效序号回退、结果解析失败回退、不请求 vision 能力。
"""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from PIL import Image as PILImage

from src.common.data_models.image_data_model import MaiEmoji
from src.maisaka.builtin_tool.send_emoji import (
    _build_emoji_text_candidate_prompt,
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


def _make_mai_emoji(file_path: Path, file_hash: str, description: str = "", emotion: list[str] | None = None) -> MaiEmoji:
    """构造 MaiEmoji 实例。"""
    emoji = MaiEmoji(file_path)
    emoji.file_hash = file_hash
    emoji.description = description
    emoji.emotion = emotion or []
    return emoji


@pytest.fixture
def app_config_port_ascii_enabled():
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


@pytest.fixture
def app_config_port_ascii_disabled():
    """注册 ASCII 开关关闭的 AppConfigPort。"""
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port

    port = SimpleNamespace(
        get_enable_ascii_image=lambda: False,
        get_ascii_column_width=lambda: 48,
        get_ascii_main_color_count=lambda: 2,
        get_ascii_cache_max_size=lambda: 256,
        get_ascii_charset=lambda: "@%#*+=-:.",
    )
    set_app_config_port(port)
    yield port
    reset_app_config_port()


@pytest.fixture
def temp_emoji_files(tmp_path: Path) -> list[MaiEmoji]:
    """创建 3 个临时表情包文件。"""
    emojis = []
    for i in range(3):
        image_bytes = _make_png_bytes()
        file_path = tmp_path / f"emoji_{i}.png"
        file_path.write_bytes(image_bytes)
        emoji = _make_mai_emoji(
            file_path,
            file_hash=f"hash_{i}",
            description=f"描述_{i}" if i > 0 else "",
            emotion=[f"情绪_{i}"] if i > 0 else [],
        )
        emojis.append(emoji)
    return emojis


# ── 测试用例 ──────────────────────────────────────────────────────


class TestIsAsciiFallbackEnabled:
    """_is_ascii_fallback_enabled 开关判断。"""

    def test_returns_true_when_ascii_enabled(self, app_config_port_ascii_enabled):
        """enable_ascii_image=true → 返回 True。"""
        assert _is_ascii_fallback_enabled() is True

    def test_returns_false_when_ascii_disabled(self, app_config_port_ascii_disabled):
        """enable_ascii_image=false → 返回 False。"""
        assert _is_ascii_fallback_enabled() is False


class TestBuildEmojiTextCandidatePrompt:
    """_build_emoji_text_candidate_prompt 拼接候选 ASCII + 描述/情绪标签。"""

    def test_prompt_contains_all_candidates(self, temp_emoji_files):
        """候选 3 个 → prompt 含 3 段 ASCII + 描述/情绪标签。"""
        emojis = temp_emoji_files
        ascii_texts = ["ascii_0", "ascii_1", "ascii_2"]
        prompt = _build_emoji_text_candidate_prompt(emojis, ascii_texts, "测试理由")
        # 应含 3 个候选标记
        assert "[候选 1]" in prompt
        assert "[候选 2]" in prompt
        assert "[候选 3]" in prompt
        # 应含 ASCII 文本
        assert "ascii_0" in prompt
        assert "ascii_1" in prompt
        assert "ascii_2" in prompt
        # 应含理由
        assert "测试理由" in prompt
        # 应含描述和情绪标签
        assert "描述：" in prompt
        assert "情绪标签：" in prompt

    def test_empty_description_shows_no_description_marker(self, temp_emoji_files):
        """描述为空 → 标注"无描述辅助"。"""
        emojis = temp_emoji_files  # emoji_0 描述为空
        ascii_texts = ["ascii_0", "ascii_1", "ascii_2"]
        prompt = _build_emoji_text_candidate_prompt(emojis, ascii_texts, "理由")
        assert "无描述辅助" in prompt

    def test_prompt_contains_emotion_tags(self, temp_emoji_files):
        """情绪标签非空 → prompt 含情绪标签列表。"""
        emojis = temp_emoji_files
        ascii_texts = ["ascii_0", "ascii_1", "ascii_2"]
        prompt = _build_emoji_text_candidate_prompt(emojis, ascii_texts, "理由")
        # emoji_1 情绪为 ["情绪_1"]
        assert "情绪_1" in prompt
        assert "情绪_2" in prompt


class TestSelectEmojiWithTextFallback:
    """_select_emoji_with_text_fallback 文本降级选择主逻辑。"""

    async def test_empty_sampled_emojis_returns_none(self, app_config_port_ascii_enabled):
        """无可用表情包：sampled_emojis 为空 → 返回 (None, "")。"""
        tool_ctx = MagicMock()
        result = await _select_emoji_with_text_fallback(tool_ctx, [], "理由")
        assert result == (None, "")

    async def test_invalid_index_falls_back_to_first(
        self, app_config_port_ascii_enabled, temp_emoji_files
    ):
        """无效序号回退：emoji_index < 1 或 > 候选数 → 回退首项。"""
        emojis = temp_emoji_files
        tool_ctx = MagicMock()
        tool_ctx.runtime.log_prefix = "[test]"

        # mock run_sub_agent 返回 emoji_index=99（超出范围）
        mock_response = SimpleNamespace(
            content='{"emoji_index": 99, "reason": "无效序号"}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="test_model",
            prompt_html_uri=None,
        )
        tool_ctx.runtime.run_sub_agent = AsyncMock(return_value=mock_response)

        selected, reason = await _select_emoji_with_text_fallback(tool_ctx, emojis, "理由")
        # 应回退到首项
        assert selected is emojis[0]

    async def test_index_below_one_falls_back_to_first(
        self, app_config_port_ascii_enabled, temp_emoji_files
    ):
        """emoji_index < 1 → 回退首项。"""
        emojis = temp_emoji_files
        tool_ctx = MagicMock()
        tool_ctx.runtime.log_prefix = "[test]"

        mock_response = SimpleNamespace(
            content='{"emoji_index": 0, "reason": "零序号"}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="test_model",
            prompt_html_uri=None,
        )
        tool_ctx.runtime.run_sub_agent = AsyncMock(return_value=mock_response)

        selected, reason = await _select_emoji_with_text_fallback(tool_ctx, emojis, "理由")
        assert selected is emojis[0]

    async def test_invalid_json_falls_back_to_first(
        self, app_config_port_ascii_enabled, temp_emoji_files
    ):
        """结果解析失败：返回非合法 JSON → 回退首项。"""
        emojis = temp_emoji_files
        tool_ctx = MagicMock()
        tool_ctx.runtime.log_prefix = "[test]"

        mock_response = SimpleNamespace(
            content="这不是合法 JSON",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="test_model",
            prompt_html_uri=None,
        )
        tool_ctx.runtime.run_sub_agent = AsyncMock(return_value=mock_response)

        selected, reason = await _select_emoji_with_text_fallback(tool_ctx, emojis, "理由")
        assert selected is emojis[0]
        assert reason == ""

    async def test_does_not_request_vision_capability(
        self, app_config_port_ascii_enabled, temp_emoji_files
    ):
        """降级路径调用 run_sub_agent(capabilities=["text_generation"])，不请求 vision。"""
        emojis = temp_emoji_files
        tool_ctx = MagicMock()
        tool_ctx.runtime.log_prefix = "[test]"

        mock_response = SimpleNamespace(
            content='{"emoji_index": 1, "reason": "选择第一张"}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="test_model",
            prompt_html_uri=None,
        )
        tool_ctx.runtime.run_sub_agent = AsyncMock(return_value=mock_response)

        await _select_emoji_with_text_fallback(tool_ctx, emojis, "理由")

        # 校验 run_sub_agent 调用参数中 capabilities 为 ["text_generation"]
        call_kwargs = tool_ctx.runtime.run_sub_agent.call_args.kwargs
        assert call_kwargs.get("capabilities") == ["text_generation"]
        assert "vision" not in call_kwargs.get("capabilities", [])

    async def test_valid_index_returns_correct_emoji(
        self, app_config_port_ascii_enabled, temp_emoji_files
    ):
        """合法序号 → 返回对应表情。"""
        emojis = temp_emoji_files
        tool_ctx = MagicMock()
        tool_ctx.runtime.log_prefix = "[test]"

        mock_response = SimpleNamespace(
            content='{"emoji_index": 2, "reason": "选第二张"}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            model_name="test_model",
            prompt_html_uri=None,
        )
        tool_ctx.runtime.run_sub_agent = AsyncMock(return_value=mock_response)

        selected, reason = await _select_emoji_with_text_fallback(tool_ctx, emojis, "理由")
        assert selected is emojis[1]  # emoji_index=2 对应索引 1


class TestFallbackNotTriggered:
    """降级不触发-开关关闭。"""

    def test_ascii_disabled_fallback_not_triggered(self, app_config_port_ascii_disabled):
        """enable_ascii_image=false → _is_ascii_fallback_enabled 返回 False，不走降级。"""
        # _is_ascii_fallback_enabled 是降级入口的开关，返回 False 即不会走降级
        assert _is_ascii_fallback_enabled() is False