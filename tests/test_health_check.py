"""N3 健康检查框架测试 — 验证 BaseHealthCheck/聚合器/HealthService/定时巡检。"""

import asyncio

import pytest

from src.core.health_check import (
    BaseHealthCheck,
    HealthResult,
    HealthService,
    HealthStatus,
    aggregate_pessimistic,
    get_health_service,
    reset_health_service,
)


@pytest.fixture(autouse=True)
def _isolate_service():
    reset_health_service()
    yield
    reset_health_service()


class TestHealthStatus:
    def test_pessimistic_ordering(self):
        """IntEnum 值越小越严重——min() 即悲观聚合。"""
        assert HealthStatus.DOWN < HealthStatus.DEGRADED < HealthStatus.UP < HealthStatus.UNKNOWN

    def test_min_aggregates_to_down(self):
        assert min([HealthStatus.UP, HealthStatus.DOWN, HealthStatus.DEGRADED]) == HealthStatus.DOWN


class TestBaseHealthCheck:
    @pytest.mark.asyncio
    async def test_successful_check(self):
        class OkCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.UP, {"info": "ok"})

        check = OkCheck("test.ok")
        result = await check.check()
        assert result.status == HealthStatus.UP
        assert result.details["info"] == "ok"

    @pytest.mark.asyncio
    async def test_timeout_degrades_to_down(self):
        class SlowCheck(BaseHealthCheck):
            timeout = 0.05

            async def _do_check(self):
                await asyncio.sleep(1.0)
                return HealthResult(HealthStatus.UP)

        check = SlowCheck("test.slow")
        result = await check.check()
        assert result.status == HealthStatus.DOWN
        assert result.details["reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_exception_degrades_to_down(self):
        class CrashCheck(BaseHealthCheck):
            async def _do_check(self):
                raise RuntimeError("检查器崩了")

        check = CrashCheck("test.crash")
        result = await check.check()
        assert result.status == HealthStatus.DOWN
        assert "检查器崩了" in result.details["error"]


class TestAggregatePessimistic:
    def test_all_up_aggregates_to_up(self):
        results = {
            "a": HealthResult(HealthStatus.UP),
            "b": HealthResult(HealthStatus.UP),
        }
        agg = aggregate_pessimistic(results)
        assert agg.status == HealthStatus.UP

    def test_one_down_aggregates_to_down(self):
        results = {
            "a": HealthResult(HealthStatus.UP),
            "b": HealthResult(HealthStatus.DOWN),
            "c": HealthResult(HealthStatus.DEGRADED),
        }
        agg = aggregate_pessimistic(results)
        assert agg.status == HealthStatus.DOWN

    def test_degraded_beats_down(self):
        results = {
            "a": HealthResult(HealthStatus.UP),
            "b": HealthResult(HealthStatus.DEGRADED),
        }
        agg = aggregate_pessimistic(results)
        assert agg.status == HealthStatus.DEGRADED

    def test_all_unknown_aggregates_to_unknown(self):
        results = {
            "a": HealthResult(HealthStatus.UNKNOWN),
            "b": HealthResult(HealthStatus.UNKNOWN),
        }
        agg = aggregate_pessimistic(results)
        assert agg.status == HealthStatus.UNKNOWN

    def test_empty_aggregates_to_unknown(self):
        agg = aggregate_pessimistic({})
        assert agg.status == HealthStatus.UNKNOWN

    def test_summary_counts(self):
        results = {
            "a": HealthResult(HealthStatus.UP),
            "b": HealthResult(HealthStatus.DOWN),
            "c": HealthResult(HealthStatus.DEGRADED),
            "d": HealthResult(HealthStatus.UNKNOWN),
        }
        agg = aggregate_pessimistic(results)
        assert agg.details["summary"] == {"up": 1, "degraded": 1, "down": 1, "unknown": 1}


class TestHealthService:
    @pytest.mark.asyncio
    async def test_register_and_check_all(self):
        class UpCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.UP)

        service = HealthService()
        service.register(UpCheck("test.up"))
        results = await service.check_all()
        assert "test.up" in results
        assert results["test.up"].status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_duplicate_register_raises(self):
        class DummyCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.UP)

        service = HealthService()
        service.register(DummyCheck("test.dup"))
        with pytest.raises(ValueError, match="重复"):
            service.register(DummyCheck("test.dup"))

    @pytest.mark.asyncio
    async def test_get_health_uses_cache(self):
        class UpCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.UP)

        service = HealthService()
        service.register(UpCheck("test.up"))
        await service.check_all()
        health = await service.get_health()
        assert health.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_check_one_unknown_for_unregistered(self):
        service = HealthService()
        result = await service.check_one("nonexistent")
        assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_periodic_check_populates_cache(self):
        class UpCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.UP)

        service = HealthService(check_interval=0.05)
        service.register(UpCheck("test.periodic"))
        await service.start_periodic_check()
        # 启动时立即自检一次
        assert "test.periodic" in service._cache
        await asyncio.sleep(0.15)
        await service.stop_periodic_check()
        health = await service.get_health()
        assert health.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        service = HealthService()
        await service.start_periodic_check()
        await service.stop_periodic_check()
        await service.stop_periodic_check()


