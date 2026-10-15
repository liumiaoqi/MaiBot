"""插件目录 → import 助手（对齐 entrypoint._discover_plugin 的合成包机制）。

插件目录名含 '-' 与 '.'（如 maibot-team.v1-compat），Python 不可直接 import；
产品在 src/plugin_runtime_v2/runner/entrypoint.py::_discover_plugin 中以
manifest.id 生成安全包名（'-'/'.' → '_'）注册为合成包。
本助手复刻"注册"这一步（不加载 plugin.py），供测试 import 插件子模块。
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def import_plugin_module(plugin_dir_name: str, module_name: str) -> Any:
    """把 plugins/<plugin_dir_name> 注册为合成包并 import 其 <module_name> 子模块。

    例：import_plugin_module("maibot-team.v1-compat", "capability_bridge")
        → 返回 maibot_team_v1_compat.capability_bridge 模块对象
    """
    plugin_dir = _PROJECT_ROOT / "plugins" / plugin_dir_name
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = plugin_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    safe = str(manifest["id"]).replace("-", "_").replace(".", "_")

    if safe not in sys.modules:
        parent = str(plugin_dir.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        pkg = types.ModuleType(safe)
        pkg.__path__ = [str(plugin_dir)]
        pkg.__package__ = safe
        pkg.__file__ = str(plugin_dir / "__init__.py")
        sys.modules[safe] = pkg

    return importlib.import_module(f"{safe}.{module_name}")
