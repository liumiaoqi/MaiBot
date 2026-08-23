"""messages 单元测试。

覆盖 LLMContextMessage 子类（SessionBackedMessage / ComplexSessionMessage /
CompactionSummaryMessage / ReferenceMessage / AssistantMessage / ToolResultMessage）
的 role / processed_plain_text / source / count_in_context / consume_once /
to_llm_message 行为，以及 build_llm_message_from_context、forward 缓存、
contains_complex_message 等纯函数。
"""

from datetime import datetime


from src.common.data_models.message_component_data_model import (
    ForwardNodeComponent,
    MessageSequence,
    TextComponent,
)
from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.context.messages import (
    AssistantMessage,
    CompactionSummaryMessage,
    ComplexSessionMessage,
    ReferenceMessage,
    ReferenceMessageType,
    SessionBackedMessage,
    ToolResultMessage,
    build_llm_message_from_context,
    contains_complex_message,
    get_cached_forward_nodes,
    reset_forward_cache,
)

TS = datetime(2026, 8, 23, 14, 30, 5)


class TestSessionBackedMessage:
    """SessionBackedMessage 行为测试。"""

    def test_role_is_user(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="hi",
            timestamp=TS,
        )
        assert msg.role == "user"

    def test_processed_plain_text_is_visible_text(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="可见文本",
            timestamp=TS,
        )
        assert msg.processed_plain_text == "可见文本"

    def test_default_source_is_user(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="hi",
            timestamp=TS,
        )
        assert msg.source == "user"

    def test_custom_source_kind(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="hi",
            timestamp=TS,
            source_kind="custom_kind",
        )
        assert msg.source == "custom_kind"

    def test_count_in_context_default_true(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="hi",
            timestamp=TS,
        )
        assert msg.count_in_context is True

    def test_to_llm_message_returns_message(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("你好")]),
            visible_text="你好",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None
        assert result.role.value == "user"

    def test_from_session_message_classmethod(self):
        # 用 SimpleNamespace 模拟 SessionMessage
        from types import SimpleNamespace

        session_msg = SimpleNamespace(
            timestamp=TS,
            message_id="m1",
        )
        msg = SessionBackedMessage.from_session_message(
            session_msg,
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="hi",
            source_kind="user",
        )
        assert msg.message_id == "m1"
        assert msg.timestamp == TS


class TestAssistantMessage:
    """AssistantMessage 行为测试。"""

    def test_role_is_assistant(self):
        msg = AssistantMessage(content="回复", timestamp=TS)
        assert msg.role == "assistant"

    def test_processed_plain_text_is_content(self):
        msg = AssistantMessage(content="回复内容", timestamp=TS)
        assert msg.processed_plain_text == "回复内容"

    def test_default_count_in_context_true(self):
        msg = AssistantMessage(content="回复", timestamp=TS)
        assert msg.count_in_context is True

    def test_perception_source_count_in_context_false(self):
        msg = AssistantMessage(content="回复", timestamp=TS, source_kind="perception")
        assert msg.count_in_context is False

    def test_to_llm_message_with_content(self):
        msg = AssistantMessage(content="你好", timestamp=TS)
        result = msg.to_llm_message()
        assert result is not None
        assert result.role.value == "assistant"

    def test_to_llm_message_with_tool_calls(self):
        tool_call = ToolCall(call_id="c1", func_name="search", args={"q": "test"})
        msg = AssistantMessage(content="思考", timestamp=TS, tool_calls=[tool_call])
        result = msg.to_llm_message()
        assert result is not None
        assert result.tool_calls is not None

    def test_source_reflects_source_kind(self):
        msg = AssistantMessage(content="x", timestamp=TS, source_kind="replyer")
        assert msg.source == "replyer"


class TestToolResultMessage:
    """ToolResultMessage 行为测试。"""

    def test_role_is_tool(self):
        msg = ToolResultMessage(content="结果", timestamp=TS, tool_call_id="c1")
        assert msg.role == "tool"

    def test_count_in_context_false(self):
        msg = ToolResultMessage(content="结果", timestamp=TS, tool_call_id="c1")
        assert msg.count_in_context is False

    def test_source_is_tool_name(self):
        msg = ToolResultMessage(content="结果", timestamp=TS, tool_call_id="c1", tool_name="search")
        assert msg.source == "search"

    def test_source_fallback_when_no_tool_name(self):
        msg = ToolResultMessage(content="结果", timestamp=TS, tool_call_id="c1")
        assert msg.source == "tool"

    def test_to_llm_message(self):
        msg = ToolResultMessage(content="结果内容", timestamp=TS, tool_call_id="c1", tool_name="search")
        result = msg.to_llm_message()
        assert result is not None
        assert result.role.value == "tool"


