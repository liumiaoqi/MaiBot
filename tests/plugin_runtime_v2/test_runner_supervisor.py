"""Phoenix-9 RunnerSupervisor + LogForwarder 单元测试。"""

from __future__ import annotations

import asyncio
import subprocess
import time as time_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.host.log_forwarder import LogForwarder
from src.plugin_runtime_v2.host.runner_supervisor import (
    ReloadResult,
    RunnerHealthStatus,
    RunnerSupervisor,
    RunnerSupervisorConfig,
    SpawnResult,
)


class TestDataModels:
    def test_supervisor_config_defaults(self):
        cfg = RunnerSupervisorConfig()
        assert cfg.max_restart_attempts == 3
        assert cfg.stability_window_s == 300.0
        assert cfg.storm_threshold == 5

    def test_spawn_result(self):
        r = SpawnResult(runner_id="r1", success=True, reason="ok")
        assert r.runner_id == "r1"
        assert r.success

    def test_reload_result(self):
        r = ReloadResult(runner_id="r1", success=False, reason="not_ready")
        assert not r.success
        assert r.reason == "not_ready"

    def test_health_status_defaults(self):
        s = RunnerHealthStatus(runner_id="r1")
        assert s.status == "starting"
        assert s.restart_count == 0
        assert s.pid is None


class TestLogForwarder:
    @pytest.mark.asyncio
    async def test_log_forwarder_start_stop(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.stdout = None
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        assert len(fwd._tasks) == 0
        await fwd.stop()
        assert len(fwd._tasks) == 0

    @pytest.mark.asyncio
    async def test_log_forwarder_reads_lines(self):
        proc = MagicMock(spec=subprocess.Popen)
        mock_stdout = MagicMock()
        mock_stdout.readline.return_value = b"hello world\n"
        proc.stdout = mock_stdout
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        with patch("src.plugin_runtime_v2.host.log_forwarder.logger.info") as mock_log:
            await fwd.start()
            await asyncio.sleep(0.1)
            await fwd.stop()
            found = any("hello world" in str(c) for c in mock_log.call_args_list)
            assert found


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_check_health_running(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(), MagicMock())
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 123
        sv._spawner._processes["r1"] = mock_proc
        mock_conn = MagicMock()
        mock_conn.state.value = "ready"
        sv._registry.get.return_value = mock_conn
        sv._health_status["r1"] = RunnerHealthStatus(runner_id="r1")

        sv._on_runner_failed = AsyncMock()
        result = await sv.check_health()
        assert result["r1"].status == "running"

    @pytest.mark.asyncio
    async def test_check_health_zombie(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(), MagicMock())
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 123
        sv._spawner._processes["r1"] = mock_proc
        sv._registry.get.return_value = None
        sv._health_status["r1"] = RunnerHealthStatus(runner_id="r1")

        sv._on_runner_failed = AsyncMock()
        result = await sv.check_health()
        assert result["r1"].status == "zombie"

    @pytest.mark.asyncio
    async def test_check_health_failed(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(), MagicMock())
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.pid = 123
        sv._spawner._processes["r1"] = mock_proc
        sv._health_status["r1"] = RunnerHealthStatus(runner_id="r1")

        sv._on_runner_failed = AsyncMock()
        result = await sv.check_health()
        assert result["r1"].status == "failed"
        assert "exit_code=1" in result["r1"].last_failure_reason


class TestShouldRestart:
    def test_restart_under_limit(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(max_restart_attempts=3), MagicMock())
        sv._restart_counts["r1"] = 1
        assert sv._should_restart("r1") is True

    def test_restart_over_limit(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(max_restart_attempts=3), MagicMock())
        sv._restart_counts["r1"] = 3
        assert sv._should_restart("r1") is False

    def test_restart_storm_detected(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(storm_window_s=60, storm_threshold=5), MagicMock())
        now = time_module.monotonic()
        sv._restart_timestamps["r1"] = [now] * 5
        sv._restart_counts["r1"] = 4
        assert sv._should_restart("r1") is False

    def test_reset_counters_if_stable(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(stability_window_s=0.01), MagicMock())
        now = time_module.monotonic()
        sv._stable_since["r1"] = now - 3600
        sv._restart_counts["r1"] = 5
        sv._restart_timestamps["r1"] = [now]
        sv._reset_counters_if_stable()
        assert "r1" not in sv._restart_counts


class TestReload:
    @pytest.mark.asyncio
    async def test_reload_one_success(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(), MagicMock())
        sv._spawner.spawn = AsyncMock()
        sv._spawner.spawn.return_value = MagicMock(pid=123)
        sv._log_forwarders["r1"] = MagicMock()
        sv._log_forwarders["r1"].stop = AsyncMock()
        sv._plugin_dirs["r1"] = "plugins"
        mock_conn = MagicMock()
        mock_conn.state.value = "ready"
        sv._registry.get.return_value = mock_conn

        result = await sv.reload_one("r1")
        assert result.success
        assert "r1" not in sv._reloading

    @pytest.mark.asyncio
    async def test_reload_one_not_ready(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(), MagicMock())
        sv._registry.get.return_value = None
        result = await sv.reload_one("r1")
        assert not result.success
        assert result.reason == "not_ready"

    @pytest.mark.asyncio
    async def test_reload_one_already_reloading(self):
        sv = RunnerSupervisor("localhost:0", RunnerSupervisorConfig(), MagicMock())
        sv._reloading.add("r1")
        result = await sv.reload_one("r1")
        assert not result.success
        assert result.reason == "already_reloading"
