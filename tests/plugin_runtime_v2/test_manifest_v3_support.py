"""把 Manifest 版本门从 v2 升到 **v2 + v3**：三个自带插件能过校验，而真坏的 manifest 仍被拒。

## 为什么
宿主校验器只收 `manifest_version = 2`（`manifest_validator.py` 的 `SUPPORTED_MANIFEST_VERSIONS`），
而**树里自带的三个插件与文档全写 3**（`plugins/*/_manifest.json`、`mai-docs/trirole_spec.md`）
⇒ 插件在 manifest 校验就被拒（且 `webui/routers/plugin/management.py` 只查字段在不在、不看值
⇒ **面板能显示、运行时一加载就拒**）。本件按 lead 裁定 (甲)：**把门升到 3**，并修 napcat 的
manifest 文件名（`manifest.json` → `_manifest.json`，loader 只认带下划线的名字）。

## 判据（lead 2026-10-17 定）
- **(甲)** 树内三个插件都能过 manifest 校验（**不是**"面板能显示"）；
- **(乙)** ⛔ **反向自检**：合成一个真坏的 manifest ⇒ **仍必须被拒**（别为了让它过而把门拆了）。

## 覆盖边界（如实）
本文件验到**校验器**这一层（`ManifestValidator.load_from_plugin_path`）；三个插件**跑起来**还过别的门
（如 hello_world 自己声明 `sdk.min_version = 4.0.0`，而本机 venv 的 SDK 是 2.13.0
⇒ 那是**它自己的意图**与本地 SDK 版本的关系，不是本件能改的）。
"""
import json
from pathlib import Path

import pytest

from src.plugin_runtime.runner.manifest_validator import ManifestValidator


REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_PLUGINS = ("hello_world_plugin", "maibot-team.v1-compat", "maibot-team.napcat-adapter")


def _valid_v3(**overrides) -> dict:
    """一个**最小且合法**的 v3 manifest（三个自带插件的公共字段）。"""
    payload = {
        "manifest_version": 3,
        "id": "e2e.manifest-demo",
        "version": "1.0.0",
        "name": "E2E manifest demo",
        "description": "v3 最小形状",
        "scopes": ["message:send:text"],
    }
    payload.update(overrides)
    return payload


def test_v3_minimal_manifest_is_accepted() -> None:
    """v3 的最小形状（无 license/urls/host_application/sdk/i18n）必须过得去。"""
    validator = ManifestValidator()
    manifest = validator.parse_manifest(_valid_v3())

    assert manifest is not None, f"v3 最小形状被拒：{validator.errors}"
    assert manifest.id == "e2e.manifest-demo"
    # scopes 归一进 capabilities（下游只认一套字段）
    assert manifest.capabilities == ["message:send:text"], manifest.capabilities
    assert manifest.manifest_version == 2, "归一后应标成 v2 形状（下游口径）"


@pytest.mark.parametrize("plugin_dir_name", BUNDLED_PLUGINS)
def test_bundled_plugin_passes_manifest_validation(plugin_dir_name: str) -> None:
    """**(甲)** 树内自带插件必须过 manifest 校验（含 napcat 的 `_manifest.json` 文件名）。"""
    plugin_path = REPO_ROOT / "plugins" / plugin_dir_name
    assert plugin_path.is_dir(), plugin_path
    assert (plugin_path / "_manifest.json").is_file(), (
        f"{plugin_dir_name} 缺 `_manifest.json`（loader 只认带下划线的名字"
        "；如该插件只写了 manifest.json，就是本件要修的那一处）"
    )

    validator = ManifestValidator()
    manifest = validator.load_from_plugin_path(plugin_path)
    if manifest is None:
        # hello_world 这类**自己声明了 SDK/Host 下界**的插件会被 runtime 兼容性检查拦下：
        # 那是它的声明与**本地 SDK 版本**的关系，不是 manifest 形状问题 ⇒ 如实区分，别混成一句。
        version_only = [error for error in validator.errors if "版本不兼容" in error]
        assert version_only == validator.errors, (
            f"{plugin_dir_name} 的失败不含版本声明问题（= manifest 形状仍需修）：{validator.errors}"
        )
        pytest.skip(f"{plugin_dir_name}: 形状通过，被自身声明的版本下界拦下（本地 SDK/Host 版本低于其声明）：{version_only}")
    assert manifest.id.startswith(("maibot-team.", "e2e.")), manifest.id


