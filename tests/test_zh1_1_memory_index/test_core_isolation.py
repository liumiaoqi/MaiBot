"""ZH1-1a 核心隔离验证 — 微内核 + 接口契约。

覆盖：
  - 核心层不改（本批改动不涉及 src/core/ 下业务接口文件）
  - error_escalation_port 复用（通过 get_error_escalation_port() 获取，不新建 Port）
"""

import inspect
from pathlib import Path

import pytest

from src.core.error_escalation_port_registry import get_error_escalation_port


class TestCoreIsolation:
    """核心隔离验证。"""

    def test_core_layer_not_modified(self) -> None:
        """核心层不改：ZH1-1a 新建文件在 src/maisaka/memory/ 不在 src/core/。"""
        repo_root = Path(__file__).resolve().parents[2]
        new_file1 = repo_root / "src" / "maisaka" / "memory" / "mid_term_persistence.py"
        new_file2 = repo_root / "src" / "maisaka" / "memory" / "mid_term_summary_queue.py"
        # 新建文件在 maisaka 层
        assert new_file1.exists()
        assert new_file2.exists()
        assert "maisaka" in str(new_file1)
        assert "maisaka" in str(new_file2)
        # 不在 core 层
        core_file1 = repo_root / "src" / "core" / "mid_term_persistence.py"
        core_file2 = repo_root / "src" / "core" / "mid_term_summary_queue.py"
        assert not core_file1.exists(), "mid_term_persistence 不应在 src/core/ 下"
        assert not core_file2.exists(), "mid_term_summary_queue 不应在 src/core/ 下"

    def test_core_not_import_new_module(self) -> None:
        """核心层不 import 新模块：src/core/ 下不 import mid_term_persistence/queue。"""
        repo_root = Path(__file__).resolve().parents[2]
        core_dir = repo_root / "src" / "core"
        if not core_dir.exists():
            pytest.skip("src/core/ 目录不存在")
        forbidden_markers = [
            "from src.maisaka.memory.mid_term_persistence import",
            "from src.maisaka.memory.mid_term_summary_queue import",
            "import src.maisaka.memory.mid_term_persistence",
            "import src.maisaka.memory.mid_term_summary_queue",
        ]
        violations = []
        for py_file in core_dir.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for marker in forbidden_markers:
                if marker in source:
                    violations.append(f"{py_file}: 含 {marker}")
        assert not violations, f"核心层违反隔离原则: {violations}"

    def test_error_escalation_port_reuse(self) -> None:
        """error_escalation_port 复用：通过 get_error_escalation_port() 获取。"""
        # get_error_escalation_port 存在且可调用
        assert callable(get_error_escalation_port)
        # 未初始化时返回 None（不抛异常）
        port = get_error_escalation_port()
        assert port is None or hasattr(port, "report")

    def test_persistence_uses_error_escalation_port(self) -> None:
        """mid_term_persistence 通过 error_escalation_port 上报（源码检查）。"""
        from src.maisaka.memory import mid_term_persistence

        source = inspect.getsource(mid_term_persistence)
        assert "get_error_escalation_port" in source, \
            "mid_term_persistence 未通过 get_error_escalation_port 上报"
        assert "ErrorLevel" in source

    def test_queue_uses_error_escalation_port(self) -> None:
        """mid_term_summary_queue 通过 error_escalation_port 上报（源码检查）。"""
        from src.maisaka.memory import mid_term_summary_queue

        source = inspect.getsource(mid_term_summary_queue)
        assert "get_error_escalation_port" in source, \
            "mid_term_summary_queue 未通过 get_error_escalation_port 上报"