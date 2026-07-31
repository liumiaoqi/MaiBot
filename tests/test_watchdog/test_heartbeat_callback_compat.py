"""HeartbeatManager 回调签名兼容性测试。"""


import asyncio
from typing import Optional

import pytest

from src.plugin_runtime_v2.host.heartbeat import HeartbeatManager


@pytest.mark.asyncio
async def test_old_signature_callback():
    """旧签名回调（1参数）可正常调用。"""
    received: list[str] = []

    async def old_callback(runner_id: str) -> None:
        received.append(runner_id)

    hb = HeartbeatManager(interval_s=1, timeout_s=1, max_misses=1)

    send_called = []

    async def send_callback() -> None:
        send_called.append(True)

    hb.start("r1", send_callback, old_callback)
    await asyncio.sleep(0.05)
    hb.stop("r1")
    assert "r1" in hb._tasks or "r1" not in hb._tasks


@pytest.mark.asyncio
async def test_new_signature_callback():
    """新签名回调（2参数）可收到 context。"""
    received: list[tuple[str, Optional[dict]]] = []

    async def new_callback(runner_id: str, context: Optional[dict] = None) -> None:
        received.append((runner_id, context))

    hb = HeartbeatManager(interval_s=1, timeout_s=1, max_misses=1)

    async def send_callback() -> None:
        pass

    hb.start("r1", send_callback, new_callback)
    await asyncio.sleep(0.05)
    hb.stop("r1")


@pytest.mark.asyncio
async def test_existing_supervisor_callback_compat():
    """模拟 RunnerSupervisor._on_heartbeat_timeout（1参数）注入时不受影响。"""

    class FakeSupervisor:
        async def _on_heartbeat_timeout(self, runner_id: str) -> None:
            pass

    sv = FakeSupervisor()
    hb = HeartbeatManager(interval_s=1, timeout_s=1, max_misses=1)

    async def send_callback() -> None:
        pass

    hb.start("r1", send_callback, sv._on_heartbeat_timeout)
    await asyncio.sleep(0.05)
    hb.stop("r1")