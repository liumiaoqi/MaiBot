"""ZG-24 测试：裁切失败不阻塞回复。

验证 spec 4.2 规则 1：裁切失败 → _trigger_post_cycle_trim 不抛异常。
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


class TestTrimFailureNoBlock:
    """验证裁切失败不阻塞回复。"""

    def test_trim_exception_no_raise(self) -> None:
        """process_chat_history_after_cycle 抛异常 → _trigger_post_cycle_trim 不抛。"""
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

        with patch(
            "src.maisaka.context.post_processor.process_chat_history_after_cycle",
            side_effect=RuntimeError("trim failed"),
        ):
            organ._trigger_post_cycle_trim(request_kind="planner")

    def test_write_back_exception_no_raise(self) -> None:
        """apply_trimmed_history 抛异常 → _trigger_post_cycle_trim 不抛。"""
        from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

        runtime = _make_mock_runtime()
        runtime.apply_trimmed_history = MagicMock(side_effect=RuntimeError("write back failed"))
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

    def test_empty_history_no_raise(self) -> None:
        """chat_history 为空 → _trigger_post_cycle_trim 不抛（提前 return）。"""
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