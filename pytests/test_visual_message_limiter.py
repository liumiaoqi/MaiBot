from src.config.official_configs import VisualConfig
from src.llm_models.payload_content.message import ImageMessagePart, MessageBuilder, RoleType, TextMessagePart
from src.maisaka.visual_message_limiter import limit_latest_images_in_messages


def _image_message(image_base64: str):
    return MessageBuilder().set_role(RoleType.User).add_image_content("png", image_base64).build()


def test_visual_config_default_max_image_num() -> None:
    assert VisualConfig().max_image_num == 128


def test_limit_latest_images_replaces_old_images_with_placeholder() -> None:
    messages = [
        _image_message("oldest"),
        MessageBuilder()
        .set_role(RoleType.User)
        .add_text_content("中间消息")
        .add_image_content("png", "older")
        .add_image_content("png", "latest-2")
        .build(),
        _image_message("latest-1"),
    ]

    limited_messages = limit_latest_images_in_messages(messages, max_image_num=2)

    assert isinstance(limited_messages[0].parts[0], TextMessagePart)
    assert limited_messages[0].get_text_content() == "[图片]"
    assert isinstance(limited_messages[1].parts[1], TextMessagePart)
    assert limited_messages[1].parts[1].text == "[图片]"
    assert isinstance(limited_messages[1].parts[2], ImageMessagePart)
    assert limited_messages[1].parts[2].image_base64 == "latest-2"
    assert isinstance(limited_messages[2].parts[0], ImageMessagePart)
    assert limited_messages[2].parts[0].image_base64 == "latest-1"

    assert isinstance(messages[0].parts[0], ImageMessagePart)


def test_limit_latest_images_zero_replaces_all_images() -> None:
    limited_messages = limit_latest_images_in_messages([_image_message("image")], max_image_num=0)

    assert limited_messages[0].get_text_content() == "[图片]"
    assert not any(isinstance(part, ImageMessagePart) for part in limited_messages[0].parts)
