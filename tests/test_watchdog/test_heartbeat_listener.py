"""HeartbeatManager 监听器组合测试（FR-1）。

覆盖 AC-1.1.1 / AC-1.1.2 / AC-1.2.1 / AC-1.2.2 / AC-1.2.3 / AC-1.4.1
与 spec.md 数据约束 1（监听器去重与随任务清理）。
"""


import asyncio
from typing import Optional

import pytest

from src.plugin_runtime_v2.host.heartbeat import HeartbeatManager


def _make_heartbeat(max_misses: int = 1) -> HeartbeatManager:
    """构造快速触发的 HeartbeatManager（interval/timeout 较小，不记录响应）。

    间隔不宜过小：与 test_event_loop_monitor 的精确时序测试共享 CPU，
    过密心跳任务会放大其 flaky 概率。
    """
    return HeartbeatManager(interval_s=0.02, timeout_s=0.02, max_misses=max_misses)


@pytest.mark.asyncio
async def test_listener_called_before_original_callback():
    """AC-1.1.1 + AC-1.2.1: start 后超时，监听器被调用且原始回调也被调用（监听器在前）。"""
    order: list[str] = []
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def original_callback(runner_id: str) -> None:
        order.append("original")

    async def listener(runner_id: str, context: Optional[dict] = None) -> None:
        order.append("listener")

    hb.add_timeout_listener("r1", listener)
    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")

    assert order == ["listener", "original"]


@pytest.mark.asyncio
async def test_listener_registered_before_start():
    """AC-1.1.2: 未 start 先 add_timeout_listener 再 start，超时后监听器仍被调用。"""
    called: list[tuple[str, Optional[dict]]] = []
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def original_callback(runner_id: str) -> None:
        pass

    async def listener(runner_id: str, context: Optional[dict] = None) -> None:
        called.append((runner_id, context))

    hb.add_timeout_listener("r1", listener)  # start 之前注册
    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")

    assert len(called) == 1
    runner_id, ctx = called[0]
    assert runner_id == "r1"
    assert ctx == {"detection_source": "heartbeat", "consecutive_failures": 1}


@pytest.mark.asyncio
async def test_original_callback_only_baseline():
    """AC-1.2.2: 仅原始回调（无监听器）时 1 参数回调走旧路径，行为与基线一致。"""
    received: list[str] = []
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def original_callback(runner_id: str) -> None:
        received.append(runner_id)

    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")

    assert received == ["r1"]


@pytest.mark.asyncio
async def test_new_signature_callback_gets_context():
    """AC-1.2.3: 新签名（2 参数）回调收到含 detection_source/consecutive_failures 的 context。"""
    received: list[tuple[str, Optional[dict]]] = []
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def new_callback(runner_id: str, context: Optional[dict] = None) -> None:
        received.append((runner_id, context))

    hb.start("r1", send_callback, new_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")

    assert len(received) == 1
    runner_id, ctx = received[0]
    assert runner_id == "r1"
    assert ctx == {"detection_source": "heartbeat", "consecutive_failures": 1}


@pytest.mark.asyncio
async def test_listener_exception_does_not_block_original():
    """AC-1.4.1: 监听器抛异常时原始回调仍执行，心跳循环正常退出。"""
    original_called: list[str] = []
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def original_callback(runner_id: str) -> None:
        original_called.append(runner_id)

    async def bad_listener(runner_id: str, context: Optional[dict] = None) -> None:
        raise RuntimeError("listener boom")

    hb.add_timeout_listener("r1", bad_listener)
    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")

    assert original_called == ["r1"]


@pytest.mark.asyncio
async def test_duplicate_listener_called_once():
    """数据约束 1: 同一 listener 重复 add 只调用一次（set 去重）。"""
    count = 0
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def original_callback(runner_id: str) -> None:
        pass

    async def listener(runner_id: str, context: Optional[dict] = None) -> None:
        nonlocal count
        count += 1

    hb.add_timeout_listener("r1", listener)
    hb.add_timeout_listener("r1", listener)  # 重复注册
    assert len(hb._timeout_listeners["r1"]) == 1

    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")

    assert count == 1


@pytest.mark.asyncio
async def test_stop_cleans_listeners():
    """数据约束 1: stop(runner_id) 后监听器被清理，重新 start 不再触发旧监听器。"""
    count = 0
    hb = _make_heartbeat()

    async def send_callback() -> None:
        pass

    async def original_callback(runner_id: str) -> None:
        pass

    async def listener(runner_id: str, context: Optional[dict] = None) -> None:
        nonlocal count
        count += 1

    hb.add_timeout_listener("r1", listener)
    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")
    assert "r1" not in hb._timeout_listeners

    # 重新 start（监听器已被清理），不应再触发
    hb.start("r1", send_callback, original_callback)
    await asyncio.sleep(0.2)
    hb.stop("r1")
    assert count == 1
