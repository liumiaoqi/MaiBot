"""data-root 收敛**绊线**（批 1–3）：谁再自推 data 根，这里就红。

判据：每个收敛点的值必须等于**唯一来源**算出来的值（`resolve_data_root()` / `resolve_data_file(...)` /
`resolve_project_root()`）。

⚠️ **本文件红了意味着**：有人（或某次重构）又把 `Path(__file__).parents[N] / "data"`、
`.parent.parent.parent / "data"`、`Path("data/…")` 这类**自推**写回来了 —— 去用
`src/common/runtime_paths.py`，**不要在这一层加豁免**（口径见 `C:\\hub\\.scratch\\data-root-family-inventory.md`）。

口径说明：
- 只断言**根从哪来**，不断言用途：`logs/`、`prompts/` 这些仍从 `PROJECT_ROOT` 派生，属另一域；
- **不设也不假设** `MAIBOT_DATA_DIR`（它要等全家族收敛完才敢用于生产）：断言写成"与唯一来源一致"，
  所以将来设了 env 也自然成立；
- 一个文件里两处推根就有两条断言（按**站点**而不是按文件）。
"""

import importlib
import inspect
import re
import shutil
from pathlib import Path

import pytest

from src.common.runtime_paths import resolve_data_file, resolve_data_root, resolve_project_root

# (模块名, 常量/访问点, 期望来源, 参数)
# 期望来源：data_root / project_root / data_file(parts)
SINGLE_SOURCE_CASES: list[tuple[str, str, str, tuple[str, ...]]] = [
    # ── 批 1：src/webui/** ────────────────────────────────────────────────
    ("src.webui.routers.system", "_PROJECT_ROOT", "project_root", ()),
    ("src.webui.routers.system", "_DATA_DIR", "data_root", ()),
    ("src.webui.routers.system", "_IMAGE_DIR", "data_file", ("images",)),
    ("src.webui.routers.system", "_EMOJI_DIR", "data_file", ("emoji",)),
    ("src.webui.routers.system", "_EMOJI_THUMBNAIL_DIR", "data_file", ("emoji_thumbnails",)),
    ("src.webui.routers.system", "_DATABASE_FILE", "data_file", ("MaiBot.db",)),
    ("src.webui.routers.reasoning_process", "PROJECT_ROOT", "project_root", ()),
    ("src.webui.routers.reasoning_process", "PROMPT_LOG_ROOT", "project_root_file", ("logs", "maisaka_prompt")),
    ("src.webui.routers.config", "CUSTOM_PROMPTS_DIR", "data_file", ("custom_prompts",)),
    ("src.webui.app", "_get_project_root", "project_root_callable", ()),
    # ── 批 2：emoji / chat / image / prompt ──────────────────────────────
    ("src.emoji_system.emoji_manager", "DATA_DIR", "data_root", ()),
    ("src.emoji_system.emoji_manager", "EMOJI_DIR", "data_file", ("emoji",)),
    ("src.emoji_system.emoji_cache_cleanup", "EMOJI_DIR", "data_file", ("emoji",)),
    ("src.chat.image_system.image_manager", "DATA_DIR", "data_root", ()),
    ("src.chat.image_system.image_manager", "IMAGE_DIR", "data_file", ("images",)),
    ("src.chat.image_system.image_cache_cleanup", "IMAGE_DIR", "data_file", ("images",)),
    ("src.common.prompt_i18n", "PROJECT_ROOT", "project_root", ()),
    ("src.common.prompt_i18n", "CUSTOM_PROMPTS_ROOT", "data_file", ("custom_prompts",)),
    ("src.prompt.prompt_manager", "PROJECT_ROOT", "project_root", ()),
    ("src.prompt.prompt_manager", "DATA_DIR", "data_root", ()),
    ("src.prompt.prompt_manager", "CUSTOM_PROMPTS_DIR", "data_file", ("custom_prompts",)),
    ("src.webui.routers.avatar", "AVATAR_CACHE_ROOT", "data_file", ("avatar",)),
    ("src.webui.routers.memory.import_", "STAGING_ROOT", "data_file", ("memory_upload_staging",)),
    # ── 批 3：plugin_runtime / A_memorix / 配置面（只动常量来源）──────────
    ("src.plugin_runtime.runner.runner_main", "_PROJECT_ROOT", "project_root", ()),
    ("src.plugin_runtime.host.supervisor", "_PROJECT_ROOT", "project_root", ()),
    ("src.config.config", "PROJECT_ROOT", "project_root", ()),
    ("src.config.config", "CONFIG_DIR", "project_root_file", ("config",)),
    ("src.config.startup_bindings", "PROJECT_ROOT", "project_root", ()),
    ("src.config.startup_bindings", "CONFIG_DIR", "project_root_file", ("config",)),
    # ── 批 4：CWD 相对族（旧写法 `Path("data/…")` / `"data/…"`，相对 CWD）──────────
    ("src.webui.services.git_mirror_service", "GitMirrorConfig.CONFIG_FILE", "data_file", ("webui.json",)),
    ("src.webui.routers.emoji.support", "THUMBNAIL_CACHE_DIR", "data_file", ("emoji_thumbnails",)),
    ("src.webui.routers.emoji.support", "EMOJI_REGISTERED_DIR", "data_file", ("emoji",)),
    ("src.webui.routers.emoji.support", "EMOJI_DIR", "data_file", ("emoji",)),
    ("src.webui.services.expression_service_web", "LEGACY_IMPORT_UPLOAD_DIR", "data_file", ("webui_legacy_expression_imports",)),
    ("src.llm_models.model_scanner", "_SCANNED_DB_PATH", "data_file", ("scanned_models.db",)),
    ("src.maisaka.agent_autonomy.reminder", "_DEFAULT_STORE_DIR", "data_file", ("reminders",)),
    ("src.maisaka.migration.coordinator", "_DEFAULT_STORE_PATH", "data_file", ("plugin_migration_states.jsonl",)),
    ("src.manager.local_store_manager", "LOCAL_STORE_FILE_PATH", "data_file", ("local_store.json",)),
    ("src.maisaka.display.preview_path_utils", "REPO_ROOT", "project_root", ()),
    ("src.maisaka.display.prompt_cli_renderer", "DATA_IMAGE_DIR", "data_file", ("images",)),
    ("src.maisaka.display.prompt_cli_renderer", "DATA_EMOJI_DIR", "data_file", ("emoji",)),
    ("src.maisaka.display.prompt_cli_renderer", "DATA_PROMPT_IMAGE_DIR", "data_file", ("prompt_imgs",)),
]

