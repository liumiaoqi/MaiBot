"""Runner 端配置与重连策略。

定义 RunnerEndpoint 端点配置和指数退避重连算法。
"""


import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class RunnerEndpointConfig:
    """Runner 端 gRPC 连接配置。"""

    host_address: str
    runner_id: str = ""
    sdk_version: str = ""
    session_token: str = ""
    scopes: list[str] = field(default_factory=list)
    tools: list = field(default_factory=list)
    events: list = field(default_factory=list)
    plugin_id: str = ""
    plugin_version: str = "1.0.0"
    reconnect_max_retries: int = 10
    reconnect_initial_delay_s: float = 1.0
    reconnect_max_delay_s: float = 30.0
    tool_timeout_ms: int = 30000

    def __post_init__(self) -> None:
        if not self.runner_id:
            self.runner_id = uuid.uuid7().hex
        if not self.sdk_version:
            self.sdk_version = "4.0.0"


class ReconnectPolicy:
    """指数退避重连策略，序列示例（1.0/2.0/4.0/8.0/16.0/30.0...）。"""

    def __init__(self, max_retries: int, initial_delay_s: float, max_delay_s: float) -> None:
        self.max_retries = max_retries
        self.initial_delay_s = initial_delay_s
        self.max_delay_s = max_delay_s
        self._attempt: int = 0

    def next_delay(self) -> float | None:
        """计算下次重连延时间隔。重试耗尽返回 None。"""
        if self._attempt >= self.max_retries:
            return None
        delay = min(self.initial_delay_s * 2 ** self._attempt, self.max_delay_s)
        self._attempt += 1
        return delay

    def reset(self) -> None:
        """重置重试计数器（连接成功后调用）。"""
        self._attempt = 0
