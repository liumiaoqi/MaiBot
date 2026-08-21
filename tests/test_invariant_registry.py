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
        from unittest.mock import patch
        from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
        from src.core.invariants.emotion import check_emotion_range

        fake_mgr = type("M", (), {"_state": type("S", (), {"emotions": {"happy": 50.0, "sad": 30.0}})()})()
        with patch.object(AgentEmotionManagerRegistry, "_shared_managers", {"agent_1": fake_mgr}):
            violations: list[str] = []
            check_emotion_range(lambda msg: violations.append(msg))
            assert violations == []

    def test_emotion_invariant_fails_when_out_of_range(self):
        from unittest.mock import patch
        from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
        from src.core.invariants.emotion import check_emotion_range

        fake_mgr = type("M", (), {"_state": type("S", (), {"emotions": {"happy": 150.0}})()})()
        with patch.object(AgentEmotionManagerRegistry, "_shared_managers", {"agent_1": fake_mgr}):
            violations: list[str] = []
            check_emotion_range(lambda msg: violations.append(msg))
            assert len(violations) == 1
            assert "超出 [0,100]" in violations[0]