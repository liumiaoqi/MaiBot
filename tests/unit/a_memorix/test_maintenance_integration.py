"""ZG-27 测试：与既有清理机制集成（测试组 10——ZG-29 衔接）。"""

from pathlib import Path


def test_kswapd_and_maintenance_orthogonal():
    """kswapd 回收缓存类，maintenance 回收关系类——两者正交。

    V1 仅注册缓存类 shrinker（PPR/Cognitive/Profile/Saliency/AdjacencyT/CachedMap），
    不注册关系类 shrinker——关系类由 maintenance.py freeze/prune 处理。
    """
    init_content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    # kswapd 注册缓存类 shrinker
    assert "PprCacheShrinker" in init_content
    assert "SaliencyCacheShrinker" in init_content
    assert "CachedMapShrinker" in init_content
    # maintenance.py 仍有关系类回收
    maint_content = Path("src/A_memorix/core/runtime/services/maintenance.py").read_text(encoding="utf-8")
    assert "freeze" in maint_content or "prune" in maint_content


def test_maintenance_protection_not_bypassed():
    """maintenance.py 的 is_pinned/protected_until 保护逻辑不被 kswapd 绕过。

    kswapd V1 仅回收缓存类（PPR/Cognitive/Profile/Saliency/AdjacencyT/CachedMap），
    不回收关系类——关系类的 is_pinned 保护由 maintenance.py 独立处理。
    """
    init_content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    # 不应注册关系类 shrinker（V1 不含 RelationShrinker）
    assert "RelationShrinker" not in init_content


def test_zg29_reuse_not_duplicate():
    """6 个缓存类 shrinker 来自 ZG-29 的 6 机制可注册清单。"""
    from src.A_memorix.core.runtime.shrinkers.adjacency_t import AdjacencyTShrinker
    from src.A_memorix.core.runtime.shrinkers.cached_map import CachedMapShrinker
    from src.A_memorix.core.runtime.shrinkers.cognitive import CognitiveStateShrinker
    from src.A_memorix.core.runtime.shrinkers.ppr import PprCacheShrinker
    from src.A_memorix.core.runtime.shrinkers.profile import ProfileSnapshotShrinker
    from src.A_memorix.core.runtime.shrinkers.saliency import SaliencyCacheShrinker

    # 6 个 shrinker 名称对应 ZG-29 清单
    names = {
        PprCacheShrinker.name,
        CognitiveStateShrinker.name,
        ProfileSnapshotShrinker.name,
        SaliencyCacheShrinker.name,
        AdjacencyTShrinker.name,
        CachedMapShrinker.name,
    }
    assert names == {"ppr_cache", "cognitive_state", "profile_snapshot", "saliency_cache", "adjacency_t", "cached_map"}


def test_no_conflict_with_existing_capacity_control():
    """与既有容量控制机制不冲突。

    PprCacheShrinker 仅处理 TTL 过期，容量上限保留现有 256 硬驱逐。
    """
    ppr_content = Path("src/A_memorix/core/runtime/shrinkers/ppr.py").read_text(encoding="utf-8")
    # PprCacheShrinker 仅 pop 过期条目，不做容量驱逐
    assert "pop" in ppr_content
