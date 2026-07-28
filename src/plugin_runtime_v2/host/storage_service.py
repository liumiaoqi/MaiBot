"""Per-plugin JSON 文件存储服务。"""


import json
import os
from typing import Any

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.host.storage_service")


class PerPluginStorage:
    """Per-plugin JSON 文件存储。

    每个插件一个 JSON 文件：{base_dir}/{plugin_id}.json
    asyncio 单线程无需加锁。
    """

    def __init__(self, base_dir: str = "data/plugin_storage") -> None:
        self._base_dir = base_dir
        self._data: dict[str, dict[str, Any]] = {}
        os.makedirs(base_dir, exist_ok=True)
        self._load_all()

    def get(self, plugin_id: str, key: str, default: Any = None) -> Any:
        return self._data.get(plugin_id, {}).get(key, default)

    def set(self, plugin_id: str, key: str, value: Any) -> None:
        self._data.setdefault(plugin_id, {})[key] = value
        self._save(plugin_id)

    def delete(self, plugin_id: str, key: str) -> bool:
        store = self._data.get(plugin_id, {})
        if key in store:
            del store[key]
            self._save(plugin_id)
            return True
        return False

    def _load_all(self) -> None:
        if not os.path.isdir(self._base_dir):
            return
        for fname in os.listdir(self._base_dir):
            if not fname.endswith(".json"):
                continue
            plugin_id = fname[:-5]
            fpath = os.path.join(self._base_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    self._data[plugin_id] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("加载插件存储失败: %s: %s", plugin_id, e)

    def _save(self, plugin_id: str) -> None:
        fpath = os.path.join(self._base_dir, f"{plugin_id}.json")
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(self._data.get(plugin_id, {}), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("保存插件存储失败: %s: %s", plugin_id, e)
