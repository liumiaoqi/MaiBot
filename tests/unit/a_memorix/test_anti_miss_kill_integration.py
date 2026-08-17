"""ZG-27 测试：防误杀集成（测试组 9——6 层冗余保护协同）。"""

import pytest

from src.A_memorix.core.runtime.eviction_score import EvictableItem
from src.A_memorix.core.runtime.shrinker import ShrinkControl


def test_is_pinned_object_not_evicted():
    """is_pinned=True 对象 oom_badness 返回 -1（永不被驱逐）。"""
    item = EvictableItem(is_pinned=True, priority_score=800)
    assert item.oom_badness(current_time=0, watermark_min=0, usage=100) == -1


def test_priority_score_minus_1000_not_evicted():
    """priority_score=-1000 对象 oom_badness 返回 -1。"""
    item = EvictableItem(priority_score=-1000)
    assert item.oom_badness(current_time=0, watermark_min=0, usage=100) == -1


def test_watermark_min_hard_floor_integration():
    """水位 MIN 硬底线——usage < watermark_min → -1。"""
    item = EvictableItem(priority_score=800)
    assert item.oom_badness(current_time=0, watermark_min=100, usage=50) == -1


@pytest.mark.asyncio
async def test_vector_shrinker_v1_count_returns_zero():
    """VectorShrinker V1 count_objects 返回 0（V1 不回收向量）。"""
    from src.A_memorix.core.runtime.shrinkers.vector import VectorShrinker

    class _EmptyVectorStore:
        pass

    shrinker = VectorShrinker(_EmptyVectorStore())
    sc = ShrinkControl()
    result = await shrinker.count_objects(sc)
    assert result == 0


@pytest.mark.asyncio
async def test_vector_shrinker_v1_scan_returns_zero():
    """VectorShrinker V1 scan_objects 返回 0。"""
    from src.A_memorix.core.runtime.shrinkers.vector import VectorShrinker

    shrinker = VectorShrinker(None)
    sc = ShrinkControl()
    result = await shrinker.scan_objects(sc)
    assert result == 0


def test_six_layer_redundancy():
    """6 层冗余保护逐层验证。"""
    # Layer 1: is_pinned
    assert EvictableItem(is_pinned=True).oom_badness(0, 0, 100) == -1
    # Layer 2: priority_score=-1000
    assert EvictableItem(priority_score=-1000).oom_badness(0, 0, 100) == -1
    # Layer 3: 核心关系 priority_score=-500 → 极低分
    assert EvictableItem(priority_score=-500).oom_badness(0, 0, 100) < EvictableItem(
        priority_score=0
    ).oom_badness(0, 0, 100)
    # Layer 4: 水位 MIN 硬底线
    assert EvictableItem(priority_score=800).oom_badness(0, 100, 50) == -1
    # Layer 5: protected_until 未过期
    assert EvictableItem(protected_until=100.0).oom_badness(50.0, 0, 100) == -1
    # Layer 6: VectorShrinker V1 count 返回 0（上方已测）
