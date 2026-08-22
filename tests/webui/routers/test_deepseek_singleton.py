"""deepseek 域 4 工厂单例化测试。

验证 4 个 _get_xxx() 工厂返回同一实例（状态跨请求存活）。
"""


from src.webui.routers import deepseek


class TestSingletonFactory:
    """4 工厂单例化验证。"""

    def test_budget_manager_singleton(self):
        """_get_budget_manager 两次调用返回同一实例。"""
        a = deepseek._get_budget_manager()
        b = deepseek._get_budget_manager()
        assert a is b

    def test_prefix_cache_manager_singleton(self):
        """_get_prefix_cache_manager 两次调用返回同一实例。"""
        a = deepseek._get_prefix_cache_manager()
        b = deepseek._get_prefix_cache_manager()
        assert a is b

    def test_batch_scheduler_singleton(self):
        """_get_batch_scheduler 两次调用返回同一实例。"""
        a = deepseek._get_batch_scheduler()
        b = deepseek._get_batch_scheduler()
        assert a is b

    def test_cost_tracker_singleton(self):
        """_get_cost_tracker 两次调用返回同一实例。"""
        a = deepseek._get_cost_tracker()
        b = deepseek._get_cost_tracker()
        assert a is b

    def test_batch_scheduler_state_survives(self):
        """BatchScheduler 状态跨请求存活——submit_task 后 _pending_tasks 非空。"""
        from src.maisaka.deepseek.batch_scheduler import BatchTask, BatchTaskType

        scheduler = deepseek._get_batch_scheduler()
        original_pending_count = len(scheduler._pending_tasks)

        task = BatchTask(
            task_id="test_singleton_task",
            agent_id="test_agent",
            task_type=BatchTaskType.PROFILE_UPDATE,
        )
        scheduler.submit_task(task)

        scheduler_again = deepseek._get_batch_scheduler()
        assert scheduler_again is scheduler
        assert len(scheduler_again._pending_tasks) > original_pending_count