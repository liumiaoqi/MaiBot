"""Maisaka 内部上下文消息抽象。"""

from abc import ABC, abstractmethod
from src.common.logger import get_logger

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Any, List, Optional, Sequence
import base64

from PIL import Image as PILImage

from src.core.types import SessionMessage
from src.common.data_models.message_component_data_model import (
    AtComponent,
    DictComponent,
    EmojiComponent,
    FileComponent,
    ForwardComponent,
    ForwardNodeComponent,
    ForwardPlaceholderComponent,
    ImageComponent,
    MessageSequence,
    ReplyComponent,
    StandardMessageComponents,
    TextComponent,
    VoiceComponent,
)
from src.llm_models.payload_content.message import Message, MessageBuilder, RoleType, TextMessagePart
from src.llm_models.payload_content.tool_option import ToolCall
logger = get_logger("auto.messages")

FORWARD_PREVIEW_LIMIT = 4
FOCUS_COOLDOWN_WAKEUP_SOURCE = "focus_cooldown_wakeup"
FOCUS_AT_WAKEUP_SOURCE = "focus_at_wakeup"
FOCUS_WAKEUP_SOURCE_KINDS = frozenset({FOCUS_COOLDOWN_WAKEUP_SOURCE, FOCUS_AT_WAKEUP_SOURCE})


def _guess_image_format(image_bytes: bytes) -> Optional[str]:
    if not image_bytes:
        return None

    try:
        with PILImage.open(BytesIO(image_bytes)) as image:
            return image.format.lower() if image.format else None
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "猜测图片格式失败", exception=exc)
        logger.warning("操作异常 in messages", exc_info=True)


def _append_emoji_component(
    builder: MessageBuilder,
    component: EmojiComponent,
    *,
    enable_visual_message: bool,
) -> bool:
    """将表情组件追加到 LLM 消息构建器。"""
    image_format = _guess_image_format(component.binary_data)
    if enable_visual_message and image_format and component.binary_data:
        builder.add_text_content("[消息类型]表情包")
        builder.add_image_content(image_format, base64.b64encode(component.binary_data).decode("utf-8"))
        return True

    normalized_content = component.content.strip()
    if normalized_content:
        builder.add_text_content(normalized_content)
        return True

    builder.add_text_content("[表情包]")
    return True


def _append_image_component(
    builder: MessageBuilder,
    component: ImageComponent,
    *,
    enable_visual_message: bool,
) -> bool:
    """将图片组件追加到 LLM 消息构建器。"""
    image_format = _guess_image_format(component.binary_data)
    if enable_visual_message and image_format and component.binary_data:
        builder.add_image_content(image_format, base64.b64encode(component.binary_data).decode("utf-8"))
        return True

    normalized_content = component.content.strip()
    if normalized_content:
        builder.add_text_content(normalized_content)
        return True

    builder.add_text_content("[图片，识别中.....]")
    return True


def _append_reply_component(builder: MessageBuilder, component: ReplyComponent) -> bool:
    """将回复组件追加到 LLM 消息构建器——引用语义进 prompt 正文。

    内容来源优先级：target_message_content（process 已填）→ DB 查 → "(原消息未找到)"。
    sender 优先级：target_message_sender_cardname → nickname → id → "未知用户"。
    返回 True 使 has_content=True → fallback 不触发 → 不与 processed_plain_text 双重输出。
    """
    content = component.target_message_content or ""
    sender = (
        component.target_message_sender_cardname
        or component.target_message_sender_nickname
        or component.target_message_sender_id
    )
    if not content or not sender:
        try:
            from sqlmodel import select

            from src.common.database.database import get_db_session
            from src.common.database.database_model import Messages

            with get_db_session() as session:
                statement = select(Messages).filter_by(message_id=component.target_message_id).limit(1)
                if db_msg := session.exec(statement).first():
                    content = content or (db_msg.processed_plain_text or "")
                    sender = sender or db_msg.user_cardname or db_msg.user_nickname or db_msg.user_id
        except Exception as exc:
            logger.warning("回复组件查询原消息失败: %s", exc, exc_info=True)
    sender = sender or "未知用户"
    content = content or "(原消息未找到)"
    builder.add_text_content(f"[回复了{sender}的消息: {content}]")
    return True