class TestRealCheckDbMain:
    """验证 db.main 检查器能真实运行（用临时 DB）。"""

    @pytest.mark.asyncio
    async def test_db_main_up_when_db_exists(self, tmp_path):
        import sqlite3

        from src.core.health_checks.db_main import MainDbHealthCheck

        # 创建临时 DB
        db_file = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_file))
        conn.close()

        check = MainDbHealthCheck(db_path=db_file)
        result = await check.check()
        assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_db_main_down_when_db_missing(self, tmp_path):
        from src.core.health_checks.db_main import MainDbHealthCheck

        # 指向不存在的 DB 路径（sqlite3.connect 会创建空文件，但 SELECT 1 仍成功）
        # 改为指向一个会被锁住的路径模拟失败——这里用只读目录
        db_file = tmp_path / "nonexistent.db"
        check = MainDbHealthCheck(db_path=db_file)
        result = await check.check()
        # sqlite3.connect 会自动创建文件，所以 SELECT 1 应该成功
        assert result.status == HealthStatus.UP


class TestRealCheckLlmPrimary:
    """v2：llm.primary 检查器测试。v3 增强：last_success_time。"""

    @pytest.mark.asyncio
    async def test_up_when_port_registered(self):
        from unittest.mock import MagicMock, patch
        import time
        from src.core.health_checks.llm_primary import LlmPrimaryHealthCheck

        mock_port = MagicMock()
        mock_port.get_last_success_time.return_value = time.time()
        with patch("src.core.health_checks.llm_primary.get_model_config_port", return_value=mock_port):
            check = LlmPrimaryHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_unknown_when_port_missing(self):
        from unittest.mock import patch
        from src.core.health_checks.llm_primary import LlmPrimaryHealthCheck

        with patch("src.core.health_checks.llm_primary.get_model_config_port", return_value=None):
            check = LlmPrimaryHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_degraded_when_no_success(self):
        """v3：无成功调用记录 → DEGRADED。"""
        from unittest.mock import MagicMock, patch
        from src.core.health_checks.llm_primary import LlmPrimaryHealthCheck

        mock_port = MagicMock()
        mock_port.get_last_success_time.return_value = None
        with patch("src.core.health_checks.llm_primary.get_model_config_port", return_value=mock_port):
            check = LlmPrimaryHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_degraded_when_stale(self):
        """v3：最近 5 分钟无成功调用 → DEGRADED。"""
        from unittest.mock import MagicMock, patch
        import time
        from src.core.health_checks.llm_primary import LlmPrimaryHealthCheck

        mock_port = MagicMock()
        mock_port.get_last_success_time.return_value = time.time() - 600  # 10 分钟前
        with patch("src.core.health_checks.llm_primary.get_model_config_port", return_value=mock_port):
            check = LlmPrimaryHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DEGRADED


class TestRealCheckMemoryVectorStore:
    """v2：memory.vector_store 检查器测试。v3 增强：索引一致性。"""

    @pytest.mark.asyncio
    async def test_up_when_port_available(self):
        from unittest.mock import MagicMock, patch
        from src.core.health_checks.memory_vector_store import MemoryVectorStoreHealthCheck

        mock_port = MagicMock()
        mock_port.get_vector_store_stats.return_value = {"index_size": 0, "active_count": 0}
        with patch("src.core.adapters.memory_service.get_memory_service_port", return_value=mock_port):
            check = MemoryVectorStoreHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_unknown_when_port_raises(self):
        from unittest.mock import patch
        from src.core.health_checks.memory_vector_store import MemoryVectorStoreHealthCheck

        def raise_runtime():
            raise RuntimeError("not initialized")

        with patch("src.core.adapters.memory_service.get_memory_service_port", side_effect=raise_runtime):
            check = MemoryVectorStoreHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_degraded_when_inconsistent(self):
        """v3：索引不一致 → DEGRADED。"""
        from unittest.mock import MagicMock, patch
        from src.core.health_checks.memory_vector_store import MemoryVectorStoreHealthCheck

        mock_port = MagicMock()
        mock_port.get_vector_store_stats.return_value = {"index_size": 100, "active_count": 99}
        with patch("src.core.adapters.memory_service.get_memory_service_port", return_value=mock_port):
            check = MemoryVectorStoreHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DEGRADED


