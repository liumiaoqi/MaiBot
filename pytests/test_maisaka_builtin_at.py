from importlib import util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import sys

import pytest

from src.common.data_models.message_component_data_model import AtComponent, TextComponent
from src.core.tooling import ToolExecutionResult, ToolInvocation

_MISSING_MODULE = object()
_module_overrides: dict[str, object] = {}


def _override_module(module_name: str, module: ModuleType) -> None:
    _module_overrides[module_name] = sys.modules.get(module_name, _MISSING_MODULE)
    sys.modules[module_name] = module


def _restore_overridden_modules() -> None:
    for module_name, previous_module in reversed(_module_overrides.items()):
        if previous_module is _MISSING_MODULE:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
    _module_overrides.clear()


fake_cli_sender_module = ModuleType("src.cli.maisaka_cli_sender")
fake_cli_sender_module.CLI_PLATFORM_NAME = "cli"
fake_cli_sender_module.render_cli_message = lambda text: text
fake_cli_module = ModuleType("src.cli")
fake_cli_module.maisaka_cli_sender = fake_cli_sender_module

fake_send_service_module = ModuleType("src.services.send_service")
fake_send_service_module._send_to_target_with_message = None
fake_services_module = ModuleType("src.services")
fake_services_module.send_service = fake_send_service_module

_override_module("src.cli", fake_cli_module)
_override_module("src.cli.maisaka_cli_sender", fake_cli_sender_module)
_override_module("src.services", fake_services_module)
_override_module("src.services.send_service", fake_send_service_module)

AT_TOOL_PATH = Path(__file__).resolve().parents[1] / "src" / "maisaka" / "builtin_tool" / "at.py"
at_tool_spec = util.spec_from_file_location("_test_maisaka_builtin_at_tool", AT_TOOL_PATH)
assert at_tool_spec is not None and at_tool_spec.loader is not None
at_tool = util.module_from_spec(at_tool_spec)
sys.modules["_test_maisaka_builtin_at_tool"] = at_tool
try:
    at_tool_spec.loader.exec_module(at_tool)
finally:
    _restore_overridden_modules()


class _ToolCtx:
    def __init__(self, runtime: SimpleNamespace) -> None:
        self.runtime = runtime

    @staticmethod
    def build_success_result(
        tool_name: str,
        content: str = "",
        structured_content: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            success=True,
            content=content,
            structured_content=structured_content,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def build_failure_result(
        tool_name: str,
        error_message: str,
        structured_content: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            success=False,
            error_message=error_message,
            structured_content=structured_content,
            metadata=dict(metadata or {}),
        )

    def append_guided_reply_to_chat_history(self, reply_text: str) -> None:
        self.runtime._chat_history.append(reply_text)


def _build_tool_ctx(*, group_id: str = "group-1") -> _ToolCtx:
    target_message = SimpleNamespace(
        message_info=SimpleNamespace(
            user_info=SimpleNamespace(
                user_id="target-user-1",
                user_nickname="目标昵称",
                user_cardname="群名片",
            )
        )
    )
    runtime = SimpleNamespace(
        _source_messages_by_id={"msg-1": target_message},
        chat_stream=SimpleNamespace(platform="qq", group_id=group_id),
        session_id="session-1",
        log_prefix="[test-at]",
        _record_reply_sent=lambda: None,
        _chat_history=[],
    )
    return _ToolCtx(runtime=runtime)


def test_at_tool_spec_does_not_embed_visibility_metadata() -> None:
    tool_spec = at_tool.get_tool_spec()

    assert tool_spec.name == "at"
    assert "deferred" not in tool_spec.metadata
    assert "visibility" not in tool_spec.metadata


@pytest.mark.asyncio
async def test_at_tool_sends_at_component_by_msg_id(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_send_to_target_with_message(**kwargs: Any) -> object:
        captured.update(kwargs)
        return SimpleNamespace(message_id="sent-msg-1")

    monkeypatch.setattr(at_tool.send_service, "_send_to_target_with_message", fake_send_to_target_with_message)

    result = await at_tool.handle_tool(
        _build_tool_ctx(),
        ToolInvocation(tool_name="at", arguments={"msg_id": "msg-1", "text": "看这里"}),
    )

    assert result.success is True
    assert result.structured_content["target_user_id"] == "target-user-1"
    assert result.structured_content["target_user_name"] == "群名片"
    assert captured["stream_id"] == "session-1"
    assert captured["display_message"] == "@群名片 看这里"
    assert captured["sync_to_maisaka_history"] is True
    assert captured["maisaka_source_kind"] == "guided_reply"

    components = captured["message_sequence"].components
    assert isinstance(components[0], AtComponent)
    assert components[0].target_user_id == "target-user-1"
    assert components[0].target_user_nickname == "目标昵称"
    assert components[0].target_user_cardname == "群名片"
    assert isinstance(components[1], TextComponent)
    assert components[1].text == " 看这里"


@pytest.mark.asyncio
async def test_at_tool_rejects_private_chat() -> None:
    result = await at_tool.handle_tool(
        _build_tool_ctx(group_id=""),
        ToolInvocation(tool_name="at", arguments={"msg_id": "msg-1"}),
    )

    assert result.success is False
    assert "群聊" in result.error_message


@pytest.mark.asyncio
async def test_at_tool_rejects_unknown_msg_id() -> None:
    result = await at_tool.handle_tool(
        _build_tool_ctx(),
        ToolInvocation(tool_name="at", arguments={"msg_id": "missing-msg"}),
    )

    assert result.success is False
    assert result.structured_content == {"msg_id": "missing-msg"}
