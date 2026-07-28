"""Phoenix-1 连接状态与数据模型。

定义连接生命周期状态枚举、Runner 连接实例、不可变快照、Host 配置。
"""


import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.host.connection")

# ── 状态转换规则（design.md 2.1.3.1） ──
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "disconnected": {"connecting"},
    "connecting": {"handshaking", "disconnected"},
    "handshaking": {"registering", "disconnected"},
    "registering": {"ready", "disconnected"},
    "ready": {"closing", "disconnected"},
    "closing": {"disconnected"},
}


class ConnectionState(str, Enum):
    """Runner 连接生命周期状态。

    DISCONNECTED：未连接，初始状态
    CONNECTING：正在建立 gRPC 连接
    HANDSHAKING：双向流已建立，等待握手完成
    REGISTERING：握手通过，等待组件注册
    READY：连接就绪，可接受 Tool 调用和 Event 推送
    CLOSING：正在关停，排空中
    """

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    HANDSHAKING = "handshaking"
    REGISTERING = "registering"
    READY = "ready"
    CLOSING = "closing"


@dataclass(slots=True)
class RunnerConnection:
    """单个 Runner 的连接实例，追踪状态和心跳信息。"""

    runner_id: str
    state: ConnectionState
    sdk_version: str
    session_token: str
    scopes: list[str]
    tools: list = field(default_factory=list)
    events: list = field(default_factory=list)
    plugin_id: str = ""
    plugin_version: str = ""
    connected_at: float = 0.0
    last_heartbeat_at: float = 0.0
    runner_listen_address: str = ""
    _heartbeat_misses: int = field(default=0, repr=False)
    _peer: str = field(default="", repr=False)

    def transition(self, new_state: ConnectionState) -> None:
        """状态转换。非法转换抛出 ValueError 并记录 ERROR 日志。"""
        allowed = _VALID_TRANSITIONS.get(self.state.value, set())
        if new_state.value not in allowed:
            msg = (
                f"Runner {self.runner_id}: 非法状态转换 "
                f"{self.state.value} → {new_state.value}"
            )
            logger.error(msg)
            raise ValueError(msg)
        self.state = new_state

    def record_heartbeat(self) -> None:
        """记录一次成功心跳响应。"""
        self._heartbeat_misses = 0
        self.last_heartbeat_at = time.time()

    def miss_heartbeat(self) -> int:
        """心跳未响应计数 +1，返回当前连续丢失次数。"""
        self._heartbeat_misses += 1
        return self._heartbeat_misses

    def to_snapshot(self) -> RunnerConnectionSnapshot:
        """返回不可变快照。"""
        return RunnerConnectionSnapshot(
            runner_id=self.runner_id,
            state=self.state.value,
            sdk_version=self.sdk_version,
            scopes=tuple(self.scopes),
            plugin_id=self.plugin_id,
            plugin_version=self.plugin_version,
            tool_count=len(self.tools),
            event_count=len(self.events),
            connected_at=self.connected_at,
            last_heartbeat_at=self.last_heartbeat_at,
        )


@dataclass(frozen=True, slots=True)
class RunnerConnectionSnapshot:
    """Runner 连接状态的不可变快照，可 JSON 序列化。"""

    runner_id: str
    state: str
    sdk_version: str
    scopes: tuple[str, ...]
    plugin_id: str
    plugin_version: str
    tool_count: int
    event_count: int
    connected_at: float
    last_heartbeat_at: float


@dataclass(frozen=True, slots=True)
class HostEndpointConfig:
    """Host 端 gRPC 服务配置。"""

    listen_address: str = "127.0.0.1:50051"
    heartbeat_interval_s: int = 30
    heartbeat_timeout_s: int = 10
    max_heartbeat_misses: int = 2
    register_timeout_s: int = 30
    default_drain_timeout_ms: int = 5000
    max_runners: int = 10
    server_id: str = ""

    def __post_init__(self) -> None:
        if not self.server_id:
            object.__setattr__(self, "server_id", uuid.uuid4().hex[:8])