# 被删掉的"自推根"常量：必须**不存在**（谁把它们写回来，这里立刻红）
REMOVED_SELF_DERIVED_ROOTS: list[tuple[str, str]] = [
    ("src.emoji_system.emoji_manager", "PROJECT_ROOT"),
    ("src.emoji_system.emoji_cache_cleanup", "PROJECT_ROOT"),
    ("src.chat.image_system.image_manager", "PROJECT_ROOT"),
    ("src.chat.image_system.image_cache_cleanup", "PROJECT_ROOT"),
    ("src.webui.routers.avatar", "PROJECT_ROOT"),
    ("src.chat.message_receive.bot", "PROJECT_ROOT"),
    # ── 批 6 · ④：表达向量索引的自推根（`Path(__file__).resolve().parents[3]`）────
    ("src.maisaka.replyer.expression_vector_index", "PROJECT_ROOT"),
]


def _expected(source_kind: str, parts: tuple[str, ...]):
    if source_kind == "data_root":
        return resolve_data_root()
    if source_kind == "data_file":
        return resolve_data_file(*parts)
    if source_kind in ("project_root", "project_root_callable"):
        return resolve_project_root()
    if source_kind == "project_root_file":
        return (resolve_project_root() / Path(*parts)).resolve()
    raise AssertionError(f"未知期望来源: {source_kind}")


def _resolve_attribute(module: object, attribute: str):
    """取属性，支持点号路径（如 `GitMirrorConfig.CONFIG_FILE`）。"""

    value: object = module
    for part in attribute.split("."):
        value = getattr(value, part)
    return value


@pytest.mark.parametrize(("module_name", "attribute", "source_kind", "parts"), SINGLE_SOURCE_CASES)
def test_site_takes_root_from_single_source(
    module_name: str, attribute: str, source_kind: str, parts: tuple[str, ...]
) -> None:
    """站点常量 == 唯一来源算出来的值（红了 ⇒ 有人自推根）。"""

    module = importlib.import_module(module_name)
    actual = _resolve_attribute(module, attribute)
    if source_kind == "project_root_callable":  # 站点是一个"取仓根"的函数
        actual = actual()
    expected = _expected(source_kind, parts)

    assert Path(actual) == Path(expected), (
        f"{module_name}.{attribute} 不再来自唯一来源：实际 {actual} ≠ 期望 {expected}"
        "（去用 src/common/runtime_paths.py，别自推 data 根）"
    )


