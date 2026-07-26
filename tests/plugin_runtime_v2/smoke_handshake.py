#!/usr/bin/env python3
"""Smoke test: V1 IPC Server + Runner subprocess handshake."""
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
    ready = await bridge.wait_ready(timeout_s=60.0)
    print(f"Ready: {ready}")
    if ready:
        components = cb.list_components()
        print(f"V1 components loaded: {len(components)}")
        for c in components:
            print(f"  - {c.component_name} ({c.component_type})")
    await bridge.stop()
    print("Stopped OK")


asyncio.run(test())