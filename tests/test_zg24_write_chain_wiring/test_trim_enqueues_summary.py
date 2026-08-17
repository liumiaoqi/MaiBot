"""ZG-24 测试：removed_messages 非空时入队摘要 build。

验证 spec 8.3 验证项 3：process_chat_history_after_cycle 被调用（内部 enqueue 由 ZH1-1a 测试覆盖）。
入队由 process_chat_history_after_cycle 内部 _enqueue_mid_term_summary_build 完成，
ZH1-1a test_post_processor_wiring.py 已覆盖 enqueue 逻辑，本测试验证接线点调用。
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


class TestTrimEnqueuesSummary:
    """验证 process_chat_history_after_cycle 被调用（enqueue 入口）。"""

    def test_trim_called_when_history_non_empty(self) -> None:
        """history 非空 → process_chat_history_after_cycle 被调用（enqueue 入口）。"""
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
        ) as trim_mock, patch("asyncio.create_task"):
            organ._trigger_post_cycle_trim(request_kind="planner")

        trim_mock.assert_called_once()
        assert trim_mock.call_args.kwargs["session_id"] == "test_session"

    def test_no_trim_when_history_empty(self) -> None:
        """history 为空 → process_chat_history_after_cycle 不被调用。"""
        from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

        runtime = _make_mock_runtime()
        adapter = MagicMock()
        adapter._runtime = runtime
        adapter.chat_history = []

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
