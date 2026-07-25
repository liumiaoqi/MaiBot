"""Task 1.7: PluginContext 运行时单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.sdk.context import LoggerContext, PluginContext, ScopeDeniedError


class TestLoggerContext:

    def test_info_bridges_to_logger(self) -> None:
        with patch("src.plugin_runtime_v2.sdk.context.get_logger") as mock_get:
            mock_logger = MagicMock()
            mock_get.return_value = mock_logger
            ctx = LoggerContext("test_plugin")
            ctx.info("hello %s", "world")
            mock_get.assert_called_once_with("plugin.test_plugin")
            mock_logger.info.assert_called_once_with("hello %s", "world")

    def test_debug_warning_error_all_bridged(self) -> None:
        with patch("src.plugin_runtime_v2.sdk.context.get_logger") as mock_get:
            mock_logger = MagicMock()
            mock_get.return_value = mock_logger
            ctx = LoggerContext("p")
            ctx.debug("d")
            ctx.warning("w")
            ctx.error("e")
            mock_logger.debug.assert_called_once_with("d")
            mock_logger.warning.assert_called_once_with("w")
            mock_logger.error.assert_called_once_with("e")


class TestEmitEvent:

    def test_emit_event_calls_runner(self) -> None:
        import asyncio
        runner = AsyncMock()
        runner.is_ready = True
        ctx = PluginContext("p", set(), runner, {})
        async def _run():
            await ctx.emit_event("evt", {"k": "v"})
        asyncio.get_event_loop().run_until_complete(_run())
        runner.emit_event.assert_called_once_with("evt", {"k": "v"})

    def test_emit_event_runner_not_ready_raises(self) -> None:
        import asyncio
        runner = AsyncMock()
        runner.is_ready = False
        ctx = PluginContext("p", set(), runner, {})
        async def _run():
            with pytest.raises(ConnectionError, match="Runner"):
                await ctx.emit_event("evt", {})
        asyncio.get_event_loop().run_until_complete(_run())


class TestEmitCard:

    def test_emit_card_constructs_payload(self) -> None:
        import asyncio
        runner = AsyncMock()
        runner.is_ready = True
        homecard_registry = {"my_card": {"title": "Test", "width": "large"}}
        ctx = PluginContext("p", set(), runner, homecard_registry)
        async def _run():
            await ctx.emit_card("my_card", {"score": 42})
        asyncio.get_event_loop().run_until_complete(_run())
        payload = runner.emit_event.call_args[0][1]
        assert payload["name"] == "my_card"
        assert payload["title"] == "Test"
        assert payload["width"] == "large"
        assert payload["data"] == {"score": 42}

    def test_emit_card_unregistered_logs_warning(self) -> None:
        import asyncio
        runner = AsyncMock()
        runner.is_ready = True
        ctx = PluginContext("p", set(), runner, {})
        async def _run():
            with patch.object(ctx._logger, "warning") as mock_warn:
                await ctx.emit_card("unknown", {})
                mock_warn.assert_called_once()
        asyncio.get_event_loop().run_until_complete(_run())


class TestGetSessionInfo:

    def test_get_session_info_returns_stub(self) -> None:
        import asyncio
        runner = AsyncMock()
        runner.is_ready = True
        ctx = PluginContext("p", {"session:read:detail"}, runner, {})
        async def _run():
            result = await ctx.get_session_info("s1")
            assert result["session_id"] == "s1"
        asyncio.get_event_loop().run_until_complete(_run())

    def test_get_session_info_denied_without_scope(self) -> None:
        import asyncio
        ctx = PluginContext("p", set(), MagicMock(), {})
        async def _run():
            with pytest.raises(ScopeDeniedError, match="session:read:detail"):
                await ctx.get_session_info("s1")
        asyncio.get_event_loop().run_until_complete(_run())


class TestHomeCardWidthValidation:

    def test_valid_widths_accepted(self) -> None:
        from src.plugin_runtime_v2.sdk.decorators import HomeCard
        for w in ("small", "medium", "large", "wide", "full"):
            deco = HomeCard(name="c", width=w)
            def dummy(): pass
            result = deco(dummy)
            assert result is dummy

    def test_invalid_width_raises(self) -> None:
        from src.plugin_runtime_v2.sdk.decorators import HomeCard
        with pytest.raises(ValueError, match="HomeCard width"):
            HomeCard(name="c", width="invalid")
