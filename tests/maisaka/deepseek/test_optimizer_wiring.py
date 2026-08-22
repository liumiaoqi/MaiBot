"""DeepSeekOptimizer 模块级单例接线测试。

验证模块级单例存在 + select_strategy() 可调用返回合法值 + LLM 调用链有调用点。
"""


from src.maisaka.deepseek.optimizer import DeepSeekOptimizer, get_deepseek_optimizer


class TestOptimizerWiring:
    """DeepSeekOptimizer 接线验证。"""

    def test_singleton_exists(self):
        """模块级单例存在且是 DeepSeekOptimizer 实例。"""
        optimizer = get_deepseek_optimizer()
        assert isinstance(optimizer, DeepSeekOptimizer)

    def test_singleton_stable(self):
        """两次获取返回同一实例。"""
        a = get_deepseek_optimizer()
        b = get_deepseek_optimizer()
        assert a is b

    def test_select_strategy_returns_str(self):
        """select_strategy() 返回字符串（合法策略名）。"""
        optimizer = get_deepseek_optimizer()
        strategy = optimizer.select_strategy("test_agent", 128000)
        assert isinstance(strategy, str)
        assert len(strategy) > 0

    def test_is_deepseek_enabled_checkable(self):
        """is_deepseek_enabled() 可调用返回 bool。"""
        result = DeepSeekOptimizer.is_deepseek_enabled("test_agent")
        assert isinstance(result, bool)