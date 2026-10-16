"""P1③：`manifest.sdk.min_version` 的**装载期比对**（v1 有、v2 搬家时漏掉的守卫）。

这一条对的是哪个洞：`src/plugin_runtime_v2/**` 里 `sdk.min_version` **零读者**（全扫 0 命中），
而 v1 是有守卫的（`src/plugin_runtime/manifest_validator.py:1067` 送 `is_in_range`）——
又一个"声明了但没人校"的字段，与 `declaration` 校不到、`metadata` 传不过来同族。

判据门（本任务特有）＝ **一发一收**：
- **声明 ≥ 宿主支持上界 ⇒ 必须被拒，且具名**（要求值 / 实际值都要在消息里）；
- **声明 = 宿主支持下界 ⇒ 必须通过**。

外加两条：**方向性**（低于下界**不拒** —— 宿主更新就能满足最小要求）、
**具名回落**（manifest 没写这个键 ⇒ 按宿主下界处理并出声，且要能与"显式写了 4.0.0"区分）。

## ⚠️ 意图变更（2026-10-17 `version-floor-soften` 线 · lmq 裁）—— 读到这里的人别把它当回归
- **旧意图**：*"声明了要更高 SDK ⇒ 拒"*（当时把**号段**当兼容判据）；
- **新意图**：**"我们根本没法用版本号定兼容性"** —— 号段与生态脱节（宿主自报 `0.1.0`、
  SDK 区间 `[4.0.0, 5.0.0)`，而插件普遍写 `1.x–1.99.99` / `4.0.0`）；
  ⇒ **下界只作提示、不作门**：越上界但**同主版本** ⇒ **具名 warning + 放行**；
  **跨主版本**（= 显式声明的不兼容）⇒ **仍拒**；
  ⇒ 判据根 = **manifest 可解析 + 所需 API 在位 + 起得来**，不是号段比较。
- **故本文件的期望随之改**：原"收"用例拿 `5.0.0`（与上界 `5.0.0` **同主版本**）当样本 ⇒ 现在应当**放行**，
  样本已换成 **`6.0.0`（跨主版本）**；同主版本那一格**新立一条用例**（必须看到**具名 warning**）。
"""

import asyncio
import json
from pathlib import Path

import pytest

from src.plugin_runtime_v2.host.runner_spawner import (
    RunnerSpawner,
    RunnerSpawnerConfig,
    SDKVersionRequirementUnsatisfied,
    _check_manifest_sdk_min_version,
)