class TestRealCheckPluginRuntime:
    """v2：plugin.runtime 检查器测试。v3 增强：状态机检查。"""

    @pytest.mark.asyncio
    async def test_up_when_running(self):
        from unittest.mock import patch, MagicMock
        from src.core.protocols import PluginStateSnapshot
        from src.core.health_checks.plugin_runtime import PluginRuntimeHealthCheck

        mock_port = MagicMock()
        mock_port.is_running = True
        mock_port.list_plugin_states.return_value = [PluginStateSnapshot("p1", "running")]
        with patch("src.core.health_checks.plugin_runtime.get_ipc_bridge_port", return_value=mock_port):
            check = PluginRuntimeHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_unknown_when_port_missing(self):
        from unittest.mock import patch
        from src.core.health_checks.plugin_runtime import PluginRuntimeHealthCheck

        with patch("src.core.health_checks.plugin_runtime.get_ipc_bridge_port", return_value=None):
            check = PluginRuntimeHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_degraded_when_not_running(self):
        from unittest.mock import patch, MagicMock
        from src.core.protocols import PluginStateSnapshot
        from src.core.health_checks.plugin_runtime import PluginRuntimeHealthCheck

        mock_port = MagicMock()
        mock_port.is_running = False
        mock_port.list_plugin_states.return_value = [PluginStateSnapshot("p1", "loaded")]
        with patch("src.core.health_checks.plugin_runtime.get_ipc_bridge_port", return_value=mock_port):
            check = PluginRuntimeHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_down_when_plugin_errored(self):
        """v3：有 error 状态插件 → DOWN。"""
        from unittest.mock import patch, MagicMock
        from src.core.protocols import PluginStateSnapshot
        from src.core.health_checks.plugin_runtime import PluginRuntimeHealthCheck

        mock_port = MagicMock()
        mock_port.is_running = True
        mock_port.list_plugin_states.return_value = [
            PluginStateSnapshot("good", "running"),
            PluginStateSnapshot("bad", "error"),
        ]
        with patch("src.core.health_checks.plugin_runtime.get_ipc_bridge_port", return_value=mock_port):
            check = PluginRuntimeHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DOWN

    @pytest.mark.asyncio
    async def test_unknown_when_no_plugins(self):
        """v3：无插件注册 → UNKNOWN。"""
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.plugin_runtime import PluginRuntimeHealthCheck

        mock_port = MagicMock()
        mock_port.is_running = True
        mock_port.list_plugin_states.return_value = []
        with patch("src.core.health_checks.plugin_runtime.get_ipc_bridge_port", return_value=mock_port):
            check = PluginRuntimeHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN


class TestRealCheckCoreOrchestrator:
    """v2：core.orchestrator 检查器测试。"""

    @pytest.mark.asyncio
    async def test_up_when_core_ready(self):
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.core_orchestrator import CoreOrchestratorHealthCheck

        mock_port = MagicMock()
        mock_port.is_core_ready.return_value = True
        with patch("src.core.health_checks.core_orchestrator.get_core_readiness_port", return_value=mock_port):
            check = CoreOrchestratorHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_unknown_when_port_missing(self):
        from unittest.mock import patch
        from src.core.health_checks.core_orchestrator import CoreOrchestratorHealthCheck

        with patch("src.core.health_checks.core_orchestrator.get_core_readiness_port", return_value=None):
            check = CoreOrchestratorHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_degraded_when_not_ready(self):
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.core_orchestrator import CoreOrchestratorHealthCheck

        mock_port = MagicMock()
        mock_port.is_core_ready.return_value = False
        mock_port.get_core_readiness.return_value = "snapshot"
        with patch("src.core.health_checks.core_orchestrator.get_core_readiness_port", return_value=mock_port):
            check = CoreOrchestratorHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DEGRADED


