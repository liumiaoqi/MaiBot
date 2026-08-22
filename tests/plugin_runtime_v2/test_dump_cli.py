"""dump.py CLI 导入路径修正测试（T3.4/T3.8）。

验证 dump.py 的 get_plugin_config_manager 导入路径已从 host_config_manager
修正为 bootstrap（P0-A23b-1 修复），main 函数可正常导入不抛 ImportError。
"""


import pytest


class TestDumpCliImport:
    """dump.py CLI 导入路径测试。"""

    def test_dump_module_importable(self):
        """dump 模块可正常导入（不抛 ImportError）。"""
        from src.plugin_runtime_v2.config import dump

        assert hasattr(dump, "main")

    def test_main_callable(self):
        """main 函数可调用（不抛 ImportError）。"""
        from src.plugin_runtime_v2.config.dump import main

        assert callable(main)

    def test_import_path_is_bootstrap(self):
        """导入路径已从 host_config_manager 修正为 bootstrap。"""
        import inspect

        from src.plugin_runtime_v2.config import dump

        source = inspect.getsource(dump)
        assert "from src.plugin_runtime_v2.bootstrap import get_plugin_config_manager" in source
        assert "from src.plugin_runtime_v2.config.host_config_manager import get_plugin_config_manager" not in source

    def test_get_plugin_config_manager_exists_in_bootstrap(self):
        """bootstrap 模块中确实定义了 get_plugin_config_manager。"""
        from src.plugin_runtime_v2.bootstrap import get_plugin_config_manager

        assert callable(get_plugin_config_manager)