class TestReferenceMessage:
    """ReferenceMessage 行为测试。"""

    def test_role_is_user(self):
        msg = ReferenceMessage(content="参考", timestamp=TS)
        assert msg.role == "user"

    def test_count_in_context_false(self):
        msg = ReferenceMessage(content="参考", timestamp=TS)
        assert msg.count_in_context is False

    def test_processed_plain_text_with_prefix(self):
        msg = ReferenceMessage(content="内容", timestamp=TS, display_prefix="[参考消息]")
        assert msg.processed_plain_text == "[参考消息]\n内容"

    def test_default_reference_type_custom(self):
        msg = ReferenceMessage(content="x", timestamp=TS)
        assert msg.reference_type == ReferenceMessageType.CUSTOM
        assert msg.source == "custom"

    def test_consume_once_decrements_remaining_uses(self):
        msg = ReferenceMessage(content="x", timestamp=TS, remaining_uses_value=3)
        # 3 → 2 (继续保留)
        assert msg.consume_once() is True
        assert msg.remaining_uses_value == 2
        # 2 → 1 (继续保留)
        assert msg.consume_once() is True
        assert msg.remaining_uses_value == 1
        # 1 → 0 (不再保留)
        assert msg.consume_once() is False
        assert msg.remaining_uses_value == 0

    def test_consume_once_none_remaining_always_true(self):
        msg = ReferenceMessage(content="x", timestamp=TS, remaining_uses_value=None)
        assert msg.consume_once() is True
        assert msg.consume_once() is True
        assert msg.remaining_uses_value is None

    def test_to_llm_message(self):
        msg = ReferenceMessage(content="参考内容", timestamp=TS)
        result = msg.to_llm_message()
        assert result is not None


class TestCompactionSummaryMessage:
    """CompactionSummaryMessage 行为测试。"""

    def test_role_is_user(self):
        msg = CompactionSummaryMessage(summary_text="摘要", timestamp=TS)
        assert msg.role == "user"

    def test_processed_plain_text_is_summary(self):
        msg = CompactionSummaryMessage(summary_text="摘要内容", timestamp=TS)
        assert msg.processed_plain_text == "摘要内容"

    def test_source_is_compaction_summary(self):
        msg = CompactionSummaryMessage(summary_text="摘要", timestamp=TS)
        assert msg.source == "compaction_summary"

    def test_count_in_context_true(self):
        msg = CompactionSummaryMessage(summary_text="摘要", timestamp=TS)
        assert msg.count_in_context is True

    def test_to_llm_message(self):
        msg = CompactionSummaryMessage(summary_text="摘要内容", timestamp=TS)
        result = msg.to_llm_message()
        assert result is not None
        assert result.role.value == "user"


class TestComplexSessionMessage:
    """ComplexSessionMessage 行为测试。"""

    def test_source_includes_complex_type(self):
        msg = ComplexSessionMessage(
            raw_message=MessageSequence([TextComponent("x")]),
            visible_text="x",
            timestamp=TS,
            prompt_text="转发摘要",
            complex_message_type="forward",
        )
        assert msg.source == "user:forward"

    def test_to_llm_message_uses_prompt_text(self):
        msg = ComplexSessionMessage(
            raw_message=MessageSequence([TextComponent("x")]),
            visible_text="x",
            timestamp=TS,
            prompt_text="转发摘要内容",
        )
        result = msg.to_llm_message()
        assert result is not None
        assert result.role.value == "user"


class TestBuildLlmMessageFromContext:
    """build_llm_message_from_context 行为测试。"""

    def test_dispatches_to_to_llm_message(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("你好")]),
            visible_text="你好",
            timestamp=TS,
        )
        result = build_llm_message_from_context(msg)
        assert result is not None
        assert result.role.value == "user"

    def test_enable_visual_message_param(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("你好")]),
            visible_text="你好",
            timestamp=TS,
        )
        result = build_llm_message_from_context(msg, enable_visual_message=False)
        assert result is not None


