"""LogForwarder — 异步读取子进程 stdout/stderr 并转发到 Host 日志。"""

from __future__ import annotations

import asyncio
import subprocess

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.host.log_forwarder")


class LogForwarder:
    """异步读取 Runner 子进程 stdout/stderr 并转发到 Host 日志。

    通过 run_in_executor 将同步 PIPE 读取适配为异步，
    不阻塞事件循环。
    """

    def __init__(self, process: subprocess.Popen, runner_id: str) -> None:
        self._process = process
        self._runner_id = runner_id
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """启动 stdout/stderr 读取任务。"""
        loop = asyncio.get_running_loop()
        if self._process.stdout:
            self._tasks.append(
                asyncio.ensure_future(self._read_stream(self._process.stdout, "stdout", loop))
            )
        if self._process.stderr:
            self._tasks.append(
                asyncio.ensure_future(self._read_stream(self._process.stderr, "stderr", loop))
            )

    async def stop(self) -> None:
        """取消所有读取任务，不关闭 process（由 Spawner 管理）。"""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    async def _read_stream(self, stream, label: str, loop: asyncio.AbstractEventLoop) -> None:
        """在线程池中逐行读取，转发到日志。"""
        try:
            while True:
                line = await loop.run_in_executor(None, stream.readline)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text:
                    logger.info("[runner:%s:%s] %s", self._runner_id, label, text)
        except (BrokenPipeError, ValueError, asyncio.CancelledError):
            pass
