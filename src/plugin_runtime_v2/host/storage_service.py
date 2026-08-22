"""Per-plugin JSON 文件存储服务。"""


import json
from pathlib import Path
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
        Path(base_dir).mkdir(parents=True, exist_ok=True)
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
        base = Path(self._base_dir)
        if not base.is_dir():
            return
        for fpath in base.glob("*.json"):
            plugin_id = fpath.stem
            try:
                with fpath.open("r", encoding="utf-8") as f:
                    self._data[plugin_id] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("加载插件存储失败: %s: %s", plugin_id, e)
                # P1: 补 port.report 双通道上报（A23a P1-4）
                try:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    _port = get_error_escalation_port()
                    if _port is not None:
                        _port.report(ErrorLevel.WARN, f"加载插件存储失败: {plugin_id}", exception=e)
                except Exception:
                    pass

    def _save(self, plugin_id: str) -> None:
        fpath = Path(self._base_dir) / f"{plugin_id}.json"
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(self._data.get(plugin_id, {}), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("保存插件存储失败: %s: %s", plugin_id, e)
            # P1: 补 port.report 双通道上报（A23a P1-4）
            try:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                _port = get_error_escalation_port()
                if _port is not None:
                    _port.report(ErrorLevel.ERROR, f"保存插件存储失败: {plugin_id}", exception=e)
            except Exception:
                pass
