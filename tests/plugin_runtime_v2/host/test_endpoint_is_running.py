"""HostEndpoint.is_running 存活标志测试（2026-10-17）。

背景：plugin_runtime 不变量原先查 v1 的 IpcBridgePort.is_running（v1 已被
ZG-32 停用 ⇒ 恒假 ⇒ 恒红），改用 v2 端点后必须保证"真的没在跑"时标志为假，
所以这里覆盖三条路径：未启动 / 启动成功 / 绑定失败。

⚠️ 绑定失败那条用 mock 的 grpc server，不建真 native 对象：实测"真建
grpc.aio server 再让它绑定失败"在 pytest 的 per-test event loop 下会让**后续**
用例于 Windows 上吃 access violation（只选该用例即可复现，2/2）。那是 grpc/pytest
侧的问题，不该由本用例背。
"""

from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest

from src.plugin_runtime_v2.host.connection import HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint


class TestHostEndpointIsRunning:
    """HostEndpoint.is_running 只在真的开始监听后为真。"""

    async def test_false_before_start(self):
        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:0"))
        assert endpoint.is_running is False

    async def test_true_after_start_false_after_stop(self):
        endpoint = HostEndpoint(config=HostEndpointConfig(
            listen_address="0.0.0.0:0", default_drain_timeout_ms=0,
        ))
        await endpoint.start()
        try:
            assert endpoint.is_running is True
        finally:
            await endpoint.stop()
        assert endpoint.is_running is False

    async def test_false_and_released_when_bind_fails(self, monkeypatch):
        """绑定失败：start() 抛错、标志保持 False、半建 server 被收掉。"""
        fake_server = AsyncMock()
        fake_server.add_insecure_port = MagicMock(
            side_effect=RuntimeError("Failed to bind to address 0.0.0.0:8001"),
        )
        monkeypatch.setattr(grpc.aio, "server", lambda **kwargs: fake_server)

        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:8001"))
        with pytest.raises(RuntimeError):
            await endpoint.start()

        assert endpoint.is_running is False
        assert endpoint._server is None
        fake_server.stop.assert_awaited_once_with(grace=0)


class TestHostEndpointPortOccupied:
    """端口被占用时 start() 必须真收尾（2026-10-17 真缺陷）。

    旧写法把 `add_insecure_port` 留在 try **外**，而它自己就是抛点 ⇒ 端口被占时
    `_discard_unstarted_server()` 不会被调用，半建 server 留在 `self._server` 上。
    收尾判据：`self._server is None`（或已 discard）+ 异常按预期穿出。

    ⚠️ 为什么判据那条用 mock 的 server（同本文件 `test_false_and_released_when_bind_fails`
    的理由，且已实测更糟）：**真** `grpc.aio.server()` + 真绑定失败 + pytest ⇒
    本进程在退出时吃 access violation（实测 3/3 组合退 0xC0000005，4 个用例全 passed
    却 EXIT=-1073741819）——成因在 grpc native 侧，不该由本用例背。
    于是把"真端口被占"拆成**两个真判据**：
    ① 子进程里用真 holder socket 占端口，证 C-core `add_insecure_port` **真的**抛
       RuntimeError（真抛点在真占用下成立）；
    ② 本进程内让 server mock 复现该 RuntimeError，测 start() 的**真收尾路径**。

    ⚠️ 边界：本组只证明"真收尾"。主案（悬挂 server 活过 loop ⇒ Windows
    access violation 硬崩）**未复现**，修法也不声称解决它。
    """

    @staticmethod
    def _occupy_port() -> tuple:
        """自建 socket 占住一个空闲端口（真占用），返回 (holder, port)。"""
        import socket

        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        return holder, holder.getsockname()[1]

    @staticmethod
    def _is_occupied(port: int) -> bool:
        """从外面探一次：能连上 ⇒ 端口确实被占着（不是"以为占了"）。"""
        import socket

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(2.0)
        try:
            return probe.connect_ex(("127.0.0.1", port)) == 0
        finally:
            probe.close()

    async def test_server_discarded_when_port_occupied(self, monkeypatch):
        """端口被占 ⇒ start() 抛错且 `_server is None`（异常按预期穿出）。"""
        holder, port = self._occupy_port()
        try:
            assert self._is_occupied(port), "合成占用不成立：holder 没占住端口"

            fake_server = AsyncMock()
            fake_server.add_insecure_port = MagicMock(
                side_effect=RuntimeError(
                    f"Failed to bind to address 127.0.0.1:{port}",
                ),
            )
            monkeypatch.setattr(grpc.aio, "server", lambda **kwargs: fake_server)

            endpoint = HostEndpoint(config=HostEndpointConfig(
                listen_address=f"127.0.0.1:{port}",
            ))
            with pytest.raises(RuntimeError):
                await endpoint.start()
        finally:
            holder.close()

        # 判据：半建 server 已被当场收掉，没留在 self._server 上
        assert endpoint._server is None
        assert endpoint.is_running is False
        assert endpoint.listen_address == ""
        assert endpoint._actual_listen_address == ""
        fake_server.stop.assert_awaited_once_with(grace=0)

    def test_real_grpc_add_port_really_raises_on_occupied_port(self):
        """真占用 ⇒ 真 C-core `add_insecure_port` 真抛（子进程隔离，避开上述崩）。

        子进程里不碰 `HostEndpoint`——只证"端口被占 ⇒ 抛点成立"这条事实。
        """
        import subprocess
        import sys
        import textwrap

        holder, port = self._occupy_port()
        code = textwrap.dedent(f"""
            import socket, sys
            import grpc

            holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            holder.bind(("127.0.0.1", {port}))
            holder.listen(1)
            srv = grpc.aio.server()
            try:
                srv.add_insecure_port("127.0.0.1:{port}")
            except RuntimeError:
                print("BIND_RAISED")
                sys.exit(7)
            print("BIND_NOT_RAISED")
            sys.exit(0)
        """)
        try:
            assert self._is_occupied(port), "合成占用不成立：holder 没占住端口"
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=120,
            )
        finally:
            holder.close()

        assert "BIND_RAISED" in proc.stdout, (
            f"真占用下 add_insecure_port 未抛：rc={proc.returncode} "
            f"out={proc.stdout!r} err={proc.stderr[-500:]!r}"
        )
        assert proc.returncode == 7
