"""local_store_manager 单元测试。

覆盖 LocalStoreManager 的加载、读写、删除、损坏恢复与原子写入行为。
使用 tmp_path 隔离文件系统副作用。
"""

import json
from pathlib import Path

import pytest

from src.manager.local_store_manager import LocalStoreManager


@pytest.fixture
def store_path(tmp_path):
    """隔离的本地存储文件路径。"""
    return str(tmp_path / "local_store.json")


class TestLocalStoreManagerLoad:
    """LocalStoreManager 加载行为测试。"""

    def test_create_new_store_when_file_absent(self, store_path):
        manager = LocalStoreManager(store_path)
        assert manager.store == {}
        # 文件应被创建
        assert Path(store_path).exists()

    def test_load_existing_store(self, store_path):
        Path(store_path).parent.mkdir(parents=True, exist_ok=True)
        Path(store_path).write_text(json.dumps({"key": "value"}, ensure_ascii=False), encoding="utf-8")
        manager = LocalStoreManager(store_path)
        assert manager.store == {"key": "value"}

    def test_load_corrupt_json_rebuilds_store(self, store_path):
        Path(store_path).parent.mkdir(parents=True, exist_ok=True)
        Path(store_path).write_text("not a valid json{{{", encoding="utf-8")
        manager = LocalStoreManager(store_path)
        # 损坏文件重建为空 store
        assert manager.store == {}
        # 原损坏文件应被备份
        backups = list(Path(store_path).parent.glob("local_store.json.corrupt*"))
        assert len(backups) >= 1

    def test_non_dict_root_rebuilds_store(self, store_path):
        Path(store_path).parent.mkdir(parents=True, exist_ok=True)
        Path(store_path).write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        manager = LocalStoreManager(store_path)
        assert manager.store == {}


class TestLocalStoreManagerAccess:
    """LocalStoreManager 读写访问测试。"""

    def test_setitem_persists(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["name"] = "Alice"
        assert manager["name"] == "Alice"
        # 重新加载验证持久化
        manager2 = LocalStoreManager(store_path)
        assert manager2["name"] == "Alice"

    def test_getitem_missing_returns_none(self, store_path):
        manager = LocalStoreManager(store_path)
        assert manager["nonexistent"] is None

    def test_contains_check(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["key"] = "value"
        assert "key" in manager
        assert "missing" not in manager

    def test_delitem_removes_and_persists(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["key"] = "value"
        del manager["key"]
        assert "key" not in manager
        manager2 = LocalStoreManager(store_path)
        assert "key" not in manager2

    def test_delitem_missing_key_logs_only(self, store_path):
        manager = LocalStoreManager(store_path)
        # 删除不存在的键不应抛异常
        del manager["missing"]
        assert manager.store == {}

    def test_supports_various_value_types(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["str"] = "text"
        manager["int"] = 42
        manager["float"] = 3.14
        manager["bool"] = True
        manager["list"] = [1, 2, 3]
        manager["dict"] = {"nested": "value"}
        assert manager["str"] == "text"
        assert manager["int"] == 42
        assert manager["float"] == 3.14
        assert manager["bool"] is True
        assert manager["list"] == [1, 2, 3]
        assert manager["dict"] == {"nested": "value"}


class TestLocalStoreManagerAtomicWrite:
    """LocalStoreManager 原子写入测试。"""

    def test_write_produces_valid_json(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["key"] = "value"
        content = Path(store_path).read_text(encoding="utf-8")
        loaded = json.loads(content)
        assert loaded == {"key": "value"}

    def test_write_chinese_preserved(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["问候"] = "你好世界"
        content = Path(store_path).read_text(encoding="utf-8")
        assert "你好世界" in content

    def test_no_temp_file_left_behind(self, store_path):
        manager = LocalStoreManager(store_path)
        manager["key"] = "value"
        # 不应残留临时文件
        temp_files = list(Path(store_path).parent.glob(".local_store.json.*.tmp"))
        assert temp_files == []


class TestLocalStoreManagerBackup:
    """LocalStoreManager 损坏备份测试。"""

    def test_backup_path_increments(self, store_path):
        parent = Path(store_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        # 预先创建一个 .corrupt 备份
        (parent / "local_store.json.corrupt").write_text("old corrupt", encoding="utf-8")
        # 写入新的损坏内容
        Path(store_path).write_text("corrupt2", encoding="utf-8")
        manager = LocalStoreManager(store_path)
        assert manager.store == {}
        # 应生成 .corrupt.1 避免覆盖
        assert (parent / "local_store.json.corrupt.1").exists()

    def test_next_backup_path_static(self):
        # 静态方法直接测试
        path = Path("some/dir/file.json")
        backup = LocalStoreManager._next_backup_path(path)
        assert backup.name == "file.json.corrupt"