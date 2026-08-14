"""UDSTransportServer UDS 传输测试 — ZG-10 遗留 2：探测活监听再报错（碰撞防御）。

覆盖场景：
- 同路径已有活监听时 start() 抛 UDSSocketOccupiedError，且不 unlink 对方活 socket
- 残留死 socket 文件（无监听进程）被安全清理后正常启动
- 报错路径走 error_escalation，报错信息区分「活监听占用」vs「残留文件」

注意：UDS 仅 Unix-like 平台可用（测试在 Linux 容器内运行）。
"""

import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import reset_error_escalation_port, set_error_escalation_port
from src.plugin_runtime.transport.base import Connection
from src.plugin_runtime.transport.uds import UDSSocketOccupiedError, UDSTransportClient, UDSTransportServer

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="UDS 仅 Unix-like 平台可用")


async def _echo_handler(conn: Connection) -> None:
    """回显 handler：收到一帧就原样返回（用于验证连接可用性）。"""
    try:
        while True:
            data = await conn.recv_frame()
            await conn.send_frame(data)
    except Exception:
        pass
    finally:
        await conn.close()


async def _assert_echo_roundtrip(socket_path: Path) -> None:
    """通过 UDSTransportClient 验证一次回显往返。"""
    client = UDSTransportClient(socket_path=socket_path)
    conn = await client.connect()
    try:
        await conn.send_frame(b"ping")
        assert await conn.recv_frame() == b"ping"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_start_with_live_listener_raises_occupied_and_keeps_original(tmp_path: Path) -> None:
    """server A 监听固定路径后，server B 同路径 start() 应报占用错误，且 A 仍可连接。"""
    socket_path = tmp_path / "collision.sock"

    server_a = UDSTransportServer(socket_path=socket_path)
    await server_a.start(_echo_handler)

    server_b = UDSTransportServer(socket_path=socket_path)
    with pytest.raises(UDSSocketOccupiedError, match="活监听占用"):
        await server_b.start(_echo_handler)

    # B 的报错路径绝不能 unlink A 的活 socket
    assert socket_path.exists()
    # B 失败后再调 stop 也不得清理 A 的 socket（只清理自己创建的）
    await server_b.stop()
    assert socket_path.exists()

    # A 仍能正常服务
    await _assert_echo_roundtrip(socket_path)

    await server_a.stop()


@pytest.mark.asyncio
async def test_start_unlinks_stale_dead_socket(tmp_path: Path) -> None:
    """残留死 socket 文件（无监听进程）应被安全 unlink 后正常启动。"""
    socket_path = tmp_path / "stale.sock"
    # 制造残留死文件：bind 后关闭 socket——文件留在磁盘上但无监听进程
    dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    dead.bind(str(socket_path))
    dead.close()
    assert socket_path.exists()

    server = UDSTransportServer(socket_path=socket_path)
    await server.start(_echo_handler)
    try:
        await _assert_echo_roundtrip(socket_path)
    finally:
        await server.stop()
    assert not socket_path.exists()


@pytest.mark.asyncio
async def test_start_reports_occupied_via_error_escalation(tmp_path: Path) -> None:
    """活监听占用时 error_escalation 上报 WARNING，报错标题区分「活监听占用」。"""
    socket_path = tmp_path / "escalation.sock"

    server_a = UDSTransportServer(socket_path=socket_path)
    await server_a.start(_echo_handler)

    port = MagicMock()
    set_error_escalation_port(port)
    try:
        server_b = UDSTransportServer(socket_path=socket_path)
        with pytest.raises(UDSSocketOccupiedError):
            await server_b.start(_echo_handler)

        port.report.assert_called_once()
        assert port.report.call_args.args[0] is ErrorLevel.WARNING
        assert "活监听占用" in port.report.call_args.args[1]
        assert isinstance(port.report.call_args.kwargs["exception"], UDSSocketOccupiedError)
    finally:
        reset_error_escalation_port()
        await server_a.stop()
