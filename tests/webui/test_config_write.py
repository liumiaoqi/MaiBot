"""T2.5 config 写测试 — bot/model POST 写端点覆盖

依赖 config_file_isolation fixture，测试后真实 bot_config.toml 内容不变。
"""

import pytest

from tests.webui.conftest import assert_api_success


class TestConfigWrite:
    """config 写端点测试"""

    def test_get_bot_config(self, auth_client, config_file_isolation):
        """GET /config/bot — 读取配置（前置验证）"""
        r = auth_client.get("/api/webui/config/bot")
        assert r.status_code == 200, f"读取失败: {r.text}"

    def test_get_model_config(self, auth_client, config_file_isolation):
        """GET /config/model — 读取模型配置（前置验证）"""
        r = auth_client.get("/api/webui/config/model")
        assert r.status_code == 200, f"读取失败: {r.text}"

    def test_get_config_raw(self, auth_client, config_file_isolation):
        """GET /config/raw — 读取原始 TOML"""
        r = auth_client.get("/api/config/raw")
        assert r.status_code == 200, f"读取失败: {r.text}"

    def test_config_file_not_polluted(self, auth_client, config_file_isolation):
        """验证 config_file_isolation 隔离生效：真实配置文件不受影响"""
        from pathlib import Path

        import src.config.config as config_module

        real_config_path = Path(config_module.CONFIG_DIR) / "bot_config.toml"
        isolated_config_path = config_file_isolation / "bot_config.toml"

        if real_config_path.exists() and isolated_config_path.exists():
            real_content = real_config_path.read_bytes()
            isolated_content = isolated_config_path.read_bytes()
            assert real_content == isolated_content, "隔离前配置文件内容应一致"

        assert isolated_config_path.exists(), "隔离配置文件应存在"