@pytest.mark.parametrize(("module_name", "attribute"), REMOVED_SELF_DERIVED_ROOTS)
def test_self_derived_root_constant_is_gone(module_name: str, attribute: str) -> None:
    """已收敛掉的自推根常量不得复活。"""

    module = importlib.import_module(module_name)

    assert not hasattr(module, attribute), (
        f"{module_name}.{attribute} 又出现了 —— 它已被 data-root 收敛删掉，"
        "别加回来（要用仓根请 import resolve_project_root）"
    )


def test_webui_token_default_path_follows_data_root() -> None:
    """`TokenManager` 的默认配置路径 = 数据根下的 webui.json（批 1 站点，行为式断言）。"""

    from src.webui.core.security import TokenManager

    manager = TokenManager()

    assert manager.config_path == resolve_data_file("webui.json")


# ── 第二条绊线：**定义行**不许自推 ────────────────────────────────────────────
# 为什么还要这一条：上面那条是**值**相等 —— 自推写法今天恰好算出同一个值（未设 env 时），
# 值断言**照过**。定义行断言才咬得住"把 `Path(__file__).parents[N] / "data"` 写回来"这件事。

_SELF_DERIVED_PATTERNS = (
    r"Path\(\s*__file__\s*\)",
    r"os\.path\.(abspath|join)\(\s*os\.path\.dirname\(\s*__file__",
    r"Path\(\s*[\"']data[/\"']",
)


def _definition_rhs(module_path: Path, attribute: str) -> str:
    """取 `attribute = ...` 的右值（跨行赋值取到下一条非空行，够本条判断用）。"""

    lines = module_path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^\s*{re.escape(attribute)}\s*(?::[^=]+)?=\s*(?P<rest>.*)$")
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match is None:
            continue
        rest = match.group("rest").strip()
        if rest.endswith("(") or not rest:
            for follow in lines[index + 1 :]:
                if follow.strip():
                    rest = f"{rest} {follow.strip()}"
                    break
        return rest
    raise AssertionError(f"{module_path} 里找不到 {attribute} 的定义行")


@pytest.mark.parametrize(("module_name", "attribute", "source_kind", "parts"), SINGLE_SOURCE_CASES)
def test_constant_definition_line_does_not_self_derive(
    module_name: str, attribute: str, source_kind: str, parts: tuple[str, ...]
) -> None:
    """定义行的右值必须来自 `resolve_*` 或同文件另一个已收敛常量（红了 ⇒ 有人自推根）。"""

    if source_kind == "project_root_callable":  # 站点是函数，交给行为式断言
        pytest.skip("函数式站点由行为断言覆盖")
    module = importlib.import_module(module_name)
    module_path = Path(inspect.getsourcefile(module) or "")
    if not module_path.is_file():  # 冻结/生成模块：拿不到源码就明说，不静默通过
        pytest.skip(f"拿不到源码：{module_name}")
    rhs = _definition_rhs(module_path, attribute.split(".")[-1])

    allowed_names = {"resolve_data_root", "resolve_data_file", "resolve_project_root"}
    allowed_names |= {name for mod, name, _, _ in SINGLE_SOURCE_CASES if mod == module_name}
    assert any(name in rhs for name in allowed_names), (
        f"{module_name}.{attribute} 的定义行不再引用唯一来源：{rhs!r} —— 去用 "
        "src/common/runtime_paths.py，别自推 data 根"
    )
    for bad_pattern in _SELF_DERIVED_PATTERNS:
        assert re.search(bad_pattern, rhs) is None, (
            f"{module_name}.{attribute} 的定义行又出现了自推写法：{rhs!r}（命中 {bad_pattern}）"
        )


def test_a_memorix_default_data_dir_follows_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """行为式绊线：`default_data_dir()` 必须**跟着 env 走**（自推写法过不了这条）。"""

    monkeypatch.setenv("MAIBOT_DATA_DIR", str(tmp_path))
    from src.A_memorix.paths import default_data_dir

    assert default_data_dir() == (tmp_path / "plugins" / "a-dawn.a-memorix").resolve()


def test_plugin_paths_keeps_legacy_contract_without_data_root(tmp_path: Path) -> None:
    """`build_plugin_paths(pid, project_root)` 的旧契约不变：数据落在 **传入根** 下（测试隔离靠它）。"""

    from src.plugin_runtime.runner.plugin_paths import build_plugin_paths

    paths = build_plugin_paths("probe.legacy-contract", tmp_path)

    assert paths.data_dir == (tmp_path / "data" / "plugins" / "probe.legacy-contract").resolve()
    assert paths.runtime_dir == (tmp_path / "temp" / "plugins" / "probe.legacy-contract").resolve()


