"""M2: 适应度采集——加权计算 fitness = 0.4×互动 + 0.2×关系 + 0.3×独特 + 0.0×情绪（预留）。

主信号来自 RelationshipManager.get_relationship()，O(1)。
权重自平衡：允许"安静的活法"——低互动角色通过 w₃ 独特性获得适应度。
"""

from typing import TYPE_CHECKING

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.maisaka.relationship.manager import RelationshipManager

logger = get_logger("maisaka.personality_drift.fitness")


class DriftFitnessCollector:
    """适应度采集器。

    fitness = w1×互动深度 + w2×关系贡献 + w3×表达独特性 + w4×情绪匹配度
    初始权重 (0.4, 0.2, 0.3, 0.0)——w4=0.0 情绪预留（V2 开启）。
    """

    def __init__(
        self,
        relationship_manager: "RelationshipManager",
        config: dict | None = None,
    ) -> None:
        self._rm = relationship_manager
        cfg = config or {}
        self._w1 = cfg.get("w_interaction", 0.4)
        self._w2 = cfg.get("w_relation", 0.2)
        self._w3 = cfg.get("w_uniqueness", 0.3)
        self._w4 = cfg.get("w_emotion", 0.0)

    def collect(self, agent_id: str, user_id: str) -> float:
        """采集适应度，O(1)。"""
        snapshot = self._rm.get_relationship(agent_id, user_id)
        interaction = min(1.0, snapshot.interaction_count / 1000.0)
        relation = snapshot.score / 1000.0
        uniqueness = self._calc_uniqueness(agent_id)
        emotion = self._calc_emotion_match(agent_id, user_id) if self._w4 > 0 else 0.0
        fitness = (
            self._w1 * interaction
            + self._w2 * relation
            + self._w3 * uniqueness
            + self._w4 * emotion
        )
        return max(0.0, min(1.0, fitness))

    def _calc_uniqueness(self, agent_id: str) -> float:
        """表达独特性——角色发言与群聊平均的余弦距离。

        V1 启发式：返回 0.5（中性），V2 用实际 embedding 余弦距离。
        归一化到 [0,1]，设阈值防极端值（参考 exp51 dist 计算）。
        """
        return 0.5

    def _calc_emotion_match(self, agent_id: str, user_id: str) -> float:
        """情绪匹配度——角色情绪与用户情绪的对齐度。

        预留，V2 实现（w4=0.0 时不调用）。
        """
        return 0.0

    @property
    def weights(self) -> tuple[float, float, float, float]:
        return (self._w1, self._w2, self._w3, self._w4)