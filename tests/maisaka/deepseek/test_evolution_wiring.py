"""ParameterEvolutionEngine @startup_item 接线测试。

验证 init_parameter_evolution() 触发创建 + 三依赖注入 + can_auto_adjust() 可调用。
接线测试铁律：含真实构造链（init → ParameterEvolutionEngine(依赖...) → can_auto_adjust 可调用）。
"""


from src.maisaka.deepseek.evolution import (
    ParameterEvolutionEngine,
    get_parameter_evolution_engine,
    init_parameter_evolution,
)


class TestEvolutionWiring:
    """ParameterEvolutionEngine 接线验证。"""

    def test_init_creates_engine(self):
        """init_parameter_evolution() 创建 ParameterEvolutionEngine 实例。"""
        init_parameter_evolution()
        engine = get_parameter_evolution_engine()
        assert engine is not None
        assert isinstance(engine, ParameterEvolutionEngine)

    def test_dependencies_injected(self):
        """三依赖注入（cost_tracker/prefix_cache_manager/budget_manager 非 None）。"""
        init_parameter_evolution()
        engine = get_parameter_evolution_engine()
        assert engine._cost_tracker is not None
        assert engine._prefix_cache_manager is not None
        assert engine._budget_manager is not None

    def test_can_auto_adjust_callable(self):
        """can_auto_adjust() 可调用返回 bool（功能可达）。"""
        init_parameter_evolution()
        engine = get_parameter_evolution_engine()
        result = engine.can_auto_adjust("test_agent", "token_budget_ratio")
        assert isinstance(result, bool)

    def test_init_idempotent(self):
        """init_parameter_evolution() 幂等——多次调用不重建。"""
        init_parameter_evolution()
        engine1 = get_parameter_evolution_engine()
        init_parameter_evolution()
        engine2 = get_parameter_evolution_engine()
        assert engine1 is engine2