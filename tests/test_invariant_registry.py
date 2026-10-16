"""N2 不变量注册表框架测试 — 验证 register/verify_all/装饰器/配置开关/定时巡检。"""

import asyncio

import pytest

from src.core.invariant_registry import (
    InvariantError,
    InvariantRegistry,
    get_invariant_registry,
    invariant,
    reset_invariant_registry,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    """每个测试用独立 registry，避免全局单例污染。"""
    reset_invariant_registry()
    yield
    reset_invariant_registry()


class TestRegisterAndDispose:
    def test_register_returns_disposer(self):
        reg = InvariantRegistry()
        disposer = reg.register(
            type("D", (), {"name": "test.mod", "installer": lambda fail: None, "source_module": ""})()
        )
        assert "test.mod" in reg.registered_names
        disposer()
        assert "test.mod" not in reg.registered_names

    def test_duplicate_register_raises(self):
        reg = InvariantRegistry()
        from src.core.invariant_registry import InvariantDesc

        desc = InvariantDesc(name="test.mod", installer=lambda fail: None)
        reg.register(desc)
        with pytest.raises(ValueError, match="重复注册"):
            reg.register(desc)


class TestVerifyAll:
    def test_no_violations_when_invariant_holds(self):
        reg = InvariantRegistry()
        from src.core.invariant_registry import InvariantDesc

        reg.register(InvariantDesc(name="test.ok", installer=lambda fail: None))
        violations = reg.verify_all()
        assert violations == []

    def test_records_violation_when_fail_called(self):
        reg = InvariantRegistry()
        from src.core.invariant_registry import InvariantDesc

        def bad_installer(fail):
            fail("不变量不成立")

        reg.register(InvariantDesc(name="test.bad", installer=bad_installer))
        violations = reg.verify_all()
        assert len(violations) == 1
        assert violations[0].name == "test.bad"
        assert violations[0].message == "不变量不成立"

    def test_installer_exception_caught_as_violation(self):
        reg = InvariantRegistry()
        from src.core.invariant_registry import InvariantDesc

        def crashing_installer(fail):
            raise RuntimeError("installer 崩了")

        reg.register(InvariantDesc(name="test.crash", installer=crashing_installer))
        violations = reg.verify_all()
        assert len(violations) == 1
        assert "installer 崩了" in violations[0].message

    def test_invariant_error_raised_inside_caught(self):
        reg = InvariantRegistry()
        from src.core.invariant_registry import InvariantDesc

        def error_installer(fail):
            raise InvariantError("显式违反")

        reg.register(InvariantDesc(name="test.err", installer=error_installer))
        violations = reg.verify_all()
        assert len(violations) == 1
        assert violations[0].message == "显式违反"


class TestConfigSwitch:
    def test_disabled_module_skipped(self):
        reg = InvariantRegistry(disabled_modules=["test.skip"])
        from src.core.invariant_registry import InvariantDesc

        reg.register(
            InvariantDesc(
                name="test.skip",
                installer=lambda fail: fail("应被跳过"),
            )
        )
        violations = reg.verify_all()
        assert violations == []

    def test_enabled_whitelist_only_checks_listed(self):
        reg = InvariantRegistry(enabled_modules=["test.allowed"])
        from src.core.invariant_registry import InvariantDesc

        reg.register(
            InvariantDesc(
                name="test.allowed",
                installer=lambda fail: fail("允许的违反"),
            )
        )
        reg.register(
            InvariantDesc(
                name="test.blocked",
                installer=lambda fail: fail("应被屏蔽"),
            )
        )
        violations = reg.verify_all()
        assert len(violations) == 1
        assert violations[0].name == "test.allowed"


class TestDecorator:
    def test_invariant_decorator_registers_to_global(self):
        @invariant("test.decorated")
        def check(fail):
            fail("装饰器注册的违反")

        reg = get_invariant_registry()
        assert "test.decorated" in reg.registered_names
        violations = reg.verify_all()
        assert len(violations) == 1
        assert violations[0].name == "test.decorated"

    def test_decorator_preserves_function_callable(self):
        @invariant("test.callable")
        def check(fail):
            pass

        # 装饰后仍可直接调用
        check(lambda msg: None)
        assert callable(check)


class TestPeriodicCheck:
    @pytest.mark.asyncio
    async def test_periodic_check_detects_violation(self):
        reg = InvariantRegistry()
        from src.core.invariant_registry import InvariantDesc

        reg.register(
            InvariantDesc(
                name="test.periodic",
                installer=lambda fail: fail("定时发现"),
            )
        )
        await reg.start_periodic_check(interval=0.05)
        await asyncio.sleep(0.15)
        await reg.stop_periodic_check()
        assert len(reg.last_violations) >= 1

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        reg = InvariantRegistry()
        await reg.start_periodic_check(interval=1.0)
        await reg.stop_periodic_check()
        await reg.stop_periodic_check()  # 不抛


class TestRealInvariantEmotion:
    """验证 emotion 不变量逻辑（直接调 installer，不走注册表导入副作用）。"""

    def test_emotion_invariant_passes_when_in_range(self):
        from unittest.mock import MagicMock, patch
        from src.core.invariants.emotion import check_emotion_range

        mock_port = MagicMock()
        mock_port.get_all_emotion_values.return_value = {"agent_1": {"happy": 50.0, "sad": 30.0}}
        with patch("src.core.emotion_port_registry.get_emotion_port", return_value=mock_port):
            violations: list[str] = []
            check_emotion_range(lambda msg: violations.append(msg))
            assert violations == []

    def test_emotion_invariant_fails_when_out_of_range(self):
        from unittest.mock import MagicMock, patch
        from src.core.invariants.emotion import check_emotion_range

        mock_port = MagicMock()
        mock_port.get_all_emotion_values.return_value = {"agent_1": {"happy": 150.0}}
        with patch("src.core.emotion_port_registry.get_emotion_port", return_value=mock_port):
            violations: list[str] = []
            check_emotion_range(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "超出 [0,100]" in violations[0]


class TestRealInvariantReplyer:
    """v2：replyer 不变量测试。"""

    def test_passes_when_port_registered(self):
        from unittest.mock import patch
        from src.core.invariants.replyer import check_replyer

        with patch("src.core.invariants.replyer.get_replyer_service_port", return_value=object()):
            violations: list[str] = []
            check_replyer(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_port_missing(self):
        from unittest.mock import patch
        from src.core.invariants.replyer import check_replyer

        with patch("src.core.invariants.replyer.get_replyer_service_port", return_value=None):
            violations: list[str] = []
            check_replyer(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未注册" in violations[0]


class TestRealInvariantSession:
    """v2：session 不变量测试。"""

    def test_passes_when_port_registered(self):
        from unittest.mock import patch
        from src.core.invariants.session import check_session

        with patch("src.core.invariants.session.get_session_info_port", return_value=object()):
            violations: list[str] = []
            check_session(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_port_missing(self):
        from unittest.mock import patch
        from src.core.invariants.session import check_session

        with patch("src.core.invariants.session.get_session_info_port", return_value=None):
            violations: list[str] = []
            check_session(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未注册" in violations[0]


class TestRealInvariantOrchestrator:
    """v2：orchestrator 不变量测试。"""

    def test_passes_when_core_ready(self):
        from unittest.mock import patch, MagicMock
        from src.core.invariants.orchestrator import check_orchestrator

        mock_port = MagicMock()
        mock_port.is_core_ready.return_value = True
        with patch("src.core.invariants.orchestrator.get_core_readiness_port", return_value=mock_port):
            violations: list[str] = []
            check_orchestrator(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_port_missing(self):
        from unittest.mock import patch
        from src.core.invariants.orchestrator import check_orchestrator

        with patch("src.core.invariants.orchestrator.get_core_readiness_port", return_value=None):
            violations: list[str] = []
            check_orchestrator(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未注册" in violations[0]

    def test_fails_when_core_not_ready(self):
        from unittest.mock import patch, MagicMock
        from src.core.invariants.orchestrator import check_orchestrator

        mock_port = MagicMock()
        mock_port.is_core_ready.return_value = False
        mock_port.get_core_readiness.return_value = "flags snapshot"
        with patch("src.core.invariants.orchestrator.get_core_readiness_port", return_value=mock_port):
            violations: list[str] = []
            check_orchestrator(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未就绪" in violations[0]


class TestRealInvariantMemorix:
    """v2：A_memorix 不变量测试。"""

    def test_passes_when_port_available(self):
        from unittest.mock import MagicMock, patch
        from src.core.invariants.memorix import check_memorix

        mock_port = MagicMock()
        mock_port.get_vector_store_stats.return_value = {"index_size": 0, "active_count": 0}
        with patch("src.core.memory_service_port_registry.get_memory_service_port", return_value=mock_port):
            violations: list[str] = []
            check_memorix(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_vector_store_inconsistent(self):
        """v3：vector_store 索引不一致时报违反。"""
        from unittest.mock import MagicMock, patch
        from src.core.invariants.memorix import check_memorix

        mock_port = MagicMock()
        mock_port.get_vector_store_stats.return_value = {"index_size": 100, "active_count": 99}
        with patch("src.core.memory_service_port_registry.get_memory_service_port", return_value=mock_port):
            violations: list[str] = []
            check_memorix(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "vector_store 不一致" in violations[0]

    def test_fails_when_port_raises_runtime_error(self):
        from unittest.mock import patch
        from src.core.invariants.memorix import check_memorix

        with patch("src.core.memory_service_port_registry.get_memory_service_port", return_value=None):
            violations: list[str] = []
            check_memorix(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未注册" in violations[0]


class TestRealInvariantControlMessage:
    """v2：control_message 不变量测试。"""

    def test_passes_when_port_available(self):
        from unittest.mock import patch
        from src.core.invariants.control_message import check_control_message

        with patch("src.core.control_message_port_registry.get_control_message_port", return_value=object()):
            violations: list[str] = []
            check_control_message(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_port_raises_runtime_error(self):
        from unittest.mock import patch
        from src.core.invariants.control_message import check_control_message

        def raise_runtime():
            raise RuntimeError("port 未初始化")

        with patch("src.core.control_message_port_registry.get_control_message_port", side_effect=raise_runtime):
            violations: list[str] = []
            check_control_message(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未注册" in violations[0]


class TestRealInvariantPluginRuntime:
    """v2：plugin_runtime 不变量测试。

    被检对象 2026-10-17 由 v1 的 IpcBridgePort 换成 v2 的 PluginRuntimeV2Port：
    v1 运行时已由 ZG-32 停用（其 is_running 恒假），原检查在 v2 启用时恒红。
    """

    @staticmethod
    def _app_port(enabled: bool):
        from unittest.mock import MagicMock

        app_port = MagicMock()
        app_port.get_plugin_runtime_v2_enabled.return_value = enabled
        return app_port

    @staticmethod
    def _lifecycle(shutting_down: bool):
        from unittest.mock import MagicMock

        adapter = MagicMock()
        adapter.is_shutting_down.return_value = shutting_down
        return adapter

    def test_passes_when_running(self):
        from unittest.mock import MagicMock, patch
        from src.core.invariants.plugin_runtime import check_plugin_runtime

        mock_port = MagicMock()
        mock_port.is_running = True
        with patch("src.core.invariants.plugin_runtime.get_app_config_port", return_value=self._app_port(True)), \
             patch("src.core.invariants.plugin_runtime.get_system_lifecycle_adapter", return_value=self._lifecycle(False)), \
             patch("src.core.invariants.plugin_runtime.get_plugin_runtime_v2_port", return_value=mock_port):
            violations: list[str] = []
            check_plugin_runtime(lambda msg: violations.append(msg))
            assert violations == []

    def test_ignores_v1_ipc_bridge_state(self):
        """v1 桥接恒假不再影响判定（原假报的回归钉）。"""
        from unittest.mock import MagicMock, patch
        from src.core.invariants.plugin_runtime import check_plugin_runtime

        dead_v1_port = MagicMock()
        dead_v1_port.is_running = False
        v2_port = MagicMock()
        v2_port.is_running = True
        with patch("src.core.invariants.plugin_runtime.get_app_config_port", return_value=self._app_port(True)), \
             patch("src.core.invariants.plugin_runtime.get_system_lifecycle_adapter", return_value=self._lifecycle(False)), \
             patch("src.core.invariants.plugin_runtime.get_plugin_runtime_v2_port", return_value=v2_port), \
             patch("src.core.ipc_bridge_port_registry.get_ipc_bridge_port", return_value=dead_v1_port):
            violations: list[str] = []
            check_plugin_runtime(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_not_running(self):
        from unittest.mock import MagicMock, patch
        from src.core.invariants.plugin_runtime import check_plugin_runtime

        mock_port = MagicMock()
        mock_port.is_running = False
        with patch("src.core.invariants.plugin_runtime.get_app_config_port", return_value=self._app_port(True)), \
             patch("src.core.invariants.plugin_runtime.get_system_lifecycle_adapter", return_value=self._lifecycle(False)), \
             patch("src.core.invariants.plugin_runtime.get_plugin_runtime_v2_port", return_value=mock_port):
            violations: list[str] = []
            check_plugin_runtime(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未启动" in violations[0]

    def test_fails_when_v2_port_missing(self):
        """v2 端点没接线（启动失败/未启用）时报违反。"""
        from unittest.mock import patch
        from src.core.invariants.plugin_runtime import check_plugin_runtime

        with patch("src.core.invariants.plugin_runtime.get_app_config_port", return_value=self._app_port(True)), \
             patch("src.core.invariants.plugin_runtime.get_system_lifecycle_adapter", return_value=self._lifecycle(False)), \
             patch("src.core.invariants.plugin_runtime.get_plugin_runtime_v2_port", return_value=None):
            violations: list[str] = []
            check_plugin_runtime(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未接线" in violations[0]

    def test_skips_when_config_disabled(self):
        """plugin_runtime_v2.enabled=false 时不报违反（有意禁用 ≠ 违反）。"""
        from unittest.mock import patch
        from src.core.invariants.plugin_runtime import check_plugin_runtime

        with patch("src.core.invariants.plugin_runtime.get_app_config_port", return_value=self._app_port(False)), \
             patch("src.core.invariants.plugin_runtime.get_plugin_runtime_v2_port", return_value=None):
            violations: list[str] = []
            check_plugin_runtime(lambda msg: violations.append(msg))
            assert violations == []

    def test_skips_when_shutting_down(self):
        """关停阶段不判定（关闭链本就要停端点）。"""
        from unittest.mock import MagicMock, patch
        from src.core.invariants.plugin_runtime import check_plugin_runtime

        mock_port = MagicMock()
        mock_port.is_running = False
        with patch("src.core.invariants.plugin_runtime.get_app_config_port", return_value=self._app_port(True)), \
             patch("src.core.invariants.plugin_runtime.get_system_lifecycle_adapter", return_value=self._lifecycle(True)), \
             patch("src.core.invariants.plugin_runtime.get_plugin_runtime_v2_port", return_value=mock_port):
            violations: list[str] = []
            check_plugin_runtime(lambda msg: violations.append(msg))
            assert violations == []


class TestRealInvariantServiceManager:
    """v2：service_manager 不变量测试。"""

    def test_passes_when_states_valid(self):
        from unittest.mock import patch, MagicMock
        from src.core.invariants.service_manager import check_service_manager

        mock_port = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.state = "running"
        mock_port.list_states.return_value = [mock_snapshot]
        with patch("src.core.invariants.service_manager.get_service_manager_port", return_value=mock_port):
            violations: list[str] = []
            check_service_manager(lambda msg: violations.append(msg))
            assert violations == []

    def test_fails_when_port_missing(self):
        from unittest.mock import patch
        from src.core.invariants.service_manager import check_service_manager

        with patch("src.core.invariants.service_manager.get_service_manager_port", return_value=None):
            violations: list[str] = []
            check_service_manager(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "未注册" in violations[0]

    def test_fails_when_state_none(self):
        from unittest.mock import patch, MagicMock
        from src.core.invariants.service_manager import check_service_manager

        mock_port = MagicMock()
        mock_port.list_states.return_value = [None]
        with patch("src.core.invariants.service_manager.get_service_manager_port", return_value=mock_port):
            violations: list[str] = []
            check_service_manager(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "None" in violations[0]

    def test_passes_with_all_enum_members(self):
        """生产路径：ServiceStateSnapshot.state 是 ServiceState 枚举成员，全部 9 个状态都应通过。"""
        from unittest.mock import patch, MagicMock
        from src.core.invariants.service_manager import check_service_manager
        from src.core.service_manager.types import ServiceState

        mock_port = MagicMock()
        mock_snapshots = []
        for state in ServiceState:
            snap = MagicMock()
            snap.state = state
            mock_snapshots.append(snap)
        mock_port.list_states.return_value = mock_snapshots
        with patch("src.core.invariants.service_manager.get_service_manager_port", return_value=mock_port):
            violations: list[str] = []
            check_service_manager(lambda msg: violations.append(msg))
            assert violations == []

    def test_str_enum_regression(self):
        """Python 3.11+ str(Enum) 返回 repr 而非 value，不变量不应因此误报。"""
        from src.core.service_manager.types import ServiceState
        from src.core.invariants.service_manager import _VALID_STATES

        assert str(ServiceState.RUNNING) == "ServiceState.RUNNING"
        assert ServiceState.RUNNING in _VALID_STATES
        assert "running" in _VALID_STATES


class TestStartupWiringWindow:
    """启动接线窗口（2026-10-17，ZG-8"先违反后接线"修复）。

    三条硬线：
    1. 默认未开窗 ⇒ 合成一个未注册端口必须红（不许把闸削弱）；
    2. 窗口内 ⇒ 同一份未注册记为"待接线"，不报违反（不教人忽略不变量）；
    3. 关窗 ⇒ 同一份未注册必须重新变红（"恒假"不许换成"恒真"）。
    """

    @pytest.fixture(autouse=True)
    def _reset_port(self):
        from src.core.control_message_port_registry import reset_control_message_port

        reset_control_message_port()
        yield
        reset_control_message_port()

    @staticmethod
    def _reg_with_real_invariant() -> InvariantRegistry:
        """挂真 installer 的独立注册表（不依赖测试执行顺序/模块缓存）。"""
        from src.core.invariant_registry import InvariantDesc
        from src.core.invariants.control_message import check_control_message

        reg = InvariantRegistry()
        reg.register(
            InvariantDesc(
                name="control_message",
                installer=check_control_message,
                source_module="src.core.invariants.control_message",
            )
        )
        return reg

    @staticmethod
    def _control_message_hits(records) -> list:
        return [r for r in records if r.name == "control_message"]

    def test_missing_port_is_violation_without_window(self):
        """① 合成未注册端口 + 未开窗 ⇒ 必须红。"""
        reg = self._reg_with_real_invariant()
        hits = self._control_message_hits(reg.verify_all())
        assert len(hits) == 1
        assert "未注册" in hits[0].message

    def test_window_defers_missing_port_as_pending(self):
        """② 开窗后同一份未注册 ⇒ 待接线，不报违反。"""
        reg = self._reg_with_real_invariant()
        reg.open_startup_wiring()
        assert reg.verify_all() == []
        pending = reg.last_pending
        assert [p.name for p in pending] == ["control_message"]
        assert "未注册" in pending[0].message

    def test_closing_window_makes_missing_port_red_again(self):
        """③ 关窗即硬线：同一份未注册重新变红。"""
        reg = self._reg_with_real_invariant()
        reg.open_startup_wiring()
        assert reg.verify_all() == []  # 窗口内：待接线
        violations = reg.close_startup_wiring()
        hits = self._control_message_hits(violations)
        assert len(hits) == 1
        assert "未注册" in hits[0].message
        assert reg.startup_wiring_open is False
        assert reg.last_pending == []

    def test_registered_port_clears_pending_and_violations(self):
        """真接上线（注册 port）⇒ 窗口内无待接线、关窗后无违反。"""
        from typing import cast

        from src.core.control_message_port_registry import set_control_message_port
        from src.core.protocols import ControlMessagePort

        set_control_message_port(cast(ControlMessagePort, object()))
        reg = self._reg_with_real_invariant()
        reg.open_startup_wiring()
        assert reg.verify_all() == []
        assert reg.last_pending == []
        assert self._control_message_hits(reg.close_startup_wiring()) == []

    def test_production_startup_opens_and_closes_window(self):
        """生产接线核查（源码级）：MainSystem.initialize 开窗 + finally 关窗。"""
        from pathlib import Path

        source = Path("src/main.py").read_text(encoding="utf-8")
        init_block = source.split("async def initialize(self) -> None:", 1)[1].split(
            "async def _init_components", 1
        )[0]
        assert init_block.count("open_startup_wiring()") == 1
        assert "finally:" in init_block
        assert init_block.count("close_startup_wiring()") == 1