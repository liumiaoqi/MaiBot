from pathlib import Path

import json

from src.config.model_configs import APIProvider, ModelInfo
from src.llm_models.model_client.base_client import ResponseRequest
from src.llm_models.payload_content.message import MessageBuilder, RoleType
from src.llm_models.payload_content.resp_format import RespFormat, RespFormatType
from src.llm_models.payload_content.tool_option import ToolCall, ToolOption
from src.llm_models.request_snapshot import (
    attach_request_snapshot,
    deserialize_messages_snapshot,
    format_request_snapshot_log_info,
    save_failed_request_snapshot,
    serialize_messages_snapshot,
    serialize_response_request_snapshot,
)
from src.llm_models import request_snapshot


def _build_api_provider() -> APIProvider:
    return APIProvider(
        api_key="secret-token",
        base_url="https://example.com/v1",
        name="test-provider",
    )


def _build_model_info() -> ModelInfo:
    return ModelInfo(
        api_provider="test-provider",
        model_identifier="demo-model",
        name="demo-model",
    )


def _build_response_request() -> ResponseRequest:
    tool_call = ToolCall(
        args={"query": "MaiBot"},
        call_id="call_1",
        func_name="search_web",
        extra_content={"google": {"thought_signature": "c2lnbmF0dXJl"}},
    )
    message_list = [
        MessageBuilder().set_role(RoleType.User).add_text_content("你好").add_image_content("png", "ZmFrZQ==").build(),
        MessageBuilder().set_role(RoleType.Assistant).set_tool_calls([tool_call]).build(),
        MessageBuilder()
        .set_role(RoleType.Tool)
        .set_tool_call_id("call_1")
        .set_tool_name("search_web")
        .add_text_content('{"ok": true}')
        .build(),
    ]
    return ResponseRequest(
        extra_params={"trace_id": "trace-123"},
        max_tokens=256,
        message_list=message_list,
        model_info=_build_model_info(),
        response_format=RespFormat(RespFormatType.JSON_OBJ),
        temperature=0.2,
        tool_options=[ToolOption(name="search_web", description="搜索网页")],
    )


def test_message_snapshot_roundtrip_preserves_tool_messages() -> None:
    request = _build_response_request()

    snapshot_messages = serialize_messages_snapshot(request.message_list)
    restored_messages = deserialize_messages_snapshot(snapshot_messages)

    assert len(restored_messages) == 3
    assert restored_messages[0].role == RoleType.User
    assert restored_messages[0].get_text_content() == "你好"
    assert restored_messages[0].parts[1].image_format == "png"
    assert restored_messages[1].role == RoleType.Assistant
    assert restored_messages[1].tool_calls is not None
    assert restored_messages[1].tool_calls[0].func_name == "search_web"
    assert restored_messages[1].tool_calls[0].args == {"query": "MaiBot"}
    assert restored_messages[1].tool_calls[0].extra_content == {"google": {"thought_signature": "c2lnbmF0dXJl"}}
    assert restored_messages[2].role == RoleType.Tool
    assert restored_messages[2].tool_call_id == "call_1"
    assert restored_messages[2].tool_name == "search_web"


def test_failed_request_snapshot_contains_replay_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(request_snapshot, "LLM_REQUEST_LOG_DIR", tmp_path)

    request = _build_response_request()
    provider = _build_api_provider()
    snapshot_path = save_failed_request_snapshot(
        api_provider=provider,
        client_type="openai",
        error=RuntimeError("boom"),
        internal_request=serialize_response_request_snapshot(request),
        model_info=request.model_info,
        operation="chat.completions.create",
        provider_request={"request_kwargs": {"model": request.model_info.model_identifier}},
    )

    assert snapshot_path is not None
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert payload["internal_request"]["request_kind"] == "response"
    assert payload["api_provider"]["name"] == "test-provider"
    assert payload["replay"]["file_uri"] == snapshot_path.as_uri()
    assert str(snapshot_path) in payload["replay"]["command"]
    assert "secret-token" not in snapshot_path.read_text(encoding="utf-8")


def test_format_request_snapshot_log_info_includes_path_uri_and_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(request_snapshot, "LLM_REQUEST_LOG_DIR", tmp_path)

    request = _build_response_request()
    snapshot_path = save_failed_request_snapshot(
        api_provider=_build_api_provider(),
        client_type="openai",
        error=ValueError("invalid"),
        internal_request=serialize_response_request_snapshot(request),
        model_info=request.model_info,
        operation="chat.completions.create",
        provider_request={"request_kwargs": {"messages": []}},
    )

    assert snapshot_path is not None
    exc = RuntimeError("wrapped")
    attach_request_snapshot(exc, snapshot_path)

    log_info = format_request_snapshot_log_info(exc)
    assert str(snapshot_path) in log_info
    assert snapshot_path.as_uri() in log_info
    assert "uv run python scripts/replay_llm_request.py" in log_info