def _write_manifest(tmp_path: Path, payload: dict) -> str:
    (tmp_path / "_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return str(tmp_path)


def _with_sdk_min(tmp_path: Path, value: object) -> str:
    return _write_manifest(
        tmp_path,
        {"id": "probe.plugin", "version": "1.0.0", "sdk": {"min_version": value}},
    )


# ── 一发一收（本任务的鉴别力判据）────────────────────────────────────────────


def test_declared_min_above_host_ceiling_in_another_major_is_rejected(tmp_path: Path) -> None:
    """**收（跨主版本）**：声明**跨主版本**地高于宿主可提供版本的 `min_version` ⇒ 仍必须被拒，且**具名**。

    ⚠️ 2026-10-17（`version-floor-soften`）：本条原本拿 `5.0.0` 当样本，而它与宿主上界 `5.0.0`
    **同主版本** ⇒ 按新判据（下界只作提示）应当**放行** ⇒ 样本已换成 **`6.0.0`（跨主版本）**；
    意图不变：**显式声明的不兼容仍拒**。
    """

    reason = _check_manifest_sdk_min_version(_with_sdk_min(tmp_path, "6.0.0"), "r1")

    assert reason is not None, "声明 6.0.0（跨主版本且 ≥ 宿主上界）却放过了 —— 守卫没生效"
    assert "6.0.0" in reason, f"具名消息里没有**要求值**：{reason}"
    assert "4.0.0" in reason and "5.0.0" in reason.split("宿主支持")[-1], (
        f"具名消息里没有**宿主支持区间**（实际值）：{reason}"
    )
    assert reason.startswith("SDK_MIN_VERSION_UNSATISFIED")
    assert "跨主版本" in reason, f"拒因没写清是'跨主版本的不兼容'：{reason}"


def test_declared_min_same_major_above_ceiling_is_named_but_allowed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """**（新判据）同主版本越上界 ⇒ 只出声、不拒** —— 号段不作门，兼容性靠 capability。

    旧意图："声明了要更高 SDK ⇒ 拒"；新意图（lmq 裁）：**我们根本没法用版本号定兼容性**。
    ⚠️ 必须能看见那条**具名 warning** —— 别把"降级"做成"静默"。
    """

    with caplog.at_level("WARNING"):
        reason = _check_manifest_sdk_min_version(_with_sdk_min(tmp_path, "5.0.0"), "r1")

    assert reason is None, f"同主版本越上界被拒了（新判据要求放行）：{reason}"
    messages = [r.getMessage() for r in caplog.records]
    assert any("5.0.0" in m and "兼容模式" in m for m in messages), f"没有具名 warning：{messages}"


def test_declared_min_equal_host_floor_passes(tmp_path: Path) -> None:
    """**发**：声明宿主支持下界（4.0.0）⇒ 必须通过。"""

    assert _check_manifest_sdk_min_version(_with_sdk_min(tmp_path, "4.0.0"), "r1") is None


def test_declared_min_below_host_floor_still_passes(tmp_path: Path) -> None:
    """**方向性**：`min_version` 是**最小**要求 ⇒ 宿主更新就能满足它，**低于下界不拒**。

    若这条红了，说明有人把守卫写成了"严格区间 [min,max)"——那会让旧插件成批坏掉
    （真例：`plugins/hello_world_plugin/_manifest.json` 声明 `4.0.0`）。
    """

    assert _check_manifest_sdk_min_version(_with_sdk_min(tmp_path, "1.0.0"), "r1") is None


def test_unparsable_declared_min_is_fail_closed(tmp_path: Path) -> None:
    """写了却解析不了 ⇒ fail-closed（"声明了但不可判"不许当通过）。"""

    reason = _check_manifest_sdk_min_version(_with_sdk_min(tmp_path, "not-a-version"), "r1")

    assert reason is not None and "UNPARSABLE" in reason, f"不可解析却被放过：{reason}"


# ── 具名回落（兼容性）──────────────────────────────────────────────────────


def test_missing_key_is_named_fallback(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """旧插件**没写** `sdk.min_version` ⇒ 按宿主下界处理，但**必须出声**（不许静默）。"""

    plugin_dir = _write_manifest(tmp_path, {"id": "probe.plugin", "version": "1.0.0"})

    with caplog.at_level("INFO"):
        assert _check_manifest_sdk_min_version(plugin_dir, "r1") is None

    messages = [r.getMessage() for r in caplog.records]
    assert any("未声明 sdk.min_version" in m for m in messages), f"缺具名回落日志：{messages}"


def test_explicit_floor_is_distinguishable_from_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """**"没写" 与 "写了 4.0.0" 必须可区分**（否则第 4 条的"具名回落"无从谈起）。"""

    plugin_dir = _with_sdk_min(tmp_path, "4.0.0")

    with caplog.at_level("INFO"):
        assert _check_manifest_sdk_min_version(plugin_dir, "r1") is None

    messages = [r.getMessage() for r in caplog.records]
    assert not any("未声明 sdk.min_version" in m for m in messages), (
        f"显式写了 4.0.0 却被当成「未声明」：{messages}"
    )


# ── 落到"拒装载"（不落进程）────────────────────────────────────────────────


def test_spawn_refuses_to_launch_runner_when_unsatisfied(tmp_path: Path) -> None:
    """守卫要真的**拦在 spawn 上**：不满足 ⇒ 抛具名异常，且**不创建进程**。

    ⚠️ 本条用 `9.9.9` —— 与宿主上界 `5.0.0` **跨主版本** ⇒ 新判据下**仍然拒** ✓
    （同主版本那一格见 `test_declared_min_same_major_above_ceiling_is_named_but_allowed`）。
    """

    plugin_dir = _with_sdk_min(tmp_path, "9.9.9")
    spawner = RunnerSpawner(host_listen_address="127.0.0.1:0", config=RunnerSpawnerConfig())

    with pytest.raises(SDKVersionRequirementUnsatisfied) as excinfo:
        asyncio.run(spawner.spawn("r1", plugin_dir))

    assert "9.9.9" in str(excinfo.value), f"异常消息里没有要求值：{excinfo.value}"
    assert spawner._processes == {}, "被拒了却还是落了进程 —— 拒装载没拦住"
