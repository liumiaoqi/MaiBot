"""`guard-anticorr-fix` 的探针：**反对齐检测必须认真实形状**（`RetrievalResult`）。

缺陷（既有，与阶段 C 接缝无关）：`confidence_guard.detect_misalignment` 旧判定链要求候选**带
`.confidence` 属性**，而真实候选是 `RetrievalResult`（confidence 在 **`metadata["confidence"]`** 里、
对象上没有该属性）⇒ 判定**恒 False** ⇒ 该护栏**永远不会降级**（只剩 floor 一半在工作）。

本文件钉三件：
1. **真实形状可用**：合成"低置信 + relevance 反相关"的 `RetrievalResult` ⇒ `degraded=True`；
2. **兼容不破**：dict 支 / 带 `.confidence`+`.score` 属性的支**照旧工作**；
3. **不越界**：形状不认识（如只有 `.confidence` 没有 `.score`）时**仍不降级**（不改成"一律降级"）。
"""

import pytest

from src.A_memorix.core.retrieval.confidence_guard import CONFIDENCE_FLOOR, ConfidenceGuard
from src.A_memorix.core.retrieval.dual_path import RetrievalResult


def _real_shape(rows: list[tuple[float, float]]) -> list[RetrievalResult]:
    """造**真实形状**的候选：`confidence` 进 `metadata`，相关度在 `.score`。"""

    return [
        RetrievalResult(
            hash_value=f"h{index}", content="c", score=score, result_type="relation",
            source="relation_search", metadata={"confidence": confidence},
        )
        for index, (confidence, score) in enumerate(rows)
    ]


def test_real_shape_anticorrelated_is_detected() -> None:
    """① **修前必红**：confidence 升序而 relevance 降序（强负相关）⇒ 必须 `degraded=True`。"""

    guard = ConfidenceGuard()
    candidates = _real_shape([(0.1, 0.9), (0.5, 0.5), (0.9, 0.1)])

    assert guard.detect_misalignment(candidates) is True, "真实形状下反对齐没被检出（护栏是死的）"

    weight, degraded = guard.compute_weight(0.1, candidates)
    assert degraded is True, "compute_weight 没走降级分支"
    # 语义说明（别读反）：降级 = **不加权** ⇒ weight 返回 **1.0**（去掉惩罚），
    # 数值上比 floor 分支的 max(0.1, 0.3)=0.3 **更大**；这不是"压低"，是"不惩罚"。
    assert weight == 1.0 and weight != max(0.1, CONFIDENCE_FLOOR)


def test_real_shape_aligned_still_uses_floor() -> None:
    """② 反面对照：confidence 与 relevance **同向** ⇒ **不降级**，走 floor（护栏 1 正常）。"""

    guard = ConfidenceGuard()
    candidates = _real_shape([(0.1, 0.1), (0.5, 0.5), (0.9, 0.9)])

    assert guard.detect_misalignment(candidates) is False, "同向竟被判为反对齐"
    weight, degraded = guard.compute_weight(0.1, candidates)
    assert degraded is False and weight == max(0.1, CONFIDENCE_FLOOR)


def test_legacy_shapes_still_work() -> None:
    """③ 兼容：dict 支与"带 .confidence/.score 属性"的支照旧。"""

    class LegacyCandidate:
        def __init__(self, confidence: float, score: float) -> None:
            self.confidence = confidence
            self.score = score

    guard = ConfidenceGuard()
    assert guard.detect_misalignment([{"confidence": 0.1, "score": 0.9}, {"confidence": 0.5, "score": 0.5}, {"confidence": 0.9, "score": 0.1}]) is True
    assert guard.detect_misalignment(
        [LegacyCandidate(0.1, 0.9), LegacyCandidate(0.5, 0.5), LegacyCandidate(0.9, 0.1)]
    ) is True


def test_unknown_shape_does_not_degrade() -> None:
    """④ 不越界：形状不认识（只有 `.confidence`、没有 relevance 分）⇒ **仍不降级**。

    真实世界里这就是 `GraphRelationCandidate`（`graph_relation_recall.py`）：调用点上还没有 relevance 分，
    无信号可判 ⇒ 维持旧行为（`False`），**不许**改成"一律降级"。
    """

    class NoScoreCandidate:
        def __init__(self, confidence: float) -> None:
            self.confidence = confidence

    guard = ConfidenceGuard()
    candidates = [NoScoreCandidate(0.1), NoScoreCandidate(0.5), NoScoreCandidate(0.9)]
    assert guard.detect_misalignment(candidates) is False
    weight, degraded = guard.compute_weight(0.1, candidates)
    assert degraded is False and weight == pytest.approx(max(0.1, CONFIDENCE_FLOOR))