def test_plugin_paths_follows_data_root_when_passed() -> None:
    """生产形态：显式传 `resolve_data_root()` ⇒ 插件数据跟唯一来源同根（批 3 站点）。"""

    from src.plugin_runtime.runner.plugin_paths import build_plugin_paths

    probe_id = "probe.data-root-convergence"
    target = resolve_data_file("plugins", probe_id)
    existed = target.exists()
    try:
        paths = build_plugin_paths(probe_id, resolve_project_root(), resolve_data_root())
        assert paths.data_dir == target
    finally:
        # 只清掉本用例自己造的那一份（跑之前已存在就不动）
        if not existed and target.exists():
            shutil.rmtree(target, ignore_errors=True)


def test_a_memorix_default_data_dir_follows_data_root() -> None:
    """A_Memorix 的默认数据目录 = 数据根/plugins/a-dawn.a-memorix（批 3 站点）。"""

    from src.A_memorix.paths import default_data_dir

    assert default_data_dir() == resolve_data_file("plugins", "a-dawn.a-memorix")


def test_manifest_validator_project_root_follows_single_source() -> None:
    """`ManifestValidator._resolve_project_root()` 走唯一来源（批 3 站点，方法式）。"""

    from src.plugin_runtime.runner.manifest_validator import ManifestValidator

    assert ManifestValidator._resolve_project_root() == resolve_project_root()


def test_dependency_pipeline_default_root_follows_single_source() -> None:
    """`PluginDependencyPipeline()` 留空 project_root 时走唯一来源（批 3 站点，实例式）。"""

    from src.plugin_runtime.dependency_pipeline import PluginDependencyPipeline

    assert PluginDependencyPipeline()._project_root == resolve_project_root()


def test_per_plugin_storage_default_dir_follows_data_root() -> None:
    """`PerPluginStorage()` 默认目录 = 数据根/plugin_storage（批 4 站点，构造器默认值）。"""

    from src.plugin_runtime_v2.host.storage_service import PerPluginStorage

    assert PerPluginStorage()._base_dir == str(resolve_data_file("plugin_storage"))


def test_scope_approval_store_default_file_follows_data_root() -> None:
    """`ScopeApprovalStore()` 默认文件 = 数据根/plugin_runtime_v2/scope_approvals.json（批 4 站点）。"""

    from src.plugin_runtime_v2.scope.approval_store import ScopeApprovalStore

    assert ScopeApprovalStore()._file_path == resolve_data_file("plugin_runtime_v2", "scope_approvals.json")


def test_local_store_singleton_uses_single_source() -> None:
    """模块级单例 `local_storage` 的路径 = 数据根/local_store.json（批 4 站点，第二次拼字面量的地方）。"""

    from src.manager.local_store_manager import local_storage

    assert local_storage.file_path == str(resolve_data_file("local_store.json"))


# ── 批 5 · A_memorix `storage.data_dir` 的 4 个消费点 ─────────────────────────
# 与批 1–4 的站点不同：这 4 处消费的是**配置值层的相对串**（不是自推的 `__file__`/CWD），
# 所以绊线要咬两件事（缺一条就咬不住）：
#   ① 设了 `MAIBOT_DATA_DIR` ⇒ 解析值必须落在该根下。旧写法 `resolve_repo_path(...)`
#      按 A_memorix 自己的仓根解析 ⇒ 不跟动（这正是本次修的静默劈叉）。
#   ② 未设 env 且值是 `"data/xxx"` 这类历史形态 ⇒ 必须与"仓根/data/xxx"**逐字同径**
#      （`resolve_data_path` 会剥掉 `data/` 前缀再挂数据根；未设 env 时两条路重合）。
# ⚠️ 一处**已知语义偏离**（裸相对值如 `"a-memorix"`：新口径挂数据根、旧口径挂仓根）——
#    绊线只咬上面两条；偏离的逐条清单见
#    `C:\hub\.scratch\data-family-batch5-site3-host-import.py` 的 E 节。


def _stub_config_plugin(raw: object):
    """只实现 `get_config(key, default)` 的鸭子类型 plugin（真方法要的就是这一个口）。"""

    class _StubPlugin:
        def get_config(self, _key: str, default: object = None) -> object:
            return raw

    return _StubPlugin()


