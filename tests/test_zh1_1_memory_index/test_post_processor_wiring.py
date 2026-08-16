"""ZH1-1a post_processor 裁切接线测试 — 裁切后入队摘要 build。

覆盖 spec 5.4.1 规则 3-4、5.4.3 场景 1-2：裁切触发入队、
空 removed 跳过、session_id 传递、异步不阻塞、既有裁切不变。
"""

from unittest.mock import MagicMock, patch


from src.maisaka.context.post_processor import (
    process_chat_history_after_cycle,
)


def _make_ctx_msg(text: str = "ctx") -> MagicMock:
    """构造 mock LLMContextMessage（通过裁切前置过滤）。"""
    msg = MagicMock()
    msg.source = "normal"  # 不在 FOCUS_WAKEUP_SOURCE_KINDS
    msg.consume_once.return_value = True  # 保留
    msg.count_in_context = True
    msg.processed_plain_text = text
    return msg


def _patch_normalize(history_list):
    """patch _normalize_history_structure 返回原列表（无移除）。"""
    return patch(
        "src.maisaka.context.post_processor._normalize_history_structure",
        return_value=(list(history_list), 0, 0),
    )


class TestPostProcessorWiring:
    """post_processor 裁切接线测试。"""

    def test_trim_triggers_enqueue(self) -> None:
        """裁切触发且 removed_messages 非空 → 入队（spec 5.4.1 规则 3）。"""
        history = [_make_ctx_msg(f"m{i}") for i in range(20)]
        removed = [_make_ctx_msg("removed1"), _make_ctx_msg("removed2")]
        enqueue_mock = MagicMock()
        with _patch_normalize(history), \
             patch("src.maisaka.context.post_processor._trim_history_to_context_target", return_value=removed), \
             patch("src.maisaka.context.post_processor._enqueue_mid_term_summary_build", new=enqueue_mock):
            process_chat_history_after_cycle(
                history, max_context_size=2, session_id="sess1",
            )
        enqueue_mock.assert_called_once()
        call_kwargs = enqueue_mock.call_args
        assert call_kwargs.kwargs["session_id"] == "sess1"

    def test_empty_removed_skip(self) -> None:
        """removed_messages 为空跳过入队。"""
        history = [_make_ctx_msg(f"m{i}") for i in range(20)]
        enqueue_mock = MagicMock()
        with _patch_normalize(history), \
             patch("src.maisaka.context.post_processor._trim_history_to_context_target", return_value=[]), \
             patch("src.maisaka.context.post_processor._enqueue_mid_term_summary_build", new=enqueue_mock):
            result = process_chat_history_after_cycle(
                history, max_context_size=100, session_id="sess1",
            )
        enqueue_mock.assert_not_called()
        assert result.removed_messages == []

    def test_session_id_passed(self) -> None:
        """session_id 传递到入队调用。"""
        history = [_make_ctx_msg(f"m{i}") for i in range(20)]
        removed = [_make_ctx_msg("r1")]
        enqueue_mock = MagicMock()
        with _patch_normalize(history), \
             patch("src.maisaka.context.post_processor._trim_history_to_context_target", return_value=removed), \
             patch("src.maisaka.context.post_processor._enqueue_mid_term_summary_build", new=enqueue_mock):
            process_chat_history_after_cycle(
                history, max_context_size=2, session_id="group:999",
            )
        assert enqueue_mock.call_args.kwargs["session_id"] == "group:999"

    def test_no_session_id_skip_enqueue(self) -> None:
        """无 session_id 时 _enqueue 内部跳过（spec 5.4.3 场景 1）。"""
        from src.maisaka.context.post_processor import _enqueue_mid_term_summary_build

        # 直接测试 _enqueue 在无 session_id 时不入队
        enqueue_mock = MagicMock()
        with patch("src.maisaka.memory.mid_term_summary_queue.get_mid_term_summary_queue", new=enqueue_mock):
            _enqueue_mid_term_summary_build([_make_ctx_msg()], session_id="")
        enqueue_mock.assert_not_called()

    def test_async_not_block(self) -> None:
        """异步不阻塞：process_chat_history_after_cycle 同步返回（enqueue 内部 put_nowait）。"""
        import time

        history = [_make_ctx_msg(f"m{i}") for i in range(20)]
        removed = [_make_ctx_msg("r1")]
        start = time.perf_counter()
        with _patch_normalize(history), \
             patch("src.maisaka.context.post_processor._trim_history_to_context_target", return_value=removed), \
             patch("src.maisaka.context.post_processor._enqueue_mid_term_summary_build"):
            process_chat_history_after_cycle(
                history, max_context_size=2, session_id="sess1",
            )
        elapsed = time.perf_counter() - start
        # 同步函数应快速返回（enqueue 不阻塞）
        assert elapsed < 0.1

    def test_existing_trim_unchanged(self) -> None:
        """既有裁切不变：removed_messages 仍出现在返回结果中。"""
        history = [_make_ctx_msg(f"m{i}") for i in range(20)]
        removed = [_make_ctx_msg("r1"), _make_ctx_msg("r2")]
        with _patch_normalize(history), \
             patch("src.maisaka.context.post_processor._trim_history_to_context_target", return_value=removed), \
             patch("src.maisaka.context.post_processor._enqueue_mid_term_summary_build"):
            result = process_chat_history_after_cycle(
                history, max_context_size=2, session_id="sess1",
            )
        # removed_messages 仍在结果中（既有裁切逻辑不变）
        assert result.removed_messages == removed
        assert result.removed_count >= len(removed)