"""Event 分发器 — 将 Runner 推送的 Event 分发到核心事件系统。

Phoenix-2 阶段采用简单规则判断：
- HomeCard → 日志记录（WebUI 转发由 Phoenix-4 实现）
- 预定义触发思考列表 → 日志记录（ThinkingOrgan 对接由 Phoenix-4 实现）
- 普通 Event → 日志记录
"""

from __future__ import annotations

from typing import Any

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.mcp.event_dispatcher")

# ── Phoenix-2 阶段触发思考的 Event 预定义列表 ──
_THINK_TRIGGER_EVENTS: frozenset[str] = frozenset({
    "timer",
    "environment_change",
    "message_received",
    "user_mentioned",
})


class EventDispatcher:
    """Host 端 Event 分发器。

    Phoenix-2 阶段不实际调用注入的接口，但保留以便后续扩展。
    """

    def __init__(
        self,
        message_port=None,
        session_repo=None,
        person_info_port=None,
    ) -> None:
        self._message_port = message_port
        self._session_repo = session_repo
        self._person_info_port = person_info_port

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

        try:
            card_meta = getattr(event_declaration, "card_metadata", None)
            if card_meta:
                logger.info(
                    "HomeCard Event: %s plugin=%s title=%s",
                    event_name, plugin_id, card_meta.get("title", ""),
                )
                # TODO: Phoenix-4 实现 WebUI 转发
                return

            if event_name in _THINK_TRIGGER_EVENTS:
                logger.info(
                    "触发思考 Event: %s plugin=%s", event_name, plugin_id,
                )
                # TODO: Phoenix-4 实现 ThinkingOrgan.think_proactive() 对接
                return

            logger.info("Event 已分发: %s plugin=%s", event_name, plugin_id)
        except Exception as exc:
            logger.warning(
                "Event %s 分发异常 (plugin=%s): %s",
                event_name, plugin_id, exc,
            )
