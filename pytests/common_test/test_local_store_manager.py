from pathlib import Path
from types import ModuleType

import importlib
import json

import pytest


def _load_local_store_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """在临时工作目录中加载本地存储模块，避免全局单例写入项目目录。"""
    monkeypatch.chdir(tmp_path)
    import src.manager.local_store_manager as local_store_module

    return importlib.reload(local_store_module)


class TestLocalStoreManager:
    """本地存储读写测试。"""

    def test_creates_store_file_without_parent_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """传入裸文件名时也应能创建本地存储文件。"""
        local_store_module = _load_local_store_module(tmp_path, monkeypatch)

        manager = local_store_module.LocalStoreManager("local_store.json")
        manager["answer"] = 42

        store_path = tmp_path / "local_store.json"
        assert store_path.exists()
        assert json.loads(store_path.read_text(encoding="utf-8")) == {"answer": 42}

    def test_backs_up_broken_json_before_rebuild(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """损坏的 JSON 应先备份，再重建为空本地存储。"""
        local_store_module = _load_local_store_module(tmp_path, monkeypatch)
        store_path = tmp_path / "data" / "local_store.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("{broken", encoding="utf-8")

        manager = local_store_module.LocalStoreManager(str(store_path))

        assert manager.store == {}
        assert json.loads(store_path.read_text(encoding="utf-8")) == {}
        assert (tmp_path / "data" / "local_store.json.corrupt").read_text(encoding="utf-8") == "{broken"

    def test_failed_save_keeps_original_file_and_cleans_temp_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """保存失败时不应留下半写入文件或临时文件。"""
        local_store_module = _load_local_store_module(tmp_path, monkeypatch)
        store_path = tmp_path / "data" / "local_store.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text('{"stable": "value"}\n', encoding="utf-8")
        manager = local_store_module.LocalStoreManager(str(store_path))

        def _raise_dump_error(*_args, **_kwargs) -> None:
            raise RuntimeError("dump failed")

        monkeypatch.setattr(local_store_module.json, "dump", _raise_dump_error)

        manager.store["new"] = "value"
        with pytest.raises(RuntimeError, match="dump failed"):
            manager.save_local_store()

        assert store_path.read_text(encoding="utf-8") == '{"stable": "value"}\n'
        assert list(store_path.parent.glob(".local_store.json.*.tmp")) == []
