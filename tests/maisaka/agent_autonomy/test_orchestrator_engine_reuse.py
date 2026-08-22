"""InteractionEngine 复用测试（T3.2/T3.7）。

验证 orchestrator 通过构造注入复用 bootstrap 装配的 InteractionEngine，
不再延迟独立创建（状态分裂修复 P0-A12a-1）。
"""


import inspect
from unittest.mock import MagicMock, patch

import pytest

from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
from src.maisaka.agent_interaction.bootstrap import get_interaction_engine


def _patch_orchestrator_deps():
    """批量 mock AgentOrchestrator.__init__ 的外部依赖。"""
    return [
        patch.object(AgentOrchestrator, "_registry", {}),
        patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port"),
        patch("src.maisaka.agent_autonomy.orchestrator.get_event_bus_port", return_value=MagicMock()),
        patch("src.maisaka.agent_autonomy.autonomy_logger.get_event_bus_port", return_value=MagicMock()),
        patch("src.maisaka.agent_autonomy.orchestrator.AgentActivityStore"),
        patch("src.maisaka.agent_autonomy.orchestrator.AgentLifecycleManager"),
        patch("src.maisaka.agent_autonomy.orchestrator.VitalityManager"),
        patch("src.maisaka.agent_autonomy.orchestrator.VitalityTickScheduler"),
        patch("src.maisaka.agent_autonomy.orchestrator.StateVisibilityRule"),
        patch("src.maisaka.agent_autonomy.orchestrator.StateAwareRuleEngine"),
        patch("src.maisaka.agent_autonomy.orchestrator.CohabitantStateSummaryGenerator"),
        patch("src.maisaka.agent_autonomy.orchestrator.AmbientAwarenessProcessor"),
        patch("src.maisaka.agent_autonomy.parallel_think.ParallelThinkScheduler"),
        patch("src.core.adapters.get_memory_service_port"),
        patch("src.maisaka.agent_autonomy.experience_writer.ExperienceWriter"),
    ]


def _enter_patches(patches):
    """进入所有 patch 上下文，返回退出函数。"""
    for p in patches:
        p.start()
    return lambda: [p.stop() for p in reversed(patches)]


class TestOrchestratorEngineReuse:
    """InteractionEngine 复用测试。"""

    def test_init_accepts_interaction_engine_param(self):
        """__init__ 签名包含 interaction_engine 参数，默认 None。"""
        sig = inspect.signature(AgentOrchestrator.__init__)
        assert "interaction_engine" in sig.parameters
        assert sig.parameters["interaction_engine"].default is None

    def test_no_lazy_creation_in_source(self):
        """源代码中不再有延迟创建 InteractionEngine 的分支。"""
        source = inspect.getsource(AgentOrchestrator)
        assert "self._interaction_engine = InteractionEngine(" not in source

    def test_get_interaction_engine_callable(self):
        """get_interaction_engine 函数存在且可调用。"""
        engine = get_interaction_engine()
        assert engine is None or hasattr(engine, "execute")

    def test_orchestrator_stores_injected_engine(self):
        """orchestrator 正确存储注入的 interaction_engine 实例。"""
        mock_engine = MagicMock(name="engine")
        patches = _patch_orchestrator_deps()
        cleanup = _enter_patches(patches)
        try:
            with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port") as mock_app:
                mock_app.return_value.get_agent_autonomy_config.return_value = MagicMock(
                    mention_chain_decay_base=0.5,
                    mention_chain_max_depth=3,
                    orchestrator_strategy="default",
                )
                orch = AgentOrchestrator(
                    session_id="test_engine_reuse",
                    session_name="test",
                    chat_loop_adapter=MagicMock(),
                    routing_service=MagicMock(),
                    notice_classifier=MagicMock(),
                    thinking_organ_factory=MagicMock(),
                    interaction_engine=mock_engine,
                )
            assert orch._interaction_engine is mock_engine
        finally:
            cleanup()

    def test_orchestrator_none_engine_when_not_injected(self):
        """未注入 engine 时 _interaction_engine 为 None。"""
        patches = _patch_orchestrator_deps()
        cleanup = _enter_patches(patches)
        try:
            with patch("src.maisaka.agent_autonomy.orchestrator.get_app_config_port") as mock_app:
                mock_app.return_value.get_agent_autonomy_config.return_value = MagicMock(
                    mention_chain_decay_base=0.5,
                    mention_chain_max_depth=3,
                    orchestrator_strategy="default",
                )
                orch = AgentOrchestrator(
                    session_id="test_engine_none",
                    session_name="test",
                    chat_loop_adapter=MagicMock(),
                    routing_service=MagicMock(),
                    notice_classifier=MagicMock(),
                    thinking_organ_factory=MagicMock(),
                )
            assert orch._interaction_engine is None
        finally:
            cleanup()


class TestBootstrapEngineCache:
    """bootstrap engine 缓存测试。"""

    def test_engine_instance_module_var_exists(self):
        """bootstrap 模块有 _engine_instance 模块级变量。"""
        import src.maisaka.agent_interaction.bootstrap as bs

        assert hasattr(bs, "_engine_instance")

    def test_get_interaction_engine_returns_engine_instance(self):
        """get_interaction_engine 返回 _engine_instance。"""
        import src.maisaka.agent_interaction.bootstrap as bs

        assert get_interaction_engine() is bs._engine_instance