"""ZG16-4 ASCII 看图功能测试 — 配置默认值。

覆盖场景：开关默认关闭、列宽默认 48、主色块数默认 2、缓存上限默认 256、字符集默认。
"""

from types import SimpleNamespace

import pytest

from src.core.adapters.app_config_port import GlobalConfigAppConfigPort


# ── 测试夹具 ──────────────────────────────────────────────────────


class _MockChatConfig:
    """模拟 ChatConfig，仅含 ASCII 相关字段（使用默认值）。"""

    mid_term_memory: bool = False
    enable_ascii_image: bool = False
    ascii_column_width: int = 48
    ascii_main_color_count: int = 2
    ascii_cache_max_size: int = 256
    ascii_charset: str = "@%#*+=-:."


@pytest.fixture
def app_config_port_with_defaults():
    """注册使用默认配置的 AppConfigPort（通过 GlobalConfigAppConfigPort + mock global_config）。"""
    from src.core.app_config_port_registry import reset_app_config_port, set_app_config_port

    # 构造 mock global_config，仅含 chat 域
    mock_config = SimpleNamespace(chat=_MockChatConfig())
    port = GlobalConfigAppConfigPort()
    # patch _get_cfg 返回 mock 配置
    with patch.object(port, "_get_cfg", return_value=mock_config):
        set_app_config_port(port)
        yield port
        reset_app_config_port()


# 需要 patch 在模块级别
from unittest.mock import patch  # noqa: E402


# ── 测试用例 ──────────────────────────────────────────────────────


class TestAsciiConfigDefaults:
    """ASCII 配置默认值验证。"""

    def test_enable_ascii_image_default_false(self):
        """开关默认关闭：get_enable_ascii_image() 返回 False。"""
        port = GlobalConfigAppConfigPort()
        mock_config = SimpleNamespace(chat=_MockChatConfig())
        with patch.object(port, "_get_cfg", return_value=mock_config):
            assert port.get_enable_ascii_image() is False

    def test_ascii_column_width_default_48(self):
        """列宽默认 48：get_ascii_column_width() 返回 48。"""
        port = GlobalConfigAppConfigPort()
        mock_config = SimpleNamespace(chat=_MockChatConfig())
        with patch.object(port, "_get_cfg", return_value=mock_config):
            assert port.get_ascii_column_width() == 48

    def test_ascii_main_color_count_default_2(self):
        """主色块数默认 2：get_ascii_main_color_count() 返回 2。"""
        port = GlobalConfigAppConfigPort()
        mock_config = SimpleNamespace(chat=_MockChatConfig())
        with patch.object(port, "_get_cfg", return_value=mock_config):
            assert port.get_ascii_main_color_count() == 2

    def test_ascii_cache_max_size_default_256(self):
        """缓存上限默认 256：get_ascii_cache_max_size() 返回 256。"""
        port = GlobalConfigAppConfigPort()
        mock_config = SimpleNamespace(chat=_MockChatConfig())
        with patch.object(port, "_get_cfg", return_value=mock_config):
            assert port.get_ascii_cache_max_size() == 256

    def test_ascii_charset_default(self):
        """字符集默认：get_ascii_charset() 返回 "@%#*+=-:."。"""
        port = GlobalConfigAppConfigPort()
        mock_config = SimpleNamespace(chat=_MockChatConfig())
        with patch.object(port, "_get_cfg", return_value=mock_config):
            assert port.get_ascii_charset() == "@%#*+=-:."


class TestAsciiConfigViaRegistry:
    """通过 AppConfigPort 注册点验证默认值。"""

    def test_registry_returns_defaults(self):
        """注册 GlobalConfigAppConfigPort 后通过 registry 读取默认值。"""
        from src.core.app_config_port_registry import get_app_config_port, reset_app_config_port, set_app_config_port

        port = GlobalConfigAppConfigPort()
        mock_config = SimpleNamespace(chat=_MockChatConfig())
        with patch.object(port, "_get_cfg", return_value=mock_config):
            set_app_config_port(port)
            try:
                registry_port = get_app_config_port()
                assert registry_port.get_enable_ascii_image() is False
                assert registry_port.get_ascii_column_width() == 48
                assert registry_port.get_ascii_main_color_count() == 2
                assert registry_port.get_ascii_cache_max_size() == 256
                assert registry_port.get_ascii_charset() == "@%#*+=-:."
            finally:
                reset_app_config_port()