def _render_at_component_text(component: AtComponent) -> str:
    """灏?AtComponent 娓叉煋涓烘枃鏈舰寮忋€?"""

    target_name = component.target_user_cardname or component.target_user_nickname or component.target_user_id
    return f"@{target_name}".strip()


def _append_at_component(builder: MessageBuilder, component: AtComponent) -> bool:
    """灏?@ 缁勪欢杞崲涓烘枃鏈苟鍐欏叆 LLM 娑堟伅銆?"""

    rendered_text = _render_at_component_text(component)
    if not rendered_text:
        return False

    builder.add_text_content(rendered_text)
    return True


# ── ZG16-1 forward 预取与读缓存（design 2.4）────────────────────────────
# 全局缓存：key=forward_id（转发内容静态不随会话变），值=节点列表（dict 格式）或 None（拉取失败标记）
_forward_cache: dict[str, Optional[List[dict]]] = {}


def get_cached_forward_nodes(forward_id: str) -> Optional[List[dict]]:
    """同步读取 forward 预取缓存（纯内存，零网络调用）。

    Args:
        forward_id: 合并转发消息 id。

    Returns:
        节点列表（命中且拉取成功）；None（未缓存或拉取失败标记）。
    """
    return _forward_cache.get(forward_id)


async def prefetch_forward_nodes(forward_ids: List[str]) -> None:
    """async 批量预取 forward 节点写全局缓存（承担全部网络调用）。

    对未命中缓存的 id 调 ForwardFetchPort.fetch_forward_nodes；
    成功写缓存（节点列表），失败/超时写 None（拉取失败标记，避免重复拉取）；
    port 未注册时全部写 None（降级，渲染时占位）。
    """
    from src.core.forward_fetch_port_registry import get_forward_fetch_port

    pending_ids = [fid for fid in forward_ids if fid and fid not in _forward_cache]
    if not pending_ids:
        return
    port = get_forward_fetch_port()
    if port is None:
        for fid in pending_ids:
            _forward_cache[fid] = None
        return
    for fid in pending_ids:
        try:
            nodes = await port.fetch_forward_nodes(fid)
            _forward_cache[fid] = nodes
        except Exception as exc:
            logger.warning("forward 预取失败 id=%s: %s", fid, exc, exc_info=True)
            _forward_cache[fid] = None


def _collect_forward_ids(components: Sequence[StandardMessageComponents]) -> List[str]:
    """扫描消息组件，收集待拉取的 forward_id（ForwardPlaceholderComponent）。"""

    return [
        component.forward_id
        for component in components
        if isinstance(component, ForwardPlaceholderComponent)
    ]


async def prefetch_forward_nodes_for_messages(messages: Sequence) -> None:
    """遍历 selected_history 所有消息，收集 ForwardPlaceholderComponent 的 forward_id 批量预取。

    区分已展开 ForwardNodeComponent（无需预取）与待拉取 ForwardPlaceholderComponent（需预取）。
    """
    forward_ids: List[str] = []
    for message in messages:
        raw_message = getattr(message, "raw_message", None)
        if raw_message is None:
            continue
        components = getattr(raw_message, "components", ())
        forward_ids.extend(_collect_forward_ids(components))
    if forward_ids:
        await prefetch_forward_nodes(forward_ids)


def _build_forward_node_component_from_nodes(nodes: List[dict]) -> Optional[ForwardNodeComponent]:
    """从预取的节点列表（dict 格式）构建 ForwardNodeComponent 供同步渲染。

    复用 message_utils 的节点解析逻辑；失败返回 None。
    """
    from src.plugin_runtime.host.message_utils import PluginMessageUtils

    try:
        forward_components = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            raw_content = node.get("content", [])
            node_components: List[StandardMessageComponents] = []
            if isinstance(raw_content, list):
                node_components = [
                    PluginMessageUtils._component_from_dict(content)
                    for content in raw_content
                    if isinstance(content, dict)
                ]
            if not node_components:
                node_components = [TextComponent(text="[empty forward node]")]
            forward_components.append(
                ForwardComponent(
                    user_nickname=str(node.get("user_nickname") or "未知用户"),
                    user_id=str(node.get("user_id") or "") or None,
                    user_cardname=str(node.get("user_cardname") or "") or None,
                    message_id=str(node.get("message_id") or ""),
                    content=node_components,
                )
            )
        if forward_components:
            return ForwardNodeComponent(forward_components=forward_components)
    except Exception as exc:
        logger.warning("构建 ForwardNodeComponent 失败: %s", exc, exc_info=True)
    return None


