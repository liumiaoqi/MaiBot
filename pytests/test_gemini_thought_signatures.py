import base64
import sys
from types import ModuleType, SimpleNamespace


config_module = ModuleType("src.config.config")


class _ConfigManagerStub:
    def get_model_config(self) -> SimpleNamespace:
        return SimpleNamespace(api_providers=[])

    def register_reload_callback(self, _: object) -> None:
        return None


config_module.config_manager = _ConfigManagerStub()
sys.modules.setdefault("src.config.config", config_module)

from src.llm_models.model_client import gemini_client
from src.llm_models.payload_content.message import MessageBuilder, RoleType
from src.llm_models.payload_content.tool_option import ToolCall


def _encode_signature(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def test_convert_messages_preserves_gemini_function_call_signature_and_tool_result_id() -> None:
    thought_signature = b"gemini-signature"
    tool_call = ToolCall(
        call_id="call-1",
        func_name="reply",
        args={"msg_id": "42"},
        extra_content={"google": {"thought_signature": _encode_signature(thought_signature)}},
    )
    assistant_message = MessageBuilder().set_role(RoleType.Assistant).set_tool_calls([tool_call]).build()
    tool_message = (
        MessageBuilder()
        .set_role(RoleType.Tool)
        .set_tool_call_id("call-1")
        .set_tool_name("reply")
        .add_text_content('{"ok": true}')
        .build()
    )

    contents, _ = gemini_client._convert_messages([assistant_message, tool_message])

    assistant_part = contents[0].parts[0]
    assert assistant_part.function_call is not None
    assert assistant_part.function_call.id == "call-1"
    assert assistant_part.function_call.name == "reply"
    assert assistant_part.thought_signature == thought_signature

    tool_part = contents[1].parts[0]
    assert tool_part.function_response is not None
    assert tool_part.function_response.id == "call-1"
    assert tool_part.function_response.name == "reply"
    assert tool_part.function_response.response == {"ok": True}


def test_convert_messages_injects_dummy_signature_for_first_historical_tool_call() -> None:
    tool_calls = [
        ToolCall(call_id="call-1", func_name="reply", args={"msg_id": "1"}),
        ToolCall(call_id="call-2", func_name="reply", args={"msg_id": "2"}),
    ]
    assistant_message = MessageBuilder().set_role(RoleType.Assistant).set_tool_calls(tool_calls).build()

    contents, _ = gemini_client._convert_messages([assistant_message])

    assert contents[0].parts[0].thought_signature == gemini_client.GEMINI_FALLBACK_THOUGHT_SIGNATURE
    assert contents[0].parts[1].thought_signature is None
