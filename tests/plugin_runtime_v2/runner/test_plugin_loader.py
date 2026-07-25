"""Task 3.3: PluginLoader 单元测试。"""

from __future__ import annotations

from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin
from src.plugin_runtime_v2.sdk.decorators import Tool, Event, HomeCard
from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader


class TestBasicLoad:
    def test_load_collects_tools(self):
        class MyPlugin(MaiBotPlugin):
            plugin_id = "test.p"
            scopes = ["message:send:text"]

            @Tool(name="t1", description="desc")
            async def my_tool(self, args):
                return {"ok": True}

        loader = PluginLoader(MyPlugin)
        tools, events, cards, instance = loader.load()
        assert loader.is_loaded
        assert instance is not None
        assert len(tools) == 1
        assert tools[0]["name"] == "t1"
        assert events == []

    def test_load_collects_events_and_homecards(self):
        class MyPlugin(MaiBotPlugin):
            plugin_id = "test.p"

            @Event(name="e1", description="evt_desc")
            async def my_event(self, payload):
                pass

            @HomeCard(name="card1", title="My Card", width="medium")
            async def my_card(self):
                pass

        loader = PluginLoader(MyPlugin)
        tools, events, cards, instance = loader.load()
        assert len(events) == 2
        assert len(cards) == 1
        assert cards["card1"] is not None
        assert cards["card1"]["title"] == "My Card"

    def test_reload_prevented_by_flag(self):
        class MyPlugin(MaiBotPlugin):
            plugin_id = "test.p"

        loader = PluginLoader(MyPlugin)
        loader.load()
        assert loader.is_loaded
        # Second load returns cached result
        tools2, _, _, inst2 = loader.load()
        assert tools2 == []

    def test_instantiation_failure_returns_empties(self):
        class BadPlugin(MaiBotPlugin):
            plugin_id = "test.p"
            def __init__(self):
                raise RuntimeError("cannot create")

        loader = PluginLoader(BadPlugin)
        tools, events, cards, instance = loader.load()
        assert instance is None
        assert tools == []
        assert events == []