def reset_forward_cache() -> None:
    """清空全局 forward 缓存（测试用）。"""
    _forward_cache.clear()


def contains_complex_message(message_sequence: MessageSequence) -> bool:
    """判断消息序列中是否包含需要通过转发浏览工具展开的组件。"""

    return any(isinstance(component, ForwardNodeComponent) for component in message_sequence.components)


async def build_full_complex_message_content(message: SessionMessage) -> str:
    """构造转发消息的完整文本内容。"""

    if _prepare_unresolved_visual_components(message.raw_message.components):
        await message.process(
            enable_heavy_media_analysis=True,
            enable_voice_transcription=False,
        )

    await prefetch_forward_nodes_for_messages([message])
    full_content = _build_complex_message_full_text(message.raw_message)
    if full_content:
        return full_content

    if not message.processed_plain_text:
        await message.process()
    return (message.processed_plain_text or "").strip()


def build_full_complex_message_content_from_sequence(message_sequence: MessageSequence) -> str:
    """从消息组件序列构造转发消息的完整文本内容。"""

    return _build_complex_message_full_text(message_sequence)


def _prepare_unresolved_visual_components(components: Sequence[StandardMessageComponents]) -> bool:
    """检查转发消息内是否存在需要补充识图文本的图片或表情。"""

    found_unresolved = False
    for component in components:
        if isinstance(component, ImageComponent):
            normalized_content = component.content.strip()
            if normalized_content in {"[image]", "[图片，识别中.....]"}:
                component.content = ""
                normalized_content = ""
            if not normalized_content and component.binary_data:
                found_unresolved = True
            continue

        if isinstance(component, EmojiComponent):
            normalized_content = component.content.strip()
            if normalized_content in {"[emoji]", "[表情包]"}:
                component.content = ""
                normalized_content = ""
            if not normalized_content and component.binary_data:
                found_unresolved = True
            continue

        if isinstance(component, ForwardNodeComponent):
            for forward_component in component.forward_components:
                if _prepare_unresolved_visual_components(forward_component.content):
                    found_unresolved = True

    return found_unresolved


def _build_complex_message_full_text(message_sequence: MessageSequence) -> str:
    """构造转发消息浏览工具返回的完整文本。"""

    full_parts: list[str] = []
    for component in message_sequence.components:
        if isinstance(component, ForwardNodeComponent):
            full_parts.append(_build_forward_full_text(component))
        elif isinstance(component, ForwardPlaceholderComponent):
            cached_nodes = get_cached_forward_nodes(component.forward_id)
            if cached_nodes is not None:
                forward_component = _build_forward_node_component_from_nodes(cached_nodes)
                if forward_component is not None:
                    full_parts.append(_build_forward_full_text(forward_component))
                else:
                    full_parts.append("[合并转发(拉取失败)]")
            else:
                full_parts.append("[合并转发(拉取失败)]")

    return "\n".join(part for part in full_parts if part).strip()


def _build_forward_full_text(component: ForwardNodeComponent) -> str:
    """构造合并转发消息的完整文本。"""

    forward_lines = ["【合并转发消息:"]
    for node in component.forward_components:
        sender_name = node.user_cardname or node.user_nickname or node.user_id or "未知用户"
        content = _render_components_inline(node.content) or "[空消息]"
        forward_lines.append(f"【{sender_name}】: {content}")
    forward_lines.append("】")
    return "\n".join(forward_lines)


def _build_complex_message_prompt_text(message_sequence: MessageSequence) -> str:
    """将转发消息转换为适合注入 Prompt 的摘要文本。"""

    prompt_parts: list[str] = []
    for component in message_sequence.components:
        rendered_text = _render_component_for_prompt(component)
        if rendered_text:
            prompt_parts.append(rendered_text)
    return "\n".join(part for part in prompt_parts if part).strip()


