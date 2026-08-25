"""SDK v4 接口定义 — Phoenix-0 产出接口设计，Phoenix-2 实现完整 SDK。

MaiBotPlugin 基类 + @Tool/@Event/@Command/@HomeCard 装饰器 + PluginContext 上下文。
"""

from src.plugin_runtime_v2.sdk.context import (
    LoggerContext,
    PluginContext,
    ScopeDeniedError,
    SendContext,
    StorageContext,
)
from src.plugin_runtime_v2.sdk.decorators import (
    Command,
    Event,
    HomeCard,
    MessageGateway,
    MessageGatewayDeclaration,
    Tool,
)
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

__all__ = [
    "MaiBotPlugin",
    "Tool",
    "Event",
    "Command",
    "HomeCard",
    "MessageGateway",
    "MessageGatewayDeclaration",
    "PluginContext",
    "SendContext",
    "StorageContext",
    "LoggerContext",
    "ScopeDeniedError",
]
