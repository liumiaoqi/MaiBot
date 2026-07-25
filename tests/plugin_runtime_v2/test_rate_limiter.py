"""Phoenix-5 PluginRateLimiter 单元测试。"""

from __future__ import annotations

from src.plugin_runtime_v2.host.rate_limiter import PluginRateLimiter


class TestPluginRateLimiter:
    def test_check_allows_under_limit(self):
        rl = PluginRateLimiter(default_rpm=60)
        for _ in range(30):
            assert rl.check("test_plugin")

    def test_check_blocks_over_limit(self):
        rl = PluginRateLimiter(default_rpm=2)
        assert rl.check("test_plugin")
        assert rl.check("test_plugin")
        assert not rl.check("test_plugin")

    def test_custom_limit(self):
        rl = PluginRateLimiter(default_rpm=60)
        rl.set_limit("test_plugin", rpm=1)
        assert rl.check("test_plugin")
        assert not rl.check("test_plugin")

    def test_reset_clears_counter(self):
        rl = PluginRateLimiter(default_rpm=1)
        rl.check("test_plugin")
        assert not rl.check("test_plugin")
        rl.reset("test_plugin")
        assert rl.check("test_plugin")
