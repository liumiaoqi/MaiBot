"""speaker_projection 的投影语义（批次 2）。"""

from src.llm_models.payload_content.message import (
    ImageMessagePart,
    Message,
    RoleType,
    TextMessagePart,
)
from src.maisaka.context.attribution import AttributionDecision
from src.maisaka.context.speaker_projection import (
    project_message,
    rewrite_message_header,
    strip_leading_speaker_tag,
)


TAG_FORMAT = "【{agent_name}】"


def _msg(text: str, role: RoleType = RoleType.User) -> Message:
    return Message(role=role, parts=[TextMessagePart(text=text)])


def test_strip_only_leading_tag():
    text = '【银狼】<message user="银狼">\n正文'
    stripped, tag = strip_leading_speaker_tag(text, TAG_FORMAT)

    assert tag == "【银狼】"
    assert stripped == '<message user="银狼">\n正文'

    body = "他说【这本书】很好"
    stripped_body, tag_body = strip_leading_speaker_tag(body, TAG_FORMAT)
    assert stripped_body == body
    assert tag_body == ""


def test_strip_allows_leading_whitespace():
    text = "  【银狼】正文"
    stripped, tag = strip_leading_speaker_tag(text, TAG_FORMAT)

    assert tag == "【银狼】"
    assert stripped == "正文"


def test_rewrite_header_sets_user_and_self():
    text = '<message msg_id="1" user="旧名">\n正文'
    rewritten = rewrite_message_header(text, user_name="新名", is_self=True)

    assert 'user="新名"' in rewritten
    assert 'is_self_message="true"' in rewritten
    assert rewritten.endswith("\n正文")


def test_rewrite_header_removes_self():
    text = '<message user="旧名" is_self_message="true">\n正文'
    rewritten = rewrite_message_header(text, user_name="新名", is_self=False)

    assert 'user="新名"' in rewritten
    assert "is_self_message" not in rewritten


def test_rewrite_header_requires_user_name():
    text = '<message user="旧名">\n正文'

    assert rewrite_message_header(text, user_name="", is_self=True) == text


def test_rewrite_header_escapes_user_name():
    text = '<message user="旧名">\n正文'
    rewritten = rewrite_message_header(text, user_name='a"b', is_self=False)

    assert 'user="a&quot;b"' in rewritten


def test_project_message_assigns_role_and_is_idempotent():
    message = _msg('【银狼】<message user="银狼">\n我说的话')
    decision = AttributionDecision(RoleType.Assistant, True, "")

    project_message(message, decision, display_name="银狼", tag_format=TAG_FORMAT)
    once = message.parts[0].text

    assert message.role is RoleType.Assistant
    assert not once.startswith("【银狼】")
    assert 'is_self_message="true"' in once
    assert 'user="银狼"' in once

    project_message(message, decision, display_name="银狼", tag_format=TAG_FORMAT)
    assert message.parts[0].text == once


def test_project_message_leaves_non_text_parts_untouched():
    message = Message(
        role=RoleType.User,
        parts=[ImageMessagePart(image_format="png", image_base64="abc")],
    )
    decision = AttributionDecision(RoleType.Assistant, True, "")

    project_message(message, decision, display_name="银狼", tag_format=TAG_FORMAT)

    assert message.role is RoleType.Assistant
    assert isinstance(message.parts[0], ImageMessagePart)
    assert message.parts[0].image_base64 == "abc"