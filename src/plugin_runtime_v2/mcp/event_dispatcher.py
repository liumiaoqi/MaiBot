"""Event 分发器 — 将 Runner 推送的 Event 分发到核心事件系统。

CQ-6 T3: 消息类 Event 路由到 MessageIngestionPort，闭环 v2 消息入站。
"""


from typing import Any, Callable, TYPE_CHECKING

from src.common.logger import get_logger
from src.plugin_runtime_v2.mcp.payload_converter import NapCatPayloadConverter

if TYPE_CHECKING:
    from src.core.protocols import MessageIngestionPort, SessionRepository

logger = get_logger("plugin_runtime_v2.mcp.event_dispatcher")

_NAPCAT_INGEST_EVENTS = frozenset({"napcat.message", "napcat.group_message", "napcat.notice"})


class EventDispatcher:
    """Host 端 Event 分发器。

    消息类 Event 转换为 SessionMessage 后路由到 MessageIngestionPort。
    其他 Event 按类型处理（HomeCard → 日志，其他 → 日志）。
    """

    def __init__(
        self,
        get_message_port: Callable[[], MessageIngestionPort],
        get_session_repo: Callable[[], SessionRepository] | None = None,
    ) -> None:
        self._get_message_port = get_message_port
        self._get_session_repo = get_session_repo
        self._payload_converter = NapCatPayloadConverter()

    async def dispatch(
        self,
        event_name: str,
        payload: dict[str, Any],
        plugin_id: str,
        event_declaration: Any | None,
    ) -> None:
        """分发 Event 到核心事件系统。

        Args:
            event_name: 事件名称
            payload: 事件载荷
            plugin_id: 插件 ID
            event_declaration: 匹配的 Event 声明（None 表示未注册，调用方应预先过滤）
        """
        if event_declaration is None:
            logger.warning("未注册的 Event: %s (plugin=%s)", event_name, plugin_id)
            return

        if event_name in _NAPCAT_INGEST_EVENTS:
            try:
                session_message = self._payload_converter.convert(payload, event_name)
                await self._get_message_port().receive_message(session_message)
                logger.info("Event %s 已路由到消息入站端口", event_name)
            except Exception as e:
                logger.error("Event %s 路由失败: %s", event_name, e)
            return

        card_meta = getattr(event_declaration, "card_metadata", None)
        if card_meta:
            logger.info(
                "HomeCard Event: %s plugin=%s title=%s",
                event_name,
                plugin_id,
                card_meta.get("title", ""),
            )
            return

        logger.info("Event 已分发: %s plugin=%s", event_name, plugin_id)
