"""P2 confidence 边权重 + 安全护栏测试（ZG-30）。"""

from dataclasses import dataclass
from typing import List

from src.A_memorix.core.retrieval.confidence_guard import ConfidenceGuard


@dataclass
class MockCandidate:
    confidence: float
    score: float


def test_weighted_ranking() -> None:
    """confidence 加权排序：高 confidence 排前。"""
    guard = ConfidenceGuard()

    candidates = [
        MockCandidate(confidence=0.1, score=0.9),
        MockCandidate(confidence=1.0, score=0.9),
        MockCandidate(confidence=0.5, score=0.9),
    ]

    weighted = [guard.compute_weight(c.confidence, candidates)[0] for c in candidates]

    assert weighted[1] > weighted[2] > weighted[0]
    assert weighted[0] == 0.3
    assert weighted[1] == 1.0
    assert weighted[2] == 0.5


def test_floor() -> None:
    """confidence floor=0.3 生效。"""
    guard = ConfidenceGuard(floor=0.3)

    w1, _ = guard.compute_weight(0.0)
    assert w1 == 0.3

    w2, _ = guard.compute_weight(0.1)
    assert w2 == 0.3

    w3, _ = guard.compute_weight(0.3)
    assert w3 == 0.3

    w4, _ = guard.compute_weight(0.5)
    assert w4 == 0.5

    w5, _ = guard.compute_weight(1.0)
    assert w5 == 1.0


def test_misalignment_fallback() -> None:
    """反对齐检测：confidence 与 score 负相关时降级为无权。"""
    guard = ConfidenceGuard(misalignment_threshold=-0.3)

    candidates = [
        MockCandidate(confidence=1.0, score=0.1),
        MockCandidate(confidence=0.9, score=0.3),
        MockCandidate(confidence=0.5, score=0.7),
        MockCandidate(confidence=0.1, score=1.0),
    ]

    weight, degraded = guard.compute_weight(0.8, candidates)
    assert degraded is True
    assert weight == 1.0


def test_clamp() -> None:
    """confidence 异常值 clamp。"""
    guard = ConfidenceGuard()

    w, _ = guard.compute_weight(-0.5)
    assert w == 0.3

    w, _ = guard.compute_weight(2.0)
    assert w == 2.0

    w, _ = guard.compute_weight(0.0)
    assert w == 0.3


def test_no_misalignment_when_aligned() -> None:
    """对齐时不降级。"""
    guard = ConfidenceGuard(misalignment_threshold=-0.3)

    candidates = [
        MockCandidate(confidence=1.0, score=1.0),
        MockCandidate(confidence=0.8, score=0.8),
        MockCandidate(confidence=0.5, score=0.5),
        MockCandidate(confidence=0.1, score=0.1),
    ]

    weight, degraded = guard.compute_weight(0.7, candidates)
    assert degraded is False
    assert weight == 0.7


def test_confidence_guard_wiring() -> None:
    """ConfidenceGuard 可独立构造（接线验证）。"""
    guard = ConfidenceGuard()
    assert guard is not None
    assert hasattr(guard, "compute_weight")
    assert hasattr(guard, "apply_floor")
    assert hasattr(guard, "detect_misalignment")