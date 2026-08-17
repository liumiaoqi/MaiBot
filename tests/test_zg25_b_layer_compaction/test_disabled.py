"""ZG-25 测试：config.enable=False 时 compaction 不触发。

验证 spec 5.4.1 规则 5：可通过配置关闭。
"""

from src.maisaka.context.compaction import compact_selected_history

from .conftest import (
    make_long_history,
    make_mock_llm_service,
)


class TestDisabledByConfig:
    """验证 config.enable=False 时 compaction 不触发。"""

    async def test_disabled_returns_original(self, disabled_config) -> None:
        """enable=False → 返回原 history（同一对象）。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service()

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=disabled_config,
        )

        assert result is history

    async def test_disabled_llm_not_called(self, disabled_config) -> None:
        """enable=False → LLM 未被调用。"""
        history = make_long_history(count=20, text_size=200)
        llm_service = make_mock_llm_service()

        await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=disabled_config,
        )

        llm_service.generate_response_with_messages.assert_not_called()

    async def test_empty_history_returns_empty(self, compaction_config) -> None:
        """空 history → 返回空（不触发 compaction）。"""
        llm_service = make_mock_llm_service()

        result = await compact_selected_history(
            [],
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result == []