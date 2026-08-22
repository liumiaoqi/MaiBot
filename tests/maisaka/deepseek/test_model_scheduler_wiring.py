"""ModelScheduler 模块级单例接线测试。

验证模块级单例存在 + select_model() 可调用返回合法 ModelTier。
"""


from src.maisaka.deepseek.model_scheduler import ModelScheduler, ModelTier, get_model_scheduler


class TestModelSchedulerWiring:
    """ModelScheduler 接线验证。"""

    def test_singleton_exists(self):
        """模块级单例存在且是 ModelScheduler 实例。"""
        scheduler = get_model_scheduler()
        assert isinstance(scheduler, ModelScheduler)

    def test_singleton_stable(self):
        """两次获取返回同一实例。"""
        a = get_model_scheduler()
        b = get_model_scheduler()
        assert a is b

    def test_select_model_returns_tier(self):
        """select_model() 返回 ModelTier 枚举。"""
        scheduler = get_model_scheduler()
        tier = scheduler.select_model("test_agent", "replyer")
        assert isinstance(tier, ModelTier)