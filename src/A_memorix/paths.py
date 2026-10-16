from pathlib import Path

from src.common.runtime_paths import resolve_data_file

A_MEMORIX_SYSTEM_ID = "a_memorix"


def package_root() -> Path:
    return Path(__file__).resolve().parent


def src_root() -> Path:
    return package_root().parent


def repo_root() -> Path:
    return src_root().parent


def config_path() -> Path:
    return repo_root() / "config" / f"{A_MEMORIX_SYSTEM_ID}.toml"


def default_data_dir() -> Path:
    """A_Memorix 的默认数据目录 —— 数据根只从唯一来源取（`src/common/runtime_paths.py`）。

    旧写法 `repo_root() / "data" / "plugins" / ...` 是"自己又拼一次 data"：`MAIBOT_DATA_DIR`
    一旦生效，主库会切走而这里仍指旧根（静默劈叉）。本模块仍可被 A_memorix 的独立脚本导入
    （`scripts/_bootstrap.py` 已把仓根放进 `sys.path`）。
    """
    return resolve_data_file("plugins", "a-dawn.a-memorix")


def artifacts_root() -> Path:
    return default_data_dir() / "artifacts"


def schema_path() -> Path:
    return package_root() / "config_schema.json"


def web_root() -> Path:
    return package_root() / "web"


def scripts_root() -> Path:
    return package_root() / "scripts"


def resolve_repo_path(raw_path: str | Path | None, *, fallback: Path | None = None) -> Path:
    if raw_path is None:
        return (fallback or default_data_dir()).resolve()

    raw_value = str(raw_path).strip()
    if not raw_value:
        return (fallback or default_data_dir()).resolve()

    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    return (repo_root() / candidate).resolve()
