"""Phoenix-5 bootstrap 集成测试。"""

from __future__ import annotations

def test_import_bootstrap():
    """bootstrap 模块可正常导入。"""
    from src.plugin_runtime_v2 import bootstrap
    assert hasattr(bootstrap, "init_v2_host_endpoint")