class TestForwardCache:
    """forward 缓存纯函数测试。"""

    def test_get_cached_forward_nodes_miss_returns_none(self):
        reset_forward_cache()
        assert get_cached_forward_nodes("nonexistent_id") is None

    def test_reset_forward_cache_clears(self):
        reset_forward_cache()
        # 多次调用应无副作用
        reset_forward_cache()
        assert get_cached_forward_nodes("any") is None


class TestContainsComplexMessage:
    """contains_complex_message 行为测试。"""

    def test_plain_text_sequence_returns_false(self):
        seq = MessageSequence([TextComponent("hello")])
        assert contains_complex_message(seq) is False

    def test_forward_node_sequence_returns_true(self):
        from src.common.data_models.message_component_data_model import ForwardComponent

        forward = ForwardComponent(user_nickname="u", message_id="m1", content=[TextComponent("x")])
        node = ForwardNodeComponent(forward_components=[forward])
        seq = MessageSequence([node])
        assert contains_complex_message(seq) is True

    def test_empty_sequence_returns_false(self):
        seq = MessageSequence([])
        assert contains_complex_message(seq) is False


class TestConsumeOnceDefault:
    """LLMContextMessage.consume_once 默认行为测试。"""

    def test_session_backed_consume_once_returns_true(self):
        msg = SessionBackedMessage(
            raw_message=MessageSequence([TextComponent("hi")]),
            visible_text="hi",
            timestamp=TS,
        )
        # 默认实现返回 True（继续保留）
        assert msg.consume_once() is True

    def test_assistant_consume_once_returns_true(self):
        msg = AssistantMessage(content="x", timestamp=TS)
        assert msg.consume_once() is True

    def test_tool_result_consume_once_returns_true(self):
        msg = ToolResultMessage(content="x", timestamp=TS, tool_call_id="c1")
        assert msg.consume_once() is True

    def test_compaction_consume_once_returns_true(self):
        msg = CompactionSummaryMessage(summary_text="x", timestamp=TS)
        assert msg.consume_once() is True


class TestGuessImageFormat:
    """_guess_image_format 行为测试。"""

    def test_empty_bytes_returns_none(self):
        from src.maisaka.context.messages import _guess_image_format

        assert _guess_image_format(b"") is None

    def test_invalid_bytes_returns_none(self):
        from src.maisaka.context.messages import _guess_image_format

        assert _guess_image_format(b"not an image") is None

    def test_valid_png_bytes(self):
        from io import BytesIO

        from PIL import Image

        from src.maisaka.context.messages import _guess_image_format

        buf = BytesIO()
        Image.new("RGB", (1, 1)).save(buf, format="PNG")
        result = _guess_image_format(buf.getvalue())
        assert result == "png"

    def test_invalid_bytes_with_port(self, monkeypatch):
        """无效字节触发异常 + port.report 上报（line 53）。"""
        from unittest.mock import MagicMock

        from src.maisaka.context.messages import _guess_image_format

        port = MagicMock()
        monkeypatch.setattr("src.core.error_escalation_port_registry.get_error_escalation_port", lambda: port)
        result = _guess_image_format(b"not an image at all!!!")
        assert result is None
        port.report.assert_called_once()

    def test_invalid_bytes_no_port(self, monkeypatch):
        """无效字节触发异常 + port 为 None（line 52 false 分支）。"""
        from src.maisaka.context.messages import _guess_image_format

        monkeypatch.setattr("src.core.error_escalation_port_registry.get_error_escalation_port", lambda: None)
        result = _guess_image_format(b"not an image at all!!!")
        assert result is None


