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

        ⚠️ **2026-10-17 修**：真实调用形状是 `RetrievalResult`（`dual_path.py:43`：字段
        `hash_value/content/score/result_type/source/metadata`）——**它没有 `confidence` 属性**，
        confidence 在 **`metadata["confidence"]`** 里。旧判定链（`hasattr(c,"confidence")` → `isinstance(c,dict)`
        → `else: return False`）对真实形状**恒 False** ⇒ 本节护栏**永远不会降级**（触发率恒 0，
        只剩 floor 那一半在工作）。本修让它认真实形状，**同时保留** dict / 带属性对象两支；
        拿不到 confidence 时**仍返回 False**（维持"不认识就不降级"，不改成一律降级）。
        """
        if len(candidates) < 3:
            return False

        confidences = []
        scores = []
        for c in candidates:
            extracted = _confidence_and_score(c)
            if extracted is None:
                return False
            confidences.append(extracted[0])
            scores.append(extracted[1])

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


def _confidence_and_score(candidate: Any) -> Tuple[float, float] | None:
    """从**任意既有形状**里取 (confidence, relevance score)；取不到 ⇒ `None`（= 维持"不降级"）。

    覆盖三支（**兼容**旧两支，新增真实一支）：
    1. **检索真实形状**：带 `metadata` 字典且其中含 `confidence`，对象另有 `.score`
       （`RetrievalResult`——`dual_path.py:43`）⇒ 读 `metadata["confidence"]`；
    2. 带 `.confidence` **且** `.score` 属性的对象（旧支，保留）；
    3. `dict`：`confidence`/`score` 键（旧支，保留原默认值 1.0 / 0.0）。

    ⚠️ **不覆盖**：像 `GraphRelationCandidate`（`graph_relation_recall.py`，有 `.confidence` 但**没有**
    `.score`）——那条支路在调用点上**还没有 relevance 分**，无信号可判 ⇒ 返回 `None`（等价于旧行为，
    不硬造一个 relevance 代理，免得把"判不了"变成"乱判"）。
    """

    metadata = getattr(candidate, "metadata", None)
    score = getattr(candidate, "score", None)
    if isinstance(metadata, dict) and "confidence" in metadata and score is not None:
        return float(metadata["confidence"]), float(score)
    if hasattr(candidate, "confidence") and score is not None:
        return float(candidate.confidence), float(score)
    if isinstance(candidate, dict):
        return float(candidate.get("confidence", 1.0)), float(candidate.get("score", 0.0))
    return None


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