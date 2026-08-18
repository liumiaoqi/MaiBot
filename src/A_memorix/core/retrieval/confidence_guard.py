"""P2 confidence 边权重安全护栏（ZG-30）。

实验结论：3/4 场景显著提升（nDCG +5-20%、MAP +61-215%、Recall +72-160%），
仅反对齐场景有害（MAP/Recall -100%）——必须双护栏。

护栏 1：confidence floor `max(confidence, 0.3)`——防止低置信度边权重过小导致召回丢失。
护栏 2：Spearman 一致性检测降级——当 confidence 排序与 relevance 排序负相关时，
       判定反对齐，降级为无权（weight=1.0）+ warning。

参考：confidence_edge_weight_compare_0817.md
对标 dsh defensive-patterns 静默失效禁令——降级时出 warning 不静默。
"""

from typing import Any, List, Sequence, Tuple

from src.common.logger import get_logger

logger = get_logger("A_Memorix.ConfidenceGuard")

CONFIDENCE_FLOOR = 0.3
MISALIGNMENT_THRESHOLD = -0.3
ROLLING_WINDOW_SIZE = 20


class ConfidenceGuard:
    """confidence 边权重安全护栏。

    接线点：dual_path.py _merge_relation_results_graph_enhanced +
           graph_relation_recall.py recall 排序处。
    """

    def __init__(
        self,
        floor: float = CONFIDENCE_FLOOR,
        misalignment_threshold: float = MISALIGNMENT_THRESHOLD,
        window_size: int = ROLLING_WINDOW_SIZE,
    ) -> None:
        self._floor = floor
        self._misalignment_threshold = misalignment_threshold
        self._window_size = window_size
        self._recent_correlations: List[float] = []

    def apply_floor(self, confidence: float) -> float:
        """护栏 1：confidence floor。"""
        return max(float(confidence), self._floor)

    def detect_misalignment(
        self,
        candidates: Sequence[Any],
    ) -> bool:
        """护栏 2：Spearman 一致性检测。

        计算 confidence 排序与 relevance score 排序的 Spearman 相关性。
        负相关且显著（< misalignment_threshold）则判定反对齐。

        candidates 需有 .confidence 和 .score 属性，或为 dict 含 confidence/score 键。
        """
        if len(candidates) < 3:
            return False

        confidences = []
        scores = []
        for c in candidates:
            if hasattr(c, "confidence") and hasattr(c, "score"):
                confidences.append(float(c.confidence))
                scores.append(float(c.score))
            elif isinstance(c, dict):
                confidences.append(float(c.get("confidence", 1.0)))
                scores.append(float(c.get("score", 0.0)))
            else:
                return False

        rho = _spearman_rank_correlation(confidences, scores)
        if rho is None:
            return False

        self._recent_correlations.append(rho)
        if len(self._recent_correlations) > self._window_size:
            self._recent_correlations.pop(0)

        return rho < self._misalignment_threshold

    def compute_weight(
        self,
        confidence: float,
        candidates: Sequence[Any] = (),
    ) -> Tuple[float, bool]:
        """计算 confidence_weight + 降级标志。

        返回 (weight, degraded)：
        - 正常：weight = max(confidence, floor)，degraded=False
        - 反对齐：weight = 1.0（降级为无权），degraded=True + warning
        """
        if candidates and self.detect_misalignment(candidates):
            logger.warning(
                "confidence-relevance misalignment detected, "
                "degrading confidence edge weight to 1.0 (no weighting)"
            )
            return 1.0, True

        return self.apply_floor(confidence), False


def _spearman_rank_correlation(x: Sequence[float], y: Sequence[float]) -> Any:
    """计算 Spearman 等级相关系数。

    返回 rho ∈ [-1, 1]，或 None（数据不足/方差为 0）。
    """
    n = len(x)
    if n < 3:
        return None

    x_ranks = _rank(x)
    y_ranks = _rank(y)

    mean_x = sum(x_ranks) / n
    mean_y = sum(y_ranks) / n

    num = sum((x_ranks[i] - mean_x) * (y_ranks[i] - mean_y) for i in range(n))
    den_x = sum((x_ranks[i] - mean_x) ** 2 for i in range(n))
    den_y = sum((y_ranks[i] - mean_y) ** 2 for i in range(n))

    if den_x == 0 or den_y == 0:
        return None

    return num / ((den_x * den_y) ** 0.5)


def _rank(values: Sequence[float]) -> List[float]:
    """计算排名（平均排名处理并列）。"""
    indexed = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and values[indexed[j]] == values[indexed[i]]:
            j += 1
        avg_rank = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[indexed[k]] = avg_rank
        i = j
    return ranks