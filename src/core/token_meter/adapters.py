"""ZG-N6 统一 Token 计量服务——N5 兼容适配器。

将真 TokenMeter 适配为 N5 compaction 的 TokenMeterPort（三方法签名）。
N5 退役后此适配器随之删除。
"""

from typing import Any, Sequence

from src.core.token_meter.service import TokenMeter


class N5TokenMeterAdapter:
    """N5 compaction TokenMeterPort 适配器——委托真 TokenMeter。

    N5 compaction engine 通过依赖注入接收 TokenMeterPort，
    不直接依赖真 TokenMeter 类（Protocol 解耦）。

    N5 退役后此类随之删除。
    """

    def __init__(self, token_meter: TokenMeter) -> None:
        self._token_meter = token_meter

    def count_tokens(self, text: str) -> int:
        """计算文本 token 数——委托 TokenMeter.estimate_text。"""
        return self._token_meter.estimate_text(text)

    def count_events_tokens(self, events: Sequence[Any]) -> int:
        """计算事件序列总 token 数——逐事件 estimate 累加。"""
        return sum(self._token_meter.estimate(e) for e in events)

    def get_context_window(self, model_route: Any) -> int:
        """获取模型上下文窗口大小——委托 TokenMeter.get_context_window。"""
        return self._token_meter.get_context_window(model_route)