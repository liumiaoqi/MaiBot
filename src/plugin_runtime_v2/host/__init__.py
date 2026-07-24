
"""gRPC Host 端 — Phoenix-1 实现。

接受 Runner 连接、校验 Scope、注册组件、转发 Tool 调用。
"""

from src.plugin_runtime_v2.host.connection import (
    ConnectionState,
    HostEndpointConfig,
    RunnerConnection,
    RunnerConnectionSnapshot,
)
from src.plugin_runtime_v2.host.endpoint import HostEndpoint
from src.plugin_runtime_v2.host.registry import RunnerRegistry

__all__ = [
    "ConnectionState",
    "HostEndpoint",
    "HostEndpointConfig",
    "RunnerConnection",
    "RunnerConnectionSnapshot",
    "RunnerRegistry",
]
