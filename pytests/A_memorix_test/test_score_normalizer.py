"""MF-P3-003 验收：ScoreNormalizer 评分空间统一。

对应 tasks.md 6.1：min-max 归一化到 [0,1]；alpha=0.5 等权；alpha 偏移效果。
"""

import pytest

from src.A_memorix.core.concept_graph.score_normalizer import ScoreNormalizer


def test_normalize_range_is_0_1() -> None:
    normalizer = ScoreNormalizer()
    fused = normalizer.normalize(
        spread_scores={"a": 0.5, "b": 1.5},
        vector_scores={"a": 0.2, "b": 0.8},
    )
    for value in fused.values():
        assert 0.0 <= value <= 1.0


def test_alpha_half_equal_weight() -> None:
    """alpha=0.5 等权：两路同分布 → 融合分 = 任一路归一化分。"""
    normalizer = ScoreNormalizer()
    fused = normalizer.normalize(
        spread_scores={"a": 1.0, "b": 2.0},
        vector_scores={"a": 1.0, "b": 2.0},
        alpha=0.5,
    )
    assert fused["a"] == pytest.approx(0.0)  # (0.5*0 + 0.5*0)
    assert fused["b"] == pytest.approx(1.0)  # (0.5*1 + 0.5*1)


def test_alpha_shifts_weight() -> None:
    """alpha 偏移：扩散分主导时，扩散分高的项占优。"""
    normalizer = ScoreNormalizer()
    # b 扩散分高、向量分低；a 反之
    fused_spread = normalizer.normalize(
        spread_scores={"a": 0.1, "b": 0.9},
        vector_scores={"a": 0.9, "b": 0.1},
        alpha=0.8,
    )
    assert fused_spread["b"] > fused_spread["a"]

    fused_vector = normalizer.normalize(
        spread_scores={"a": 0.1, "b": 0.9},
        vector_scores={"a": 0.9, "b": 0.1},
        alpha=0.2,
    )
    assert fused_vector["a"] > fused_vector["b"]


def test_empty_scores_returns_empty() -> None:
    normalizer = ScoreNormalizer()
    assert normalizer.normalize(spread_scores={}, vector_scores={}) == {}


def test_single_item_constant_scores() -> None:
    """单元素（零方差）→ 归一化 0（无相对差异）。"""
    normalizer = ScoreNormalizer()
    fused = normalizer.normalize(
        spread_scores={"a": 3.0},
        vector_scores={"a": 0.6},
        alpha=0.5,
    )
    assert fused["a"] == pytest.approx(0.0)  # 两路均零方差 → 0


def test_union_of_keys() -> None:
    """两路不同键集 → 并集，缺失侧按 0 处理。"""
    normalizer = ScoreNormalizer()
    fused = normalizer.normalize(
        spread_scores={"a": 1.0, "b": 3.0},
        vector_scores={"c": 0.9},
        alpha=0.5,
    )
    assert set(fused) == {"a", "b", "c"}
