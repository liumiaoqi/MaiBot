import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = CURRENT_DIR.parent
SRC_ROOT = PLUGIN_ROOT.parent
PROJECT_ROOT = SRC_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT
MAIBOT_ROOT = PROJECT_ROOT

for _path in (SRC_ROOT, PROJECT_ROOT, PLUGIN_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from A_memorix.paths import config_path, default_data_dir  # noqa: E402  # 需先完成 sys.path 引导
from src.common.runtime_paths import resolve_data_file  # noqa: E402  # 唯一来源（data 根）

DEFAULT_CONFIG_PATH = config_path()
DEFAULT_DATA_DIR = default_data_dir()
# ⑤：`MaiBot.db` 属 data 域 ⇒ 走唯一来源。
# 旧写法 `PROJECT_ROOT / "data" / "MaiBot.db"` 是**自推 data 路径**：`MAIBOT_DATA_DIR` 一生效，
# 它就指到仓根下的 `data/`（= 宿主侧"多出来的那个库"的上游），而其余站点已经挂到数据根上。
# 未设 env 时两者**逐字同径**（`resolve_data_file("MaiBot.db") == <仓根>/data/MaiBot.db`）。
DEFAULT_DB_PATH = resolve_data_file("MaiBot.db")
