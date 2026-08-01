"""ResourceLimitPort 契约测试 — 对应 tasks §10.2。

用 AST 解析适配器源码验证方法存在，避免导入适配器触发 __init__.py 依赖链。
"""


import ast
from pathlib import Path

from src.core.protocols import ResourceLimitPort


_ADAPTER_PATH = (
    Path(__file__).resolve().parents[3]
    / "src" / "core" / "adapters" / "resource_limit_adapter.py"
)

_REQUIRED_METHODS = [
    "charge",
    "uncharge",
    "get_usage_snapshot",
    "register_plugin",
    "unregister_plugin",
    "reload_config",
    "record_pressure_sample",
    "trigger_oom",
    "get_resource_tree_view",
    "get_pressure_history",
    "get_oom_history",
]


class TestResourceLimitPortContract:
    """验证适配器满足 ResourceLimitPort Protocol 契约。"""

    def test_port_defines_all_methods(self):
        """ResourceLimitPort Protocol 定义了全部 11 个方法。"""
        for method_name in _REQUIRED_METHODS:
            assert hasattr(ResourceLimitPort, method_name), f"Protocol 缺少方法: {method_name}"

    def test_adapter_implements_all_methods(self):
        """适配器源码定义了全部 11 个方法。"""
        source = _ADAPTER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        adapter_methods: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ResourceLimitAdapter":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        adapter_methods.add(item.name)

        for method_name in _REQUIRED_METHODS:
            assert method_name in adapter_methods, f"适配器缺少方法: {method_name}"

    def test_adapter_inherits_port(self):
        """适配器继承 ResourceLimitPort。"""
        source = _ADAPTER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ResourceLimitAdapter":
                base_names = [
                    base.id if isinstance(base, ast.Name) else ""
                    for base in node.bases
                ]
                assert "ResourceLimitPort" in base_names, "适配器未继承 ResourceLimitPort"
                return
        raise AssertionError("未找到 ResourceLimitAdapter 类定义")
