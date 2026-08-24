"""ZG-25 测试：token 超阈值时 compaction 触发。

验证 spec 5.4：enable=true + token 超阈值 → compaction 触发，
compacted_history[0] 是 CompactionSummaryMessage，尾部不变。
"""

from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import CompactionSummaryMessage

from .conftest import (
    make_long_history,
    make_mock_llm_service,
)


class TestCompactionTriggers:
    """验证 token 超阈值时 compaction 正确触发。"""

    async def test_compaction_produces_summary_message(self, compaction_config) -> None:
        """超阈值 → compacted[0] 是 CompactionSummaryMessage。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要内容")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert isinstance(result[0], CompactionSummaryMessage)
        assert result[0].summary_text == "摘要内容"
        # ZG-25 升级：N5 surface 替换事务身份 + 代数递增
        assert result[0].tx_id != ""
        assert result[0].replace_generation >= 1

    async def test_compaction_preserves_tail(self, compaction_config) -> None:
        """超阈值 → compacted 尾部 = 原 history 尾部。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要内容")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result[-1] is history[-1]
        assert result[-2] is history[-2]

    async def test_compaction_reduces_count(self, compaction_config) -> None:
        """超阈值 → compacted 条数 < 原 history 条数。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要内容")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert len(result) < len(history)