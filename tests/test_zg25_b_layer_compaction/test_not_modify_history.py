"""ZG-25 测试：compaction 不修改输入 selected_history。

验证 spec 4.3 安全性规则 3：不修改输入 selected_history。
"""

from src.maisaka.context.compaction import compact_selected_history

from .conftest import (
    make_long_history,
    make_mock_llm_service,
)


class TestNotModifyHistory:
    """验证 compaction 不修改输入 history。"""

    async def test_input_history_unchanged_after_compaction(self, compaction_config) -> None:
        """compaction 后输入 history 长度不变。"""
        history = make_long_history(count=20, text_size=200)
        original_len = len(history)
        llm_service = make_mock_llm_service(summary_text="摘要")

        await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert len(history) == original_len

    async def test_input_history_elements_unchanged(self, compaction_config) -> None:
        """compaction 后输入 history 元素引用不变。"""
        history = make_long_history(count=20, text_size=200)
        original_refs = list(history)
        llm_service = make_mock_llm_service(summary_text="摘要")

        await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        for i, ref in enumerate(original_refs):
            assert history[i] is ref

    async def test_result_is_new_list(self, compaction_config) -> None:
        """compaction 返回新列表（不就地修改）。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is not history