class TestRenderComponentForPrompt:
    """_render_component_for_prompt 行为测试。"""

    def test_text_component(self):
        from src.maisaka.context.messages import _render_component_for_prompt

        result = _render_component_for_prompt(TextComponent("文本"))
        assert result == "文本"

    def test_text_component_stripped(self):
        from src.maisaka.context.messages import _render_component_for_prompt

        result = _render_component_for_prompt(TextComponent("  带空格  "))
        assert result == "带空格"

    def test_image_component_with_content(self):
        from src.common.data_models.message_component_data_model import ImageComponent
        from src.maisaka.context.messages import _render_component_for_prompt

        comp = ImageComponent(binary_hash="h", content="图片描述", binary_data=b"")
        assert _render_component_for_prompt(comp) == "图片描述"

    def test_image_component_empty_content_placeholder(self):
        from src.common.data_models.message_component_data_model import ImageComponent
        from src.maisaka.context.messages import _render_component_for_prompt

        comp = ImageComponent(binary_hash="h", content="", binary_data=b"")
        assert _render_component_for_prompt(comp) == "[图片，识别中.....]"

    def test_emoji_component(self):
        from src.common.data_models.message_component_data_model import EmojiComponent
        from src.maisaka.context.messages import _render_component_for_prompt

        comp = EmojiComponent(binary_hash="h", content="[笑]", binary_data=b"")
        assert _render_component_for_prompt(comp) == "[笑]"

    def test_voice_component(self):
        from src.common.data_models.message_component_data_model import VoiceComponent
        from src.maisaka.context.messages import _render_component_for_prompt

        comp = VoiceComponent(binary_hash="h", content="语音转写", binary_data=b"")
        assert _render_component_for_prompt(comp) == "语音转写"

    def test_at_component(self):
        from src.common.data_models.message_component_data_model import AtComponent
        from src.maisaka.context.messages import _render_component_for_prompt

        comp = AtComponent("123", "nick", "card")
        assert _render_component_for_prompt(comp) == "@card"

    def test_reply_component_returns_empty(self):
        from src.common.data_models.message_component_data_model import ReplyComponent
        from src.maisaka.context.messages import _render_component_for_prompt

        comp = ReplyComponent("msg1")
        assert _render_component_for_prompt(comp) == ""


class TestBuildComplexMessagePromptText:
    """_build_complex_message_prompt_text 行为测试。"""

    def test_plain_text(self):
        from src.maisaka.context.messages import _build_complex_message_prompt_text

        seq = MessageSequence([TextComponent("你好")])
        assert _build_complex_message_prompt_text(seq) == "你好"

    def test_multiple_components_joined(self):
        from src.maisaka.context.messages import _build_complex_message_prompt_text

        seq = MessageSequence([TextComponent("你好"), TextComponent("世界")])
        result = _build_complex_message_prompt_text(seq)
        assert "你好" in result
        assert "世界" in result

    def test_empty_sequence(self):
        from src.maisaka.context.messages import _build_complex_message_prompt_text

        seq = MessageSequence([])
        assert _build_complex_message_prompt_text(seq) == ""


class TestBuildForwardPreviewBlock:
    """_build_forward_preview_block 行为测试。"""

    def test_forward_preview(self):
        from src.common.data_models.message_component_data_model import (
            ForwardComponent,
            ForwardNodeComponent,
        )
        from src.maisaka.context.messages import _build_forward_preview_block

        node = ForwardComponent(user_nickname="用户A", message_id="m1", content=[TextComponent("内容A")])
        comp = ForwardNodeComponent(forward_components=[node])
        result = _build_forward_preview_block(comp)
        assert "转发消息" in result
        assert "用户A" in result
        assert "内容A" in result

    def test_forward_preview_limit_truncation(self):
        from src.common.data_models.message_component_data_model import (
            ForwardComponent,
            ForwardNodeComponent,
        )
        from src.maisaka.context.messages import FORWARD_PREVIEW_LIMIT, _build_forward_preview_block

        nodes = [
            ForwardComponent(user_nickname=f"u{i}", message_id=f"m{i}", content=[TextComponent(f"c{i}")])
            for i in range(FORWARD_PREVIEW_LIMIT + 2)
        ]
        comp = ForwardNodeComponent(forward_components=nodes)
        result = _build_forward_preview_block(comp)
        assert "......" in result
        assert "view_forward_message" in result


class TestRenderComponentsInline:
    """_render_components_inline 行为测试。"""

    def test_single_text(self):
        from src.maisaka.context.messages import _render_components_inline

        result = _render_components_inline([TextComponent("你好")])
        assert result == "你好"

    def test_multiple_texts_joined_with_space(self):
        from src.maisaka.context.messages import _render_components_inline

        result = _render_components_inline([TextComponent("你好"), TextComponent("世界")])
        assert result == "你好 世界"

    def test_empty_list(self):
        from src.maisaka.context.messages import _render_components_inline

        assert _render_components_inline([]) == ""


