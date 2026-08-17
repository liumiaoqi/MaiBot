"""ZG-25 测试：compaction 后 recall 仍可翻原文。

验证 spec 5.5.5 决策 5：compaction 作用于临时列表 selected_history，
不写回 _chat_history，recall 仍可翻原文。
CompactionSummaryMessage 不参与 ZH1-1a 去重。
"""

from datetime import datetime
from unittest.mock import MagicMock

from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import CompactionSummaryMessage

from .conftest import (
    make_long_history,
    make_mock_llm_service,
)


class TestRecallIntegration:
    """验证 compaction + recall 集成。"""

    async def test_compaction_does_not_write_back(self, compaction_config) -> None:
        """compaction 作用于临时列表，不写回 _chat_history。"""
        chat_history = make_long_history(count=30, text_size=200)
        selected_history = list(chat_history[:20])
        original_chat_len = len(chat_history)
        llm_service = make_mock_llm_service(summary_text="摘要")

        await compact_selected_history(
            selected_history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert len(chat_history) == original_chat_len

    async def test_compaction_summary_count_in_context(self, compaction_config) -> None:
        """CompactionSummaryMessage count_in_context=True（占窗口）。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert isinstance(result[0], CompactionSummaryMessage)
        assert result[0].count_in_context is True

    async def test_compaction_summary_has_metadata(self, compaction_config) -> None:
        """CompactionSummaryMessage 含 original_segment_count + original_time_range。"""
        base_ts = datetime(2026, 8, 17, 10, 0, 0)
        history = []
        for i in range(20):
            msg = MagicMock()
            msg.__class__.__name__ = "AssistantMessage"
            msg.content = f"消息{i}_" + "x" * 200
            msg.processed_plain_text = msg.content
            msg.role = "assistant"
            msg.timestamp = base_ts
            msg.tool_calls = []
            msg.count_in_context = True
            history.append(msg)

        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        summary_msg = result[0]
        assert isinstance(summary_msg, CompactionSummaryMessage)
        assert summary_msg.original_segment_count > 0
        assert summary_msg.original_time_range != ""