"""Task 5.2: EventDispatcher 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher


class TestDispatch:

    @pytest.mark.asyncio
    async def test_dispatch_null_declaration_logs_warning(self):
        dispatcher = EventDispatcher()
        with patch("src.plugin_runtime_v2.mcp.event_dispatcher.logger.warning") as mock_warn:
            await dispatcher.dispatch("evt", {}, "p1", None)
            mock_warn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_homecard_logs_info(self):
        dispatcher = EventDispatcher()
        decl = MagicMock()
        decl.card_metadata = {"title": "Test Card"}
        with patch("src.plugin_runtime_v2.mcp.event_dispatcher.logger.info") as mock_info:
            await dispatcher.dispatch("evt", {}, "p1", decl)
            mock_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_think_trigger_logs_info(self):
        dispatcher = EventDispatcher()
        decl = MagicMock()
        decl.card_metadata = None
        with patch("src.plugin_runtime_v2.mcp.event_dispatcher.logger.info") as mock_info:
            await dispatcher.dispatch("message_received", {}, "p1", decl)
            mock_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_normal_event_logs_info(self):
        dispatcher = EventDispatcher()
        decl = MagicMock()
        decl.card_metadata = None
        with patch("src.plugin_runtime_v2.mcp.event_dispatcher.logger.info") as mock_info:
            await dispatcher.dispatch("custom", {}, "p1", decl)
            mock_info.assert_called_once()
