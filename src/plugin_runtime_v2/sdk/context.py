"""SDK v4 插件上下文 — 替代 v3 的 self.ctx。

通过 self.ctx 访问，提供消息发送、键值存储、日志桥接等子对象。
所有方法使用 session_id 替代 v3 的 stream_id。
"""

from __future__ import annotations

from typing import Any



class ScopeDeniedError(Exception):
    """Scope 未授权异常。"""


class SendContext:
    """消息发送上下文 — 需要 message:send:* scope。"""

    _SCOKE_CHECK = {
        "text": "message:send:text",
        "image": "message:send:image",
        "emoji": "message:send:emoji",
        "forward": "message:send:forward",
        "hybrid": "message:send:hybrid",
    }

    def __init__(self, granted_scopes: set[str]) -> None:
        self._granted_scopes = granted_scopes

    def _check_scope(self, method: str) -> None:
        scope = self._SCOKE_CHECK[method]
        if scope not in self._granted_scopes:
            raise ScopeDeniedError(f"Scope {scope} 未授权")

    async def text(self, session_id: str, text: str) -> dict[str, Any]:
        """发送文本消息。需要 message:send:text scope。"""
        self._check_scope("text")
        return {"session_id": session_id, "type": "text"}

    async def image(self, session_id: str, image_base64: str) -> dict[str, Any]:
        """发送图片。需要 message:send:image scope。"""
        self._check_scope("image")
        return {"session_id": session_id, "type": "image"}

    async def emoji(self, session_id: str, emoji_base64: str) -> dict[str, Any]:
        """发送表情包。需要 message:send:emoji scope。"""
        self._check_scope("emoji")
        return {"session_id": session_id, "type": "emoji"}

    async def hybrid(self, session_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
        """发送图文混合消息。需要 message:send:hybrid scope。"""
        self._check_scope("hybrid")
        return {"session_id": session_id, "type": "hybrid"}


class StorageContext:
    """键值存储上下文 — 需要 database:read:self / database:write:self scope。"""

    def __init__(self, granted_scopes: set[str]) -> None:
        self._granted_scopes = granted_scopes

    async def get(self, key: str, default: Any = None) -> Any:
        """读取键值。需要 database:read:self scope。"""
        if "database:read:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:read:self 未授权")
        return default

    async def set(self, key: str, value: Any) -> None:
        """写入键值。需要 database:write:self scope。"""
        if "database:write:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:write:self 未授权")

    async def delete(self, key: str) -> bool:
        """删除键值。需要 database:write:self scope。"""
        if "database:write:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:write:self 未授权")
        return False


class LoggerContext:
    """日志桥接上下文 — 无需 scope。"""

    def __init__(self, plugin_id: str) -> None:
        self._prefix = f"[{plugin_id}]"

    def debug(self, msg: str, *args: Any) -> None:
        pass

    def info(self, msg: str, *args: Any) -> None:
        pass

    def warning(self, msg: str, *args: Any) -> None:
        pass

    def error(self, msg: str, *args: Any) -> None:
        pass


class PluginContext:
    """插件运行时上下文 — 替代 v3 的 self.ctx。

    通过 self.ctx 访问，提供消息发送、键值存储、日志桥接等子对象。
    """

    def __init__(self, plugin_id: str, granted_scopes: set[str]) -> None:
        self._send = SendContext(granted_scopes)
        self._storage = StorageContext(granted_scopes)
        self._logger = LoggerContext(plugin_id)
        self._granted_scopes = granted_scopes

    @property
    def send(self) -> SendContext:
        """消息发送子对象。"""
        return self._send

    @property
    def storage(self) -> StorageContext:
        """键值存储子对象。"""
        return self._storage

    @property
    def logger(self) -> LoggerContext:
        """日志桥接子对象。"""
        return self._logger

    async def emit_event(self, name: str, payload: dict[str, Any]) -> None:
        """推送事件。需要对应 Event 的 scope。"""
        pass

    async def emit_card(self, name: str, data: dict[str, Any]) -> None:
        """推送卡片数据。需要对应 HomeCard 的 scope。"""
        pass