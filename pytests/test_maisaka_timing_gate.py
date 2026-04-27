from datetime import datetime
from types import SimpleNamespace

import pytest

from src.core.tooling import ToolExecutionResult
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.chat_loop_service import ChatResponse, MaisakaChatLoopService
from src.maisaka.context_messages import AssistantMessage, TIMING_GATE_INVALID_TOOL_HINT_SOURCE
from src.maisaka.reasoning_engine import MaisakaReasoningEngine


def _build_chat_response(tool_calls: list[ToolCall]) -> ChatResponse:
    return ChatResponse(
        content="The model returned an invalid timing tool.",
        tool_calls=tool_calls,
        request_messages=[],
        raw_message=AssistantMessage(
            content="",
            timestamp=datetime.now(),
            source_kind="perception",
        ),
        selected_history_count=1,
        tool_count=len(tool_calls),
        prompt_tokens=10,
        built_message_count=1,
        completion_tokens=3,
        total_tokens=13,
        prompt_section=None,
    )


@pytest.mark.asyncio
async def test_timing_gate_invalid_tool_defaults_to_no_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = SimpleNamespace(
        _force_next_timing_continue=False,
        _chat_history=[],
        log_prefix="[test]",
        stopped=False,
    )

    def _enter_stop_state() -> None:
        runtime.stopped = True

    runtime._enter_stop_state = _enter_stop_state
    engine = MaisakaReasoningEngine(runtime)  # type: ignore[arg-type]

    async def _fake_timing_gate_sub_agent(**kwargs: object) -> ChatResponse:
        del kwargs
        return _build_chat_response([
            ToolCall(call_id="invalid-timing-tool", func_name="finish", args={}),
        ])

    async def _fail_invoke_tool_call(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("invalid timing tools must not be executed")

    monkeypatch.setattr(engine, "_run_timing_gate_sub_agent", _fake_timing_gate_sub_agent)
    monkeypatch.setattr(engine, "_invoke_tool_call", _fail_invoke_tool_call)

    action, response, tool_results, tool_monitor_results = await engine._run_timing_gate(object())  # type: ignore[arg-type]

    assert action == "no_reply"
    assert response.tool_calls[0].func_name == "finish"
    assert runtime.stopped is True
    assert tool_monitor_results == []
    assert len(runtime._chat_history) == 1
    assert runtime._chat_history[0].source == TIMING_GATE_INVALID_TOOL_HINT_SOURCE
    assert "finish" in runtime._chat_history[0].processed_plain_text
    assert tool_results == [
        "- no_reply [非法 Timing 工具]: 返回了 finish，已停止本轮并等待新消息",
    ]


def test_timing_gate_invalid_tool_hint_keeps_only_latest() -> None:
    old_hint = SimpleNamespace(source=TIMING_GATE_INVALID_TOOL_HINT_SOURCE)
    runtime = SimpleNamespace(_chat_history=[old_hint])
    engine = MaisakaReasoningEngine(runtime)  # type: ignore[arg-type]

    engine._append_timing_gate_invalid_tool_hint("finish")
    engine._append_timing_gate_invalid_tool_hint("reply")

    assert len(runtime._chat_history) == 1
    hint_message = runtime._chat_history[0]
    assert hint_message.source == TIMING_GATE_INVALID_TOOL_HINT_SOURCE
    assert "reply" in hint_message.processed_plain_text
    assert "finish" not in hint_message.processed_plain_text


def test_timing_gate_invalid_tool_hint_only_visible_to_timing_gate() -> None:
    runtime = SimpleNamespace(_chat_history=[])
    engine = MaisakaReasoningEngine(runtime)  # type: ignore[arg-type]
    engine._append_timing_gate_invalid_tool_hint("finish")
    hint_message = runtime._chat_history[0]

    timing_history = MaisakaChatLoopService._filter_history_for_request_kind(
        [hint_message],
        request_kind="timing_gate",
    )
    planner_history = MaisakaChatLoopService._filter_history_for_request_kind(
        [hint_message],
        request_kind="planner",
    )

    assert timing_history == [hint_message]
    assert planner_history == []


def test_finish_tool_is_not_written_back_to_history() -> None:
    finish_call = ToolCall(call_id="finish-call", func_name="finish", args={})
    reply_call = ToolCall(call_id="reply-call", func_name="reply", args={})
    assistant_message = AssistantMessage(
        content="当前不需要继续回复。",
        timestamp=datetime.now(),
        tool_calls=[finish_call, reply_call],
    )
    runtime = SimpleNamespace(_chat_history=[assistant_message])
    engine = MaisakaReasoningEngine(runtime)  # type: ignore[arg-type]

    engine._append_tool_execution_result(
        finish_call,
        ToolExecutionResult(
            tool_name="finish",
            success=True,
            content="当前对话循环已结束本轮思考，等待新的消息到来。",
        ),
    )

    assert runtime._chat_history == [assistant_message]
    assert [tool_call.func_name for tool_call in assistant_message.tool_calls] == ["reply"]


def test_finish_tool_removes_empty_assistant_history_message() -> None:
    finish_call = ToolCall(call_id="finish-call", func_name="finish", args={})
    assistant_message = AssistantMessage(
        content="",
        timestamp=datetime.now(),
        tool_calls=[finish_call],
    )
    runtime = SimpleNamespace(_chat_history=[assistant_message])
    engine = MaisakaReasoningEngine(runtime)  # type: ignore[arg-type]

    engine._append_tool_execution_result(
        finish_call,
        ToolExecutionResult(tool_name="finish", success=True),
    )

    assert runtime._chat_history == []
