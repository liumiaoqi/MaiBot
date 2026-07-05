"""交互影响计算器。

基于交互类型和关系类型的规则引擎，计算量化的情绪/关系影响。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# 情绪影响规则：(interaction_type, relationship_type) → (initiator_deltas, target_deltas, relationship_delta, tag)
_EFFECT_RULES: dict[str, dict[str, tuple[dict[str, float], dict[str, float], float, str]]] = {
    "emotion_driven": {
        "family": (
            {"lonely": -15, "happy": 10},
            {"happy": 5, "calm": -5},
            3.0,
            "positive",
        ),
        "romantic": (
            {"lonely": -20, "happy": 15},
            {"happy": 8, "excited": 5},
            5.0,
            "positive",
        ),
        "friend": (
            {"lonely": -8, "happy": 5},
            {"happy": 3},
            2.0,
            "positive",
        ),
        "mentor": (
            {"anxious": -10, "calm": 5},
            {"happy": 2},
            1.5,
            "positive",
        ),
        "rival": (
            {"excited": 3},
            {"angry": 5, "happy": 3},
            1.0,
            "mixed",
        ),
    },
    "time_awareness": {
        "family": (
            {"happy": 5, "calm": 3},
            {"happy": 3},
            1.5,
            "positive",
        ),
        "romantic": (
            {"happy": 8, "excited": 3},
            {"happy": 5, "excited": 2},
            2.0,
            "positive",
        ),
        "friend": (
            {"happy": 3},
            {"happy": 2},
            1.0,
            "positive",
        ),
        "mentor": (
            {"calm": 3},
            {"happy": 1},
            0.5,
            "neutral",
        ),
        "rival": (
            {"excited": 2},
            {"angry": 2},
            0.5,
            "mixed",
        ),
    },
    "mention_propagation": {
        "family": (
            {"happy": 5},
            {"happy": 3, "excited": 2},
            1.0,
            "positive",
        ),
        "romantic": (
            {"happy": 8, "excited": 3},
            {"happy": 5, "excited": 3},
            1.5,
            "positive",
        ),
        "friend": (
            {"happy": 3},
            {"happy": 2},
            0.5,
            "positive",
        ),
        "mentor": (
            {"calm": 2},
            {"happy": 1},
            0.3,
            "neutral",
        ),
        "rival": (
            {"angry": 3},
            {"angry": 2},
            -0.5,
            "negative",
        ),
    },
    "event_ripple": {
        "family": (
            {"anxious": 5, "sad": 3},
            {"anxious": 3, "sad": 2},
            1.0,
            "negative",
        ),
        "romantic": (
            {"anxious": 8, "sad": 5},
            {"anxious": 5, "sad": 3},
            1.5,
            "negative",
        ),
        "friend": (
            {"anxious": 3},
            {"calm": -2},
            0.5,
            "neutral",
        ),
        "mentor": (
            {"calm": -3, "anxious": 2},
            {"calm": -1},
            0.3,
            "neutral",
        ),
        "rival": (
            {"excited": 3, "happy": 2},
            {"angry": 2},
            -0.3,
            "mixed",
        ),
    },
    "inner_need": {
        "family": (
            {"lonely": -10, "happy": 8},
            {"happy": 3},
            2.0,
            "positive",
        ),
        "romantic": (
            {"lonely": -15, "happy": 12},
            {"happy": 5, "excited": 3},
            3.0,
            "positive",
        ),
        "friend": (
            {"lonely": -5, "happy": 3},
            {"happy": 2},
            1.0,
            "positive",
        ),
        "mentor": (
            {"lonely": -3, "calm": 2},
            {"happy": 1},
            0.5,
            "neutral",
        ),
        "rival": (
            {"excited": 2},
            {"angry": 2},
            0.5,
            "mixed",
        ),
    },
}

_DEFAULT_RULE = ({"happy": 1}, {"happy": 1}, 0.5, "neutral")


@dataclass
class InteractionEffect:
    """交互影响结果。"""

    initiator_emotion_deltas: dict[str, float] = field(default_factory=dict)
    target_emotion_deltas: dict[str, float] = field(default_factory=dict)
    relationship_delta: float = 0.0
    memory_content: str = ""
    emotion_tag: str = "neutral"

    @property
    def is_empty(self) -> bool:
        """所有影响量为0时返回True。"""
        if self.relationship_delta != 0.0:
            return False
        if any(v != 0.0 for v in self.initiator_emotion_deltas.values()):
            return False
        if any(v != 0.0 for v in self.target_emotion_deltas.values()):
            return False
        return True


class EffectCalculator:
    """交互影响计算器。

    基于交互类型和关系类型的规则引擎，计算量化的情绪/关系影响。
    回声深度 > 0 时影响量 × echo_decay_ratio^echo_depth。
    """

    def __init__(self, echo_decay_ratio: float = 0.5) -> None:
        self._echo_decay_ratio = echo_decay_ratio

    def calculate(
        self,
        interaction_type: str,
        relationship_type: str,
        initiator_emotion: str,
        target_emotion: str,
        echo_depth: int = 0,
    ) -> InteractionEffect:
        """计算交互影响。

        Args:
            interaction_type: 交互类型
            relationship_type: 关系类型
            initiator_emotion: 发起方主导情绪
            target_emotion: 目标方主导情绪
            echo_depth: 回声深度（0=直接交互）

        Returns:
            InteractionEffect 交互影响结果
        """
        type_rules = _EFFECT_RULES.get(interaction_type, {})
        initiator_deltas, target_deltas, rel_delta, tag = type_rules.get(
            relationship_type, _DEFAULT_RULE
        )

        # 回声衰减
        if echo_depth > 0:
            decay = self._echo_decay_ratio ** echo_depth
            initiator_deltas = {k: v * decay for k, v in initiator_deltas.items()}
            target_deltas = {k: v * decay for k, v in target_deltas.items()}
            rel_delta *= decay

        effect = InteractionEffect(
            initiator_emotion_deltas=dict(initiator_deltas),
            target_emotion_deltas=dict(target_deltas),
            relationship_delta=rel_delta,
            emotion_tag=tag,
        )

        if effect.is_empty:
            return InteractionEffect()

        return effect