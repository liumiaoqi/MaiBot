"""ZG-24 测试：thinking_organ 调用 process_chat_history_after_cycle（生产路径覆盖）。

验证 spec 8.3 验证项 1：chat_loop_step 执行后 process_chat_history_after_cycle 被调用。
接线点在 thinking_organ.py _trigger_post_cycle_trim，_think_with_tools 内调用。
"""

from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_runtime() -> MagicMock:
    """构造 mock runtime（含 apply_trimmed_history + _trigger_trimmed_history_learning）。"""
    runtime = MagicMock()
    runtime.session_id = "test_session"
    runtime.apply_trimmed_history = MagicMock()
    runtime._trigger_trimmed_history_learning = AsyncMock()
    return runtime


def _make_mock_adapter(runtime: MagicMock) -> MagicMock:
    """构造 mock chat_loop_adapter（含 _runtime + chat_history）。"""
    adapter = MagicMock()
    adapter._runtime = runtime
    adapter.chat_history = [MagicMock()]
    return adapter


class TestChatLoopStepTriggersTrim:
    """验证 thinking_organ._trigger_post_cycle_trim 调用 process_chat_history_after_cycle。"""

    def test_trim_called_with_session_id(self) -> None:
        """_trigger_post_cycle_trim 调用 process_chat_history_after_cycle 且传 session_id。"""
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
        ) as trim_mock:
            organ._trigger_post_cycle_trim(request_kind="planner")

        trim_mock.assert_called_once()
        assert trim_mock.call_args.kwargs["session_id"] == "test_session"

    def test_trim_called_with_max_context_size(self) -> None:
        """_trigger_post_cycle_trim 传 max_context_size 从 _resolve_context_window 获取。"""
        from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

        runtime = _make_mock_runtime()
        adapter = _make_mock_adapter(runtime)
        service = MagicMock()
        service._resolve_context_window = MagicMock(return_value=32768)

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
        ) as trim_mock:
            organ._trigger_post_cycle_trim(request_kind="planner")

        assert trim_mock.call_args.kwargs["max_context_size"] == 32768