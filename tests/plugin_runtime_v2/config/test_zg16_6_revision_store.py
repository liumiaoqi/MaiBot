"""ZG16-6a: revision 持久化测试——单调递增 + 乐观并发检查。

覆盖 design 4.4 全部 10 个场景，spec 8.3 实测验证项（5 项）。
"""

import pytest

from src.plugin_runtime_v2.config.revision_store import ConfigConflictError, RevisionStore


def test_revision_monotonic_increase(tmp_path):
    """revision 单调递增（spec 5.4.1 规则 1）。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    assert store.get("X") == 0
    assert store.bump("X") == 1
    assert store.bump("X") == 2


def test_optimistic_concurrency_pass(tmp_path):
    """expected == actual 通过（spec 5.4.1 规则 3b）。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    store.bump("X")  # revision=1
    store.check("X", 1)  # expected=1, actual=1 → 通过


def test_optimistic_concurrency_conflict(tmp_path):
    """expected != actual 抛 ConfigConflictError（spec 5.4.1 规则 3a）。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    store.bump("X")  # revision=1
    store.bump("X")  # revision=2
    with pytest.raises(ConfigConflictError) as exc_info:
        store.check("X", 1)  # expected=1, actual=2
    assert exc_info.value.plugin_id == "X"
    assert exc_info.value.expected == 1
    assert exc_info.value.actual == 2


def test_revision_persistence_recovery(tmp_path):
    """revision 持久化恢复（spec 5.4.1 规则 2）。"""
    path = str(tmp_path / "rev.json")
    store1 = RevisionStore(path)
    store1.bump("X")  # revision=1
    store1.bump("X")  # revision=2
    # 模拟 Host 重启
    store2 = RevisionStore(path)
    assert store2.get("X") == 2  # 从持久化恢复，不回退到 0


def test_independent_revision(tmp_path):
    """每插件独立 revision（spec 5.4.1 规则 8）。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    store.bump("X")
    store.bump("Y")
    assert store.get("X") == 1 and store.get("Y") == 1
    store.bump("X")
    assert store.get("X") == 2 and store.get("Y") == 1  # Y 不受影响


def test_expected_none_skip_check(tmp_path):
    """expected is None 跳过检查（spec 5.4.1 规则 3）。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    store.bump("X")
    store.check("X", None)  # 不抛异常


def test_new_plugin_revision_starts_zero(tmp_path):
    """新插件 revision 从 0 开始。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    assert store.get("new_plugin") == 0


def test_corrupted_file_fallback_empty(tmp_path):
    """revision 文件损坏 → 回退空 dict（spec 5.4.3 场景 1）。"""
    path = tmp_path / "rev.json"
    path.write_text("not valid json", encoding="utf-8")
    store = RevisionStore(str(path))
    assert store.get("X") == 0  # 损坏文件回退空


def test_bump_returns_new_revision(tmp_path):
    """bump 返回递增后的新 revision 值。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    rev1 = store.bump("X")
    rev2 = store.bump("X")
    rev3 = store.bump("X")
    assert rev1 == 1 and rev2 == 2 and rev3 == 3


def test_check_nonexistent_plugin(tmp_path):
    """check 不存在的插件——expected=0 通过，expected!=0 冲突。"""
    store = RevisionStore(str(tmp_path / "rev.json"))
    store.check("nonexistent", 0)  # actual=0, expected=0 → 通过
    with pytest.raises(ConfigConflictError):
        store.check("nonexistent", 1)  # actual=0, expected=1 → 冲突