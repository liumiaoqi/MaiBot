"""运行时端口全局注册点 — maisaka 外围模块通过此注册点查询运行时实例。

替代直接导入 heartflow_manager，打破 maisaka → chat.heart_flow 的物理依赖：
maisaka 通过 ChatRuntimeRegistry 接口查询运行时，不依赖 heartflow_manager 单例。

注册点：
- ChatRuntimeRegistry：运行时查询/创建/列表
- ChatRuntimeFactory：运行时工厂（heartflow_manager 通过此创建运行时，不依赖 maisaka 具体类）
"""

from __future__ import annotations

from typing import Optional

from src.core.protocols import ChatRuntimeFactory, ChatRuntimeRegistry

_registry: Optional[ChatRuntimeRegistry] = None
_factory: Optional[ChatRuntimeFactory] = None


# ── ChatRuntimeRegistry ───────────────────────────────────────────


def register_chat_runtime_registry(registry: ChatRuntimeRegistry) -> None:
    """注册全局 ChatRuntimeRegistry 实例（启动时由适配器层调用一次）。"""
    global _registry
    _registry = registry


def get_chat_runtime_registry() -> Optional[ChatRuntimeRegistry]:
    """获取全局 ChatRuntimeRegistry 实例。

    Returns:
        ChatRuntimeRegistry 实例，未注册时返回 None
    """
    return _registry


# ── ChatRuntimeFactory ────────────────────────────────────────────


def register_chat_runtime_factory(factory: ChatRuntimeFactory) -> None:
    """注册全局 ChatRuntimeFactory 实例（启动时由 maisaka 层调用一次）。

    heartflow_manager 通过此工厂创建运行时，不再知道 MaisakaHeartFlowChatting 具体类。
    """
    global _factory
    _factory = factory


def get_chat_runtime_factory() -> Optional[ChatRuntimeFactory]:
    """获取全局 ChatRuntimeFactory 实例。

    Returns:
        ChatRuntimeFactory 实例，未注册时返回 None
    """
    return _factory
