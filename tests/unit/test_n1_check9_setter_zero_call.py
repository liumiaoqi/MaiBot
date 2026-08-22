"""N1 检查项 9 单元测试 — set_* 配置注入点零调用检测。

5 用例：缺陷/白名单/修复/无 docstring/仅测试引用。
测试用真实 AST 调用 _check_setter_zero_call，走生产路径（接线四连问第 4 问）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.n1_wiring_checker import (
    WhitelistRule,
    _check_setter_zero_call,
)


# ── 辅助 ──────────────────────────────────────────────────


def _write_fixture(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _scan_check9(path: Path, call_index: dict | None = None, whitelist: list | None = None) -> list:
    """对单个文件运行检查 9，返回违反列表。"""
    source = path.read_text(encoding="utf-8")
    violations = []
    wl = whitelist or []
    _check_setter_zero_call(source, path, violations, lambda c, n, l: any(r.matches(str(path), n, c) for r in wl), call_index)
    return violations


# ── 测试用例 ──────────────────────────────────────────────


_SETTER_WITH_DOCSTRING = '''\
class EmojiManager:
    def set_ports(self, model_config_port, app_config_port):
        """注入配置端口。由 main.py 调用。"""
        self._model_config_port = model_config_port
        self._app_config_port = app_config_port
'''

_SETTER_NO_DOCSTRING = '''\
class FooManager:
    def set_name(self, name):
        self._name = name
'''


class TestSetterZeroCall:
    """检查 9：set_* 配置注入点零调用检测。"""

    def test_setter_zero_call_defect(self, tmp_path):
        """缺陷样本：set_ports 有定义 + docstring 声明注入 + 零调用 → 报 1 条。"""
        p = _write_fixture(tmp_path, "emoji_manager.py", _SETTER_WITH_DOCSTRING)
        violations = _scan_check9(p, call_index=None)
        assert len(violations) == 1
        assert violations[0].check_id == "9"
        assert "set_ports" in violations[0].message

    def test_setter_zero_call_whitelisted(self, tmp_path):
        """白名单样本：缺陷 + 白名单含 set_ports → 报 0 条。"""
        p = _write_fixture(tmp_path, "emoji_manager.py", _SETTER_WITH_DOCSTRING)
        wl = [WhitelistRule(path_substr="emoji_manager.py", checks=["9"], names=["set_ports"])]
        violations = _scan_check9(p, call_index=None, whitelist=wl)
        assert len(violations) == 0

    def test_setter_zero_call_fixed(self, tmp_path):
        """修复样本：set_ports 在 main.py 有生产调用 → 报 0 条。"""
        p = _write_fixture(tmp_path, "emoji_manager.py", _SETTER_WITH_DOCSTRING)
        call_index = {"set_ports": {"src/main.py"}}
        violations = _scan_check9(p, call_index=call_index)
        assert len(violations) == 0

    def test_setter_no_docstring_not_checked(self, tmp_path):
        """无 docstring 声明：set_name 不纳入检测 → 报 0 条。"""
        p = _write_fixture(tmp_path, "foo_manager.py", _SETTER_NO_DOCSTRING)
        violations = _scan_check9(p, call_index=None)
        assert len(violations) == 0

    def test_setter_only_test_call(self, tmp_path):
        """仅测试引用：set_ports 仅在 test_*.py 调用 → 报 1 条（仅测试引用不算生产调用）。"""
        p = _write_fixture(tmp_path, "emoji_manager.py", _SETTER_WITH_DOCSTRING)
        call_index = {"set_ports": {"tests/unit/test_emoji.py"}}
        violations = _scan_check9(p, call_index=call_index)
        assert len(violations) == 1
        assert violations[0].check_id == "9"