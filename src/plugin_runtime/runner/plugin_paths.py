"""插件运行时路径分配。

插件只能拿到由运行时授予的目录，不允许自行声明或拼接宿主根目录。
"""

from dataclasses import dataclass
from pathlib import Path

import re


_PLUGIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)+$")


@dataclass(frozen=True)
class PluginPaths:
    """插件可使用的运行时路径。"""

    data_dir: Path
    runtime_dir: Path


def ensure_child_path(path: Path, root: Path) -> Path:
    """解析路径并确保它没有逃逸出给定根目录。"""

    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"插件路径逃逸: {resolved_path}")
    return resolved_path


def validate_plugin_id_for_path(plugin_id: str) -> str:
    """校验插件 ID 可安全作为单级目录名使用。"""

    normalized_plugin_id = str(plugin_id or "").strip()
    if not _PLUGIN_ID_PATTERN.fullmatch(normalized_plugin_id):
        raise ValueError(f"非法插件 ID: {plugin_id}")
    if "/" in normalized_plugin_id or "\\" in normalized_plugin_id:
        raise ValueError(f"插件 ID 不能包含路径分隔符: {plugin_id}")
    if any(part in {"", ".", ".."} for part in Path(normalized_plugin_id).parts):
        raise ValueError(f"插件 ID 不能包含路径跳转片段: {plugin_id}")
    return normalized_plugin_id


def build_plugin_paths(plugin_id: str, project_root: Path, data_root: Path | None = None) -> PluginPaths:
    """为插件分配持久数据目录和非持久运行时目录。

    :param project_root: 项目根 —— 只用于 ``temp/`` 这类**非数据**用途。
    :param data_root: 数据根。留空 ⇒ 回落 ``project_root / "data"``（保持既有调用方/测试语义不变）；
        生产调用方（``runner_main``）显式传 ``resolve_data_root()``，让插件**数据**跟着唯一来源走
        （`MAIBOT_DATA_DIR` 生效时与主库同根，不再各拼一次 "data"）。
    """

    safe_plugin_id = validate_plugin_id_for_path(plugin_id)
    data_base = data_root if data_root is not None else project_root / "data"
    plugins_data_root = (data_base / "plugins").resolve()
    runtime_root = (project_root / "temp" / "plugins").resolve()
    plugins_data_root.mkdir(parents=True, exist_ok=True)
    runtime_root.mkdir(parents=True, exist_ok=True)

    data_dir = ensure_child_path(plugins_data_root / safe_plugin_id, plugins_data_root)
    runtime_dir = ensure_child_path(runtime_root / safe_plugin_id, runtime_root)
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return PluginPaths(data_dir=data_dir, runtime_dir=runtime_dir)
