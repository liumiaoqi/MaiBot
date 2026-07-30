"""A6: 自我验证计算器 — 基于 Swann 自我验证理论，认同层一致性维持"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonalityConfig


class SelfVerificationCalculator:
    """A6: 自我验证 — 认同层一致性维持

    基于 Swann (1983) 自我验证理论：
    - 当自我确定性高 + 公开场合 → self-verification（寻求验证性反馈）
    - 当自我确定性低 或 私下场合 → self-enhancement（寻求提升性反馈）

    selective_attention: 对验证性信息分配更高权重（softmax + temperature）。
    """

    def __init__(self, config: "LayeredPersonalityConfig") -> None:
        self._certainty_threshold = config.verification_certainty_threshold
        self._public_threshold = config.verification_public_threshold
        self._temperature = config.verification_temperature

    def verification_vs_enhancement(self, self_certainty: float, context_publicness: float) -> str:
        """判断当前策略是 verification 还是 enhancement。

        Args:
            self_certainty: 自我确定度 [0, 1]，越高越确定"我是谁"
            context_publicness: 场合公开度 [0, 1]，越高越公开

        Returns:
            'verification' 或 'enhancement'
        """
        # Swann: 私下+高确定 → verification（坚持自我）；公开或低确定 → enhancement
        if self_certainty > self._certainty_threshold and context_publicness < self._public_threshold:
            return "verification"
        return "enhancement"

    def selective_attention(
        self,
        incoming_feedback: list[str],
        self_concept_hash: float,
    ) -> list[tuple[str, float]]:
        """对验证性信息分配更高权重。softmax + temperature。

        Args:
            incoming_feedback: 传入反馈文本列表
            self_concept_hash: 自我概念哈希值 [0, 1]（来自认同层文本）

        Returns:
            (反馈文本, 权重) 的排序列表，权重和为 1
        """
        if not incoming_feedback:
            return []

        scores: list[float] = []
        for fb in incoming_feedback:
            # 用反馈的哈希与自我概念哈希的相似度作为"验证性"
            fb_hash = _normalized_text_hash(fb)
            # 距离越小 → 越验证 → 权重越高
            similarity = 1.0 - abs(fb_hash - self_concept_hash)
            scores.append(similarity)

        # softmax + temperature
        if self._temperature <= 0:
            self._temperature = 0.01  # 防止除零

        scaled = [s / self._temperature for s in scores]
        max_s = max(scaled)
        exp_sum = 0.0
        exp_vals: list[float] = []
        for s in scaled:
            ev = math.exp(s - max_s)  # 数值稳定
            exp_vals.append(ev)
            exp_sum += ev

        if exp_sum == 0:
            # fallback: 均匀权重
            w = 1.0 / len(incoming_feedback)
            return [(fb, w) for fb in incoming_feedback]

        weights = [ev / exp_sum for ev in exp_vals]
        result = list(zip(incoming_feedback, weights, strict=True))
        result.sort(key=lambda x: x[1], reverse=True)
        return result


def _normalized_text_hash(text: str) -> float:
    """将文本哈希为 [0, 1] 范围的浮点数"""
    h = hash(text)
    # 将哈希值映射到 [0, 1]
    return abs(h % 10000) / 10000.0
