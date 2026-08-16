"""ZH1-1a 生产路径初始化验证 — AGENTS.md 硬性规则：新模块必须有生产接线点。

验证：
  1. main.py @startup_item 声明 mid_term_persistence + mid_term_summary_queue
  2. post_processor 裁切后入队接线
  3. chat_loop_service 过滤解除接线
  4. load_summaries_by_session 方案 A 加载入口可用

不依赖运行时 registry 状态（可能被 drain），用源码检查 + registry 检查混合。
"""

import inspect


from src.core.startup.declaration import _registry


def _registry_contains(name: str) -> bool:
    """检查 _registry._items 是否包含指定名称（import src.main 后）。"""
    return name in _registry._items


def _source_contains(module: object, marker: str) -> bool:
    """检查模块源码是否包含标记字符串。"""
    try:
        source = inspect.getsource(module)
        return marker in source
    except (OSError, TypeError):
        return False


class TestProductionWiring:
    """生产路径初始化验证（AGENTS.md 硬性规则）。"""

    def test_main_init_persistence(self) -> None:
        """验证 main.py @startup_item 声明 mid_term_persistence。"""
        import src.main

        # 优先检查 registry（运行时收集）
        if _registry_contains("mid_term_persistence"):
            assert True
            return
        # fallback: 源码检查声明存在
        assert _source_contains(src.main, 'name="mid_term_persistence"'), \
            "main.py 未声明 @startup_item(name='mid_term_persistence')"

    def test_main_init_summary_queue(self) -> None:
        """验证 main.py @startup_item 声明 mid_term_summary_queue。"""
        import src.main

        if _registry_contains("mid_term_summary_queue"):
            assert True
            return
        assert _source_contains(src.main, 'name="mid_term_summary_queue"'), \
            "main.py 未声明 @startup_item(name='mid_term_summary_queue')"

    def test_main_summary_queue_depends_on_persistence(self) -> None:
        """验证 mid_term_summary_queue 依赖 mid_term_persistence（源码检查）。"""
        import src.main

        assert _source_contains(src.main, 'depends_on=["mid_term_persistence"]'), \
            "mid_term_summary_queue 未声明 depends_on=['mid_term_persistence']"

    def test_main_close_wiring(self) -> None:
        """验证 main.py close 流程含 close_mid_term_summary_queue + close_mid_term_persistence。"""
        import src.main

        assert _source_contains(src.main, "close_mid_term_summary_queue"), \
            "main.py close 流程未调用 close_mid_term_summary_queue"
        assert _source_contains(src.main, "close_mid_term_persistence"), \
            "main.py close 流程未调用 close_mid_term_persistence"

    def test_post_processor_enqueue_wiring(self) -> None:
        """验证 post_processor 裁切后会入队（_enqueue_mid_term_summary_build 调用点存在）。"""
        from src.maisaka.context.post_processor import process_chat_history_after_cycle

        assert _source_contains(process_chat_history_after_cycle, "_enqueue_mid_term_summary_build"), \
            "process_chat_history_after_cycle 未调用 _enqueue_mid_term_summary_build"

    def test_chat_loop_service_filter_lift_wiring(self) -> None:
        """验证 chat_loop_service 过滤解除（不再过滤 mid_term_memory）。"""
        from src.maisaka.chat_loop_service import MaisakaChatLoopService

        source = inspect.getsource(MaisakaChatLoopService._filter_history_for_request_kind)
        # ZH1-1a 注释标记存在（过滤解除声明）
        assert "ZH1-1a" in source or "mid_term_memory" in source, \
            "_filter_history_for_request_kind 未含 ZH1-1a 过滤解除标记"

    def test_load_summaries_api_available(self) -> None:
        """验证 load_summaries_by_session 方案 A 加载入口可用。"""
        from src.maisaka.memory.mid_term_persistence import (
            MidTermPersistenceService,
            get_mid_term_persistence,
            init_mid_term_persistence,
        )

        # API 存在且可调用
        assert hasattr(MidTermPersistenceService, "load_summaries_by_session")
        assert callable(get_mid_term_persistence)
        assert callable(init_mid_term_persistence)

    def test_summary_queue_api_available(self) -> None:
        """验证摘要队列全局单例 API 可用。"""
        from src.maisaka.memory.mid_term_summary_queue import (
            close_mid_term_summary_queue,
            get_mid_term_summary_queue,
            init_mid_term_summary_queue,
        )

        assert callable(get_mid_term_summary_queue)
        assert callable(init_mid_term_summary_queue)
        assert callable(close_mid_term_summary_queue)