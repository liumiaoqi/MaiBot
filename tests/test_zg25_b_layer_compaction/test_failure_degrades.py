"""ZG-25 测试：compaction 失败时降级返回原 history。

验证 spec 4.2 规则 1：失败 → 返回原 selected_history + warning。
"""

from src.maisaka.context.compaction import compact_selected_history

from .conftest import (
    make_long_history,
    make_mock_llm_service_raising,
)


class TestFailureDegrades:
    """验证 compaction 失败降级。"""

    async def test_llm_exception_returns_original(self, compaction_config) -> None:
        """LLM 抛异常 → 返回原 history。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service_raising(RuntimeError("LLM error"))

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is history

    async def test_llm_timeout_returns_original(self, compaction_config) -> None:
        """LLM 超时 → 返回原 history。"""
        import asyncio

        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service_raising(asyncio.TimeoutError())

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is history

    async def test_empty_summary_returns_original(self, compaction_config) -> None:
        """LLM 返回空摘要 → 返回原 history。"""
        from unittest.mock import AsyncMock, MagicMock

        history = make_long_history(count=20, text_size=200)
        llm_service = MagicMock()
        result_mock = MagicMock()
        result_mock.response = ""
        llm_service.generate_response_with_messages = AsyncMock(return_value=result_mock)

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is history