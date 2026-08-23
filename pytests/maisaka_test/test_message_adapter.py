"""message_adapter 单元测试。

覆盖 format_speaker_content / parse_speaker_content /
clone_message_sequence / build_visible_text_from_sequence 的
正常、边界与组件渲染行为。
"""

from datetime import datetime

from src.common.data_models.message_component_data_model import (
    AtComponent,
    EmojiComponent,
    ImageComponent,
    MessageSequence,
    ReplyComponent,
    TextComponent,
    VoiceComponent,
)
from src.maisaka.context.message_adapter import (
    build_visible_text_from_sequence,
    clone_message_sequence,
    format_speaker_content,
    parse_speaker_content,
)


class TestFormatSpeakerContent:
    """format_speaker_content 行为测试。"""

    def test_basic_speaker_prefix(self):
        result = format_speaker_content("Alice", "你好")
        assert result == "[Alice]你好"

    def test_with_timestamp(self):
        ts = datetime(2026, 8, 23, 14, 30, 5)
        result = format_speaker_content("Bob", "hi", timestamp=ts)
        assert result == "14:30:05[Bob]hi"

    def test_with_message_id(self):
        result = format_speaker_content("Bob", "hi", message_id="msg123")
        assert result == "[msg_id:msg123][Bob]hi"

    def test_with_timestamp_and_message_id(self):
        ts = datetime(2026, 1, 2, 3, 4, 5)
        result = format_speaker_content("Bob", "hi", timestamp=ts, message_id="m1")
        assert result == "03:04:05[msg_id:m1][Bob]hi"

    def test_empty_content(self):
        result = format_speaker_content("Alice", "")
        assert result == "[Alice]"

    def test_empty_message_id_omitted(self):
        result = format_speaker_content("Alice", "hi", message_id="")
        assert "[msg_id:" not in result


class TestParseSpeakerContent:
    """parse_speaker_content 行为测试。"""

    def test_basic_parse(self):
        speaker, content = parse_speaker_content("[Alice]你好")
        assert speaker == "Alice"
        assert content == "你好"

    def test_with_timestamp_and_message_id(self):
        speaker, content = parse_speaker_content("14:30:05[msg_id:m1][Bob]hi")
        assert speaker == "Bob"
        assert content == "hi"

    def test_no_match_returns_none_speaker(self):
        speaker, content = parse_speaker_content("plain text without speaker")
        assert speaker is None
        assert content == "plain text without speaker"

    def test_empty_string(self):
        speaker, content = parse_speaker_content("")
        assert speaker is None
        assert content == ""

    def test_none_input(self):
        speaker, content = parse_speaker_content(None)
        assert speaker is None
        assert content == ""

    def test_multiline_content(self):
        # DOTALL 模式下 content 可含换行
        speaker, content = parse_speaker_content("[Alice]line1\nline2")
        assert speaker == "Alice"
        assert content == "line1\nline2"


class TestCloneMessageSequence:
    """clone_message_sequence 行为测试。"""

    def test_clone_preserves_components(self):
        seq = MessageSequence([TextComponent("hello"), AtComponent("123", "nick")])
        cloned = clone_message_sequence(seq)
        assert len(cloned.components) == 2
        assert cloned.components[0].text == "hello"
        assert cloned.components[1].target_user_id == "123"

    def test_clone_is_deep_copy(self):
        seq = MessageSequence([TextComponent("original")])
        cloned = clone_message_sequence(seq)
        cloned.components[0].text = "modified"
        # 原序列不受影响
        assert seq.components[0].text == "original"

    def test_clone_empty_sequence(self):
        seq = MessageSequence([])
        cloned = clone_message_sequence(seq)
        assert cloned.components == []


class TestBuildVisibleTextFromSequence:
    """build_visible_text_from_sequence 行为测试。"""

    def test_plain_text_component(self):
        seq = MessageSequence([TextComponent("你好")])
        result = build_visible_text_from_sequence(seq)
        assert result == "你好"

    def test_speaker_prefixed_text_normalized(self):
        seq = MessageSequence([TextComponent("14:30:05[msg_id:m1][Alice]hello")])
        result = build_visible_text_from_sequence(seq)
        assert "[Alice]" in result
        assert "hello" in result

    def test_at_component_rendered(self):
        seq = MessageSequence([AtComponent("123", "nick", "card")])
        result = build_visible_text_from_sequence(seq)
        # cardname 优先
        assert "@card" in result

    def test_at_component_fallback_to_nickname(self):
        seq = MessageSequence([AtComponent("123", "nick", None)])
        result = build_visible_text_from_sequence(seq)
        assert "@nick" in result

    def test_at_component_fallback_to_id(self):
        seq = MessageSequence([AtComponent("123", None, None)])
        result = build_visible_text_from_sequence(seq)
        assert "@123" in result

    def test_emoji_component_with_content(self):
        seq = MessageSequence([EmojiComponent(binary_hash="h", content="[笑]", binary_data=b"")])
        result = build_visible_text_from_sequence(seq)
        assert result == "[笑]"

    def test_emoji_component_empty_content_placeholder(self):
        seq = MessageSequence([EmojiComponent(binary_hash="h", content="", binary_data=b"")])
        result = build_visible_text_from_sequence(seq)
        assert result == "[表情包]"

    def test_image_component_with_content(self):
        seq = MessageSequence([ImageComponent(binary_hash="h", content="图片描述", binary_data=b"")])
        result = build_visible_text_from_sequence(seq)
        assert result == "图片描述"

    def test_image_component_empty_content_placeholder(self):
        seq = MessageSequence([ImageComponent(binary_hash="h", content="", binary_data=b"")])
        result = build_visible_text_from_sequence(seq)
        assert result == "[图片，识别中.....]"

    def test_voice_component_with_content(self):
        seq = MessageSequence([VoiceComponent(binary_hash="h", content="语音转写", binary_data=b"")])
        result = build_visible_text_from_sequence(seq)
        assert result == "语音转写"

    def test_voice_component_empty_content_placeholder(self):
        seq = MessageSequence([VoiceComponent(binary_hash="h", content="", binary_data=b"")])
        result = build_visible_text_from_sequence(seq)
        assert result == "[语音消息]"

    def test_reply_component_with_target_id(self):
        seq = MessageSequence([ReplyComponent("msg123")])
        result = build_visible_text_from_sequence(seq)
        assert "[引用消息]msg123" in result

    def test_reply_component_empty_id_omitted(self):
        seq = MessageSequence([ReplyComponent("")])
        result = build_visible_text_from_sequence(seq)
        assert "[引用消息]" not in result

    def test_multiple_components_concatenated(self):
        seq = MessageSequence([TextComponent("你好"), AtComponent("1", "n")])
        result = build_visible_text_from_sequence(seq)
        assert "你好" in result
        assert "@n" in result

    def test_empty_sequence(self):
        seq = MessageSequence([])
        result = build_visible_text_from_sequence(seq)
        assert result == ""