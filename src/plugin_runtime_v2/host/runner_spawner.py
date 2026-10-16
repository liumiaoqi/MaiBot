"""Host 端 Runner 子进程管理器。"""


import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.plugin_runtime_v2.scope.token_service import TokenService

logger = get_logger("plugin_runtime_v2.host.runner_spawner")


@dataclass
class RunnerSpawnerConfig:
    """Runner 子进程管理配置。"""

    max_restart_attempts: int = 3
    spawn_timeout_sec: float = 30.0


class RunnerSpawner:
    """Host 端 Runner 子进程管理器。"""

    def __init__(self, host_listen_address: str, config: RunnerSpawnerConfig, token_service: TokenService | None = None) -> None:
        self._host_addr = host_listen_address
        self._config = config
        self._token_service = token_service
        self._processes: dict[str, subprocess.Popen] = {}
        self._plugin_dirs: dict[str, str] = {}
        self._restart_counts: dict[str, int] = {}

    async def spawn(self, runner_id: str, plugin_dir: str) -> subprocess.Popen:
        """spawn 一个 Runner 子进程。

        ⚠️ **先过装载期守卫**（P1③）：插件 manifest 声明的 `sdk.min_version` 若**跨主版本地**
        越过宿主 SDK 区间，这里**拒装载**（fail-closed + 具名），不落进程；
        **同主版本**越过 ⇒ 只**具名 warning**、照常装载（判据见 `_check_manifest_sdk_min_version`
        的"意图变更"段：兼容性靠 capability，不靠号段）。
        """
        rejection = _check_manifest_sdk_min_version(plugin_dir, runner_id)
        if rejection is not None:
            logger.error(
                "拒绝装载 Runner（插件声明的 SDK 版本要求无法满足）: %s | plugin_dir=%s runner=%s",
                rejection,
                plugin_dir,
                runner_id,
            )
            raise SDKVersionRequirementUnsatisfied(rejection)

        session_token = ""
        if self._token_service is not None:
            plugin_id = _read_plugin_id(plugin_dir, runner_id)
            session_token = self._token_service.issue(plugin_id)

        cmd = [
            sys.executable, "-m", "src.plugin_runtime_v2.runner.entrypoint",
            "--host-address", self._host_addr,
            "--plugin-dir", plugin_dir,
            "--runner-id", runner_id,
        ]
        # session_token 通过环境变量传递，避免 ps/proc 可见（A23a P1-2 安全）
        child_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if session_token:
            child_env["_SESSION_TOKEN"] = session_token
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
        )
        self._processes[runner_id] = process
        self._plugin_dirs[runner_id] = plugin_dir
        logger.info("Spawned Runner: %s plugin_dir=%s", runner_id, plugin_dir)
        return process

    async def check_health(self) -> dict[str, str]:
        """检查所有 Runner 进程健康状态。"""
        result: dict[str, str] = {}
        for rid, proc in self._processes.items():
            poll = proc.poll()
            if poll is None:
                result[rid] = "running"
            elif poll == 0:
                result[rid] = "stopped"
            else:
                result[rid] = "failed"
        return result

    async def restart_failed(self) -> None:
        """重启崩溃的 Runner 进程（不超过 max_restart_attempts）。"""
        health = await self.check_health()
        for rid, status in health.items():
            if status != "failed":
                continue
            if self._restart_counts.get(rid, 0) >= self._config.max_restart_attempts:
                continue
            plugin_dir = self._plugin_dirs.get(rid)
            if plugin_dir is None:
                continue
            self._processes[rid].kill()
            del self._processes[rid]
            self._restart_counts[rid] = self._restart_counts.get(rid, 0) + 1
            await self.spawn(rid, plugin_dir)
            logger.info("Restarted Runner: %s (attempt %d)", rid, self._restart_counts[rid])

    async def kill_runner(self, runner_id: str, timeout_sec: float = 5.0) -> bool:
        """两段式终止单个 Runner：SIGTERM 优雅 → 超时 → SIGKILL 强制（ZG-5 OOM 处置用）。"""
        proc = self._processes.get(runner_id)
        if proc is None or proc.poll() is not None:
            return False
        proc.terminate()
        try:
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout_sec)
        self._processes.pop(runner_id, None)
        logger.info("Runner 已终止: %s", runner_id)
        return True

    async def stop_all(self) -> None:
        """停止所有 Runner 进程。"""
        for proc in self._processes.values():
            proc.terminate()
        for proc in self._processes.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._processes.clear()
        self._plugin_dirs.clear()
        logger.info("所有 Runner 进程已停止")


class SDKVersionRequirementUnsatisfied(RuntimeError):
    """插件 manifest 声明的 `sdk.min_version` 无法被宿主满足 ⇒ **拒绝装载**（P1③）。"""


def _read_manifest_json(plugin_dir: str) -> dict[str, object] | None:
    """读插件 manifest（`_manifest.json` 优先，与本文件既有读法一致）；读不到/不是对象 ⇒ None。"""
    for name in ("_manifest.json", "manifest.json"):
        path = Path(plugin_dir) / name
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
            return data if isinstance(data, dict) else None
    return None


