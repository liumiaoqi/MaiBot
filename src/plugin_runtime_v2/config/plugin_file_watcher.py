"""ZG16-6a: 每插件一个 watcher，监听其 config.toml。复用 watchfiles.awatch。

设计参考：dsh Chokidar watcher `settings-file/src/index.ts:232-269`。
"""

import asyncio
from collections.abc import Awaitable, Callable

from watchfiles import awatch

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.config.plugin_file_watcher")


class PluginFileWatcher:
    """每插件一个 watcher，监听其 config.toml。复用 watchfiles.awatch。

    设计参考 dsh Chokidar watcher `settings-file/src/index.ts:232-269`。
    """

    def __init__(
        self,
        plugin_id: str,
        config_path: str,
        debounce_ms: int = 300,
        callback: Callable[[str, str], Awaitable[None]] | None = None,  # (plugin_id, source) -> None
    ) -> None:
        self._plugin_id = plugin_id
        self._config_path = config_path
        self._debounce_ms = debounce_ms
        self._callback = callback
        self._stop_event = asyncio.Event()
        self._debounce_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动 watchfiles.awatch 监听插件 config.toml。"""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        """监听循环。失败降级为不监听 + warning（spec 5.3.3 场景 1）。"""
        try:
            async for _changes in awatch(self._config_path, stop_event=self._stop_event):
                await self._on_change()
        except Exception as e:
            logger.warning(f"插件 {self._plugin_id} FileWatcher 失败，降级不监听: {e}")

    async def stop(self) -> None:
        """取消监听。"""
        self._stop_event.set()
        if self._task is not None:
            await self._task

    async def _on_change(self) -> None:
        """debounce → callback(plugin_id, source='file_watcher')。

        设计参考 dsh queueRefresh `settings-file/src/index.ts:200`。
        """
        async with self._debounce_lock:
            await asyncio.sleep(self._debounce_ms / 1000)
            if self._callback is not None:
                await self._callback(self._plugin_id, "file_watcher")