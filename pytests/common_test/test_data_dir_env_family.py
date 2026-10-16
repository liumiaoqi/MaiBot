"""data-family ⑥：`MAIBOT_DATA_DIR` 全家族**对账**（正向 + 反向 + 负控 + 两列 + env 复原）。

判据（lead 派单 ⑥）：

- **正向**：临时设 `MAIBOT_DATA_DIR=<tmp>` ⇒ **逐站点**断言"解析值前缀 == `<tmp>` **且与未设时不同**"；
- **反向**：**非 data 域**（logs / prompts / config / 仓根）**必须不跟动**；
- **负控**：合成"某站点没跟动"或"非 data 域被带走"的状态 ⇒ 判据**必须红**（证明它红得起来）；
- **两列**：每个站点报 **未设 / 设了** 两个值；
- **复原**：跑完 env 必须回到原值，并且**显式断言**已复原。

⚠️ 口径说明（为什么站点分两类，别把它读成"漏了一半"）：

- **A 类 · 可重复求值**（函数 / 工厂 / 属性）：每次调用都重新读 env ⇒ 本用例直接断言，
  这是本文件的主体；
- **B 类 · import 期常量**（如 `webui.routers.system._DATA_DIR`）：值在**导入时**就定死，
  设了 env 也不会变 —— 本用例**不重载模块**（重载有副作用），
  它们的"未设 env 时 == 唯一来源"由绊线 `pytests/common_test/test_data_root_convergence.py`
  的 `test_site_takes_root_from_single_source` 覆盖。两者合起来才是全家族。

⚠️ 另一条与本文件互补的**源码级**断言：`scripts/**` 里不许再有"自推 data 路径"
（`PROJECT_ROOT / "data"`、`os.path.join(PROJECT_ROOT, "data", …)`）—— ⑤ 的站点在那边，
那些脚本不适合 import（有 CLI 主流程），故用源码级咬。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, NamedTuple

import pytest

from src.common.runtime_paths import DATA_DIR_ENV, resolve_data_file, resolve_data_root, resolve_project_root
from src.A_memorix.paths import default_data_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


class Site(NamedTuple):
    """一个**可重复求值**的站点：标签 + 取值 + 期望它跟动还是不跟动。"""

    label: str
    probe: Callable[[], str]
    follows_data_root: bool


def _live_sites() -> list[Site]:
    """构造站点清单（在用例内调用：这些 import 都要等 env 设好之后再取值）。"""

    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel
    from src.A_memorix.core.utils.web_import_manager import ImportTaskManager
    from src.maisaka.replyer.expression_vector_index import resolve_project_path
    from src.plugin_runtime.runner.manifest_validator import ManifestValidator
    from src.plugin_runtime_v2.host.storage_service import PerPluginStorage
    from src.plugin_runtime_v2.scope.approval_store import ScopeApprovalStore

    class _StubPlugin:
        def get_config(self, _key: str, default: object = None) -> object:
            return "data/a-memorix"

    def _import_task_data_dir() -> str:
        manager = ImportTaskManager.__new__(ImportTaskManager)
        manager.plugin = _StubPlugin()
        return str(manager._resolve_data_dir())

    return [
        # ── 正向：data 域，必须跟动 ─────────────────────────────────
        Site("runtime_paths.resolve_data_root()", lambda: str(resolve_data_root()), True),
        Site('resolve_data_file("MaiBot.db")', lambda: str(resolve_data_file("MaiBot.db")), True),
        Site("A_memorix.paths.default_data_dir()", lambda: str(default_data_dir()), True),
        Site(
            '④ resolve_project_path("data/expression_selection/x.json")',
            lambda: str(resolve_project_path("data/expression_selection/x.json")),
            True,
        ),
        Site("PerPluginStorage()._base_dir", lambda: str(PerPluginStorage()._base_dir), True),
        Site("ScopeApprovalStore()._file_path", lambda: str(ScopeApprovalStore()._file_path), True),
        Site(
            "SDKMemoryKernel(...).data_dir",
            lambda: str(
                SDKMemoryKernel(
                    plugin_root=Path("."), config={"storage": {"data_dir": "data/a-memorix"}}
                ).data_dir
            ),
            True,
        ),
        Site("ImportTaskManager._resolve_data_dir()", _import_task_data_dir, True),
        # ── 反向：非 data 域，必须**不**跟动 ─────────────────────────
        Site("runtime_paths.resolve_project_root()", lambda: str(resolve_project_root()), False),
        Site('resolve_project_root() / "config"', lambda: str((resolve_project_root() / "config").resolve()), False),
        Site(
            "ManifestValidator._resolve_project_root()",
            lambda: str(ManifestValidator._resolve_project_root()),
            False,
        ),
    ]


def _is_under(value: str, root: Path) -> bool:
    """`value` 是否落在 `root` 下（负控要用的**判据本身**）。"""

    try:
        Path(value).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def test_data_domain_sites_follow_temp_data_dir(tmp_path: Path) -> None:
    """⑥ 正向 + 反向 + 两列 + env 复原（一个用例把四件事一起报，避免彼此漏项）。"""

    before = os.environ.get(DATA_DIR_ENV)
    unset_column: dict[str, str] = {}
    os.environ.pop(DATA_DIR_ENV, None)
    for site in _live_sites():
        unset_column[site.label] = site.probe()

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(DATA_DIR_ENV, str(tmp_path))
        print(f"\n临时数据根 = {tmp_path}")
        print(f"{'站点':<54} {'未设 env':<58} 设了 env")
        print("-" * 150)

        for site in _live_sites():
            now = site.probe()
            unset = unset_column[site.label]
            print(f"{site.label:<54} {unset:<58} {now}")
            if site.follows_data_root:
                assert _is_under(now, tmp_path), f"{site.label} 没跟动：{now} 不在 {tmp_path} 下"
                assert now != unset, f"{site.label} 跟动了但值与未设时相同（判据失效）：{now}"
            else:
                assert not _is_under(now, tmp_path), f"{site.label} 是非 data 域却被带走了：{now}"
                assert now == unset, f"{site.label} 是非 data 域但值变了：未设={unset} 设了={now}"

    # 复原断言（monkeypatch 会还原；这里**显式**再断言一次，免得改了写法就悄悄漏）
    assert os.environ.get(DATA_DIR_ENV) == before, (
        f"{DATA_DIR_ENV} 没复原：before={before!r} now={os.environ.get(DATA_DIR_ENV)!r}"
    )


def test_negative_control_forward_predicate_can_go_red(tmp_path: Path) -> None:
    """负控①：**"某站点没跟动"的状态必须被判据判红**（用旧写法的取值当样本）。"""

    stale = [
        # 旧写法：自推仓根 + data（⑤ 修之前 `_bootstrap` 的形状）
        str((REPO_ROOT / "data" / "MaiBot.db").resolve()),
        # 旧写法：A_memorix 自推根
        str((REPO_ROOT / "data" / "plugins" / "a-dawn.a-memorix").resolve()),
    ]
    for value in stale:
        assert not _is_under(value, tmp_path), f"负控失效：{value} 竟被判为落在 {tmp_path} 下"
    # 正样本（真跟动）必须判真 —— 否则上面两条"判假"毫无意义
    assert _is_under(str(tmp_path / "MaiBot.db"), tmp_path)


def test_negative_control_reverse_predicate_can_go_red(tmp_path: Path) -> None:
    """负控②：**"非 data 域被带走"的状态必须被判据判红**。"""

    dragged = [str(tmp_path / "config"), str(tmp_path / "logs"), str(tmp_path / "prompts")]
    for value in dragged:
        assert _is_under(value, tmp_path), f"负控失效：{value} 竟没被判为落在 {tmp_path} 下"
    # 真·非 data 域（仓根）必须判假
    assert not _is_under(str(resolve_project_root()), tmp_path)


_SELF_DERIVED_DATA_PATTERNS = (
    # ⑤ 的形状：仓根常量 + 字面量 "data" 拼出来的路径
    re.compile(r"""PROJECT_ROOT\s*/\s*["']data["']"""),
    re.compile(r"""os\.path\.join\(\s*PROJECT_ROOT\s*,\s*["']data["']"""),
)


