#!/usr/bin/env python3
"""Debug test: Capture V1 Runner subprocess stderr."""
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

    # Wait a bit for runner to start
    await asyncio.sleep(5.0)

    # Check runner process
    if bridge._runner_process is not None:
        returncode = bridge._runner_process.returncode
        print(f"Runner returncode: {returncode}")
        if returncode is not None:
            # Process exited, read stderr
            stderr = await bridge._runner_process.stderr.read()
            print(f"Runner stderr:\n{stderr.decode('utf-8', errors='replace')[:3000]}")
    else:
        print("No runner process")

    await bridge.stop()


asyncio.run(test())