@pytest.mark.parametrize(
    ("payload", "label"),
    [
        (_valid_v3(manifest_version=4), "版本 4（门之外）"),
        (_valid_v3(id="X Y"), "非法 id"),
        (_valid_v3(version="1.0"), "非三段式版本"),
        (_valid_v3(name=""), "空 name"),
        (_valid_v3(scopes=["ok", ""]), "scopes 空项"),
        (_valid_v3(typo_field=1), "未知字段"),
        (_valid_v3(id=123), "id 不是字符串"),
    ],
)
def test_broken_manifest_is_still_rejected(payload: dict, label: str) -> None:
    """**(乙)** 反向自检：真坏的 manifest 必须被拒（门升 3 不等于拆门）。"""
    validator = ManifestValidator()
    manifest = validator.parse_manifest(payload)
    assert manifest is None, f"{label} 竟然通过了 ⇒ 门被拆了：{payload!r}"
    assert validator.errors, f"{label} 被拒但没留原因 ⇒ 静默拒绝"


@pytest.mark.parametrize("field_name", ["name", "description", "id"])
def test_v3_identity_fields_still_must_be_non_empty(field_name: str) -> None:
    """**身份三件不放宽**：v3 可把 `license`/`urls` 留着不写，但 `name`/`description`/`id` 留空必须拒。

    配 ⑤ 的裁定：v3 的放宽是"**有意放宽、仅 v3、只放宽内容、不放宽在位**"；
    这条专钉**没有**把身份字段一起放掉（否则"门升 3"就变成"拆门"）。
    """
    validator = ManifestValidator()
    manifest = validator.parse_manifest(_valid_v3(**{field_name: ""}))

    assert manifest is None, f"v3 的 {field_name} 留空竟然通过了 ⇒ 身份三件被放宽了"
    assert validator.errors, f"{field_name} 被拒但没留原因 ⇒ 静默拒绝"


def test_v3_may_omit_license_and_urls_without_placeholder() -> None:
    """⑤ 裁定的正面：**未声明** `license` / `urls` ⇒ 过，且归一为**空串而不是占位符**。"""
    validator = ManifestValidator()
    manifest = validator.parse_manifest(_valid_v3())

    assert manifest is not None, f"v3 未声明 license/urls 应当放行：{validator.errors}"
    assert manifest.license == "", f"未声明应归一为空串（不是占位值）：{manifest.license!r}"
    assert manifest.urls.repository == "", f"未声明应归一为空串（不是占位值）：{manifest.urls.repository!r}"


def test_v2_manifest_still_accepted_and_v3_shape_does_not_leak() -> None:
    """v2 那套**不动**（严格性不减）：完整 v2 manifest 仍过，且缺必填字段的 v2 仍被拒。"""
    v2_payload = json.loads(
        (REPO_ROOT / "plugins" / "hello_world_plugin" / "_manifest.json").read_text(encoding="utf-8")
    )
    v2_payload["manifest_version"] = 2
    v2_payload["host_application"] = {"min_version": "0.0.1", "max_version": "9999.0.0"}
    v2_payload["sdk"] = {"min_version": "0.0.1", "max_version": "9999.0.0"}
    v2_payload["capabilities"] = v2_payload.pop("scopes")
    v2_payload["i18n"] = {"default_locale": "zh_CN"}

    validator = ManifestValidator()
    assert validator.parse_manifest(v2_payload) is not None, f"v2 完整形状被拒：{validator.errors}"

    broken_v2 = dict(v2_payload)
    broken_v2.pop("i18n")
    strict = ManifestValidator()
    # v2 的 i18n 是**必填**（v3 才可省）⇒ 少了它必须红（证明 v2 的严格性没被 v3 的放宽带走）
    assert strict.parse_manifest(broken_v2) is None, "v2 少 i18n 竟然过了 ⇒ v2 的严格性被 v3 放宽带走了"
