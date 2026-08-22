"""提及传递连锁深度节流组件（ZG-23a）。

限制插话提及传递的连锁深度，通过概率衰减（``base ** depth``）抑制
多角色轮流刷屏的风暴。

机制：
1. 深度上限熔断：连锁深度超过上限时直接抑制
2. 概率衰减：``trigger_probability = base ** depth``，深度越深概率越低
3. 随机抽样：计算衰减概率后随机抽样判定，只有命中才触发

降级策略：
- 概率计算异常 → 用默认 base 重新计算
- 随机数异常 → 不触发（保守）
- 深度计数器异常 → 允许触发 probability = base ** 1
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import heapq
import random
import time

from src.common.logger import get_logger
from src.core.tainted_mask.mark import mark_exception_swallowed

logger = get_logger("agent_autonomy.mention_chain_throttle")


@dataclass
class ChainThrottleDecision:
    """连锁深度节流决策结果。

    Attributes:
        allow: True 表示允许触发提及传递，False 表示抑制。
        trigger_probability: 衰减后的触发概率（allow=True 时有效）。
        reason: 决策原因（depth_exceeded / probability_miss / probability_hit / degraded）。
    """

    allow: bool = False
    trigger_probability: float = 0.0
    reason: str = ""


class MentionChainThrottle:
    """提及传递连锁深度节流器。

    通过深度计数器 + 概率衰减 + 随机抽样三层机制抑制多角色连锁刷屏。

    Notes:
        - 非线程安全，依赖单事件循环串行调用
        - 深度是"会话级近似"而非"事件链精确"（见 design.md 2.5.2）
        - chain_id 的 TTL 过期清理复用 dict + heapq 模式
    """

    def __init__(
        self,
        base: float = 0.6,
        max_depth: int = 4,
        chain_ttl: float = 300.0,
    ) -> None:
        """初始化连锁深度节流器。

        Args:
            base: 概率衰减基数，取值范围 0.5-0.8，越界回退 0.6。
            max_depth: 连锁深度上限，取值范围 3-5，越界回退 4。
            chain_ttl: 链条状态 TTL（秒），过期后清理。
        """
        # 越界回退
        if base < 0.5 or base > 0.8:
            logger.warning(f"提及传递概率衰减基数越界: {base}，回退默认值 0.6")
            base = 0.6
        if max_depth < 3 or max_depth > 5:
            logger.warning(f"提及传递连锁深度上限越界: {max_depth}，回退默认值 4")
            max_depth = 4

        self._base = base
        self._max_depth = max_depth
        self._chain_ttl = chain_ttl
        # 会话级深度状态：chain_id -> depth
        self._chain_depths: Dict[str, int] = {}
        # 过期清理堆：(expires_at, chain_id)
        self._chain_expire_heap: List[Tuple[float, str]] = []

    def check_and_decide(self, chain_id: str, depth: int) -> ChainThrottleDecision:
        """检查连锁深度并做出节流决策。

        Args:
            chain_id: 连锁链标识（会话级，基于首条入站消息 ID）。
            depth: 当前连锁深度（从 1 起计）。

        Returns:
            ChainThrottleDecision: allow=True 时携带衰减后的触发概率。
        """
        try:
            # 更新链条深度状态
            if chain_id:
                self._chain_depths[chain_id] = depth
                now = time.monotonic()
                expires_at = now + self._chain_ttl
                heapq.heappush(self._chain_expire_heap, (expires_at, chain_id))
                self._purge_expired_chains(now)

            # 深度上限熔断
            if depth > self._max_depth:
                logger.info(
                    f"提及传递连锁熔断: chain_id={chain_id} "
                    f"depth={depth} > max_depth={self._max_depth}"
                )
                return ChainThrottleDecision(
                    allow=False,
                    reason="depth_exceeded",
                )

            # 概率衰减计算
            probability = self._compute_probability(depth)

            # 随机抽样判定（单独 try，异常时保守不触发）
            try:
                sample = random.random()
            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '随机数生成异常，降级不触发（保守）', exception=e)
                logger.warning(f"随机数生成异常，降级不触发（保守）: {e}")
                mark_exception_swallowed("mention_chain_throttle.random_error")
                return ChainThrottleDecision(
                    allow=False,
                    trigger_probability=probability,
                    reason="random_error",
                )

            if sample < probability:
                return ChainThrottleDecision(
                    allow=True,
                    trigger_probability=probability,
                    reason="probability_hit",
                )
            else:
                logger.debug(
                    f"提及传递概率未命中: chain_id={chain_id} "
                    f"depth={depth} probability={probability:.4f} sample={sample:.4f}"
                )
                return ChainThrottleDecision(
                    allow=False,
                    trigger_probability=probability,
                    reason="probability_miss",
                )

        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '连锁深度节流异常，降级允许触发', exception=e)
            # 降级：允许触发，probability = base ** 1
            logger.warning(f"连锁深度节流异常，降级允许触发: {e}")
            mark_exception_swallowed("mention_chain_throttle.check_and_decide")
            fallback_prob = self._base ** 1
            return ChainThrottleDecision(
                allow=True,
                trigger_probability=fallback_prob,
                reason="degraded",
            )

    def reset_chain(self, chain_id: str) -> None:
        """重置指定链条的深度计数器。

        新入站消息触发新链条时调用，深度从 1 重新开始。

        Args:
            chain_id: 要重置的连锁链标识。
        """
        if chain_id and chain_id in self._chain_depths:
            del self._chain_depths[chain_id]

    def _compute_probability(self, depth: int) -> float:
        """计算概率衰减：trigger_probability = base ** depth。"""
        try:
            return self._base ** depth
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '概率计算异常，降级使用默认 base 0.6', exception=e)
            # 降级：用默认 base 0.6 重新计算
            logger.warning(f"概率计算异常，降级使用默认 base 0.6: {e}")
            mark_exception_swallowed("mention_chain_throttle._compute_probability")
            return 0.6 ** depth

    def _purge_expired_chains(self, now: float) -> None:
        """清理过期的链条深度状态。"""
        while self._chain_expire_heap and self._chain_expire_heap[0][0] <= now:
            expires_at, chain_id = heapq.heappop(self._chain_expire_heap)
            # 链条可能已被 reset 或更新，只清理过期的
            if chain_id in self._chain_depths:
                del self._chain_depths[chain_id]