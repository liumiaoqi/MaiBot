"""Host 端 Runner 子进程管理器。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.host.runner_spawner")


@dataclass
class RunnerSpawnerConfig:
    """Runner 子进程管理配置。"""

    max_restart_attempts: int = 3
    spawn_timeout_sec: float = 30.0


class RunnerSpawner:
    """Host 端 Runner 子进程管理器。"""

    def __init__(self, host_listen_address: str, config: RunnerSpawnerConfig) -> None:
        self._host_addr = host_listen_address
        self._config = config
        self._processes: dict[str, subprocess.Popen] = {}
        self._plugin_dirs: dict[str, str] = {}
        self._restart_counts: dict[str, int] = {}

    async def spawn(self, runner_id: str, plugin_dir: str) -> None:
        """spawn 一个 Runner 子进程。"""
        cmd = [
            sys.executable, "-m", "src.plugin_runtime_v2.runner.entrypoint",
            "--host-address", self._host_addr,
            "--plugin-dir", plugin_dir,
            "--runner-id", runner_id,
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._processes[runner_id] = process
        self._plugin_dirs[runner_id] = plugin_dir
        logger.info("Spawned Runner: %s plugin_dir=%s", runner_id, plugin_dir)

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
