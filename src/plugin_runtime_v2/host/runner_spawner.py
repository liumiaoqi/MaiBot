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
        """spawn 一个 Runner 子进程。"""
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
