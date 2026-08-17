"""ZG-27 测试：生产路径接线验证（测试组 8——AGENTS.md 硬性规则）。

新模块必须存在生产接线点，禁止"只有定义没有调用点"。
"""

from pathlib import Path


def test_kswapd_registration_in_start_background_tasks():
    """kswapd 在 start_background_tasks registrations 中。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert 'registrations["kswapd"]' in content
    assert "_memory_kswapd.run" in content


def test_reclaim_scheduler_init_in_kernel_initializer():
    """ReclaimScheduler 在 kernel_initializer 中初始化。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "ReclaimScheduler(" in content
    assert "WatermarkZone(" in content
    assert "MemoryKswapd(" in content


def test_v1_shrinkers_registered():
    """V1 注册 5 个内存缓存 shrinker（ppr/saliency/adjacency_t/cached_map/vector）。

    cognitive/profile 为 DB-backed，V1 跳过并出声（见 test_db_backed_shrinkers_skipped_with_log）。
    """
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "register(PprCacheShrinker" in content
    assert "register(SaliencyCacheShrinker" in content
    assert "register(AdjacencyTShrinker" in content
    assert "register(CachedMapShrinker" in content
    assert "register(VectorShrinker" in content


def test_db_backed_shrinkers_skipped_with_log():
    """cognitive/profile shrinker V1 跳过且有显式日志（静默失效禁令）。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "跳过 cognitive_state" in content
    assert "跳过 profile_snapshot" in content


def test_usage_provider_wired():
    """usage_provider 注入到 WatermarkZone。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "_build_usage_provider" in content
    assert "usage_provider=" in content


def test_grep_production_call_sites():
    """所有新模块入口函数存在生产调用点。"""
    base = Path("src/A_memorix")
    init_content = (base / "core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "MemoryKswapd" in init_content
    assert "ReclaimScheduler" in init_content
    assert "WatermarkZone" in init_content
    kswapd_content = (base / "core/runtime/kswapd.py").read_text(encoding="utf-8")
    assert "run_reclaim" in kswapd_content


def test_init_watermark_reclaim_called():
    """init_watermark_reclaim 在 init_all_services 中被调用。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "init_watermark_reclaim" in content


def test_kswapd_error_port_wired():
    """kswapd 双通道上报——error_port 注入（P2-7 修复）。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert "error_port=get_error_escalation_port()" in content