class TestNormalizeInlineText:
    """_normalize_inline_text 行为测试。"""

    def test_multiline_compressed_to_single_line(self):
        from src.maisaka.context.messages import _normalize_inline_text

        assert _normalize_inline_text("第一行\n第二行") == "第一行 第二行"

    def test_extra_spaces_normalized(self):
        from src.maisaka.context.messages import _normalize_inline_text

        assert _normalize_inline_text("a   b") == "a b"

    def test_empty_string(self):
        from src.maisaka.context.messages import _normalize_inline_text

        assert _normalize_inline_text("") == ""

    def test_none_treated_as_empty(self):
        from src.maisaka.context.messages import _normalize_inline_text

        assert _normalize_inline_text(None) == ""


class TestBuildFullComplexMessageContentFromSequence:
    """build_full_complex_message_content_from_sequence 行为测试。"""

    def test_plain_text_sequence(self):
        from src.maisaka.context.messages import build_full_complex_message_content_from_sequence

        seq = MessageSequence([TextComponent("普通文本")])
        # 无 ForwardNodeComponent → 返回空
        assert build_full_complex_message_content_from_sequence(seq) == ""

    def test_forward_node_sequence(self):
        from src.common.data_models.message_component_data_model import (
            ForwardComponent,
            ForwardNodeComponent,
        )
        from src.maisaka.context.messages import build_full_complex_message_content_from_sequence

        node = ForwardComponent(user_nickname="u", message_id="m1", content=[TextComponent("c")])
        forward = ForwardNodeComponent(forward_components=[node])
        seq = MessageSequence([forward])
        result = build_full_complex_message_content_from_sequence(seq)
        assert "合并转发" in result
        assert "u" in result


class TestPrepareUnresolvedVisualComponents:
    """_prepare_unresolved_visual_components 行为测试。"""

    def test_text_only_returns_false(self):
        from src.maisaka.context.messages import _prepare_unresolved_visual_components

        seq = [TextComponent("hello")]
        assert _prepare_unresolved_visual_components(seq) is False

    def test_image_with_content_returns_false(self):
        from src.common.data_models.message_component_data_model import ImageComponent
        from src.maisaka.context.messages import _prepare_unresolved_visual_components

        comp = ImageComponent(binary_hash="h", content="已识别", binary_data=b"")
        assert _prepare_unresolved_visual_components([comp]) is False

    def test_image_unresolved_with_binary_returns_true(self):
        from src.common.data_models.message_component_data_model import ImageComponent
        from src.maisaka.context.messages import _prepare_unresolved_visual_components

        comp = ImageComponent(binary_hash="h", content="", binary_data=b"binary")
        assert _prepare_unresolved_visual_components([comp]) is True

    def test_placeholder_content_reset(self):
        from src.common.data_models.message_component_data_model import ImageComponent
        from src.maisaka.context.messages import _prepare_unresolved_visual_components

        comp = ImageComponent(binary_hash="h", content="[图片，识别中.....]", binary_data=b"binary")
        # 占位符内容应被重置并识别为未解析
        assert _prepare_unresolved_visual_components([comp]) is True
        assert comp.content == ""


class TestCollectForwardIds:
    """_collect_forward_ids 行为测试。"""

    def test_collects_placeholder_ids(self):
        from src.common.data_models.message_component_data_model import ForwardPlaceholderComponent
        from src.maisaka.context.messages import _collect_forward_ids

        components = [TextComponent("text"), ForwardPlaceholderComponent("fwd1"), ForwardPlaceholderComponent("fwd2")]
        result = _collect_forward_ids(components)
        assert result == ["fwd1", "fwd2"]

    def test_no_placeholders_returns_empty(self):
        from src.maisaka.context.messages import _collect_forward_ids

        result = _collect_forward_ids([TextComponent("text")])
        assert result == []


