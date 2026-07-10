"""会话端口全局注册点 — maisaka 外围模块通过此注册点查询会话信息。

替代直接导入 chat_manager，实现组件兼容核心原则：
核心模块不依赖 chat_manager 具体实现，只通过 Protocol 查询。

注册点：
- SessionInfoPort：会话信息快照查询
- SessionLifecyclePort：会话创建/获取、持久化、初始化
- SessionQueryPort：批量解析、消息缓存、会话列表、路由元数据
- MessageRegistryPort：入站消息注册
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.protocols import (
    MessageRegistryPort,
    SessionInfoPort,
    SessionLifecyclePort,
    SessionQueryPort,
)
from src.core.types import SessionInfo

_info_port: Optional[SessionInfoPort] = None
_lifecycle_port: Optional[SessionLifecyclePort] = None
_query_port: Optional[SessionQueryPort] = None
_registry_port: Optional[MessageRegistryPort] = None


# ── SessionInfoPort ────────────────────────────────────────────────


def register_session_info_port(port: SessionInfoPort) -> None:
    """注册全局 SessionInfoPort 实例（启动时由适配器层调用一次）。"""
    global _info_port
    _info_port = port


def get_session_info_port() -> Optional[SessionInfoPort]:
    """获取全局 SessionInfoPort 实例。

    供需要持有 port 引用的模块使用（如 A_memorix 注入到 SDKMemoryKernel）。
    未注册时返回 None。
    """
    return _info_port


def get_session_info(session_id: str) -> Optional[SessionInfo]:
    """查询会话信息快照。

    未注册时返回 None（启动早期或测试环境）。
    """
    if _info_port is None:
        return None
    return _info_port.get_session_info(session_id)


def get_session_name(session_id: str) -> str:
    """查询会话展示名称。

    未注册或会话不存在时返回 session_id 本身。
    """
    info = get_session_info(session_id)
    if info is not None:
        return info.session_name or session_id
    return session_id


def get_existing_session_info(session_id: str) -> Optional[SessionInfo]:
    """查询会话信息（内存未命中时从数据库加载）。

    未注册时返回 None（启动早期或测试环境）。
    """
    if _info_port is None:
        return None
    return _info_port.get_existing_session_info(session_id)


# ── SessionLifecyclePort ──────────────────────────────────────────


def register_session_lifecycle_port(port: SessionLifecyclePort) -> None:
    """注册全局 SessionLifecyclePort 实例（启动时由适配器层调用一次）。"""
    global _lifecycle_port
    _lifecycle_port = port


def get_session_lifecycle_port() -> Optional[SessionLifecyclePort]:
    """获取全局 SessionLifecyclePort 实例。未注册时返回 None。"""
    return _lifecycle_port


# ── SessionQueryPort ──────────────────────────────────────────────


def register_session_query_port(port: SessionQueryPort) -> None:
    """注册全局 SessionQueryPort 实例（启动时由适配器层调用一次）。"""
    global _query_port
    _query_port = port


def get_session_query_port() -> Optional[SessionQueryPort]:
    """获取全局 SessionQueryPort 实例。未注册时返回 None。"""
    return _query_port


def get_last_message(session_id: str) -> Optional[Any]:
    """查询会话最新消息。

    通过 SessionQueryPort 获取，不再直接导入 chat_manager。
    未注册或无消息时返回 None。
    """
    if _query_port is not None:
        return _query_port.get_last_message(session_id)
    return None


# ── MessageRegistryPort ───────────────────────────────────────────


def register_message_registry_port(port: MessageRegistryPort) -> None:
    """注册全局 MessageRegistryPort 实例（启动时由适配器层调用一次）。"""
    global _registry_port
    _registry_port = port


def get_message_registry_port() -> Optional[MessageRegistryPort]:
    """获取全局 MessageRegistryPort 实例。未注册时返回 None。"""
    return _registry_port