def _render_component_for_prompt(component: StandardMessageComponents) -> str:
    """将单个组件渲染为 Prompt 文本。"""

    if isinstance(component, TextComponent):
        return (component.text or "").strip()

    if isinstance(component, ImageComponent):
        return component.content.strip() if component.content else "[图片，识别中.....]"

    if isinstance(component, EmojiComponent):
        return component.content.strip() if component.content else "[表情包]"

    if isinstance(component, VoiceComponent):
        return component.content.strip() if component.content else "[语音消息]"

    if isinstance(component, FileComponent):
        return component.to_plain_text()

    if isinstance(component, AtComponent):
        return _render_at_component_text(component)

    if isinstance(component, ReplyComponent):
        return ""

    if isinstance(component, ForwardNodeComponent):
        return _build_forward_preview_block(component)

    if isinstance(component, DictComponent):
        raw_type = component.data.get("type") if isinstance(component.data, dict) else None
        if isinstance(raw_type, str) and raw_type.strip():
            return f"[{raw_type.strip()}消息]"
        return "[非标准消息]"

    return ""


def _build_forward_preview_block(component: ForwardNodeComponent) -> str:
    """构造转发消息的预览块。"""

    preview_lines = ["[消息类型]转发消息", f"预览前{FORWARD_PREVIEW_LIMIT}条："]
    preview_nodes = component.forward_components[:FORWARD_PREVIEW_LIMIT]

    for node in preview_nodes:
        sender_name = node.user_cardname or node.user_nickname or node.user_id or "未知用户"
        content = _render_components_inline(node.content) or "[空消息]"
        preview_lines.append(f"{sender_name}：{content}")

    total_count = len(component.forward_components)
    if total_count > FORWARD_PREVIEW_LIMIT:
        preview_lines.append("......")
        preview_lines.append(f"共{total_count}条，可以使用 view_forward_message 查看完整转发内容。")

    return "\n".join(preview_lines).strip()


def _render_components_inline(components: Sequence[StandardMessageComponents]) -> str:
    """将组件序列压缩为单行预览文本。"""

    rendered_parts: list[str] = []
    for component in components:
        if isinstance(component, ForwardNodeComponent):
            rendered_parts.append("[转发消息]")
            continue

        rendered_text = _render_component_for_prompt(component)
        normalized_text = _normalize_inline_text(rendered_text)
        if normalized_text:
            rendered_parts.append(normalized_text)

    return " ".join(rendered_parts).strip()


def _normalize_inline_text(text: str) -> str:
    """将多行文本压缩为适合预览的一行。"""

    return " ".join((text or "").split()).strip()


def _build_message_from_sequence(
    role: RoleType,
    message_sequence: MessageSequence,
    fallback_text: str,
    *,
    enable_visual_message: bool = True,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_calls: Optional[list[ToolCall]] = None,
    reasoning_content: Optional[str] = None,
) -> Optional[Message]:
    """根据消息片段构造统一 LLM 消息。"""
    builder = MessageBuilder().set_role(role)
    if role == RoleType.Assistant and tool_calls:
        builder.set_tool_calls(tool_calls)
    if role == RoleType.Tool and tool_call_id:
        builder.add_tool_call(tool_call_id)
    if role == RoleType.Tool and tool_name:
        builder.set_tool_name(tool_name)
    if role == RoleType.Assistant and reasoning_content:
        builder.set_reasoning_content(reasoning_content)

    has_content = False
    for component in message_sequence.components:
        if isinstance(component, TextComponent):
            if component.text.strip():
                builder.add_text_content(component.text)
                has_content = True
            continue

        if isinstance(component, EmojiComponent):
            has_content = (
                _append_emoji_component(
                    builder,
                    component,
                    enable_visual_message=enable_visual_message,
                )
                or has_content
            )
            continue

        if isinstance(component, ImageComponent):
            has_content = (
                _append_image_component(
                    builder,
                    component,
                    enable_visual_message=enable_visual_message,
                )
                or has_content
            )
            continue

        if isinstance(component, VoiceComponent):
            voice_text = component.content.strip() if component.content else "[语音消息]"
            builder.add_text_content(voice_text)
            has_content = True
            continue

        if isinstance(component, FileComponent):
            builder.add_text_content(component.to_plain_text())
            has_content = True
            continue

        if isinstance(component, AtComponent):
            has_content = _append_at_component(builder, component) or has_content
            continue

        if isinstance(component, ReplyComponent):
            has_content = _append_reply_component(builder, component) or has_content
            continue

        if isinstance(component, ForwardPlaceholderComponent):
            cached_nodes = get_cached_forward_nodes(component.forward_id)
            if cached_nodes:
                forward_node = _build_forward_node_component_from_nodes(cached_nodes)
                if forward_node is not None:
                    builder.add_text_content(_build_forward_preview_block(forward_node))
                    has_content = True
                    continue
            builder.add_text_content("[合并转发(拉取失败)]")
            has_content = True
            continue

    if not has_content and fallback_text.strip():
        builder.add_text_content(fallback_text)
        has_content = True

    if not has_content and not (role == RoleType.Assistant and tool_calls):
        return None
    return builder.build()


