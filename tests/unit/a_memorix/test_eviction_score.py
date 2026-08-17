"""ZG-27 测试：驱逐评分与防误杀（测试组 4——防误杀测试）。"""

from src.A_memorix.core.runtime.eviction_score import EvictableItem


def test_oom_badness_explicit_score():
    """oom_badness 显式分数：priority_score 越高分数越高。"""
    high = EvictableItem(priority_score=800)
    low = EvictableItem(priority_score=100)
    assert high.oom_badness(current_time=0, watermark_min=0, usage=100) > low.oom_badness(
        current_time=0, watermark_min=0, usage=100
    )


def test_is_pinned_hard_protection():
    """is_pinned 硬保护 → oom_badness 返回 -1。"""
    item = EvictableItem(is_pinned=True, priority_score=800)
    assert item.oom_badness(current_time=0, watermark_min=0, usage=100) == -1


def test_priority_score_minus_1000_hard_protection():
    """priority_score=-1000 硬保护（人格记忆）→ oom_badness 返回 -1。"""
    item = EvictableItem(priority_score=-1000)
    assert item.oom_badness(current_time=0, watermark_min=0, usage=100) == -1


def test_core_relation_hard_protection():
    """核心关系 priority_score=-500 → 极低分。"""
    core = EvictableItem(priority_score=-500)
    normal = EvictableItem(priority_score=0)
    assert core.oom_badness(current_time=0, watermark_min=0, usage=100) < normal.oom_badness(
        current_time=0, watermark_min=0, usage=100
    )


def test_watermark_min_hard_floor():
    """水位 MIN 硬底线：usage < watermark_min → -1。"""
    item = EvictableItem(priority_score=800)
    assert item.oom_badness(current_time=0, watermark_min=100, usage=50) == -1
    assert item.oom_badness(current_time=0, watermark_min=100, usage=150) > 0


def test_protected_until_not_expired():
    """protected_until 未过期 → -1；已过期 → 正分。"""
    item = EvictableItem(priority_score=800, protected_until=100.0)
    assert item.oom_badness(current_time=50.0, watermark_min=0, usage=100) == -1
    assert item.oom_badness(current_time=200.0, watermark_min=0, usage=100) > 0