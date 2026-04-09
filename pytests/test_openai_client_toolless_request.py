from src.llm_models.model_client.openai_client import _sanitize_messages_for_toolless_request
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart
from src.llm_models.payload_content.tool_option import ToolCall


def test_sanitize_messages_for_toolless_request_drops_assistant_tool_call_without_parts() -> None:
    messages = [
        Message(
            role=RoleType.Assistant,
            tool_calls=[
                ToolCall(
                    call_id="call_1",
                    func_name="mute_user",
                    args={"target": "alice"},
                )
            ],
        ),
        Message(
            role=RoleType.User,
            parts=[TextMessagePart(text="继续")],
        ),
    ]

    sanitized_messages = _sanitize_messages_for_toolless_request(messages)

    assert len(sanitized_messages) == 1
    assert sanitized_messages[0].role == RoleType.User
