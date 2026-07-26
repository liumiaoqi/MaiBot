#!/usr/bin/env python3
"""Smoke test: V1 IPC Server startup without Runner subprocess."""
import asyncio
import sys
sys.path.insert(0, "/MaiMBot")

from plugins.maibot_team.v1_compat.compat_bridge import CompatBridge
from plugins.maibot_team.v1_compat.component_bridge import ComponentBridge
from plugins.maibot_team.v1_compat.config import CompatConfig


async def test():
    config = CompatConfig(plugin_dirs=["/MaiMBot/plugins"])
    cb = ComponentBridge()
    bridge = CompatBridge(config, cb)
    await bridge.start()
    print(f"IPC Server started on port {bridge._listen_port}")
    ready = await bridge.wait_ready(timeout_s=3.0)
    print(f"Ready: {ready} (expected False - no Runner subprocess)")
    await bridge.stop()
    print("Stopped OK")


asyncio.run(test())