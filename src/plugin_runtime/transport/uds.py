"""Unix Domain Socket 传输实现

适用于 Linux / macOS 平台。

注意：UDS (Unix Domain Socket) 是 Unix-like 系统特有的 IPC 机制，
在 Windows 平台上不可用。Windows 平台请使用 Named Pipe 传输。
"""

from src.common.logger import get_logger

from pathlib import Path
from typing import Optional

import asyncio
import contextlib
import os
import sys
import tempfile
import time

from .base import Connection, ConnectionHandler, TransportClient, TransportServer


class UDSConnection(Connection):
    """基于 UDS 的连接
    
    封装了底层 StreamReader/StreamWriter，提供分帧读写能力。
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        super().__init__(reader, writer)


# Unix domain socket 路径的系统限制（sun_path 字段长度）
# Linux: 108 字节，macOS: 104 字节，其他 Unix: 通常 104 字节
if sys.platform == "linux":
    _UDS_PATH_MAX = 108
elif sys.platform == "darwin":  # macOS
    _UDS_PATH_MAX = 104
else:
    _UDS_PATH_MAX = 104  # 保守默认值

# 探测活监听时的连接超时（秒）。
# UDS 连接成功/被拒都是即时返回的，超时只可能出现在极端异常场景
# （如目标进程卡死未 accept）——此时按"活监听"保守处理，拒绝 unlink。
_UDS_PROBE_TIMEOUT = 1.0


class UDSSocketOccupiedError(OSError):
    """UDS socket 路径被其他进程活监听占用（ZG-10 遗留 2 碰撞防御）。

    与普通 bind 失败（如权限不足、路径非法）区分，报错信息面向人工排查：
    包含路径与碰撞诊断信息（本进程 pid、socket 文件创建时间）。
    业务层可按此类型专门捕获"活监听占用"场景。
    """


class UDSTransportServer(TransportServer):
    """UDS 传输服务端"""

    def __init__(self, socket_path: Optional[Path] = None) -> None:
        if socket_path is None:
            # 默认放在临时目录，使用 uuid 确保同一进程多实例不碰撞
            import uuid

            socket_path = Path(tempfile.gettempdir()) / f"maibot-plugin-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"

            # 如果路径超出 UDS 限制，回退到更短的路径
            if len(str(socket_path).encode()) > _UDS_PATH_MAX:
                socket_path = Path("/tmp") / f"mb-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
        if len(str(socket_path).encode()) > _UDS_PATH_MAX:
            raise OSError(f"UDS socket 路径过长 ({len(str(socket_path).encode())} > {_UDS_PATH_MAX} 字节): {socket_path}")

        self._socket_path: Path = socket_path
        self._server: Optional[asyncio.AbstractServer] = None
        # 该 socket 文件是否由本实例创建（bind 成功）——只有自己创建的才允许清理，
        # 绝不允许 unlink 其他进程的活 socket（碰撞防御，ZG-10 遗留 2）。
        self._owns_socket: bool = False

    async def _probe_live_listener(self) -> bool:
        """探测 socket 路径上是否存在活监听进程。

        通过主动连接判断路径归属（ZG-10 遗留 2 碰撞防御）：
        - 连接成功 = 有活监听进程 → 返回 True（禁止 unlink，避免串线）
        - ConnectionRefusedError / FileNotFoundError = 残留死文件 → 返回 False（可安全 unlink）
        - 其他 OSError（超时/无权限等）= 无法确认 → 保守返回 True（宁可报占用也不误删活 socket）

        竞态说明：探测与后续 bind 之间路径状态可能变化（另一进程可能恰好在此窗口
        启动/退出）。单进程内此探测足够，跨进程强一致需上层互斥（已知局限）。
        """
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self._socket_path)),
                timeout=_UDS_PROBE_TIMEOUT,
            )
        except (ConnectionRefusedError, FileNotFoundError):
            return False
        except OSError:
            return True
        # 连接成功：关闭探测连接并确认"活监听"
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return True

    async def start(self, handler: ConnectionHandler) -> None:
        """启动 UDS 服务端
        
        Args:
            handler: 新连接到来时的回调函数
            
        Raises:
            RuntimeError: 当在非 Unix 平台（如 Windows）上调用时
            UDSSocketOccupiedError: socket 路径被其他进程活监听占用（碰撞防御，ZG-10 遗留 2）
            OSError: 其他启动失败（bind 失败等）
        """
        # 平台检查：UDS 仅在 Unix-like 系统上可用
        if sys.platform == "win32":
            raise RuntimeError("UDS 不支持 Windows 平台，请使用 Named Pipe")
        
        async def _on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            conn = UDSConnection(reader, writer)
            try:
                await handler(conn)
            finally:
                await conn.close()

        try:
            # 清理残留 socket 文件前先探测是否被活监听占用（碰撞防御，ZG-10 遗留 2）。
            # 连接成功 = 有活监听进程 → 不 unlink 并抛错；连接被拒/文件不存在 = 残留死文件 → 安全 unlink。
            # 竞态说明：探测与 bind 之间路径状态可能变化，单进程内足够（见 _probe_live_listener）。
            if self._socket_path.exists():
                if await self._probe_live_listener():
                    raise UDSSocketOccupiedError(
                        f"UDS socket 路径被活监听占用: {self._socket_path}。"
                        f"碰撞诊断: 本进程 pid={os.getpid()}，socket 文件创建于 "
                        f"{self._format_socket_mtime()}。检测到该路径上存在其他进程的活监听，"
                        "为避免消息串线已拒绝 unlink。请检查是否重复启动了 MaiBot/插件进程，"
                        "或改用其他 socket 路径。"
                    )
                # 残留死文件 → 安全 unlink（原逻辑）
                get_logger("plugin_runtime.transport").debug("清理 UDS 残留 socket 文件: %s", self._socket_path)
                with contextlib.suppress(FileNotFoundError):
                    self._socket_path.unlink()

            # 确保父目录存在
            self._socket_path.parent.mkdir(parents=True, exist_ok=True)

            self._server = await asyncio.start_unix_server(_on_connect, path=str(self._socket_path))
            # bind 成功 → 此文件归本实例所有，后续清理仅限此处
            self._owns_socket = True

            # 设置文件权限为仅当前用户可访问
            self._socket_path.chmod(0o600)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                # 报错信息区分「活监听占用」vs「残留文件/其他启动失败」
                title = "UDS socket 路径被活监听占用" if isinstance(exc, UDSSocketOccupiedError) else "UDS 传输异常"
                port.report(ErrorLevel.WARNING, title, exception=exc)
            get_logger("plugin_runtime.transport").debug("UDS 传输异常: %s", exc)
            # 只清理自己创建的 socket——活监听占用时绝不能 unlink 他人的活 socket
            if self._owns_socket and self._socket_path.exists():
                self._socket_path.unlink()
                self._owns_socket = False
            raise

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        # 只清理自己创建的 socket 文件——start 失败（活监听占用）时绝不能 unlink 他人的活 socket
        if self._owns_socket:
            with contextlib.suppress(FileNotFoundError):
                self._socket_path.unlink()
            self._owns_socket = False

    def _format_socket_mtime(self) -> str:
        """格式化 socket 文件修改时间（碰撞诊断用）；stat 失败时返回占位符。"""
        try:
            mtime = self._socket_path.stat().st_mtime
        except OSError:
            return "未知"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))

    def get_address(self) -> str:
        return str(self._socket_path)


class UDSTransportClient(TransportClient):
    """UDS 传输客户端
    
    用于主动连接到 UDS 服务端。
    """

    def __init__(self, socket_path: Path) -> None:
        self._socket_path: Path = socket_path

    async def connect(self) -> Connection:
        """建立到 UDS 服务端的连接
        
        Returns:
            UDSConnection: 连接对象
            
        Raises:
            RuntimeError: 当在非 Unix 平台（如 Windows）上调用时
        """
        # 平台检查：UDS 仅在 Unix-like 系统上可用
        if sys.platform == "win32":
            raise RuntimeError("UDS 不支持 Windows 平台，请使用 Named Pipe")
        
        reader, writer = await asyncio.open_unix_connection(str(self._socket_path))
        return UDSConnection(reader, writer)
