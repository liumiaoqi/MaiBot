"""SDK v4 插件上下文 — 替代 v3 的 self.ctx。

通过 self.ctx 访问，提供消息发送、键值存储、日志桥接等子对象。
所有方法使用 session_id 替代 v3 的 stream_id。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint


class ScopeDeniedError(Exception):
    """Scope 未授权异常。"""


class SendContext:
    """消息发送上下文 — 需要 message:send:* scope。"""

    _SCOPE_CHECK = {
        "text": "message:send:text",
        "image": "message:send:image",
        "emoji": "message:send:emoji",
        "forward": "message:send:forward",
        "hybrid": "message:send:hybrid",
    }

    def __init__(self, granted_scopes: set[str], runner_endpoint: RunnerEndpoint) -> None:
        self._granted_scopes = granted_scopes
        self._runner = runner_endpoint

    def _check_scope(self, method: str) -> None:
        scope = self._SCOPE_CHECK[method]
        if scope not in self._granted_scopes:
            raise ScopeDeniedError(f"Scope {scope} 未授权")

    async def text(self, session_id: str, text: str) -> dict[str, Any]:
        """发送文本消息。需要 message:send:text scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        self._check_scope("text")
        return {"session_id": session_id, "type": "text"}

    async def image(self, session_id: str, image_base64: str) -> dict[str, Any]:
        """发送图片。需要 message:send:image scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        self._check_scope("image")
        return {"session_id": session_id, "type": "image"}

    async def emoji(self, session_id: str, emoji_base64: str) -> dict[str, Any]:
        """发送表情包。需要 message:send:emoji scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        self._check_scope("emoji")
        return {"session_id": session_id, "type": "emoji"}

    async def forward(self, session_id: str, message_id: str) -> dict[str, Any]:
        """发送转发消息。需要 message:send:forward scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        self._check_scope("forward")
        return {"session_id": session_id, "type": "forward"}

    async def hybrid(self, session_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
        """发送图文混合消息。需要 message:send:hybrid scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        self._check_scope("hybrid")
        return {"session_id": session_id, "type": "hybrid"}


class StorageContext:
    """键值存储上下文 — 需要 database:read:self / database:write:self scope。"""

    def __init__(self, granted_scopes: set[str], runner_endpoint: RunnerEndpoint, plugin_id: str) -> None:
        self._granted_scopes = granted_scopes
        self._runner = runner_endpoint
        self._plugin_id = plugin_id

    async def get(self, key: str, default: Any = None) -> Any:
        """读取键值。需要 database:read:self scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        if "database:read:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:read:self 未授权")
        return default

    async def set(self, key: str, value: Any) -> None:
        """写入键值。需要 database:write:self scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        if "database:write:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:write:self 未授权")

    async def delete(self, key: str) -> bool:
        """删除键值。需要 database:write:self scope。

        Phoenix-2 占位实现。TODO: Phoenix-4 实现 RPC 通道
        """
        if "database:write:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:write:self 未授权")
        return False


class LoggerContext:
    """日志桥接上下文 — 无需 scope。"""

    def __init__(self, plugin_id: str) -> None:
        from src.common.logger import get_logger
        self._logger = get_logger(f"plugin.{plugin_id}")

    def debug(self, msg: str, *args: Any) -> None:
        self._logger.debug(msg, *args)

    def info(self, msg: str, *args: Any) -> None:
        self._logger.info(msg, *args)

    def warning(self, msg: str, *args: Any) -> None:
        self._logger.warning(msg, *args)

    def error(self, msg: str, *args: Any) -> None:
        self._logger.error(msg, *args)


class PluginContext:

    """插件运行时上下文 — 替代 v3 的 self.ctx。Phoenix-2 补全实现。"""

    def __init__(
        self,
        plugin_id: str,
        granted_scopes: set[str],
        runner_endpoint: RunnerEndpoint,
        homecard_registry: dict[str, dict[str, Any]],
    ) -> None:
        self._send = SendContext(granted_scopes, runner_endpoint)
        self._storage = StorageContext(granted_scopes, runner_endpoint, plugin_id)
        self._logger = LoggerContext(plugin_id)
        self._runner = runner_endpoint
        self._homecard_registry = homecard_registry

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

    def _check_scope(self, label: str, scope: str) -> None:
        if scope not in self._send._granted_scopes:
            raise ScopeDeniedError(f"{label}: Scope {scope} 未授权")

    async def emit_event(self, name: str, payload: dict[str, Any]) -> None:

        """推送事件。通过 RunnerEndpoint 发送到 Host。"""
        if not self._runner.is_ready:
            raise ConnectionError("Runner 未连接")
        await self._runner.emit_event(name, payload)

    async def emit_card(self, name: str, data: dict[str, Any]) -> None:

        """推送 HomeCard 数据。自动合并卡片元数据后通过 emit_event 发送。"""
        card_metadata = self._homecard_registry.get(name)
        if card_metadata is None:
            self._logger.warning(f"未找到 HomeCard 声明: {name}")
        homecard_payload = {
            "name": name,
            "title": (card_metadata or {}).get("title", ""),
            "width": (card_metadata or {}).get("width", "medium"),
            "data": data,
        }
        await self.emit_event(name, homecard_payload)

    async def get_session_info(self, session_id: str) -> dict[str, Any]:
        """查询会话信息。需要 session:read:detail scope。TODO: Phoenix-4 实现 RPC 通道。"""
        self._check_scope("get_session_info", "session:read:detail")
        return {"session_id": session_id, "session_name": "", "platform": "", "is_group_session": False}
