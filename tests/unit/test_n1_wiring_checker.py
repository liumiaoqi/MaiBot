"""N1 接线检查器单元测试 — 排除规则 + 索引范围 + 间接构造。

v3 精化：验证检查 1 排除规则（dataclass/Pydantic/Enum/Protocol 等）+
索引范围扩展（scripts/）+ 间接构造识别（注册表模式）。
"""

from pathlib import Path


from scripts.n1_wiring_checker import (
    _build_call_index,
    _scan_class_check,
)


# ── 辅助：构造 fixture 文件并扫描 ──────────────────────────


def _write_fixture(tmp_path: Path, name: str, content: str) -> Path:
    """写入 fixture .py 文件，返回路径。"""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _scan_check1(path: Path, call_index=None) -> list:
    """对单个文件运行检查 1，返回违反列表。"""
    source = path.read_text(encoding="utf-8")
    violations = []
    _scan_class_check(source, path, violations, lambda *a: False, call_index)
    return violations


# ── P0-1：排除规则测试 ──────────────────────────────────────


class TestExclusionRules:
    """检查 1 排除规则——框架/数据类不应报零创建。"""

    def test_dataclass_not_reported(self, tmp_path):
        """@dataclass 类不报告。"""
        p = _write_fixture(tmp_path, "foo.py", "from dataclasses import dataclass\n\n@dataclass\nclass Foo:\n    x: int\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_pydantic_basemodel_name_not_reported(self, tmp_path):
        """class Foo(BaseModel) 不报告（ast.Name 基类）。"""
        p = _write_fixture(tmp_path, "foo.py", "from pydantic import BaseModel\n\nclass Foo(BaseModel):\n    x: int\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_pydantic_basemodel_attribute_not_reported(self, tmp_path):
        """class Foo(pydantic.BaseModel) 不报告（ast.Attribute 基类末段）。"""
        p = _write_fixture(tmp_path, "foo.py", "import pydantic\n\nclass Foo(pydantic.BaseModel):\n    x: int\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_enum_not_reported(self, tmp_path):
        """class Foo(Enum) 不报告。"""
        p = _write_fixture(tmp_path, "foo.py", "from enum import Enum\n\nclass Foo(Enum):\n    A = 1\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_protocol_not_reported(self, tmp_path):
        """class Foo(Protocol) 不报告。"""
        p = _write_fixture(tmp_path, "foo.py", "from typing import Protocol\n\nclass Foo(Protocol):\n    def bar(self) -> None: ...\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_typeddict_not_reported(self, tmp_path):
        """class Foo(TypedDict) 不报告。"""
        p = _write_fixture(tmp_path, "foo.py", "from typing import TypedDict\n\nclass Foo(TypedDict):\n    x: int\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_namedtuple_not_reported(self, tmp_path):
        """class Foo(NamedTuple) 不报告。"""
        p = _write_fixture(tmp_path, "foo.py", "from typing import NamedTuple\n\nclass Foo(NamedTuple):\n    x: int\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_abc_not_reported(self, tmp_path):
        """class Foo(ABC) 不报告。"""
        p = _write_fixture(tmp_path, "foo.py", "from abc import ABC\n\nclass Foo(ABC):\n    pass\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)

    def test_business_class_still_reported(self, tmp_path):
        """无装饰器/基类的业务类仍报告零创建候选。"""
        p = _write_fixture(tmp_path, "foo.py", "class Foo:\n    pass\n")
        violations = _scan_check1(p)
        assert any("Foo" in v.message for v in violations)

    def test_config_name_heuristic_forbidden(self, tmp_path):
        """类名含 Config 但无框架装饰器/基类——仍报告（禁止类名启发式）。"""
        p = _write_fixture(tmp_path, "foo.py", "class FooConfig:\n    pass\n")
        violations = _scan_check1(p)
        assert any("FooConfig" in v.message for v in violations)


# ── P0-2：索引范围测试 ──────────────────────────────────────


class TestCallIndex:
    """_build_call_index 索引范围——src/ + scripts/ + __main__ + 工厂函数。"""

    def test_src_call_indexed(self, tmp_path):
        """src/ 下的函数调用被索引。"""
        src = _write_fixture(tmp_path, "src/foo.py", "def bar():\n    pass\n\nbar()\n")
        idx = _build_call_index(src.parent)
        assert "bar" in idx

    def test_scripts_call_indexed(self, tmp_path):
        """scripts/ 下的函数调用被索引（extra_roots）。"""
        src = _write_fixture(tmp_path, "src/empty.py", "")
        scripts = _write_fixture(tmp_path, "scripts/run.py", "def bar():\n    pass\n\nbar()\n")
        idx = _build_call_index(src.parent, extra_roots=[scripts.parent])
        assert "bar" in idx

    def test_main_block_call_indexed(self, tmp_path):
        """if __name__ == '__main__' 块内的调用被索引。"""
        p = _write_fixture(tmp_path, "src/foo.py", "def bar():\n    pass\n\nif __name__ == '__main__':\n    bar()\n")
        idx = _build_call_index(p.parent)
        assert "bar" in idx

    def test_factory_return_call_indexed(self, tmp_path):
        """工厂函数 return ClassName() 被索引。"""
        p = _write_fixture(tmp_path, "src/foo.py", "class Bar:\n    pass\n\ndef create():\n    return Bar()\n")
        idx = _build_call_index(p.parent)
        assert "Bar" in idx

    def test_venv_not_scanned(self, tmp_path):
        """.venv/ 下的文件不被扫描。"""
        _write_fixture(tmp_path, "src/.venv/lib/foo.py", "bar()\n")
        src = _write_fixture(tmp_path, "src/main.py", "")
        idx = _build_call_index(src.parent)
        assert "bar" not in idx


# ── P1-1：间接构造测试 ──────────────────────────────────────


class TestIndirectConstruction:
    """间接构造识别——注册表模式 + plugins/ 排除。"""

    def test_register_classname_indexed(self, tmp_path):
        """register(ClassName) 被索引。"""
        p = _write_fixture(tmp_path, "src/foo.py", "class FooClass:\n    pass\n\nregister(FooClass)\n")
        idx = _build_call_index(p.parent)
        assert "FooClass" in idx

    def test_registry_assign_classname_indexed(self, tmp_path):
        """_REGISTRY['foo'] = FooClass 被索引。"""
        p = _write_fixture(tmp_path, "src/foo.py", "class FooClass:\n    pass\n\n_REGISTRY = {}\n_REGISTRY['foo'] = FooClass\n")
        idx = _build_call_index(p.parent)
        assert "FooClass" in idx

    def test_registry_assign_self_not_indexed(self, tmp_path):
        """self._registry[k] = self 不索引 self。"""
        p = _write_fixture(tmp_path, "src/foo.py", "class Foo:\n    def bar(self):\n        self._registry = {}\n        self._registry['k'] = self\n")
        idx = _build_call_index(p.parent)
        assert "self" not in idx

    def test_non_registry_func_not_indexed(self, tmp_path):
        """非注册函数的参数不被索引。"""
        p = _write_fixture(tmp_path, "src/foo.py", "class FooClass:\n    pass\n\nlogger.info(FooClass)\n")
        idx = _build_call_index(p.parent)
        assert "FooClass" not in idx

    def test_plugin_dir_not_reported(self, tmp_path):
        """plugins/ 下的类不报告检查 1。"""
        p = _write_fixture(tmp_path, "plugins/foo.py", "class Foo:\n    pass\n")
        violations = _scan_check1(p)
        assert not any("Foo" in v.message for v in violations)


# ── 注解式注册表赋值（ast.AnnAssign）：抽取器不得静默漏掉 ──────


class TestAnnotatedRegistryAssign:
    """`_REGISTRY['foo']: type = FooClass` —— 只有 ast.AnnAssign 节点。

    2026-10-17 修：旧 `_build_call_index` 只认 `ast.Assign` ⇒ 注解式写法索引不到
    ⇒ 检查 1 抽到 0 条间接构造、静默放过或误报（"抽取器太窄"那族）。
    """

    def test_annotated_registry_assign_indexed(self, tmp_path):
        """⭐ 反向自检钉：注解式注册表赋值必须被索引（否则下面那条会红）。"""
        p = _write_fixture(
            tmp_path, "src/foo.py",
            "class FooClass:\n    pass\n\n_REGISTRY: dict = {}\n_REGISTRY['foo']: type = FooClass\n",
        )
        idx = _build_call_index(p.parent)
        assert "FooClass" in idx

    def test_annotated_indirect_construction_not_reported(self, tmp_path):
        """注解式间接构造 ⇒ 检查 1 不报「零创建候选: FooClass」。"""
        p = _write_fixture(
            tmp_path, "src/foo.py",
            "class FooClass:\n    pass\n\n_REGISTRY: dict = {}\n_REGISTRY['foo']: type = FooClass\n",
        )
        violations = _scan_check1(p, call_index=_build_call_index(p.parent))
        assert not any("FooClass" in v.message for v in violations)

    def test_plain_registry_assign_still_indexed(self, tmp_path):
        """回归：老写法 `_REGISTRY['foo'] = FooClass` 仍被索引（别把闸弄成恒红）。"""
        p = _write_fixture(
            tmp_path, "src/foo.py",
            "class FooClass:\n    pass\n\n_REGISTRY = {}\n_REGISTRY['foo'] = FooClass\n",
        )
        assert "FooClass" in _build_call_index(p.parent)

    def test_bare_annotation_not_indexed(self, tmp_path):
        """纯注解 `FooClass: type`（AnnAssign.value is None）不得炸/不得瞎索引。"""
        p = _write_fixture(tmp_path, "src/foo.py", "class FooClass:\n    pass\n\n_OTHER: type\n")
        idx = _build_call_index(p.parent)
        assert "_OTHER" not in idx

    def test_self_annotated_registry_assign_not_indexed(self, tmp_path):
        """`self._registry['k']: X = self` 不得把 self 索引进去。"""
        p = _write_fixture(
            tmp_path, "src/foo.py",
            "class Foo:\n    def bar(self):\n        self._registry: dict = {}\n"
            "        self._registry['k']: object = self\n",
        )
        assert "self" not in _build_call_index(p.parent)


class TestEmptyCallIndexGate:
    """空数据源闸：扫了文件却抽不到任何调用节点 ⇒ 必须出告警（不是静默绿）。"""

    def test_warning_when_no_call_nodes(self, tmp_path, capsys):
        """合成"索索引面失效"：文件里没有任何 Call 节点 ⇒ stderr 出告警。"""
        _write_fixture(tmp_path, "src/foo.py", "X = 1\nY = 2\n")
        idx = _build_call_index(tmp_path)
        captured = capsys.readouterr()
        assert idx == {}
        assert "空数据源告警" in captured.err

    def test_no_warning_when_call_nodes_present(self, tmp_path, capsys):
        """正常路径静默：有调用节点 ⇒ 不出告警、索引非空。"""
        _write_fixture(tmp_path, "src/foo.py", "def bar():\n    pass\n\nbar()\n")
        idx = _build_call_index(tmp_path)
        captured = capsys.readouterr()
        assert idx
        assert "空数据源告警" not in captured.err

    def test_stats_out_param_reports_counts(self, tmp_path):
        """stats 出参回报真实计数（供 --strict 断言用）。"""
        _write_fixture(tmp_path, "src/foo.py", "def bar():\n    pass\n\nbar()\n")
        stats: dict = {}
        _build_call_index(tmp_path, stats=stats)
        assert stats["scanned_files"] == 1
        assert stats["call_nodes"] == 1