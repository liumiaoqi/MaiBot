"""ZG-27 测试：配置关闭回归（测试组 7——灰度安全）。"""

from pathlib import Path


def test_config_off_default_false():
    """enable_watermark_reclaim 默认 False（灰度安全）。"""
    from src.config.official_configs import AMemorixMemoryEvolutionConfig

    config = AMemorixMemoryEvolutionConfig()
    assert config.enable_watermark_reclaim is False


def test_config_off_no_kswapd_in_registrations():
    """配置关闭时 start_background_tasks registrations 不含 kswapd。"""
    content = Path("src/A_memorix/core/runtime/services/kernel_initializer.py").read_text(encoding="utf-8")
    assert 'registrations["kswapd"]' in content
    assert "hasattr(kernel, \"_memory_kswapd\")" in content


def test_maintenance_unchanged():
    """maintenance.py 既有逻辑未被改动。"""
    content = Path("src/A_memorix/core/runtime/services/maintenance.py").read_text(encoding="utf-8")
    assert "memory_maintenance_loop" in content
    assert "_process_freeze_and_prune" in content