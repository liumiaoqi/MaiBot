"""ZG-5 验证与回归测试 — 对应 tasks §12。

§12.1 不补清单落地验证 (N1-N6)
§12.2 架构约束验证
§12.3 回归测试
§12.4 资源占用验证
"""


import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock

if "structlog" not in sys.modules:
    sys.modules["structlog"] = MagicMock()

import pytest

from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.types import ResourceDimension

_SRC_CORE = Path(__file__).resolve().parents[3] / "src" / "core"
_RL_DIR = _SRC_CORE / "resource_limit"


class TestN1N6NotImplementedList:
    """§12.1 不补清单落地验证。"""

    def test_n1_no_redblack_tree(self):
        """N1: soft_limit 不用红黑树（用简单遍历或 heapq）。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "redblack" not in source.lower()
            assert "RedBlack" not in source
            assert "RBTree" not in source

    def test_n2_no_per_cpu_stock(self):
        """N2: 不补 per-cpu stock 缓存。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "per_cpu" not in source.lower()
            assert "stock_cache" not in source.lower()

    def test_n3_no_oom_kill_disable(self):
        """N3: 不补 oom_kill_disable + 用户态等待。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "oom_kill_disable" not in source

    def test_n4_unified_event_with_local_switch(self):
        """N4: 统一一套事件机制 + events_local 开关。"""
        propagator_source = (_RL_DIR / "resource_event_propagator.py").read_text("utf-8")
        assert "events_local" in propagator_source
        assert "is_local" in propagator_source

    def test_n5_hard_protection_exemption_implemented(self):
        """N5: 硬保护豁免（OOM 跳过 usage < min）已实现。"""
        oom_source = (_RL_DIR / "oom_handler.py").read_text("utf-8")
        assert "min_val" in oom_source
        assert "current_usage < min_val" in oom_source

    def test_n6_no_numa_cpuset(self):
        """N6: 不补 NUMA/cpuset 约束。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "numa" not in source.lower()
            assert "cpuset" not in source.lower()


class TestArchitectureConstraints:
    """§12.2 架构约束验证。"""

    def test_core_no_resource_limit_import(self):
        """核心模块不导入 resource_limit 具体引擎类（仅 protocols.py 导入类型）。"""
        skip_dirs = {"resource_limit", "adapters", "__pycache__"}
        for py_file in _SRC_CORE.rglob("*.py"):
            if any(part in skip_dirs for part in py_file.parts):
                continue
            source = py_file.read_text(encoding="utf-8")
            # protocols.py 允许导入 types（类型定义）
            if py_file.name == "protocols.py":
                continue
            # 不允许导入引擎类
            for engine in ["ResourceCounter", "OOMHandler", "PressureDetector",
                           "ResourceEventPropagator", "ResourceLimitConfigManager"]:
                assert f"import {engine}" not in source, \
                    f"{py_file.name} 导入了 {engine}"

    def test_no_autonomy_event_bus_get_instance(self):
        """不调用 AutonomyEventBus.get_instance()。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "AutonomyEventBus" not in source
            assert "get_instance" not in source

    def test_no_direct_config_manager_import(self):
        """不直接导入 config_manager 模块。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "from src.config" not in source
            assert "import config_manager" not in source

    def test_no_direct_global_config_import(self):
        """不直接导入 global_config。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "import global_config" not in source
            assert "from src.config.global_config" not in source


class TestRegression:
    """§12.3 回归测试。"""

    def test_unconfigured_plugin_passthrough(self):
        """未配置四档限制的插件保持原有行为（不限制）。"""
        counter = ResourceCounter()  # 无 max_limit_provider
        counter.register_plugin("a")
        # 无限制，任何量都应通过
        result = counter.charge("a", ResourceDimension.TOKEN, 999999)
        assert result.accepted is True

    def test_python_314_no_future_annotations(self):
        """不使用 from __future__ import annotations。"""
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "from __future__ import annotations" not in source, \
                f"{py_file.name} 使用了 future annotations"


class TestResourceFootprint:
    """§12.4 资源占用验证。"""

    def test_no_new_dependencies(self):
        """不引入新依赖（仅用标准库 heapq、asyncio.Lock）。"""
        allowed_imports = {
            "asyncio", "logging", "time", "uuid", "os", "collections",
            "typing", "dataclasses", "enum", "heapq",
        }
        for py_file in _RL_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top not in allowed_imports and top != "src":
                            pytest.fail(f"{py_file.name} 引入非标准依赖: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and not node.level:
                        top = node.module.split(".")[0]
                        if top not in allowed_imports and top != "src":
                            pytest.fail(f"{py_file.name} 引入非标准依赖: {node.module}")