def _check_manifest_sdk_min_version(plugin_dir: str, runner_id: str) -> str | None:
    """装载期守卫：插件 manifest 声明的 `sdk.min_version` 能否被宿主满足（P1③）。

    Returns:
        None = 通过（可继续装载）；否则是**具名的拒绝原因**（含**要求值**与宿主**支持区间**）。

    ⚠️ **方向性 —— 别以为漏写了半边判断**：
        `min_version` 是**最小**要求 ⇒ **宿主更新就能满足它**。所以只有
        「声明值 ≥ 宿主支持的上界」才可能是真冲突（插件要的比我们能给的还新）；
        「声明值**低于**宿主下界」**不算冲突**（插件向后兼容，我们满足得了）。

    ⚠️ **意图变更（2026-10-17 `version-floor-soften` 线 · lmq 裁）—— 下一条读者别当成回归**：
        - **旧意图**：*"声明了要更高 SDK ⇒ 拒"*（当时把**号段**当兼容判据）；
        - **新意图**：**"我们根本没法用版本号定兼容性"**——我们的号段与生态脱节
          （宿主自报 `0.1.0`，本处 SDK 区间 `[4.0.0, 5.0.0)`，而插件普遍写 `1.x–1.99.99` / `4.0.0` 这类号）；
        - **故**：**下界只作提示、不作门** ⇒ 声明值落在区间之上但**同主版本** ⇒ **具名 warning + 照常装载**；
          **只有跨主版本**（= 显式声明的不兼容）**才拒**。
        - **判据根**：兼容性 = **manifest 可解析 + 所需 API 在位 + 起得来**，不是号段比较
          （与 `src/plugin_runtime/runner/manifest_validator.py` 的 `_validate_runtime_compatibility`
          同一判据、同一晚落的两处）。

    **与 v1 的差异（2026-10-17 起已**缩小**）**：v1
    `src/plugin_runtime/manifest_validator.py:1067` 把 `manifest.sdk.min_version` 送进
    `is_in_range(...)`（`:119-138`）——那是**严格区间**语义。本处**仍不照抄那半边**：
    按严格区间硬卡会让"声明 `4.0.0`、宿主下界更高"的旧插件成批坏掉
    （真例：`plugins/hello_world_plugin/_manifest.json:21` 声明的正是 `4.0.0`）。
    ⚠️ 而 v1 那处**调用点**已在同一晚按 capability 判据放宽（下界 ⇒ 提示；跨主版本才拒）
    ⇒ 两侧语义现在**基本对齐**，差别只剩"号段边界取闭区间还是半开区间"。

    为什么落在 `spawn`：**"要不要起这个 runner"就是"要不要装载这个插件"** —— 天然是"拒装载"
    该落的地方（`dependency_resolver` 管插件间依赖、`activation_coordinator` 管发现，都不是这个语义）。
    """
    # 延迟 import：复用宿主既有的版本常量与解析器（不另立一套，避免两处漂移）；
    # 放函数内是为了不与 servicer 形成模块级循环 import。
    from src.plugin_runtime_v2.host.servicer import (
        _MAX_SDK_VERSION,
        _MIN_SDK_VERSION,
        _parse_version_tuple,
    )

    manifest = _read_manifest_json(plugin_dir)
    if manifest is None:
        # manifest 读不到的处理**不归本守卫**（别在这兜底：那会把"读不到"伪装成"版本 OK"）
        return None

    sdk_section = manifest.get("sdk")
    if not isinstance(sdk_section, dict) or "min_version" not in sdk_section:
        # ④ 兼容性：旧插件**没写**这个键 ⇒ **具名回落**
        # （判的是**原始 JSON 的键在不在**，所以能与"显式写了 4.0.0"区分开）
        logger.info(
            "插件未声明 sdk.min_version，按宿主支持下界 %s 处理（回退路径，不是正常态）"
            " | plugin_dir=%s runner=%s",
            _MIN_SDK_VERSION,
            plugin_dir,
            runner_id,
        )
        return None

    declared_raw = str(sdk_section.get("min_version", "") or "").strip()
    declared = _parse_version_tuple(declared_raw)
    if not declared:
        # 写了却解析不了 ⇒ fail-closed（"声明了但不可判"不许当通过）
        return (
            f"SDK_MIN_VERSION_UNPARSABLE: 插件声明 sdk.min_version={declared_raw!r} 无法解析（要求值）；"
            f"宿主支持 [{_MIN_SDK_VERSION}, {_MAX_SDK_VERSION})（实际值）"
        )

    ceiling = _parse_version_tuple(_MAX_SDK_VERSION)
    if declared >= ceiling:
        # ⚠️ 意图变更（见 docstring）：**同主版本 ⇒ 出声放行**；**跨主版本 ⇒ 仍拒**。
        declared_major = declared[0] if declared else -1
        ceiling_major = ceiling[0] if ceiling else -1
        if declared_major != ceiling_major:
            return (
                f"SDK_MIN_VERSION_UNSATISFIED: 插件要求 sdk>={declared_raw}（要求值），"
                f"而宿主支持 [{_MIN_SDK_VERSION}, {_MAX_SDK_VERSION})"
                f"（实际可提供的最高版本 < {_MAX_SDK_VERSION}）——**跨主版本，属显式声明的不兼容**"
            )
        logger.warning(
            "插件声明 sdk.min_version=%s 在本宿主 SDK 区间 [%s, %s) 之上（**同主版本**）"
            "⇒ 按兼容模式装载（只出声、不拒；判据 = manifest 可解析 + 所需 API 在位 + 起得来）"
            " | plugin_dir=%s runner=%s",
            declared_raw,
            _MIN_SDK_VERSION,
            _MAX_SDK_VERSION,
            plugin_dir,
            runner_id,
        )
        return None
    return None


def _read_plugin_id(plugin_dir: str, fallback: str) -> str:
    """从 manifest 读取 plugin_id，失败则返回 fallback。"""
    for name in ("_manifest.json", "manifest.json"):
        p = Path(plugin_dir) / name
        if p.is_file():
            try:
                manifest = json.loads(p.read_text(encoding="utf-8"))
                return manifest.get("id", fallback)
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "读取插件 ID 失败", exception=exc)
                # P1: 补 logger 双通道上报（A23a P1-4）
                logger.warning("读取插件 ID 失败: %s", exc)
    return fallback
