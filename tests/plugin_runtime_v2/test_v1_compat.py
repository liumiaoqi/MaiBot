"""Phoenix-8 V1 兼容层单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.maibot_team.v1_compat.capability_bridge import CapabilityBridge
from plugins.maibot_team.v1_compat.component_bridge import ComponentBridge
from plugins.maibot_team.v1_compat.config import CompatConfig


class TestComponentBridgeDispatch:

    @pytest.mark.asyncio
    async def test_tool_dispatch(self):
        bridge = ComponentBridge()
        mock_compat = AsyncMock()
        mock_compat.invoke_component.return_value = {"success": True, "result": "ok"}
        bridge.set_bridge(mock_compat)
        bridge.register_v1_components("p1", [{"name": "t1", "component_type": "TOOL"}], [], [])
        result = await bridge.invoke_component("p1.t1", {"arg": 1})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_action_dispatch(self):
        bridge = ComponentBridge()
        mock_compat = AsyncMock()
        mock_compat.invoke_component.return_value = {"success": True}
        bridge.set_bridge(mock_compat)
        bridge.register_v1_components("p1", [{"name": "a1", "component_type": "ACTION"}], [], [])
        result = await bridge.invoke_component("p1.a1", {})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_command_dispatch(self):
        bridge = ComponentBridge()
        mock_compat = AsyncMock()
        mock_compat.invoke_component.return_value = {"success": True}
        bridge.set_bridge(mock_compat)
        bridge.register_v1_components("p1", [{"name": "cmd1", "component_type": "COMMAND"}], [], [])
        result = await bridge.invoke_component("p1.cmd1", {})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_api_dispatch(self):
        bridge = ComponentBridge()
        mock_compat = AsyncMock()
        mock_compat.invoke_component.return_value = {"success": True}
        bridge.set_bridge(mock_compat)
        bridge.register_v1_components("p1", [{"name": "api1", "component_type": "API"}], [], [])
        result = await bridge.invoke_component("p1.api1", {})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_llm_provider_dispatch(self):
        bridge = ComponentBridge()
        mock_compat = AsyncMock()
        mock_compat.invoke_component.return_value = {"success": True}
        bridge.set_bridge(mock_compat)
        bridge.register_v1_components("p1", [], [{"provider_name": "openai"}], [])
        result = await bridge.invoke_component("p1.llm.openai", {})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_component_not_found(self):
        bridge = ComponentBridge()
        result = await bridge.invoke_component("ghost", {})
        assert result["success"] is False
        assert "COMPONENT_NOT_FOUND" in result["error"]

    def test_duplicate_registration(self):
        bridge = ComponentBridge()
        bridge.register_v1_components("p1", [{"name": "t1", "component_type": "TOOL"}], [], [])
        bridge.register_v1_components("p1", [{"name": "t1", "component_type": "TOOL"}, {"name": "t2", "component_type": "TOOL"}], [], [])
        comps = bridge.list_components()
        names = [c.component_name for c in comps]
        assert "p1.t1" in names
        assert "p1.t2" in names

    def test_list_components(self):
        bridge = ComponentBridge()
        bridge.register_v1_components("p1", [{"name": "t1", "component_type": "TOOL"}], [], [])
        comps = bridge.list_components()
        assert len(comps) == 1
        assert comps[0].component_name == "p1.t1"

    def test_unregister_plugin(self):
        bridge = ComponentBridge()
        bridge.register_v1_components("p1", [{"name": "t1", "component_type": "TOOL"}], [], [])
        bridge.unregister_plugin("p1")
        comps = bridge.list_components()
        assert len(comps) == 0


class TestCapabilityBridge:

    @pytest.mark.asyncio
    async def test_send_text_bridge(self):
        ctx = MagicMock()
        ctx.send.text = AsyncMock(return_value={"type": "text"})
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "send.text", {"stream_id": "s1", "text": "hello"})
        assert result["success"] is True
        ctx.send.text.assert_called_once_with("s1", "hello")

    @pytest.mark.asyncio
    async def test_send_image_bridge(self):
        ctx = MagicMock()
        ctx.send.image = AsyncMock(return_value={"type": "image"})
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "send.image", {"image_base64": "abc"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_emoji_bridge(self):
        ctx = MagicMock()
        ctx.send.emoji = AsyncMock(return_value={"type": "emoji"})
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "send.emoji", {"emoji_base64": "abc"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_db_get_bridge(self):
        ctx = MagicMock()
        ctx.storage.get = AsyncMock(return_value="myval")
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "database.get", {"key": "k1"})
        assert result["success"] is True
        assert result["result"] == "myval"
        ctx.storage.get.assert_called_once_with("v1:test_plugin:k1", None)

    @pytest.mark.asyncio
    async def test_db_save_bridge(self):
        ctx = MagicMock()
        ctx.storage.set = AsyncMock()
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "database.save", {"key": "k1", "value": "v1"})
        assert result["success"] is True
        ctx.storage.set.assert_called_once_with("v1:test_plugin:k1", "v1")

    @pytest.mark.asyncio
    async def test_db_delete_bridge(self):
        ctx = MagicMock()
        ctx.storage.delete = AsyncMock(return_value=True)
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "database.delete", {"key": "k1"})
        assert result["success"] is True
        ctx.storage.delete.assert_called_once_with("v1:test_plugin:k1")

    @pytest.mark.asyncio
    async def test_unsupported_capability(self):
        ctx = MagicMock()
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "emoji.get_random", {})
        assert result["success"] is False
        assert "not supported" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_capability(self):
        ctx = MagicMock()
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "xyz.abc", {})
        assert result["success"] is False
        assert "unknown" in result["error"]

    @pytest.mark.asyncio
    async def test_capability_exception(self):
        ctx = MagicMock()
        ctx.send.text = AsyncMock(side_effect=RuntimeError("boom"))
        bridge = CapabilityBridge(ctx, "test_plugin")
        result = await bridge.handle_cap_call("p1", "send.text", {"stream_id": "s1", "text": "x"})
        assert result["success"] is False
        assert "boom" in result["error"]


class TestCompatConfig:

    def test_default_config(self):
        cfg = CompatConfig()
        assert cfg.plugin_dirs == ["data/MaiMBot/plugins"]
        assert cfg.max_restart_attempts == 3
        assert cfg.host_version == "compat-v1"

    def test_custom_config(self):
        cfg = CompatConfig(plugin_dirs=["/custom"], max_restart_attempts=5)
        assert cfg.plugin_dirs == ["/custom"]
        assert cfg.max_restart_attempts == 5
