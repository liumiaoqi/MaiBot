"""状态可见性规则——判定目标智能体对观察者的可见信息粒度。"""


from dataclasses import dataclass

from src.core.app_config_port_registry import get_app_config_port


@dataclass
class VisibilityInfo:
    """可见性判定结果。"""

    visible: bool = False
    show_emotion: bool = False
    show_vitality_level: bool = False


class StateVisibilityRule:
    """状态可见性规则——基于配置判定目标对观察者的可见信息粒度。"""

    def __init__(self) -> None:
        self._config = get_app_config_port().get_agent_autonomy_config()

    def evaluate(self, observer_state: str, target_state: str) -> VisibilityInfo:
        """判定目标智能体对观察者的可见信息粒度。"""
        # 沉睡智能体对任何人都不可见
        if target_state == "dormant":
            if not self._config.dormant_visible_to_any:
                return VisibilityInfo()

        # 活跃观察活跃
        if observer_state == "active" and target_state == "active":
            if self._config.active_visible_to_active:
                return VisibilityInfo(
                    visible=True,
                    show_emotion=True,
                    show_vitality_level=True,
                )

        # 活跃观察待命
        if observer_state == "active" and target_state == "standby":
            if self._config.standby_visible_to_active:
                return VisibilityInfo(
                    visible=True,
                    show_emotion=self._config.standby_emotion_visible_to_active,
                    show_vitality_level=True,
                )

        return VisibilityInfo()