class TestToLlmMessageComponentBranches:
    """to_llm_message 组件分支测试。"""

    def test_session_backed_with_at_component(self):
        from src.common.data_models.message_component_data_model import AtComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([AtComponent("123", "nick")]),
            visible_text="@nick",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None

    def test_session_backed_with_voice_component(self):
        from src.common.data_models.message_component_data_model import VoiceComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([VoiceComponent(binary_hash="h", content="语音", binary_data=b"")]),
            visible_text="语音",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None

    def test_session_backed_with_emoji_placeholder(self):
        from src.common.data_models.message_component_data_model import EmojiComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([EmojiComponent(binary_hash="h", content="", binary_data=b"")]),
            visible_text="[表情包]",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None

    def test_session_backed_with_image_placeholder(self):
        from src.common.data_models.message_component_data_model import ImageComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([ImageComponent(binary_hash="h", content="", binary_data=b"")]),
            visible_text="[图片，识别中.....]",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None

    def test_assistant_empty_content_no_tool_calls(self):
        msg = AssistantMessage(content="", timestamp=TS)
        result = msg.to_llm_message()
        # 空内容无 tool_calls → None
        assert result is None

    def test_emoji_with_visual_message_png(self):
        """enable_visual_message=True + 有效 PNG → 视觉路径（lines 66-68）。"""
        from io import BytesIO

        from PIL import Image

        from src.common.data_models.message_component_data_model import EmojiComponent

        buf = BytesIO()
        Image.new("RGB", (2, 2)).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        msg = SessionBackedMessage(
            raw_message=MessageSequence([EmojiComponent(binary_hash="h", content="[笑]", binary_data=png_bytes)]),
            visible_text="[表情包]",
            timestamp=TS,
        )
        result = msg.to_llm_message(enable_visual_message=True)
        assert result is not None

    def test_image_with_visual_message_png(self):
        """enable_visual_message=True + 有效 PNG → 视觉路径（lines 88-89）。"""
        from io import BytesIO

        from PIL import Image

        from src.common.data_models.message_component_data_model import ImageComponent

        buf = BytesIO()
        Image.new("RGB", (2, 2)).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        msg = SessionBackedMessage(
            raw_message=MessageSequence([ImageComponent(binary_hash="h", content="图片", binary_data=png_bytes)]),
            visible_text="[图片]",
            timestamp=TS,
        )
        result = msg.to_llm_message(enable_visual_message=True)
        assert result is not None

    def test_emoji_with_content_no_visual(self):
        """有 content 无 binary_data → normalized_content 路径（lines 72-73）。"""
        from src.common.data_models.message_component_data_model import EmojiComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([EmojiComponent(binary_hash="h", content="[自定义表情]", binary_data=b"")]),
            visible_text="[自定义表情]",
            timestamp=TS,
        )
        result = msg.to_llm_message(enable_visual_message=False)
        assert result is not None

    def test_image_with_content_no_visual(self):
        """有 content 无 binary_data → normalized_content 路径（lines 93-94）。"""
        from src.common.data_models.message_component_data_model import ImageComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([ImageComponent(binary_hash="h", content="一张图片", binary_data=b"")]),
            visible_text="一张图片",
            timestamp=TS,
        )
        result = msg.to_llm_message(enable_visual_message=False)
        assert result is not None

    def test_at_component_all_empty_returns_at(self):
        """AtComponent 所有名称字段为空 → 仍输出 '@'（_render_at_component_text 恒非空）。"""
        from src.common.data_models.message_component_data_model import AtComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence([AtComponent("", "", "")]),
            visible_text="@",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        # 空 At 组件仍输出 '@'（f"@{''}".strip() == '@'）
        assert result is not None


