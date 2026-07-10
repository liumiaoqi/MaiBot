"""SessionInfoPort 全局注册点 — maisaka 外围模块通过此注册点查询会话信息。

替代直接导入 chat_manager，实现组件兼容核心原则：
核心模块不依赖 chat_manager 具体实现，只通过 SessionInfoPort Protocol 查询。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from src.core.protocols import SessionInfoPort
from src.core.types import SessionInfo

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage

_port: Optional[SessionInfoPort] = None


def register_session_info_port(port: SessionInfoPort) -> None:
    """注册全局 SessionInfoPort 实例（启动时由适配器层调用一次）。"""
    global _port
    _port = port


def get_session_info_port() -> Optional[SessionInfoPort]:
    """获取全局 SessionInfoPort 实例。

    供需要持有 port 引用的模块使用（如 A_memorix 注入到 SDKMemoryKernel）。
    未注册时返回 None。
    """
    return _port


def get_session_info(session_id: str) -> Optional[SessionInfo]:
    """查询会话信息快照。

    未注册时返回 None（启动早期或测试环境）。
    """
    if _port is None:
        return None
    return _port.get_session_info(session_id)


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
    if _port is None:
        return None
    return _port.get_existing_session_info(session_id)


def get_last_message(session_id: str) -> Optional[Any]:
    """查询会话最新消息。

    延迟导入 chat_manager.last_messages，避免核心层直接依赖。
    未注册或无消息时返回 None。
    """
    from src.chat.message_receive.chat_manager import chat_manager

    return chat_manager.last_messages.get(session_id)