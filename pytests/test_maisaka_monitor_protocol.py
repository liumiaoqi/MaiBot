from types import SimpleNamespace
from typing import Any, Callable

import pytest

from src.chat.replyer import maisaka_generator as legacy_replyer_module
from src.chat.replyer import maisaka_generator_multi as multimodal_replyer_module
from src.common.data_models.reply_generation_data_models import (
    GenerationMetrics,
    LLMCompletionResult,
    ReplyGenerationResult,
)
from src.core.tooling import ToolExecutionResult, ToolInvocation
from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext
from src.maisaka.builtin_tool import reply as reply_tool_module
from src.maisaka.monitor_events import emit_planner_finalized
from src.maisaka.reasoning_engine import MaisakaReasoningEngine


class _FakeLLMResult:
    def __init__(self) -> None:
        self.response = "测试回复"
        self.reasoning = "先理解上下文，再给出自然回复。"
        self.model_name = "fake-model"
        self.tool_calls = []
        self.prompt_tokens = 12
        self.completion_tokens = 7
        self.total_tokens = 19


class _FakeLegacyLLMServiceClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args
        del kwargs

    async def generate_response(self, prompt: str) -> _FakeLLMResult:
        assert prompt
        return _FakeLLMResult()


class _FakeMultimodalLLMServiceClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args
        del kwargs

    async def generate_response_with_messages(self, *, message_factory: Callable[[object], list[Any]]) -> _FakeLLMResult:
        assert message_factory(object())
        return _FakeLLMResult()


@pytest.mark.asyncio
async def test_legacy_and_multimodal_replyer_monitor_detail_have_same_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(legacy_replyer_module, "LLMServiceClient", _FakeLegacyLLMServiceClient)
    monkeypatch.setattr(multimodal_replyer_module, "LLMServiceClient", _FakeMultimodalLLMServiceClient)
    monkeypatch.setattr(legacy_replyer_module, "load_prompt", lambda *args, **kwargs: "legacy prompt")
    monkeypatch.setattr(multimodal_replyer_module, "load_prompt", lambda *args, **kwargs: "multi prompt")

    legacy_generator = legacy_replyer_module.MaisakaReplyGenerator(chat_stream=None, request_type="test_legacy")
    multimodal_generator = multimodal_replyer_module.MaisakaReplyGenerator(chat_stream=None, request_type="test_multi")

    legacy_success, legacy_result = await legacy_generator.generate_reply_with_context(
        stream_id="session-legacy",
        chat_history=[],
        reply_reason="测试原因",
    )
    multimodal_success, multimodal_result = await multimodal_generator.generate_reply_with_context(
        stream_id="session-multi",
        chat_history=[],
        reply_reason="测试原因",
    )

    assert legacy_success is True
    assert multimodal_success is True
    assert legacy_result.monitor_detail is not None
    assert multimodal_result.monitor_detail is not None
    assert set(legacy_result.monitor_detail.keys()) == set(multimodal_result.monitor_detail.keys())
    assert set(legacy_result.monitor_detail["metrics"].keys()) == set(multimodal_result.monitor_detail["metrics"].keys())
    assert legacy_result.monitor_detail["metrics"]["prompt_tokens"] == 12
    assert legacy_result.monitor_detail["metrics"]["completion_tokens"] == 7
    assert legacy_result.monitor_detail["metrics"]["total_tokens"] == 19


