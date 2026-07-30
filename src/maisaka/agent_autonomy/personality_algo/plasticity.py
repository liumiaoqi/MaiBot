"""A5: 锚定/可塑机制 — sigmoid 固化 + 社会投资修正（Roberts 社会投资理论）"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maisaka.agent.config import LayeredPersonalityConfig


class PlasticityCalculator:
    """A5: 锚定/可塑机制 — sigmoid 固化 + 社会投资修正

    基于 Roberts (2006) 社会投资理论：
    - 随交互次数增加，性格通过 sigmoid 函数逐渐固化
    - 新的社会角色投资（如新关系、新环境）可重新打开可塑窗口

    stability = 1 - 1 / (1 + exp(-k * (n - N_mid)))
    plasticity = max(plasticity_min, 1 - stability)
    若 role_investment > 0.5: plasticity += re_plastication_boost * role_investment
    最终 clamp 到 [0, 1]
    """

    def __init__(self, config: "LayeredPersonalityConfig") -> None:
        self._n_mid = config.plasticity_n_mid
        self._k = config.plasticity_k
        self._plasticity_min = config.plasticity_min
        self._re_plastication_boost = config.re_plastication_boost

    def compute(self, interaction_count: int, role_investment: float = 0.0) -> float:
        """计算当前可塑性。

        Args:
            interaction_count: 累计交互次数
            role_investment: 新角色投资强度 [0, 1]，越高表示越可能重新打开可塑窗口

        Returns:
            可塑性值 [plasticity_min, 1.0]
        """
        # sigmoid: S(x) = 1 / (1 + exp(-k * (n - N_mid)))
        x = -self._k * (interaction_count - self._n_mid)
        try:
            sigmoid = 1.0 / (1.0 + math.exp(x))
        except OverflowError:
            # x 极小 → exp 极大 → sigmoid ≈ 0（已完全固化）
            sigmoid = 0.0
        except Exception:
            sigmoid = 0.5

        stability = 1.0 - sigmoid
        plasticity = max(self._plasticity_min, 1.0 - stability)

        if role_investment > 0.5:
            plasticity += self._re_plastication_boost * role_investment

        return min(1.0, plasticity)
