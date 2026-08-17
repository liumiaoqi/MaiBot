"""ZG-24 测试：裁切后历史写回 runtime。

验证 spec 8.3 验证项 2：裁切后 runtime.apply_trimmed_history 被调用。
"""

from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.session_id = "test_session"
    runtime.apply_trimmed_history = MagicMock()
    runtime._trigger_trimmed_history_learning = AsyncMock()
    return runtime


def _make_mock_adapter(runtime: MagicMock) -> MagicMock:
    adapter = MagicMock()
    adapter._runtime = runtime
    adapter.chat_history = [MagicMock()]
    return adapter


class TestTrimWritesBackHistory:
    """验证裁切后历史写回 runtime.apply_trimmed_history。"""

    def test_writes_back_trimmed_history(self) -> None:
        """裁切后 result.history 写回 runtime.apply_trimmed_history。"""
        from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

        runtime = _make_mock_runtime()
        adapter = _make_mock_adapter(runtime)
        service = MagicMock()
        service._resolve_context_window = MagicMock(return_value=65536)

        organ = ThinkingOrgan(
            agent_id="test_agent",
            prompt_builder=MagicMock(),
            chat_loop_service=service,
            tool_registry=MagicMock(),
            chat_loop_adapter=adapter,
        )

        trimmed_history = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.history = trimmed_history
        mock_result.removed_messages = []
        mock_result.removed_count = 0
        mock_result.remaining_context_count = 2

        with patch(
            "src.maisaka.context.post_processor.process_chat_history_after_cycle",
            return_value=mock_result,
        ):
            organ._trigger_post_cycle_trim(request_kind="planner")

        runtime.apply_trimmed_history.assert_called_once_with(trimmed_history)

    def test_no_write_back_when_no_runtime(self) -> None:
        """runtime 为 None 时不写回（adapter 无 _runtime）。"""
        from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

        adapter = MagicMock()
        adapter._runtime = None
        adapter.chat_history = [MagicMock()]

        service = MagicMock()
        service._resolve_context_window = MagicMock(return_value=65536)

        organ = ThinkingOrgan(
            agent_id="test_agent",
            prompt_builder=MagicMock(),
            chat_loop_service=service,
            tool_registry=MagicMock(),
            chat_loop_adapter=adapter,
        )

        with patch(
            "src.maisaka.context.post_processor.process_chat_history_after_cycle",
        ) as trim_mock:
            organ._trigger_post_cycle_trim(request_kind="planner")

        trim_mock.assert_not_called()