def _self_derived_data_hits(source: str) -> list[str]:
    """源码里"自推 data 路径"的行（负控要用同一个判据函数）。

    ⚠️ **跳过注释行**：⑤ 的修复会**在注释里引用旧写法**（说明为什么改），
    不跳注释就会把"解释"当成"违规" —— 那是扫描器的假阳性，不是代码的错。
    （同款口径：`C:\\hub\\.scratch\\data-family-batch5-site3-host-import.py` 的 `code1` 那行。）
    """

    return [
        line.strip()
        for line in source.splitlines()
        if not line.lstrip().startswith("#") and any(p.search(line) for p in _SELF_DERIVED_DATA_PATTERNS)
    ]


def test_scripts_have_no_self_derived_data_path() -> None:
    """⑤ 的源码级咬合：`scripts/**` 与 `src/A_memorix/scripts/**` 不许再自推 data 路径。"""

    targets = sorted(
        [*REPO_ROOT.glob("scripts/*.py"), *REPO_ROOT.glob("src/A_memorix/scripts/*.py")]
    )
    assert targets, "一个脚本都没扫到 —— 扫描器自己瞎了（扫描失败不许当通过）"

    hits: list[str] = []
    for path in targets:
        for line in _self_derived_data_hits(path.read_text(encoding="utf-8")):
            hits.append(f"{path.relative_to(REPO_ROOT)}: {line}")
    assert hits == [], "又出现自推 data 路径（去用 src/common/runtime_paths.py）：\n" + "\n".join(hits)


def test_negative_control_source_scanner_can_go_red() -> None:
    """负控③：合成一份自推 data 路径 ⇒ 源码级判据必须红。"""

    bad = 'DB = PROJECT_ROOT / "data" / "MaiBot.db"\nOUT = os.path.join(PROJECT_ROOT, "data", "emoji_registered")\n'
    hits = _self_derived_data_hits(bad)
    assert len(hits) == 2, f"自推样本没被扫到：{hits}"
    assert _self_derived_data_hits('DB = resolve_data_file("MaiBot.db")\n') == []