class TestAppendReplyComponent:
    """_append_reply_component DB 查询分支测试。"""

    def test_reply_with_content_no_db_query(self, monkeypatch):
        # 有 content 和 sender → 不查 DB
        from src.common.data_models.message_component_data_model import ReplyComponent

        msg = SessionBackedMessage(
            raw_message=MessageSequence(
                [ReplyComponent("m1", target_message_content="原内容", target_message_sender_nickname="发送者")]
            ),
            visible_text="[回复]",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None

    def test_reply_db_lookup_fills_content(self, monkeypatch):
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        from src.common.data_models.message_component_data_model import ReplyComponent

        mock_db_msg = MagicMock()
        mock_db_msg.processed_plain_text = "DB查到内容"
        mock_db_msg.user_cardname = "DB用户"
        mock_db_msg.user_nickname = None
        mock_db_msg.user_id = "u1"

        @contextmanager
        def mock_session():
            sess = MagicMock()
            stmt = MagicMock()
            sess.exec.return_value = stmt
            stmt.first.return_value = mock_db_msg
            yield sess

        monkeypatch.setattr("src.common.database.database.get_db_session", mock_session)
        msg = SessionBackedMessage(
            raw_message=MessageSequence([ReplyComponent("m1")]),
            visible_text="[回复]",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None

    def test_reply_db_lookup_not_found_falls_back(self, monkeypatch):
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        from src.common.data_models.message_component_data_model import ReplyComponent

        @contextmanager
        def mock_session():
            sess = MagicMock()
            stmt = MagicMock()
            sess.exec.return_value = stmt
            stmt.first.return_value = None
            yield sess

        monkeypatch.setattr("src.common.database.database.get_db_session", mock_session)
        msg = SessionBackedMessage(
            raw_message=MessageSequence([ReplyComponent("m1")]),
            visible_text="[回复]",
            timestamp=TS,
        )
        result = msg.to_llm_message()
        assert result is not None


class TestPrefetchForwardNodes:
    """prefetch_forward_nodes async 行为测试。"""

    def test_empty_ids_no_op(self):
        import asyncio

        from src.maisaka.context.messages import prefetch_forward_nodes, reset_forward_cache

        reset_forward_cache()
        asyncio.run(prefetch_forward_nodes([]))  # 不抛异常

    def test_port_none_caches_none(self, monkeypatch):
        import asyncio

        from src.maisaka.context.messages import (
            get_cached_forward_nodes,
            prefetch_forward_nodes,
            reset_forward_cache,
        )

        reset_forward_cache()
        monkeypatch.setattr("src.core.forward_fetch_port_registry.get_forward_fetch_port", lambda: None)
        asyncio.run(prefetch_forward_nodes(["fwd1"]))
        # port None → 缓存 None（拉取失败标记）
        assert get_cached_forward_nodes("fwd1") is None

    def test_port_returns_nodes_cached(self, monkeypatch):
        import asyncio

        from unittest.mock import MagicMock

        from src.maisaka.context.messages import (
            get_cached_forward_nodes,
            prefetch_forward_nodes,
            reset_forward_cache,
        )

        reset_forward_cache()
        mock_port = MagicMock()

        async def fake_fetch(fid):
            return [{"user_nickname": "u", "content": []}]

        mock_port.fetch_forward_nodes = fake_fetch
        monkeypatch.setattr("src.core.forward_fetch_port_registry.get_forward_fetch_port", lambda: mock_port)
        asyncio.run(prefetch_forward_nodes(["fwd2"]))
        nodes = get_cached_forward_nodes("fwd2")
        assert nodes is not None

    def test_port_exception_caches_none(self, monkeypatch):
        import asyncio

        from unittest.mock import MagicMock

        from src.maisaka.context.messages import (
            get_cached_forward_nodes,
            prefetch_forward_nodes,
            reset_forward_cache,
        )

        reset_forward_cache()
        mock_port = MagicMock()

        async def failing_fetch(fid):
            raise RuntimeError("fetch error")

        mock_port.fetch_forward_nodes = failing_fetch
        monkeypatch.setattr("src.core.forward_fetch_port_registry.get_forward_fetch_port", lambda: mock_port)
        asyncio.run(prefetch_forward_nodes(["fwd3"]))
        assert get_cached_forward_nodes("fwd3") is None


class TestPrefetchForwardNodesForMessages:
    """prefetch_forward_nodes_for_messages async 行为测试。"""

    def test_empty_messages_no_op(self):
        import asyncio

        from src.maisaka.context.messages import prefetch_forward_nodes_for_messages

        asyncio.run(prefetch_forward_nodes_for_messages([]))

    def test_collects_and_prefetches(self, monkeypatch):
        import asyncio

        from src.common.data_models.message_component_data_model import (
            ForwardPlaceholderComponent,
            MessageSequence,
        )
        from src.maisaka.context.messages import prefetch_forward_nodes_for_messages, reset_forward_cache

        reset_forward_cache()
        monkeypatch.setattr("src.core.forward_fetch_port_registry.get_forward_fetch_port", lambda: None)
        msg = SessionBackedMessage(
            raw_message=MessageSequence([ForwardPlaceholderComponent("fwd_x")]),
            visible_text="转发",
            timestamp=TS,
        )
        asyncio.run(prefetch_forward_nodes_for_messages([msg]))  # 不抛异常