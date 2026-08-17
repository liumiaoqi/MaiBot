"""ZG-24 测试：removed_messages 非空时触发裁切历史学习。

验证 spec 8.3 验证项 4：_trigger_trimmed_history_learning 被 fire-and-forget 触发。
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


class TestTrimTriggersLearning:
    """验证 removed_messages 非空时 _trigger_trimmed_history_learning 被触发。"""

    def test_learning_triggered_when_removed_non_empty(self) -> None:
        """removed_messages 非空 → _trigger_trimmed_history_learning 被 create_task 触发。"""
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

        removed = [MagicMock(), MagicMock()]
        mock_result = MagicMock()
        mock_result.history = []
        mock_result.removed_messages = removed
        mock_result.removed_count = 2
        mock_result.remaining_context_count = 5

        with patch(
            "src.maisaka.context.post_processor.process_chat_history_after_cycle",
            return_value=mock_result,
        ), patch("asyncio.create_task"):
            organ._trigger_post_cycle_trim(request_kind="planner")

        runtime._trigger_trimmed_history_learning.assert_called_once_with(removed)

    def test_no_learning_when_removed_empty(self) -> None:
        """removed_messages 为空 → _trigger_trimmed_history_learning 不被调用。"""
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

        mock_result = MagicMock()
        mock_result.history = []
        mock_result.removed_messages = []
        mock_result.removed_count = 0
        mock_result.remaining_context_count = 5

        with patch(
            "src.maisaka.context.post_processor.process_chat_history_after_cycle",
            return_value=mock_result,
        ):
            organ._trigger_post_cycle_trim(request_kind="planner")

        runtime._trigger_trimmed_history_learning.assert_not_called()