def test_a_memorix_storage_data_dir_sites_follow_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """批 5 站点：`storage.data_dir` 的消费点全部跟着 env 走（`data/` 前缀被剥掉）。"""

    monkeypatch.setenv("MAIBOT_DATA_DIR", str(tmp_path))

    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel
    from src.A_memorix.core.utils.web_import_manager import ImportTaskManager

    # 站点 2：走**真构造函数**
    kernel = SDKMemoryKernel(
        plugin_root=Path("."), config={"storage": {"data_dir": "data/a-memorix"}}
    )
    assert kernel.data_dir == (tmp_path / "a-memorix").resolve()

    # 站点 3 / 4：走**真方法**（`__new__` 绕过 `__init__`，只喂 plugin 桩）
    for raw, expect in (
        ("data/a-memorix", (tmp_path / "a-memorix").resolve()),
        # `"./data"` 解析出来**就是数据根本身** —— 这不是笔误，是既定口径
        # （`resolve_data_path("./data") == resolve_data_root()`）。
        ("./data", tmp_path.resolve()),
        ("data", tmp_path.resolve()),
    ):
        manager = ImportTaskManager.__new__(ImportTaskManager)
        manager.plugin = _stub_config_plugin(raw)
        assert manager._resolve_data_dir() == expect, raw
        assert manager._resolve_temp_root() == expect / "web_import_tmp", raw


def test_a_memorix_storage_data_dir_keeps_legacy_shape_without_env() -> None:
    """未设 env：历史形态 `"data/a-memorix"` 与"仓根/data/a-memorix"**逐字同径**（不许漂）。"""

    from src.A_memorix.core.utils.web_import_manager import ImportTaskManager

    manager = ImportTaskManager.__new__(ImportTaskManager)
    manager.plugin = _stub_config_plugin("data/a-memorix")

    assert manager._resolve_data_dir() == resolve_data_file("a-memorix")


def test_a_memorix_storage_data_dir_empty_falls_back_to_default() -> None:
    """空值/None 仍回落到 `default_data_dir()`（与旧 `fallback=` 语义一字不变）。"""

    from src.A_memorix.core.utils.web_import_manager import ImportTaskManager
    from src.A_memorix.paths import default_data_dir

    for raw in (None, "", "   "):
        manager = ImportTaskManager.__new__(ImportTaskManager)
        manager.plugin = _stub_config_plugin(raw)
        assert manager._resolve_data_dir() == default_data_dir().resolve(), raw


# ── 批 6 · ④ · 表达向量索引的 `expression_vector_index_path` 消费点 ───────────
# 与批 5 同族：消费的是**配置值层的相对串**（不是自推的 `__file__`/CWD），所以要咬三件事：
#   ① 设了 `MAIBOT_DATA_DIR` ⇒ 解析值必须落在该根下（旧实现自推仓根 ⇒ 不跟动 = 本次修的劈叉）；
#   ② 未设 env 且值是 `"data/…"` 历史形态 ⇒ 与"仓根/data/…"**逐字同径**（活配置写的就是这种形状）；
#   ③ **fail-closed**：空/空白 ⇒ 抛 `ValueError`（旧实现静默当"仓根"）。
# ③ 是 ④ **有意引入的行为变更**，单独一条咬住它 —— 没有这条，谁把空值回落加回来都不会红。
# ⚠️ 一处**已知语义偏离**（裸相对值如 `"expression_selection/x.json"`：新口径挂数据根、
#    旧口径挂仓根）—— 绊线只咬上面三条；偏离清单见
#    `C:\hub\.scratch\data-family-batch6-site4-host-import.py` 的 B1 节。


def test_expression_vector_index_path_follows_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """④ 站点：配置值跟 `MAIBOT_DATA_DIR` 走（`data/` 前缀被剥掉）。"""

    monkeypatch.setenv("MAIBOT_DATA_DIR", str(tmp_path))

    from src.maisaka.replyer.expression_vector_index import resolve_project_path

    assert resolve_project_path("data/expression_selection/expression_vector_index.json") == (
        tmp_path / "expression_selection" / "expression_vector_index.json"
    ).resolve()


def test_expression_vector_index_path_keeps_legacy_shape_without_env() -> None:
    """④ 站点：未设 env 时与历史形态（仓根/data/…）逐字同径 —— 活配置写的正是这种形状。"""

    from src.common.runtime_paths import resolve_data_file
    from src.maisaka.replyer.expression_vector_index import resolve_project_path

    assert resolve_project_path(
        "data/expression_selection/expression_vector_index.json"
    ) == resolve_data_file("expression_selection", "expression_vector_index.json")


def test_expression_vector_index_path_empty_is_fail_closed() -> None:
    """④ 的**行为变更**：空/空白 ⇒ `ValueError`（旧实现静默当"仓根"，见该函数 docstring）。"""

    from src.maisaka.replyer.expression_vector_index import resolve_project_path

    for raw in ("", "   ", "\t"):
        with pytest.raises(ValueError):
            resolve_project_path(raw)
