"""ZG-N6 统一 Token 计量服务——Protocol 接口契约。

核心契约——port_registry 注入点依赖此 Protocol，不直接依赖 TokenMeter 类。
对齐 dsh Service 基类隐式契约。
"""

from typing import Any, Protocol, runtime_checkable

from src.core.token_meter.types import TokenMeasurement


@runtime_checkable
class TokenMeterPort(Protocol):
    """TokenMeter 核心契约——统一 token 计量服务接口。"""

    def estimate(self, message: Any) -> int:
        """估算单条消息 token 数。"""
        ...

    def estimate_text(self, text: str) -> int:
        """估算纯文本 token 数。"""
        ...

    def measure(self, session_id: str, *, request_header: Any | None = None) -> TokenMeasurement:
        """计量会话压力快照。"""
        ...

    def get_context_window(self, model_route: Any | None = None) -> int:
        """获取上下文窗口大小。"""
        ...