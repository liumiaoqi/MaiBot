"""ZG-N6 统一 Token 计量服务——单例服务。

对齐 dsh `@deepseek-ai/dsh-token-meter` 的 index.ts TokenMeter class。
单例 + 无状态 + 固定启发式（有意无配置）+ 两个操作（estimate/measure）。

接线方式：@startup_item phase=INFRASTRUCTURE 创建单例 → 消费方通过 get_token_meter() 获取。
静默失效禁令：未接线时 get_token_meter() 抛 RuntimeError（不静默返回 None）。
"""

from typing import Any

from src.common.logger import get_logger
from src.core.token_meter.estimate import estimate_message, estimate_text
from src.core.token_meter.types import (
    TokenMeasurement,
    TokenMeasurementBaseline,
    TokenSurfaceNode,
)

logger = get_logger("core.token_meter")

DEFAULT_CONTEXT_WINDOW: int = 32768

_instance: "TokenMeter | None" = None


def _set_instance(meter: "TokenMeter") -> None:
    """设置 TokenMeter 单例实例（仅 @startup_item init_fn 调用）。"""
    global _instance
    _instance = meter


def get_token_meter() -> "TokenMeter":
    """获取 TokenMeter 单例实例。

    所有消费方必须通过此函数获取，禁止直接构造。

    Returns:
        TokenMeter 单例实例。

    Raises:
        RuntimeError: 单例未接线（@startup_item init_fn 未执行）。
    """
    if _instance is None:
        raise RuntimeError("TokenMeter 未接线——@startup_item init_fn 未执行")
    return _instance


class TokenMeter:
    """统一 Token 计量服务单例——所有 token 定价决策的唯一会计。

    无状态服务 + 固定启发式（CHARS_PER_TOKEN=4 / BLOCK_OVERHEAD=4 / ROLE_OVERHEAD=4）。
    锚点复用后续按需实现（依赖持久日志 fold，MaiBot 暂无等价机制）。
    会话投影后续按需实现（依赖持久日志 + 提供方用量上报 + 路由容量解析）。

    约束：
    - 必须通过 get_token_meter() 获取实例，禁止消费方直接构造
    - __init__ 的 config 参数必须为 None 或空 dict（非空抛 ValueError）
    """

    def __init__(self, config: dict | None = None) -> None:
        if config is not None and config:
            raise ValueError("TokenMeter 不接受配置项——固定启发式，对齐 dsh validateConfigKeys")
        self._store: Any = None

    def _set_store(self, store: Any) -> None:
        """注入表层事件存储端口（可选——measure() 需要）。

        Args:
            store: 具有 async read_surface_events(session_id) -> Sequence[Any] 的存储端口。
        """
        self._store = store

    def estimate(self, message: Any) -> int:
        """估算单条消息 token 数（委托 estimate_message 纯函数）。

        Args:
            message: 待估算消息（支持多种格式——见 estimate_message docstring）。

        Returns:
            非负整数 token 估算值。
        """
        return estimate_message(message)

    def estimate_text(self, text: str) -> int:
        """估算纯文本 token 数（委托 estimate_text 纯函数）。

        Args:
            text: 待估算文本。

        Returns:
            非负整数；空文本返回 0。
        """
        return estimate_text(text)

    async def measure(
        self,
        session_id: str,
        *,
        request_header: Any | None = None,
    ) -> TokenMeasurement:
        """计量会话压力快照（初版完整启发式估算兜底）。

        初版不实现锚点复用（依赖持久日志 fold，MaiBot 暂无等价日志）。
        持久日志读取失败时回退空快照（surface_tokens=0, nodes=()）+ 日志告警。

        Args:
            session_id: 会话 ID。
            request_header: 请求标头（锚点匹配用，初版不使用）。

        Returns:
            深度不可变的 TokenMeasurement 快照。
        """
        if self._store is None:
            logger.debug(f"measure 无存储端口，返回空快照: session_id={session_id}")
            return TokenMeasurement(
                total_tokens=0,
                surface_tokens=0,
                nodes=(),
                log_revision=0,
                baseline=TokenMeasurementBaseline(kind="none", tokens=0),
                surface_delta_tokens=0,
            )

        try:
            events = await self._store.read_surface_events(session_id)
        except Exception as exc:
            logger.warning(f"measure 读取表层事件失败，回退空快照: session_id={session_id}, error={exc}")
            return TokenMeasurement(
                total_tokens=0,
                surface_tokens=0,
                nodes=(),
                log_revision=0,
                baseline=TokenMeasurementBaseline(kind="none", tokens=0),
                surface_delta_tokens=0,
            )

        nodes: list[TokenSurfaceNode] = []
        surface_tokens = 0
        for position, event in enumerate(events):
            event_tokens = self._estimate_event(event)
            surface_tokens += event_tokens
            nodes.append(
                TokenSurfaceNode(
                    tokens=event_tokens,
                    position=position,
                    kind=type(event).__name__,
                )
            )

        return TokenMeasurement(
            total_tokens=surface_tokens,
            surface_tokens=surface_tokens,
            nodes=tuple(nodes),
            log_revision=0,
            baseline=TokenMeasurementBaseline(kind="estimated", tokens=surface_tokens),
            surface_delta_tokens=0,
        )

    def _estimate_event(self, event: Any) -> int:
        """估算单个事件的 token 数——按事件结构提取消息后 estimate。"""
        if hasattr(event, "data") and hasattr(event.data, "message"):
            return self.estimate(event.data.message)
        if hasattr(event, "message"):
            return self.estimate(event.message)
        if isinstance(event, dict):
            message = event.get("message")
            if message is not None:
                return self.estimate(message)
            text = event.get("text", "")
            return self.estimate_text(str(text))
        return self.estimate_text(str(event))

    def get_context_window(self, model_route: Any | None = None) -> int:
        """获取上下文窗口大小。

        Args:
            model_route: 模型路由（初版不解析，固定返回 DEFAULT_CONTEXT_WINDOW）。

        Returns:
            上下文窗口大小（正整数）。
        """
        if model_route is None:
            return DEFAULT_CONTEXT_WINDOW

        context_window = getattr(model_route, "context_window", None)
        if context_window is not None and isinstance(context_window, int) and context_window > 0:
            return context_window

        context = getattr(model_route, "context", None)
        if context is not None:
            ctx_window = getattr(context, "window", None)
            if ctx_window is not None and isinstance(ctx_window, int) and ctx_window > 0:
                return ctx_window

        return DEFAULT_CONTEXT_WINDOW