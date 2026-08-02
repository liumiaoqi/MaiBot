"""ResourceEventPropagator — 事件传播引擎，对标 Linux memory.events。

沿插件父链 do-while 向上传播至根，支持"仅本地"开关与去重。
对标 Linux __memcg_memory_event 的 do-while 沿 parent 循环。
"""


from src.common.logger import get_logger
import time
from typing import Any, Optional

logger = get_logger(__name__)

_DEFAULT_DEDUP_WINDOW_MS = 1000
_DEFAULT_MAX_DEPTH = 32


class ResourceEventPropagator:
    """事件传播引擎，对应 design §3.5。"""

    def __init__(
        self,
        event_bus: Any = None,
        config_manager: Any = None,
        dedup_window_ms: int = _DEFAULT_DEDUP_WINDOW_MS,
        max_depth: int = _DEFAULT_MAX_DEPTH,
    ):
        self._event_bus = event_bus
        self._config = config_manager
        self._dedup_window_ms = dedup_window_ms
        self._max_depth = max_depth
        # 去重缓存: key=(plugin_id, event_type), value=上次传播时间
        self._dedup_cache: dict[tuple[str, str], float] = {}

    async def propagate(
        self,
        plugin_id: str,
        event_type: str,
        data: dict[str, Any],
        local_only: bool = False,
        node_provider: Optional[Any] = None,
    ) -> None:
        """事件向上传播，对应 design §3.5.3。

        去重判定 → local_only 则仅当前节点 → 否则 do-while 沿父链向上 emit。

        Args:
            plugin_id: 事件源插件标识
            event_type: 事件类型（resource.usage / resource.limit_exceeded / resource.pressure.{level} / resource.oom）
            data: 事件数据
            local_only: 仅本地标志
            node_provider: 提供 get_node(plugin_id) 方法的对象（ResourceCounter）
        """
        # 去重判定
        cache_key = (plugin_id, event_type)
        now = time.monotonic()
        last_time = self._dedup_cache.get(cache_key)
        if last_time is not None:
            elapsed_ms = (now - last_time) * 1000
            if elapsed_ms < self._dedup_window_ms:
                return  # 窗口内去重

        self._dedup_cache[cache_key] = now

        # local_only 或节点配置 events_local=true 时仅当前节点
        is_local = local_only
        if not is_local and self._config:
            is_local = self._config.is_events_local(plugin_id)

        if is_local:
            await self._emit_one(plugin_id, event_type, data)
            return

        # do-while 沿父链向上传播至根
        if node_provider is None:
            await self._emit_one(plugin_id, event_type, data)
            return

        current = node_provider.get_node(plugin_id)
        depth = 0
        while current is not None:
            if depth > self._max_depth:
                logger.warning(
                    "事件传播深度超限 %d，截断: %s/%s",
                    self._max_depth,
                    plugin_id,
                    event_type,
                )
                break

            await self._emit_one(current.plugin_id, event_type, data)
            current = getattr(current, "parent", None)
            depth += 1

    async def _emit_one(self, plugin_id: str, event_type: str, data: dict[str, Any]) -> None:
        """向单个插件 emit 事件，失败时记录但继续至下一节点。"""
        if self._event_bus is None:
            return

        try:
            emit_data = {**data, "plugin_id": plugin_id}
            await self._event_bus.emit(event_type, emit_data)
        except Exception as e:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.error(
                "事件 emit 失败，继续至下一节点: %s/%s -> %s",
                plugin_id,
                event_type,
                e,
            )

    def clear_dedup_cache(self) -> None:
        """清除去重缓存（测试用）。"""
        self._dedup_cache.clear()
