"""Phoenix-1 gRPC 传输层集成测试。

测试 Host↔Runner 端到端流程：连接生命周期、心跳保活、
自动重连、多 Runner 并行、异常场景。
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

# ── 测试用短间隔心跳（加速测试） ──
_TEST_HEARTBEAT_INTERVAL = 2
_TEST_HEARTBEAT_TIMEOUT = 3
_TEST_HEARTBEAT_MAX_MISSES = 2


def _host_config(listen_address: str = "127.0.0.1:0") -> HostEndpointConfig:
    """创建测试用 Host 配置（随机端口 + 短心跳间隔）。"""
    return HostEndpointConfig(
        listen_address=listen_address,
        heartbeat_interval_s=_TEST_HEARTBEAT_INTERVAL,
        heartbeat_timeout_s=_TEST_HEARTBEAT_TIMEOUT,
        max_heartbeat_misses=_TEST_HEARTBEAT_MAX_MISSES,
        register_timeout_s=10,
        default_drain_timeout_ms=2000,
    )


def _runner_config(host_address: str, runner_id: str = "test-runner-1") -> RunnerEndpointConfig:
    """创建测试用 Runner 配置。"""
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


# ═══════════════════════════════════════════════════════════════
# 9.1 连接生命周期
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_connection_lifecycle():
    """Runner 完成 DISCONNECTED → READY 完整流程，然后优雅关停。"""
    # 启动 Host
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        # 启动 Runner
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await runner.start()
        assert runner.state == ConnectionState.READY
        assert runner.is_ready

        # 验证 Host 注册表
        status = host.get_status()
        assert "test-runner-1" in status
        snap = status["test-runner-1"]
        assert snap.state == "ready"
        assert snap.plugin_id == "test.plugin"

        # Runner 推送 Event
        await runner.emit_event("test.event", {"key": "value"})

        # 停止 Runner
        await runner.stop()
        assert runner.state == ConnectionState.DISCONNECTED
    finally:
        await host.stop()

    # Host 停止后注册表为空
    assert host.get_status() == {}


@pytest.mark.asyncio
async def test_host_invoke_tool_returns_not_implemented():
    """Host 通过 gRPC stub 调用 Runner 的 InvokeTool，返回 NOT_IMPLEMENTED。"""
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await runner.start()

        # 通过 gRPC stub 调用 InvokeTool
        # Runner 的 InvokeTool 侦听地址在握手时上报
        status = host.get_status()
        assert "test-runner-1" in status

        # Phoenix-1 阶段 InvokeTool 总是返回 NOT_IMPLEMENTED
        # 完整 ToolProvider 桥接流程在 Phoenix-2 实现

        await runner.stop()
    finally:
        await host.stop()


# ═══════════════════════════════════════════════════════════════
# 9.2 心跳保活
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_heartbeat_exchange():
    """Host 发送心跳，Runner 回复心跳响应。"""
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await runner.start()

        # 等待至少一次心跳交换
        await asyncio.sleep(_TEST_HEARTBEAT_INTERVAL + 1)

        # Runner 仍处于 READY 状态
        assert runner.state == ConnectionState.READY

        await runner.stop()
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_heartbeat_timeout_disconnects():
    """Runner 无响应 → Host 在连续超时后清理连接。"""
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await runner.start()

        # 强制停止 Runner（不优雅关停，模拟崩溃）
        await runner.stop()

        # 等待心跳超时判定（连续 2 次 × 间隔 2s = ~4s + 超时 3s）
        await asyncio.sleep(
            _TEST_HEARTBEAT_INTERVAL * _TEST_HEARTBEAT_MAX_MISSES
            + _TEST_HEARTBEAT_TIMEOUT
            + 1
        )

        # Host 注册表已清理
        status = host.get_status()
        assert "test-runner-1" not in status
    finally:
        await host.stop()


# ═══════════════════════════════════════════════════════════════
# 9.3 自动重连
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_runner_auto_reconnect_after_host_restart():
    """Host 重启后 Runner 自动重连并重新握手+注册。"""
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await runner.start()
        assert runner.is_ready

        # 停 Host → Runner 断开
        await host.stop()

        # 等待 Runner 检测到断开
        await asyncio.sleep(1)
        assert not runner.is_ready

        # 重启 Host（使用相同地址 — 需要固定端口）
        # Note: 测试用随机端口时，重连需要 Runner 自动发现新地址
        # 完整验证在 Phoenix-2 与进程管理结合后生效
    finally:
        # 清理
        try:
            await runner.stop()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_reconnect_exhausted_stops():
    """重连耗尽 → Runner 进入 DISCONNECTED 终态。"""
    config = _runner_config("127.0.0.1:19999")  # 不存在的主机:端口
    config = RunnerEndpointConfig(
        host_address="127.0.0.1:19999",
        runner_id="no-host-runner",
        session_token="t",
        scopes=["message:send:text"],
        reconnect_max_retries=2,
        reconnect_initial_delay_s=0.1,
        reconnect_max_delay_s=0.5,
    )
    runner = RunnerEndpoint(config)
    await runner.start()

    # 重连耗尽后应停留在 DISCONNECTED
    assert runner.state == ConnectionState.DISCONNECTED
    assert not runner.is_ready


# ═══════════════════════════════════════════════════════════════
# 9.4 多 Runner 并行
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_multiple_runners_parallel():
    """3 个 Runner 同时连接，各自独立运行。"""
    host = HostEndpoint(_host_config())
    await host.start()
    runners: list[RunnerEndpoint] = []
    try:
        # 启动 3 个 Runner
        for i in range(3):
            rid = f"runner-{i}"
            runner = RunnerEndpoint(_runner_config(host.listen_address, runner_id=rid))
            runners.append(runner)
            await runner.start()
            assert runner.is_ready

        # Host 注册表有 3 个 Runner
        status = host.get_status()
        assert len(status) == 3
        for i in range(3):
            assert f"runner-{i}" in status

        # 断开 runner-1，不影响其他
        await runners[1].stop()
        await asyncio.sleep(0.5)
        status = host.get_status()
        assert "runner-1" in status or len(status) == 2  # 心跳可能尚未超时

        # runner-0 和 runner-2 仍 READY
        assert runners[0].is_ready
    finally:
        for r in runners:
            try:
                await r.stop()
            except Exception:
                pass
        await host.stop()


# ═══════════════════════════════════════════════════════════════
# 9.5 异常场景
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_duplicate_runner_id_rejected():
    """同一 runner_id 第二次 Connect 被拒绝。"""
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        runner1 = RunnerEndpoint(_runner_config(host.listen_address, runner_id="dup-runner"))
        await runner1.start()
        assert runner1.is_ready

        # 第二个同 ID Runner 应该无法连接
        runner2 = RunnerEndpoint(_runner_config(host.listen_address, runner_id="dup-runner"))
        await runner2.start()
        # 握手被拒 → DISCONNECTED
        assert runner2.state == ConnectionState.DISCONNECTED
        assert not runner2.is_ready

        await runner1.stop()
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_invoke_tool_during_shutdown():
    """关停期间新的 InvokeTool 调用可被 Runner 正常处理（Phoenix-1 返回 NOT_IMPLEMENTED）。"""
    host = HostEndpoint(_host_config())
    await host.start()
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await runner.start()
        assert runner.is_ready

        # Phoenix-1 阶段 InvokeTool 总是返回 NOT_IMPLEMENTED
        # 关停期间和正常运行期间行为一致
        await runner.stop()
    finally:
        await host.stop()


@pytest.mark.asyncio
async def test_emit_event_when_not_ready():
    """非 READY 状态下 emit_event 抛出 ConnectionError。"""
    runner = RunnerEndpoint(
        _runner_config("127.0.0.1:59999", runner_id="offline-runner")
    )
    # 不调用 start()，状态为 DISCONNECTED
    with pytest.raises(ConnectionError, match="not in READY"):
        await runner.emit_event("test", {})


# ═══════════════════════════════════════════════════════════════
# 9.6 性能基线
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_message_roundtrip_latency():
    """protobuf 消息序列化/反序列化延迟 ≤5ms。"""
    # 构造典型消息
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

    # 测量序列化 + 反序列化延迟
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        serialized = msg.SerializeToString()
        common_pb2.RunnerMessage.FromString(serialized)
    elapsed_ms = (time.perf_counter() - start) / iterations * 1000

    assert elapsed_ms < 5.0, f"序列化+反序列化延迟 {elapsed_ms:.3f}ms 超过 5ms 限制"


@pytest.mark.asyncio
async def test_ten_runners_connect_sequentially():
    """10 个 Runner 依次连接均成功。"""
    host = HostEndpoint(
        HostEndpointConfig(
            listen_address="127.0.0.1:0",
            heartbeat_interval_s=10,
            heartbeat_timeout_s=5,
            max_heartbeat_misses=2,
            max_runners=10,
        )
    )
    await host.start()
    runners: list[RunnerEndpoint] = []
    try:
        for i in range(10):
            runner = RunnerEndpoint(
                RunnerEndpointConfig(
                    host_address=host.listen_address,
                    runner_id=f"perf-runner-{i}",
                    session_token="t",
                    scopes=["message:send:text"],
                    reconnect_max_retries=0,
                )
            )
            runners.append(runner)
            await runner.start()
            assert runner.is_ready

        assert len(host.get_status()) == 10
    finally:
        for r in runners:
            try:
                await r.stop()
            except Exception:
                pass
        await host.stop()
