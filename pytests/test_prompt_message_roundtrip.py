from src.llm_models.payload_content.message import MessageBuilder, RoleType
from src.plugin_runtime.hook_payloads import deserialize_prompt_messages, serialize_prompt_messages


def test_prompt_messages_roundtrip_preserves_image_parts() -> None:
    messages = [
        MessageBuilder().set_role(RoleType.User).add_text_content("你好").add_image_content("png", "ZmFrZQ==").build(),
    ]

    serialized_messages = serialize_prompt_messages(messages)
    restored_messages = deserialize_prompt_messages(serialized_messages)

    assert len(restored_messages) == 1
    assert restored_messages[0].role == RoleType.User
    assert restored_messages[0].get_text_content() == "你好"
    assert len(restored_messages[0].parts) == 2
    assert restored_messages[0].parts[1].image_format == "png"
    assert restored_messages[0].parts[1].image_base64 == "ZmFrZQ=="
