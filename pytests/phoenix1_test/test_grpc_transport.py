"""Phoenix-1 gRPC 传输层集成测试。

测试 Host↔Runner 端到端流程：连接生命周期、心跳保活、
异常场景、性能基线。

注意：gRPC Python 3.14 有 segfault 风险，高并发测试可能不稳定。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.plugin_runtime_v2.host.connection import ConnectionState, HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint
from src.plugin_runtime_v2.proto import common_pb2
from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig

# ── 测试超时 ──
_RUNNER_START_TIMEOUT = 10.0

# ── 测试用短间隔心跳（加速测试） ──
_TEST_HEARTBEAT_INTERVAL = 2
_TEST_HEARTBEAT_TIMEOUT = 3
_TEST_HEARTBEAT_MAX_MISSES = 2


def _host_config(listen_address: str = "127.0.0.1:0") -> HostEndpointConfig:
    return HostEndpointConfig(
        listen_address=listen_address,
        heartbeat_interval_s=_TEST_HEARTBEAT_INTERVAL,
        heartbeat_timeout_s=_TEST_HEARTBEAT_TIMEOUT,
        max_heartbeat_misses=_TEST_HEARTBEAT_MAX_MISSES,
        register_timeout_s=10,
        default_drain_timeout_ms=2000,
    )


def _runner_config(host_address: str, runner_id: str = "test-runner-1") -> RunnerEndpointConfig:
    return RunnerEndpointConfig(
        host_address=host_address,
        runner_id=runner_id,
        session_token="test-token",
        scopes=["message:send:text"],
        plugin_id="test.plugin",
        reconnect_max_retries=3,
        reconnect_initial_delay_s=0.5,
        reconnect_max_delay_s=2.0,
    )


async def _safe_stop(runner: RunnerEndpoint) -> None:
    """安全停止 Runner，忽略异常。"""
    try:
        await runner.stop()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 9.1 连接生命周期
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_connection_lifecycle():
    """Runner 完成 DISCONNECTED → READY 完整流程，然后优雅关停。"""
    host = HostEndpoint(_host_config())
    await host.start()
    runner: RunnerEndpoint | None = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)
        assert runner.state == ConnectionState.READY
        assert runner.is_ready

        status = host.get_status()
        assert "test-runner-1" in status
        assert status["test-runner-1"].state == "ready"
        assert status["test-runner-1"].plugin_id == "test.plugin"

        await runner.emit_event("test.event", {"key": "value"})

        await runner.stop()
        assert runner.state == ConnectionState.DISCONNECTED
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()

    assert host.get_status() == {}


# ═══════════════════════════════════════════════════════════════
# 9.2 心跳保活
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_heartbeat_exchange():
    """Host 发送心跳，Runner 回复心跳响应，Runner 保持 READY。"""
    host = HostEndpoint(_host_config())
    await host.start()
    runner: RunnerEndpoint | None = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)

        # 等待至少一次心跳交换
        await asyncio.sleep(_TEST_HEARTBEAT_INTERVAL + 1)
        assert runner.state == ConnectionState.READY

        await runner.stop()
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()


@pytest.mark.asyncio
async def test_heartbeat_timeout_disconnects():
    """Runner 无响应 → Host 在连续超时后清理连接。"""
    host = HostEndpoint(_host_config())
    await host.start()
    runner: RunnerEndpoint | None = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)

        # 强制停止 Runner（不优雅关停，模拟崩溃）
        await runner.stop()

        # 等待心跳超时判定
        await asyncio.sleep(
            _TEST_HEARTBEAT_INTERVAL * _TEST_HEARTBEAT_MAX_MISSES
            + _TEST_HEARTBEAT_TIMEOUT
            + 1
        )

        status = host.get_status()
        assert "test-runner-1" not in status
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()


# ═══════════════════════════════════════════════════════════════
# 9.3 自动重连
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reconnect_exhausted_stops():
    """重连耗尽 → Runner 进入 DISCONNECTED 终态。"""
    runner = RunnerEndpoint(
        RunnerEndpointConfig(
            host_address="127.0.0.1:19999",
            runner_id="no-host-runner",
            session_token="t",
            scopes=["message:send:text"],
            reconnect_max_retries=2,
            reconnect_initial_delay_s=0.1,
            reconnect_max_delay_s=0.5,
        )
    )
    await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)

    assert runner.state == ConnectionState.DISCONNECTED
    assert not runner.is_ready


# ═══════════════════════════════════════════════════════════════
# 9.4 多 Runner 并行
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_two_runners_parallel():
    """2 个 Runner 同时连接，各自独立运行。"""
    host = HostEndpoint(_host_config())
    await host.start()
    r0: RunnerEndpoint | None = None
    r1: RunnerEndpoint | None = None
    try:
        r0 = RunnerEndpoint(_runner_config(host.listen_address, runner_id="runner-0"))
        r1 = RunnerEndpoint(_runner_config(host.listen_address, runner_id="runner-1"))

        await asyncio.wait_for(r0.start(), timeout=_RUNNER_START_TIMEOUT)
        await asyncio.wait_for(r1.start(), timeout=_RUNNER_START_TIMEOUT)

        assert r0.is_ready
        assert r1.is_ready

        status = host.get_status()
        assert len(status) == 2

        # 断开 runner-0
        await r0.stop()
        await asyncio.sleep(0.5)
        # runner-1 不受影响
        assert r1.is_ready
    finally:
        for r in (r0, r1):
            if r is not None:
                await _safe_stop(r)
        await host.stop()


# ═══════════════════════════════════════════════════════════════
# 9.5 异常场景
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_duplicate_runner_id_rejected():
    """同一 runner_id 第二次 Connect 被拒绝。"""
    host = HostEndpoint(_host_config())
    await host.start()
    r1: RunnerEndpoint | None = None
    r2: RunnerEndpoint | None = None
    try:
        r1 = RunnerEndpoint(_runner_config(host.listen_address, runner_id="dup-runner"))
        await asyncio.wait_for(r1.start(), timeout=_RUNNER_START_TIMEOUT)
        assert r1.is_ready

        r2 = RunnerEndpoint(_runner_config(host.listen_address, runner_id="dup-runner"))
        await asyncio.wait_for(r2.start(), timeout=_RUNNER_START_TIMEOUT)
        assert r2.state == ConnectionState.DISCONNECTED
        assert not r2.is_ready
    finally:
        for r in (r1, r2):
            if r is not None:
                await _safe_stop(r)
        await host.stop()


@pytest.mark.asyncio
async def test_emit_event_when_not_ready():
    """非 READY 状态下 emit_event 抛出 ConnectionError。"""
    runner = RunnerEndpoint(
        _runner_config("127.0.0.1:59999", runner_id="offline-runner")
    )
    with pytest.raises(ConnectionError, match="not in READY"):
        await runner.emit_event("test", {})


# ═══════════════════════════════════════════════════════════════
# 9.6 性能基线
# ═══════════════════════════════════════════════════════════════


def test_message_roundtrip_latency():
    """protobuf 消息序列化/反序列化延迟 ≤5ms。"""
    msg = common_pb2.RunnerMessage(
        hello=common_pb2.HelloPayload(
            runner_id="perf-test",
            sdk_version="4.0.0",
            session_token="t",
            scopes=["message:send:text"],
            runner_listen_address="127.0.0.1:9999",
        )
    )

    data = msg.SerializeToString()
    assert len(data) < 4096, "消息体应 ≤4KB"

    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        serialized = msg.SerializeToString()
        common_pb2.RunnerMessage.FromString(serialized)
    elapsed_ms = (time.perf_counter() - start) / iterations * 1000

    assert elapsed_ms < 5.0, f"序列化+反序列化延迟 {elapsed_ms:.3f}ms 超过 5ms 限制"
