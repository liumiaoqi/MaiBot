"""SDK v4 插件上下文 — 替代 v3 的 self.ctx。

通过 self.ctx 访问，提供消息发送、键值存储、日志桥接等子对象。
所有方法使用 session_id 替代 v3 的 stream_id。Phoenix-6 补全 RPC 调用。
"""


import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger

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
        """发送文本消息。需要 message:send:text scope。"""
        self._check_scope("text")
        return await self._runner.send_message("TEXT", session_id, text_content=text)

    async def image(self, session_id: str, image_base64: str) -> dict[str, Any]:
        """发送图片。需要 message:send:image scope。"""
        self._check_scope("image")
        return await self._runner.send_message("IMAGE", session_id, image_base64=image_base64)

    async def emoji(self, session_id: str, emoji_base64: str) -> dict[str, Any]:
        """发送表情包。需要 message:send:emoji scope。"""
        self._check_scope("emoji")
        return await self._runner.send_message("EMOJI", session_id, emoji_base64=emoji_base64)

    async def forward(self, session_id: str, message_id: str) -> dict[str, Any]:
        """发送转发消息。需要 message:send:forward scope。"""
        self._check_scope("forward")
        return await self._runner.send_message("FORWARD", session_id, forward_message_id=message_id)

    async def hybrid(self, session_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
        """发送图文混合消息。需要 message:send:hybrid scope。"""
        self._check_scope("hybrid")
        import json
        return await self._runner.send_message("HYBRID", session_id, hybrid_payload=json.dumps(segments))


class StorageContext:
    """键值存储上下文 — 需要 database:read:self / database:write:self scope。"""

    def __init__(self, granted_scopes: set[str], runner_endpoint: RunnerEndpoint, plugin_id: str) -> None:
        self._granted_scopes = granted_scopes
        self._runner = runner_endpoint
        self._plugin_id = plugin_id

    async def get(self, key: str, default: Any = None) -> Any:
        """读取键值。需要 database:read:self scope。"""
        if "database:read:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:read:self 未授权")
        return await self._runner.storage_get(key, default)

    async def set(self, key: str, value: Any) -> None:
        """写入键值。需要 database:write:self scope。"""
        if "database:write:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:write:self 未授权")
        await self._runner.storage_set(key, value)

    async def delete(self, key: str) -> bool:
        """删除键值。需要 database:write:self scope。"""
        if "database:write:self" not in self._granted_scopes:
            raise ScopeDeniedError("Scope database:write:self 未授权")
        return await self._runner.storage_delete(key)


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


class ConfigContext:
    """SDK 暴露给插件的配置访问对象。设计参考 dsh SettingsScope `index.ts:103-129`。"""

    def __init__(self, plugin_id: str, runner_endpoint) -> None:
        self._plugin_id = plugin_id
        self._runner_endpoint = runner_endpoint
        self._cache: dict = {}  # 配置缓存（初始空 dict，spec 5.2.3 场景 3）
        self._revision: int = 0
        self._watch_callbacks: list[Callable[[dict, dict], None]] = []
        self._ready: bool = False

    def get(self) -> dict:
        """返回合并后配置（内存读取，不触发 gRPC）。"""
        if not self._ready:
            get_logger("plugin_runtime_v2.sdk.context").warning(
                f"插件 {self._plugin_id} 配置未就绪，返回空 dict"
            )
        return self._cache

    def watch(
        self,
        callback: Callable[[dict, dict], None],
    ) -> Callable[[], None]:
        """注册配置变更回调 callback(new, prev)。返回取消订阅函数。"""
        self._watch_callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._watch_callbacks:
                self._watch_callbacks.remove(callback)
        return unsubscribe

    async def update(self, patch: dict) -> None:
        """发起配置更新请求到 Host（通过 gRPC）。Host 合并后回推。"""
        await self._runner_endpoint.update_plugin_config(self._plugin_id, patch)

    def _apply_update(self, new_config: dict, revision: int) -> None:
        """Runner 收到 RPC 推送时调用：更新缓存 → 风扇出 watch callbacks(new, prev)。"""
        prev_config = self._cache
        self._cache = new_config
        self._revision = revision
        self._ready = True
        # 风扇出 watch callbacks（spec 5.3.1 规则 9）
        for callback in self._watch_callbacks:
            try:
                callback(new_config, prev_config)
            except Exception as e:
                get_logger("plugin_runtime_v2.sdk.context").error(
                    f"watch callback 异常: {e}"
                )

    @property
    def revision(self) -> int:
        """返回当前配置 revision。"""
        return self._revision


class PluginContext:
    """插件运行时上下文 — 替代 v3 的 self.ctx。Phoenix-6 补全 RPC 调用。"""

    def __init__(
        self,
        plugin_id: str,
        granted_scopes: set[str],
        runner_endpoint: RunnerEndpoint,
        homecard_registry: dict[str, dict[str, Any]],
        config: ConfigContext | None = None,  # ZG16-6a 新增（可选，初始下发后注入）
    ) -> None:
        self._send = SendContext(granted_scopes, runner_endpoint)
        self._storage = StorageContext(granted_scopes, runner_endpoint, plugin_id)
        self._logger = LoggerContext(plugin_id)
        self._runner = runner_endpoint
        self._homecard_registry = homecard_registry
        # ZG-15：自启任务登记（on_unload 前 cancel_all_tasks 统一取消）
        self._registered_tasks: set[asyncio.Task] = set()
        # ZG16-6a: 配置访问对象
        self._config = config or ConfigContext(plugin_id, runner_endpoint)

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

    @property
    def config(self) -> ConfigContext:
        """SDK 配置访问对象（ctx.config.get/watch/update）。ZG16-6a 新增。"""
        return self._config

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
        self._check_scope("get_session_info", "session:read:detail")
        return await self._runner.get_session_info(session_id)

    def update_granted_scopes(self, new_scopes: set[str]) -> None:
        """更新已授权的 scope 集合（Host 拒绝部分 scope 后调用）。"""
        self._send._granted_scopes = new_scopes
        self._storage._granted_scopes = new_scopes

    # ── ZG-15：自启任务登记 ─────────────────────────────────────

    def register_task(self, task: "asyncio.Task") -> None:
        """登记插件自启的后台任务（硬契约：on_unload 前由 cancel_all_tasks 统一取消）。

        GOING 状态后拒绝新登记——卸载已开始，新任务会成为孤儿。

        Args:
            task: 插件 on_load 中创建的 asyncio.Task
        """
        if self._runner.is_going():
            self._logger.warning(
                "GOING 状态下 register_task 被拒绝（任务将成为孤儿）")
            return
        self._registered_tasks.add(task)
        task.add_done_callback(self._registered_tasks.discard)

    async def cancel_all_tasks(self, timeout_s: float = 5.0) -> None:
        """取消所有已登记的自启任务（卸载前调用）。

        - 已完成的 task 自动移除（done callback）
        - 拒绝取消（捕获 CancelledError 未退出）的任务等待超时后继续，输出 WARNING
        """
        if not self._registered_tasks:
            return
        tasks = list(self._registered_tasks)
        for task in tasks:
            task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "自启任务取消超时（%ss），继续卸载：%d 个任务未退出",
                timeout_s, len(self._registered_tasks),
            )
        self._registered_tasks.clear()
