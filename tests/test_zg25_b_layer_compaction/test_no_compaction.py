"""ZG-25 测试：token 未超阈值时不触发 compaction。

验证 spec 5.4.1：token ≤ 阈值 → 返回原 selected_history。
"""

from src.maisaka.context.compaction import compact_selected_history

from .conftest import (
    make_long_history,
    make_mock_llm_service,
)


class TestNoCompactionUnderThreshold:
    """验证 token 未超阈值时 compaction 不触发。"""

    async def test_under_threshold_returns_original(self, compaction_config) -> None:
        """token 未超阈值 → 返回原 history（同一对象）。"""
        history = make_long_history(count=4, text_size=50)
        llm_service = make_mock_llm_service()

        result = await compact_selected_history(
            history,
            context_window=100000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is history

    async def test_llm_not_called_under_threshold(self, compaction_config) -> None:
        """token 未超阈值 → LLM 未被调用。"""
        history = make_long_history(count=4, text_size=50)
        llm_service = make_mock_llm_service()

        await compact_selected_history(
            history,
            context_window=100000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        llm_service.generate_response_with_messages.assert_not_called()