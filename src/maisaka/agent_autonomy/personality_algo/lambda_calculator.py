"""A3: λ 参数计算器 — 控制 inner_voice 对 L2 的影响权重（Granato 模型）"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonalityConfig


class LambdaCalculator:
    """A3: λ 参数计算 — 控制 inner_voice 对 L2 的影响权重

    λ = default_lambda + emotion_boost + relationship_boost
    最终 clamp 到 [0.1, 0.9]

    - emotion_boost: 当情绪强度超过阈值时激活，超出部分 × scale
    - relationship_boost: 共激活强度 × relationship_scale
    """

    def __init__(self, config: "LayeredPersonalityConfig") -> None:
        self._default = config.default_lambda
        self._emotion_threshold = config.lambda_emotion_threshold
        self._emotion_scale = config.lambda_emotion_scale
        self._relationship_scale = config.lambda_relationship_scale

    def compute(self, emotion_intensity: float, coactivation_strength: float) -> float:
        """计算 λ 值。

        Args:
            emotion_intensity: 情绪强度 [0, 1]
            coactivation_strength: 共激活强度 [0, 1]（来自内部关系）

        Returns:
            λ 值，clamp 到 [0.1, 0.9]
        """
        lam = self._default

        if emotion_intensity > self._emotion_threshold:
            lam += (emotion_intensity - self._emotion_threshold) * self._emotion_scale

        lam += coactivation_strength * self._relationship_scale

        return max(0.1, min(0.9, lam))