class ReferenceMessageType(str, Enum):
    """参考消息类型。"""

    CONTEXT_RESTORE = "context_restore"
    CUSTOM = "custom"
    JARGON = "jargon"
    MEMORY = "memory"
    PLANNER_TOOL_HINT = "planner_tool_hint"
    TOOL_HINT = "tool_hint"


class LLMContextMessage(ABC):
    """Maisaka 内部用于组织 LLM 上下文的统一消息抽象。"""

    timestamp: datetime

    @property
    @abstractmethod
    def role(self) -> str:
        """返回 LLM 消息角色。"""

    @property
    @abstractmethod
    def processed_plain_text(self) -> str:
        """返回可读的纯文本内容。"""

    @property
    def count_in_context(self) -> bool:
        """是否占用普通 user/assistant 上下文窗口。"""
        return True

    @property
    def source(self) -> str:
        """返回消息来源。"""
        return self.__class__.__name__

    @abstractmethod
    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        """转换为统一 LLM 消息。"""

    def consume_once(self) -> bool:
        """消费一次生命周期，返回是否继续保留。"""
        return True


@dataclass(slots=True)
class SessionBackedMessage(LLMContextMessage):
    """真实会话上下文消息。"""

    raw_message: MessageSequence
    visible_text: str
    timestamp: datetime
    message_id: Optional[str] = None
    original_message: Optional[SessionMessage] = None
    source_kind: str = "user"

    @property
    def role(self) -> str:
        return RoleType.User.value

    @property
    def processed_plain_text(self) -> str:
        return self.visible_text

    @property
    def source(self) -> str:
        return self.source_kind

    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        return _build_message_from_sequence(
            RoleType.User,
            self.raw_message,
            self.processed_plain_text,
            enable_visual_message=enable_visual_message,
        )

    @classmethod
    def from_session_message(
        cls,
        session_message: SessionMessage,
        *,
        raw_message: MessageSequence,
        visible_text: str,
        source_kind: str = "user",
    ) -> "SessionBackedMessage":
        """从真实 SessionMessage 构造上下文消息。"""
        return cls(
            raw_message=raw_message,
            visible_text=visible_text,
            timestamp=session_message.timestamp,
            message_id=session_message.message_id,
            original_message=session_message,
            source_kind=source_kind,
        )


@dataclass(slots=True)
class ComplexSessionMessage(SessionBackedMessage):
    """复杂消息上下文消息。"""

    prompt_text: str = ""
    complex_message_type: str = "forward"

    @property
    def source(self) -> str:
        return f"{self.source_kind}:{self.complex_message_type}"

    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        del enable_visual_message
        message_sequence = MessageSequence([TextComponent(self.prompt_text)])
        return _build_message_from_sequence(
            RoleType.User,
            message_sequence,
            self.prompt_text,
        )

    @classmethod
    def from_session_message(
        cls,
        session_message: SessionMessage,
        *,
        planner_prefix: str,
        visible_text: str,
        source_kind: str = "user",
    ) -> Optional["ComplexSessionMessage"]:
        """从真实 SessionMessage 构造复杂消息上下文消息。"""

        prompt_text = _build_complex_message_prompt_text(session_message.raw_message)
        if not prompt_text:
            return None

        return cls(
            raw_message=session_message.raw_message,
            visible_text=visible_text,
            timestamp=session_message.timestamp,
            message_id=session_message.message_id,
            original_message=session_message,
            source_kind=source_kind,
            prompt_text=f"{planner_prefix}{prompt_text}",
        )


