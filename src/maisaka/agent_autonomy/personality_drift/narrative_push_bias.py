"""M4: 叙事推力→参数临时偏置。弱信号 6%，不持久化。

事件→8方向→参数偏置向量（B4 借鉴点 + exp56 +11.7%）。
偏置临时不累积，下次漂移循环合并后自然消化。
"""

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.personality_drift.drift_params import DriftParams

logger = get_logger("maisaka.personality_drift.narrative")

EVENT_BIAS_MAP: dict[str, dict[str, float]] = {
    "join_group": {"social_strength": +1.0, "exploration_rate": +1.0},
    "leave_group": {"social_strength": -1.0},
    "mention": {"social_strength": +1.0, "vitality_intensity": +1.0},
    "topic_switch": {"exploration_rate": +1.0, "recall_diversity": +1.0},
    "long_silence": {"vitality_intensity": -1.0},
    "joy": {"empathy": +1.0, "social_strength": +1.0},
    "sadness": {"empathy": +1.0, "vitality_intensity": -1.0},
    "anger": {"emotion_volatility": +1.0, "social_polarity": -1.0},
}


class NarrativePushBias:
    """叙事推力→参数临时偏置。弱信号 6%，不持久化。"""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self._bias_magnitude = cfg.get("bias_magnitude", 0.06)

    def on_event(self, event_type: str, params: DriftParams) -> None:
        """事件触发→参数临时偏置。"""
        bias = EVENT_BIAS_MAP.get(event_type)
        if bias is None:
            return
        for param_name, direction in bias.items():
            p = params.get_param(param_name)
            if p is not None:
                p.value += direction * self._bias_magnitude
                p.clamp()
        logger.debug("narrative push: event=%s bias=%s", event_type, bias)

    def clear_bias(self, params: DriftParams) -> None:
        """下次漂移循环合并后清零偏置。

        偏置已合并到参数值，无需额外清理——偏置不累积。
        """
        pass