@pytest.mark.asyncio
async def test_reply_tool_puts_monitor_detail_into_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_monitor_detail = {
        "prompt_text": "reply prompt",
        "reasoning_text": "reply reasoning",
        "output_text": "reply output",
        "metrics": {"model_name": "fake-model", "total_tokens": 10},
    }
    fake_reply_result = ReplyGenerationResult(
        success=True,
        completion=LLMCompletionResult(response_text="测试回复"),
        metrics=GenerationMetrics(overall_ms=11.5),
        monitor_detail=fake_monitor_detail,
    )

    class _FakeReplyer:
        async def generate_reply_with_context(self, **kwargs: Any) -> tuple[bool, ReplyGenerationResult]:
            del kwargs
            return True, fake_reply_result

    monkeypatch.setattr(reply_tool_module.replyer_manager, "get_replyer", lambda **kwargs: _FakeReplyer())
    monkeypatch.setattr(reply_tool_module, "render_cli_message", lambda text: text)

    target_message = SimpleNamespace(
        message_id="msg-1",
        message_info=SimpleNamespace(
            user_info=SimpleNamespace(
                user_cardname="测试用户",
                user_nickname="测试用户",
                user_id="user-1",
            )
        ),
    )
    runtime = SimpleNamespace(
        _source_messages_by_id={"msg-1": target_message},
        log_prefix="[test]",
        chat_stream=SimpleNamespace(platform=reply_tool_module.CLI_PLATFORM_NAME),
        session_id="session-1",
        _chat_history=[],
        _clear_force_continue_until_reply=lambda: None,
        run_sub_agent=None,
    )
    engine = SimpleNamespace(_get_runtime_manager=lambda: None)
    tool_ctx = BuiltinToolRuntimeContext(engine=engine, runtime=runtime)
    invocation = ToolInvocation(tool_name="reply", arguments={"msg_id": "msg-1", "set_quote": True})

    result = await reply_tool_module.handle_tool(tool_ctx, invocation)

    assert result.success is True
    assert result.metadata["monitor_detail"] == fake_monitor_detail


@pytest.mark.asyncio
async def test_emit_planner_finalized_broadcasts_new_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _fake_broadcast(event: str, data: dict[str, Any]) -> None:
        captured["event"] = event
        captured["data"] = data

    monkeypatch.setattr("src.maisaka.monitor_events._broadcast", _fake_broadcast)

    await emit_planner_finalized(
        session_id="session-1",
        cycle_id=3,
        request_messages=[{"role": "user", "content": "你好"}],
        selected_history_count=5,
        tool_count=2,
        planner_content="先查询再回复",
        planner_tool_calls=[SimpleNamespace(call_id="call-1", func_name="reply", args={"msg_id": "m1"})],
        prompt_tokens=100,
        completion_tokens=30,
        total_tokens=130,
        duration_ms=88.5,
        tools=[
            {
                "tool_call_id": "call-1",
                "tool_name": "reply",
                "tool_args": {"msg_id": "m1"},
                "success": True,
                "duration_ms": 22.0,
                "summary": "- reply [成功]: 已回复",
                "detail": {"output_text": "测试回复"},
            }
        ],
        time_records={"planner": 0.1, "tool_calls": 0.2},
        agent_state="stop",
    )

    assert captured["event"] == "planner.finalized"
    payload = captured["data"]
    assert payload["request"]["messages"][0]["content"] == "你好"
    assert payload["request"]["tool_count"] == 2
    assert payload["planner"]["tool_calls"][0]["id"] == "call-1"
    assert payload["tools"][0]["detail"]["output_text"] == "测试回复"
    assert payload["final_state"]["agent_state"] == "stop"


def test_reasoning_engine_build_tool_monitor_result_keeps_non_reply_tool_without_detail() -> None:
    engine = object.__new__(MaisakaReasoningEngine)
    tool_call = SimpleNamespace(call_id="call-2", func_name="query_memory")
    invocation = ToolInvocation(tool_name="query_memory", arguments={"query": "Alice"})
    result = ToolExecutionResult(tool_name="query_memory", success=True, content="查询成功")

    tool_result = engine._build_tool_monitor_result(tool_call, invocation, result, duration_ms=18.6)

    assert tool_result["tool_call_id"] == "call-2"
    assert tool_result["tool_name"] == "query_memory"
    assert tool_result["tool_args"] == {"query": "Alice"}
    assert tool_result["detail"] is None
