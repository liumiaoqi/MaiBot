"""A4: 预测处理器 — 三层预测处理（predict→error→update），纯 Python 实现"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonalityConfig


class PredictiveProcessor:
    """A4: 三层预测处理 — predict→error→update 核心循环。纯 Python，不依赖 pymdp。

    三层结构：
    - L0: 情绪层，学习率较快（反映即时情绪波动）
    - L1: 行为层，学习率中等（反映行为模式变化）
    - L2: 认同层，学习率极慢（反映核心自我认知变化）

    每层的 update 公式：
        error = observation - prediction
        update = error * learning_rate * (1 - precision)
        new_state = clamp(state + update, 0, 1)
    """

    DEFAULT_LAYER_CONFIGS = {
        "L0": {"lr": 0.1},
        "L1": {"lr": 0.05},
        "L2": {"lr": 0.01},
    }

    def __init__(self, config: "LayeredPersonalityConfig") -> None:
        self.layers: dict[str, dict[str, float]] = {
            "L0": {"state": 0.5, "prediction": 0.5, "lr": config.predictive_l0_lr},
            "L1": {"state": 0.5, "prediction": 0.5, "lr": config.predictive_l1_lr},
            "L2": {"state": 0.5, "prediction": 0.5, "lr": config.predictive_l2_lr},
        }

    def update(self, layer_name: str, observation: float, precision: float = 0.5) -> dict[str, Any]:
        """感知更新：error = obs - pred, update = error * lr * (1-precision), clamp [0,1]

        Args:
            layer_name: 层名，必须为 "L0" / "L1" / "L2"
            observation: 观测值 [0, 1]
            precision: 预测精度 [0, 1]，越高表示越确定，更新幅度越小

        Returns:
            包含更新前后状态的 dict：layer, old_state, old_prediction, error,
            update_amount, new_state, new_prediction
        """
        layer = self.layers.get(layer_name)
        if layer is None:
            return {"layer": layer_name, "error": 0.0, "update_amount": 0.0, "new_state": 0.5}

        old_state = layer["state"]
        old_prediction = layer["prediction"]

        error = observation - old_prediction
        update_amount = error * layer["lr"] * max(0.0, 1.0 - precision)
        new_state = max(0.0, min(1.0, old_state + update_amount))
        new_prediction = new_state

        layer["state"] = new_state
        layer["prediction"] = new_prediction

        return {
            "layer": layer_name,
            "old_state": old_state,
            "old_prediction": old_prediction,
            "error": error,
            "update_amount": update_amount,
            "new_state": new_state,
            "new_prediction": new_prediction,
        }

    def get_state(self, layer_name: str) -> float:
        """获取层当前状态值"""
        layer = self.layers.get(layer_name)
        if layer is None:
            return 0.5
        return layer["state"]

    def get_prediction(self, layer_name: str) -> float:
        """获取层当前预测值"""
        layer = self.layers.get(layer_name)
        if layer is None:
            return 0.5
        return layer["prediction"]

    def reset(self) -> None:
        """重置所有层到默认状态"""
        for name, lr_val in [("L0", self.layers["L0"]["lr"]), ("L1", self.layers["L1"]["lr"]), ("L2", self.layers["L2"]["lr"])]:
            self.layers[name] = {"state": 0.5, "prediction": 0.5, "lr": lr_val}
