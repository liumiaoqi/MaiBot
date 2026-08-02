"""ChatManagerAdapter — 统一适配器，同时满足 5 个 Protocol。

合并 SessionRepository + SessionInfoPort + SessionLifecyclePort + SessionQueryPort + MessageRegistryPort。
子模块实例通过构造注入，不再通过 ChatManager 单例间接访问。
"""


import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from src.common.logger import get_logger
from src.core.protocols import (
    AgentRoutingService,
)
from src.core.service_manager.types import HealthCheckResult
from src.core.types import SessionInfo
from src.platform_io.route_key_factory import RouteKeyFactory

logger = get_logger("core.adapters.chat_manager_adapter")


class ChatManagerAdapter:
    """通过子模块直接注入实现 5 个 Protocol。

    返回不可变 SessionInfo 快照，外部修改不影响内部状态。
    不再持有 ChatManager 单例引用。
    """

    def __init__(
        self,
        routing_service: AgentRoutingService,
        session_store: Any,
        message_registry: Any,
        name_cache: Any,
        resolver: Any,
        binding_restorer: Any = None,
        session_lifecycle: Any = None,
    ) -> None:
        self._routing_service = routing_service
        self._session_store = session_store
        self._message_registry = message_registry
        self._name_cache = name_cache
        self._resolver = resolver
        self._binding_restorer = binding_restorer
        self._session_lifecycle = session_lifecycle
        # T14 ZG-8 衔接：会话生命周期订阅 + 关联任务注册表（致命扩散目标）
        self._session_created_subscribers: list[Callable[[str], None]] = []
        self._session_destroyed_subscribers: list[Callable[[str], None]] = []
        self._session_tasks: dict[str, list[asyncio.Task]] = {}
        for name, val in (
            ("routing_service", routing_service),
            ("session_store", session_store),
            ("message_registry", message_registry),
            ("name_cache", name_cache),
            ("resolver", resolver),
        ):
            if val is None:
                raise TypeError(f"ChatManagerAdapter: {name} 不能为 None")

    def _ensure_binding_restorer(self):
        if self._binding_restorer is None:
            raise RuntimeError("ChatManagerAdapter: binding_restorer 未注入")
        return self._binding_restorer

    def _ensure_session_lifecycle(self):
        if self._session_lifecycle is None:
            raise RuntimeError("ChatManagerAdapter: session_lifecycle 未注入")
        return self._session_lifecycle

    def _build_session_info(self, session, session_id: str) -> SessionInfo:
        primary_agent_id = self._routing_service.get_primary_agent(session_id) or ""
        cohabitant_ids = self._routing_service.get_session_all_agents(session_id) - {primary_agent_id}
        session_name = self._name_cache.get(session_id) or session_id

        return SessionInfo(
            session_id=session.session_id,
            session_name=session_name,
            platform=session.platform,
            is_group_session=session.is_group_session,
            group_id=session.group_id or "",
            group_name=session.group_name or "",
            user_id=session.user_id or "",
            user_nickname=session.user_nickname or "",
            primary_agent_id=primary_agent_id,
            cohabitant_agent_ids=cohabitant_ids,
            created_timestamp=session.created_timestamp,
            last_active_timestamp=session.last_active_timestamp,
            account_id=session.account_id or "",
            scope=session.scope or "",
            user_cardname=session.user_cardname or "",
        )

    # ── SessionRepository ──────────────────────────────────────────

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        session = self._session_store.get(session_id)
        if session is None:
            return None
        return self._build_session_info(session, session_id)

    async def get_session_name(self, session_id: str) -> str:
        name = self._name_cache.get(session_id)
        return name or session_id

    # ── SessionInfoPort ────────────────────────────────────────────

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        session = self._session_store.get(session_id)
        if session is None:
            return None
        return self._build_session_info(session, session_id)

    def get_existing_session_info(self, session_id: str) -> Optional[SessionInfo]:
        session = self._session_store.get_existing(session_id)
        if session is None:
            return None
        return self._build_session_info(session, session_id)

    # ── SessionLifecyclePort ───────────────────────────────────────

    async def get_or_create_session_id(
        self,
        platform: str,
        user_id: str = "",
        group_id: str = "",
        account_id: str = "",
        scope: str = "",
    ) -> str:
        lifecycle = self._ensure_session_lifecycle()
        before = set(self._session_store.list_session_ids()) if hasattr(self._session_store, "list_session_ids") else None
        session = await lifecycle.get_or_create_session(
            platform=platform,
            user_id=user_id,
            group_id=group_id or None,
            account_id=account_id or None,
            scope=scope or None,
        )
        # T14 ZG-8 衔接：新建会话通知订阅者（私有 pending 队列创建）
        if before is not None and session.session_id not in before:
            self._notify_session_created(session.session_id)
        return session.session_id

    def subscribe_session_created(self, callback: Callable[[str], None]) -> None:
        """订阅会话创建事件（ZG-8 维护私有 pending 队列）。"""
        self._session_created_subscribers.append(callback)

    def subscribe_session_destroyed(self, callback: Callable[[str], None]) -> None:
        """订阅会话销毁事件（ZG-8 清理私有队列 + 致命扩散）。

        说明：MaiBot 会话常驻无显式销毁路径，触发点待未来会话销毁功能接入；
        回调注册机制先行（渐进启用，spec §4.5 兼容性 3）。
        """
        self._session_destroyed_subscribers.append(callback)

    def _notify_session_created(self, session_id: str) -> None:
        for callback in self._session_created_subscribers:
            try:
                callback(session_id)
            except Exception:
                logger.warning("会话创建订阅回调异常", exc_info=True)

    def register_session_task(self, session_id: str, task: asyncio.Task) -> None:
        """注册会话关联异步任务（致命扩散取消目标，T14 ZG-8 衔接）。

        任务完成时自动从注册表移除。
        """
        tasks = self._session_tasks.setdefault(session_id, [])
        if task not in tasks:
            tasks.append(task)
            task.add_done_callback(
                lambda _t: self._session_tasks.get(session_id, []).remove(task)
                if task in self._session_tasks.get(session_id, [])
                else None
            )

    async def list_session_async_tasks(self, session_id: str) -> list:
        """查询会话关联的异步任务列表（致命扩散使用，T14 ZG-8 衔接）。"""
        return list(self._session_tasks.get(session_id, []))

    def save_all_sessions(self) -> None:
        lifecycle = self._ensure_session_lifecycle()
        lifecycle.save_all_sessions()

    async def initialize(self) -> None:
        lifecycle = self._ensure_session_lifecycle()
        restorer = self._ensure_binding_restorer()
        await lifecycle.initialize(restorer)

    async def regularly_save_sessions(self, interval_seconds: float = 300) -> None:
        lifecycle = self._ensure_session_lifecycle()
        await lifecycle.regularly_save_sessions(interval_seconds=int(interval_seconds))

    # ── SessionQueryPort ───────────────────────────────────────────

    def resolve_sessions_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> List[SessionInfo]:
        sessions = self._resolver.resolve_by_target(
            platform=platform,
            target_id=target_id,
            chat_type=chat_type,
        )
        return [
            self._build_session_info(session, session.session_id)
            for session in sessions
        ]

    def resolve_session_ids_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> set[str]:
        return self._resolver.resolve_ids_by_target(
            platform=platform,
            target_id=target_id,
            chat_type=chat_type,
        )

    def get_last_message(self, session_id: str) -> Any:
        return self._message_registry.last_messages.get(session_id)

    def list_sessions(self) -> List[SessionInfo]:
        sessions = self._session_store.sessions
        return [
            self._build_session_info(session, session_id)
            for session_id, session in list(sessions.items())
        ]

    def get_route_metadata(self, session_id: str) -> Dict[str, object]:
        session = self._session_store.get(session_id)
        if session is None:
            return {}

        metadata: Dict[str, object] = {}

        if session.account_id:
            metadata["account_id"] = session.account_id
        if session.scope:
            metadata["scope"] = session.scope

        if session.context is not None and session.context.message is not None:
            additional_config = session.context.message.message_info.additional_config
            if isinstance(additional_config, dict):
                for key in RouteKeyFactory.ACCOUNT_ID_KEYS:
                    if key in additional_config and key not in metadata:
                        metadata[key] = additional_config[key]
                for key in RouteKeyFactory.SCOPE_KEYS:
                    if key in additional_config and key not in metadata:
                        metadata[key] = additional_config[key]

        return metadata

    def get_session_count(self) -> int:
        sessions = self._session_store.sessions
        return len(sessions)

    # ── MessageRegistryPort ────────────────────────────────────────

    def register_message(self, message: Any) -> None:
        self._message_registry.register(message)

    # ── HealthProbePort ───────────────────────────────────────────

    async def health_probe(self) -> HealthCheckResult:
        """检查消息管道核心子模块是否可用。

        快速检查（≤5s），验证注入的 session_store / routing_service / message_registry 均可访问。
        """
        now = time.monotonic()
        checks: list[str] = []

        if self._session_store is None:
            checks.append("session_store 为 None")
        if self._routing_service is None:
            checks.append("routing_service 为 None")
        if self._message_registry is None:
            checks.append("message_registry 为 None")

        if checks:
            return HealthCheckResult(
                alive=False, timestamp=now, detail="; ".join(checks)
            )
        return HealthCheckResult(
            alive=True, timestamp=now, detail="消息管道所有核心子模块可用"
        )