@dataclass(slots=True)
class CompactionSummaryMessage(LLMContextMessage):
    """B 层 compaction 摘要消息（替换原段，占窗口）。

    ZG-25：select 后对 selected_history 中"可压缩段"做摘要替换，
    替换为一条本消息，释放 token 且信息损失最小。
    """

    summary_text: str
    timestamp: datetime
    original_segment_count: int = 0
    original_time_range: str = ""
    message_id: Optional[str] = None

    @property
    def role(self) -> str:
        return RoleType.User.value

    @property
    def processed_plain_text(self) -> str:
        return self.summary_text

    @property
    def count_in_context(self) -> bool:
        return True

    @property
    def source(self) -> str:
        return "compaction_summary"

    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        return Message(role=RoleType.User, parts=[TextMessagePart(text=self.summary_text)])


@dataclass(slots=True)
class ReferenceMessage(LLMContextMessage):
    """参考消息。"""

    content: str
    timestamp: datetime
    reference_type: ReferenceMessageType = ReferenceMessageType.CUSTOM
    remaining_uses_value: Optional[int] = 1
    display_prefix: str = "[参考消息]"

    @property
    def role(self) -> str:
        return RoleType.User.value

    @property
    def processed_plain_text(self) -> str:
        return f"{self.display_prefix}\n{self.content}".strip()

    @property
    def count_in_context(self) -> bool:
        return False

    @property
    def source(self) -> str:
        return self.reference_type.value

    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        del enable_visual_message
        message_sequence = MessageSequence([TextComponent(self.processed_plain_text)])
        return _build_message_from_sequence(RoleType.User, message_sequence, self.processed_plain_text)

    def consume_once(self) -> bool:
        if self.remaining_uses_value is None:
            return True

        self.remaining_uses_value -= 1
        return self.remaining_uses_value > 0


@dataclass(slots=True)
class AssistantMessage(LLMContextMessage):
    """内部 assistant 消息。"""

    content: str
    timestamp: datetime
    tool_calls: list[ToolCall] = field(default_factory=list)
    source_kind: str = "assistant"
    reasoning_content: str | None = None

    @property
    def role(self) -> str:
        return RoleType.Assistant.value

    @property
    def processed_plain_text(self) -> str:
        return self.content

    @property
    def count_in_context(self) -> bool:
        return self.source_kind != "perception"

    @property
    def source(self) -> str:
        return self.source_kind

    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        del enable_visual_message
        message_sequence = MessageSequence([])
        if self.content:
            message_sequence.text(self.content)
        return _build_message_from_sequence(
            RoleType.Assistant,
            message_sequence,
            self.content,
            tool_calls=self.tool_calls or None,
            reasoning_content=self.reasoning_content,
        )


@dataclass(slots=True)
class ToolResultMessage(LLMContextMessage):
    """工具返回结果消息。"""

    content: str
    timestamp: datetime
    tool_call_id: str
    tool_name: str = ""
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def role(self) -> str:
        return RoleType.Tool.value

    @property
    def processed_plain_text(self) -> str:
        return self.content

    @property
    def count_in_context(self) -> bool:
        return False

    @property
    def source(self) -> str:
        return self.tool_name or "tool"

    def to_llm_message(self, enable_visual_message: bool = True) -> Optional[Message]:
        del enable_visual_message
        message_sequence = MessageSequence([TextComponent(self.content)])
        return _build_message_from_sequence(
            RoleType.Tool,
            message_sequence,
            self.content,
            tool_call_id=self.tool_call_id,
            tool_name=self.tool_name,
        )


def build_llm_message_from_context(
    context_message: LLMContextMessage,
    *,
    enable_visual_message: bool = True,
) -> Optional[Message]:
    """将 Maisaka 内部上下文消息转换为发给 LLM 的统一消息。"""

    return context_message.to_llm_message(enable_visual_message=enable_visual_message)
