"""`src/common/runtime_paths` 的契约测试（数据根的唯一来源）。

守三件事：
1. **缺省推导**：`resolve_data_root()` == `resolve_project_root() / "data"` —— 这是"全仓唯一
   的 `__file__` 推导点"，容器与宿主都靠它（容器内实测 `/MaiMBot/data`，宿主上 `<仓根>/data`）。
2. **显式覆盖**：`MAIBOT_DATA_DIR` 优先；**相对值按仓根解释**（不许随 CWD 漂 —— 旧写法
   `Path("data/deepseek_cost.db")` 正是随 CWD 漂，才长出第二个数据根）。
3. **推导深度**：本文件若被搬家而 `parents[N]` 没跟着改，第 1 条会立刻红。
"""

import os
from pathlib import Path

import pytest

from src.common import runtime_paths


def test_default_root_is_project_root_over_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(runtime_paths.DATA_DIR_ENV, raising=False)
    assert runtime_paths.resolve_data_root() == (runtime_paths.resolve_project_root() / "data").resolve()


def test_derivation_depth_matches_file_location() -> None:
    """守卫：`resolve_project_root()` 必须真的等于本模块所在位置的仓根。

    搬动本文件（`src/common/runtime_paths.py` → 别处）而不改 `parents[2]` ⇒ 本用例立刻红。
    """
    module_path = Path(runtime_paths.__file__).resolve()
    assert module_path.parent == runtime_paths.resolve_project_root() / "src" / "common"
    assert module_path.parents[2] == runtime_paths.resolve_project_root()


def test_absolute_env_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(runtime_paths.DATA_DIR_ENV, str(tmp_path))
    assert runtime_paths.resolve_data_root() == tmp_path.resolve()


def test_relative_env_override_anchors_at_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """相对值按**仓根**解释（而不是 CWD）——否则又变成"随谁启动就落到哪"。"""
    monkeypatch.setenv(runtime_paths.DATA_DIR_ENV, "data/MaiMBot")
    assert runtime_paths.resolve_data_root() == (runtime_paths.resolve_project_root() / "data" / "MaiMBot").resolve()


def test_data_file_joins_under_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(runtime_paths.DATA_DIR_ENV, raising=False)
    assert runtime_paths.resolve_data_file("MaiBot.db") == runtime_paths.resolve_data_root() / "MaiBot.db"
    assert runtime_paths.resolve_data_file("a", "b.db") == runtime_paths.resolve_data_root() / "a" / "b.db"


def test_host_side_alternate_root_detects_marker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """宿主侧信号：data 根下有 `MaiMBot/` 子目录（容器内不存在）。没有该子目录 ⇒ None。"""
    monkeypatch.setenv(runtime_paths.DATA_DIR_ENV, str(tmp_path))
    assert runtime_paths.resolve_host_side_alternate_root() is None
    (tmp_path / "MaiMBot").mkdir()
    assert runtime_paths.resolve_host_side_alternate_root() == tmp_path / "MaiMBot"


def test_describe_reports_the_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(runtime_paths.DATA_DIR_ENV, str(tmp_path))
    described = runtime_paths.describe_data_root()
    assert runtime_paths.DATA_DIR_ENV in described and str(tmp_path.resolve()) in described


def test_module_imports_nothing_from_src() -> None:
    """本模块必须**零 src 依赖**（要能在 `bot.py` 的 tz 修正之前、极早被导入）。"""
    source = Path(runtime_paths.__file__).read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import src", "from src"))
    ]
    assert not offenders, f"runtime_paths 不得依赖 src.*（否则可能成环/过晚可用）：{offenders}"


def test_env_var_name_is_stable() -> None:
    assert runtime_paths.DATA_DIR_ENV == "MAIBOT_DATA_DIR"
    assert os.environ.get("__never_set__") is None  # 占位：确认本用例不依赖外部环境
