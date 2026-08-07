"""A1: 自我差异计算器 — 零 LLM 调用，基于 Higgins 自我差异理论"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonalityConfig

from .embedding_cache import EmbeddingCache


class SelfDiscrepancyCalculator:
    """A1: 自我差异 → 情绪预测。零 LLM 调用。

    基于 Higgins (1987) 自我差异理论：
    - actual-ideal 差异 → dejection（沮丧）: sad, lonely
    - actual-ought 差异 → agitation（不安）: anxious, angry

    两种差异都大幅时 → 混合负面情绪，抑制 happy/excited/calm
    """

    DIM = 32

    def __init__(self, config: "LayeredPersonalityConfig", embedding_cache: EmbeddingCache) -> None:
        self._config = config
        self._cache = embedding_cache
        self._d_norm = config.discrepancy_d_norm

    def compute(
        self,
        actual_text: str,
        ideal_text: str,
        ought_text: str,
        context: str = "",
    ) -> dict[str, float]:
        """返回 7 种情绪增量。

        返回情绪键：happy, sad, anxious, angry, calm, excited, lonely

        embedding 失败时返回空 dict {}，不抛异常。
        """
        try:
            actual_emb = self._cache.get_or_compute("__a1__", "actual", actual_text)
            ideal_emb = self._cache.get_or_compute("__a1__", "ideal", ideal_text)
            ought_emb = self._cache.get_or_compute("__a1__", "ought", ought_text)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "计算自我差异失败，返回空", exception=exc)
            return {}

        if not actual_emb or not ideal_emb or not ought_emb:
            return {}

        # L2 距离
        ai_dist = _l2_distance(actual_emb, ideal_emb)
        ao_dist = _l2_distance(actual_emb, ought_emb)

        # 差异幅度 × 可及性 → 激活
        ai_activation = ai_dist / self._d_norm
        ao_activation = ao_dist / self._d_norm

        # 映射到情绪增量
        # actual-ideal → dejection: sad, lonely
        # actual-ought → agitation: anxious, angry
        # 两种差异混合 → 抑制正向情绪
        sad = min(1.0, ai_activation * 0.7)
        lonely = min(1.0, ai_activation * 0.5)
        anxious = min(1.0, ao_activation * 0.7)
        angry = min(1.0, ao_activation * 0.5)

        # 正向情绪被混合差异抑制
        disruption = min(1.0, (ai_activation + ao_activation) / 2)
        happy = max(-1.0, -disruption * 0.6)
        excited = max(-1.0, -disruption * 0.4)
        calm = max(-1.0, -disruption * 0.5)

        return {
            "happy": happy,
            "sad": sad,
            "anxious": anxious,
            "angry": angry,
            "calm": calm,
            "excited": excited,
            "lonely": lonely,
        }


def _l2_distance(a: list[float], b: list[float]) -> float:
    """两个向量的欧几里得距离"""
    if len(a) != len(b):
        raise ValueError(f"向量维度不匹配: {len(a)} != {len(b)}")
    total = 0.0
    for va, vb in zip(a, b, strict=True):
        diff = va - vb
        total += diff * diff
    return math.sqrt(total)
