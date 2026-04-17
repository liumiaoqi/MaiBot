"""
MaiSaka asynchronous stdin reader for CLI interaction.
"""

from typing import Optional

import asyncio
import sys
import threading


class InputReader:
    """后台读取标准输入，并通过 asyncio.Queue 向主循环投递结果。"""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """启动后台输入线程。重复调用时忽略。"""
        if self._thread and self._thread.is_alive():
            return

        self._loop = loop
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, name="maisaka-input-reader", daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        """在后台线程中阻塞读取 stdin。"""
        while not self._stop_event.is_set():
            line = sys.stdin.readline()
            if self._loop is None:
                return

            if line == "":
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
                return

            self._loop.call_soon_threadsafe(self._queue.put_nowait, line.rstrip("\r\n"))

    async def get_line(self, timeout: Optional[int] = None) -> Optional[str]:
        """异步获取一行输入；设置 timeout 时支持超时返回。"""
        if timeout is None:
            return await self._queue.get()

        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def close(self) -> None:
        """请求后台线程停止。"""
        self._stop_event.set()