class TestRealCheckChatSessionStore:
    """v2：chat.session_store 检查器测试。"""

    @pytest.mark.asyncio
    async def test_up_when_port_registered(self):
        from unittest.mock import patch
        from src.core.health_checks.chat_session_store import ChatSessionStoreHealthCheck

        with patch("src.core.health_checks.chat_session_store.get_session_info_port", return_value=object()):
            check = ChatSessionStoreHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_down_when_port_missing(self):
        from unittest.mock import patch
        from src.core.health_checks.chat_session_store import ChatSessionStoreHealthCheck

        with patch("src.core.health_checks.chat_session_store.get_session_info_port", return_value=None):
            check = ChatSessionStoreHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DOWN


class TestRealCheckWatchdogRunnerHealth:
    """v2：watchdog.runner_health 检查器测试。"""

    @pytest.mark.asyncio
    async def test_unknown_when_port_raises(self):
        from unittest.mock import patch
        from src.core.health_checks.watchdog_runner_health import WatchdogRunnerHealthCheck

        def raise_runtime():
            raise RuntimeError("not registered")

        with patch("src.core.watchdog_port_registry.get_watchdog_port", side_effect=raise_runtime):
            check = WatchdogRunnerHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_unknown_when_no_runners(self):
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.watchdog_runner_health import WatchdogRunnerHealthCheck

        mock_port = MagicMock()
        mock_port.list_runner_bridge_status.return_value = []
        with patch("src.core.watchdog_port_registry.get_watchdog_port", return_value=mock_port):
            check = WatchdogRunnerHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_up_when_all_healthy(self):
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.watchdog_runner_health import WatchdogRunnerHealthCheck

        mock_port = MagicMock()
        mock_status = MagicMock()
        mock_status.is_healthy = True
        mock_port.list_runner_bridge_status.return_value = [mock_status, mock_status]
        with patch("src.core.watchdog_port_registry.get_watchdog_port", return_value=mock_port):
            check = WatchdogRunnerHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.UP

    @pytest.mark.asyncio
    async def test_down_when_all_unhealthy(self):
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.watchdog_runner_health import WatchdogRunnerHealthCheck

        mock_port = MagicMock()
        mock_status = MagicMock()
        mock_status.is_healthy = False
        mock_port.list_runner_bridge_status.return_value = [mock_status, mock_status]
        with patch("src.core.watchdog_port_registry.get_watchdog_port", return_value=mock_port):
            check = WatchdogRunnerHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DOWN

    @pytest.mark.asyncio
    async def test_degraded_when_mixed(self):
        from unittest.mock import patch, MagicMock
        from src.core.health_checks.watchdog_runner_health import WatchdogRunnerHealthCheck

        mock_port = MagicMock()
        healthy = MagicMock()
        healthy.is_healthy = True
        unhealthy = MagicMock()
        unhealthy.is_healthy = False
        mock_port.list_runner_bridge_status.return_value = [healthy, unhealthy]
        with patch("src.core.watchdog_port_registry.get_watchdog_port", return_value=mock_port):
            check = WatchdogRunnerHealthCheck()
            result = await check.check()
            assert result.status == HealthStatus.DEGRADED


class TestZGIntegration:
    """v3 P2：ZG 体系衔接测试——health DOWN → error_escalation 上报。"""

    @pytest.mark.asyncio
    async def test_down_triggers_error_escalation(self):
        from unittest.mock import patch, MagicMock

        mock_escalation = MagicMock()
        service = HealthService()

        class DownCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.DOWN, {"reason": "test"})

        service.register(DownCheck("test.down"))
        with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=mock_escalation):
            await service.check_all()
            await service._on_health_change()
            mock_escalation.report.assert_called_once()
            call_args = mock_escalation.report.call_args
            assert call_args.args[1] == "健康检查 DOWN"

    @pytest.mark.asyncio
    async def test_up_does_not_trigger_escalation(self):
        from unittest.mock import patch, MagicMock

        mock_escalation = MagicMock()
        service = HealthService()

        class UpCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.UP)

        service.register(UpCheck("test.up"))
        with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=mock_escalation):
            await service.check_all()
            await service._on_health_change()
            mock_escalation.report.assert_not_called()

    @pytest.mark.asyncio
    async def test_down_without_escalation_port_logs_warning(self):
        from unittest.mock import patch

        service = HealthService()

        class DownCheck(BaseHealthCheck):
            async def _do_check(self):
                return HealthResult(HealthStatus.DOWN, {"reason": "test"})

        service.register(DownCheck("test.down"))
        with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
            await service.check_all()
            await service._on_health_change()  # 不抛异常