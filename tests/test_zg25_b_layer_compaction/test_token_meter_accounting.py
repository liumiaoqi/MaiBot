"""ZG-25 升级测试：N6 token meter 统一会计验证（spec 15.3）。

验证 compaction.py 委托 get_token_meter() 单例，无旧 estimate_messages 残留。
"""

from pathlib import Path


from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import CompactionSummaryMessage

from .conftest import make_long_history, make_mock_llm_service


def _compaction_source() -> str:
    """读取 compaction.py 源码（grep 断言用）。"""
    return Path("src/maisaka/context/compaction.py").read_text(encoding="utf-8")


class TestTokenMeterAccounting:
    """N6 token meter 统一会计验证。"""

    def test_grep_uses_get_token_meter(self) -> None:
        """用例1：compaction 源码含 get_token_meter() 调用，无 estimate_messages 拽留。"""
        source = _compaction_source()
        assert "get_token_meter" in source
        assert "estimate_messages" not in source

    def test_grep_no_direct_token_meter_construction(self) -> None:
        """用例2：compaction 源码无 TokenMeter() 直接构造。"""
        source = _compaction_source()
        assert "TokenMeter()" not in source

    async def test_over_threshold_triggers_compaction(self, compaction_config) -> None:
        """用例3：token 超阈值（N6 估算）→ 触发压缩。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")
        result = await compact_selected_history(
            history, context_window=1000, session_id="test",
            llm_service=llm_service, config=compaction_config,
        )
        assert isinstance(result[0], CompactionSummaryMessage)

    async def test_under_threshold_no_compaction(self, compaction_config) -> None:
        """用例4：token 未超阈值（N6 估算）→ 不触发。"""
        history = make_long_history(count=4, text_size=10)
        llm_service = make_mock_llm_service(summary_text="摘要")
        result = await compact_selected_history(
            history, context_window=100000, session_id="test",
            llm_service=llm_service, config=compaction_config,
        )
        assert result is history

    async def test_summary_not_smaller_no_replace(self, compaction_config) -> None:
        """用例5：摘要 token >= 原段 token → 不替换（无收益）。"""
        history = make_long_history(count=20, text_size=200)
        long_summary = "x" * 10000
        llm_service = make_mock_llm_service(summary_text=long_summary)
        result = await compact_selected_history(
            history, context_window=1000, session_id="test",
            llm_service=llm_service, config=compaction_config,
        )
        assert result is history

    async def test_token_meter_not_wired_degrades(self, compaction_config) -> None:
        """用例6：get_token_meter() 未接线 → RuntimeError 降级返回原 history。"""
        import src.core.token_meter.service as svc

        original = svc._instance
        svc._instance = None
        try:
            history = make_long_history(count=20, text_size=200)
            llm_service = make_mock_llm_service(summary_text="摘要")
            result = await compact_selected_history(
                history, context_window=1000, session_id="test",
                llm_service=llm_service, config=compaction_config,
            )
            assert result is history
        finally:
            svc._instance = original