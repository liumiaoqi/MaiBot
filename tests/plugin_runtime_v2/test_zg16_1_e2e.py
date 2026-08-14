"""ZG16-1 QQ 适配器上下文供给链端到端测试。

覆盖 napcat 适配器 emit 端 → Host 解析 → prompt 渲染全链路，
验证 face/record/video/forward 段、@ 段、reply 语义、metadata 保留、
群名片/群名、forward 预取与读缓存等 9 类场景。
"""


import contextlib
import inspect
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── 插件包 bootstrap ──────────────────────────────────────────────────
# plugins/maibot-team.napcat-adapter 目录名含连字符，无法直接 import，
# 注册为 plugins.maibot_team.napcat_adapter 包供测试 import。
_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "maibot-team.napcat-adapter"
_PKG = "plugins.maibot_team.napcat_adapter"


def _bootstrap_plugin_package() -> None:
    if _PKG in sys.modules:
        return
    for parent in ("plugins", "plugins.maibot_team"):
        if parent not in sys.modules:
            mod = types.ModuleType(parent)
            mod.__path__ = []  # type: ignore[assignment]
            sys.modules[parent] = mod
    for sub, rel in [("", ""), (".codecs", "codecs"), (".codecs.inbound", "codecs/inbound"), (".services", "services")]:
        full = _PKG + sub
        mod = types.ModuleType(full)
        mod.__path__ = [str(_PLUGIN_DIR / rel)] if rel else [str(_PLUGIN_DIR)]  # type: ignore[assignment]
        sys.modules[full] = mod


_bootstrap_plugin_package()

from plugins.maibot_team.napcat_adapter.codecs.inbound.message_codec import NapCatInboundCodec  # noqa: E402
from plugins.maibot_team.napcat_adapter.session_mapper import SessionIdMapper  # noqa: E402
from src.common.data_models.message_component_data_model import (  # noqa: E402
    AtComponent,
    DictComponent,
    ForwardPlaceholderComponent,
    MessageSequence,
    ReplyComponent,
    TextComponent,
    VoiceComponent,
)
from src.common.data_models.session_message_data_model import SessionMessage  # noqa: E402
from src.core.forward_fetch_port_registry import reset_forward_fetch_port, set_forward_fetch_port  # noqa: E402
from src.llm_models.payload_content.message import RoleType  # noqa: E402
from src.maisaka.context.messages import (  # noqa: E402
    _build_message_from_sequence,
    prefetch_forward_nodes_for_messages,
    reset_forward_cache,
)
from src.plugin_runtime.host.message_utils import PluginMessageUtils  # noqa: E402
from src.plugin_runtime_v2.mcp.payload_converter import NapCatPayloadConverter  # noqa: E402


# ── 辅助构造 ──────────────────────────────────────────────────────────


def _make_codec() -> NapCatInboundCodec:
    """构造测试用 NapCatInboundCodec（query_service 全 mock，download_binary 返回 None）。"""
    query_service = MagicMock()
    query_service.download_binary = AsyncMock(return_value=None)
    sid_mapper = SessionIdMapper()
    return NapCatInboundCodec(self_id="999", query_service=query_service, sid_mapper=sid_mapper)


def _make_payload(
    message: list,
    *,
    message_type: str = "private",
    user_id: str = "1001",
    group_id: str = "",
    group_name: str | None = None,
    sender_nick: str = "测试用户",
    sender_card: str | None = None,
) -> dict:
    """构造 OneBot 11 消息 payload。"""
    payload: dict = {
        "message_type": message_type,
        "self_id": "999",
        "user_id": user_id,
        "sender": {"user_id": user_id, "nickname": sender_nick},
        "message_id": "m1",
        "message": message,
    }
    if sender_card is not None:
        payload["sender"]["card"] = sender_card
    if message_type == "group":
        payload["group_id"] = group_id or "2001"
        if group_name is not None:
            payload["group_name"] = group_name
    return payload


async def _e2e(payload: dict) -> tuple[SessionMessage, NapCatInboundCodec]:
    """OneBot payload → SessionMessage 端到端转换（适配器 emit → Host 解析）。"""
    codec = _make_codec()
    event_name, event_payload = await codec.build_event_payload(payload)
    converter = NapCatPayloadConverter()
    return converter.convert(event_payload, event_name), codec


def _render_prompt(session_message: SessionMessage) -> str:
    """SessionMessage → prompt 文本（同步渲染，零网络调用）。"""
    fallback = session_message.processed_plain_text or ""
    msg = _build_message_from_sequence(RoleType.User, session_message.raw_message, fallback)
    return msg.get_text_content() if msg else ""


@contextlib.contextmanager
def _mock_reply_db(*, found: bool, content: str = "", sender: str = ""):
    """mock 回复组件 DB 查询——found=False 模拟原消息未找到。"""
    mock_session = MagicMock()
    if found:
        db_msg = MagicMock()
        db_msg.processed_plain_text = content
        db_msg.user_cardname = sender
        db_msg.user_nickname = None
        db_msg.user_id = None
        mock_session.exec.return_value.first.return_value = db_msg
    else:
        mock_session.exec.return_value.first.return_value = None
    with patch("src.common.database.database.get_db_session") as mock_get:
        mock_get.return_value.__enter__.return_value = mock_session
        mock_get.return_value.__exit__.return_value = False
        yield


# ════════════════════════════════════════════════════════════════════
# 5.1 face 段端到端测试
# ════════════════════════════════════════════════════════════════════


async def test_face_segment_e2e():
    """face 段：OneBot {id:178} → 适配器 emit {data:"178"} → Host [表情:178] → prompt 含 [表情:178]。"""
    payload = _make_payload([{"type": "face", "data": {"id": "178"}}])
    msg, _ = await _e2e(payload)
    prompt = _render_prompt(msg)
    assert "[表情:178]" in prompt
    assert prompt.strip() != ""


async def test_face_segment_host_fallback_empty_id():
    """face_id 为空时 Host 端降级为 [表情]（防御性降级，适配器总是兜底 "0"）。"""
    component = PluginMessageUtils._component_from_dict({"type": "face", "data": ""})
    assert isinstance(component, TextComponent)
    assert component.text == "[表情]"


# ════════════════════════════════════════════════════════════════════
# 5.2 record→voice 段端到端测试
# ════════════════════════════════════════════════════════════════════


async def test_record_to_voice_segment_e2e():
    """record 段：OneBot {type:record} → 适配器 emit {type:voice,data:""} → Host VoiceComponent → [语音消息]。"""
    payload = _make_payload([{"type": "record", "data": {}}])
    msg, _ = await _e2e(payload)
    assert any(isinstance(c, VoiceComponent) for c in msg.raw_message.components)
    prompt = _render_prompt(msg)
    assert "[语音消息]" in prompt
    assert prompt.strip() != ""


def test_voice_asr_success_render():
    """ASR 成功 mock：VoiceComponent content 非空 → prompt 含转写文本。"""
    seq = MessageSequence(components=[VoiceComponent(binary_hash="", content="你好语音")])
    msg = _build_message_from_sequence(RoleType.User, seq, "")
    assert msg is not None
    assert "你好语音" in msg.get_text_content()


# ════════════════════════════════════════════════════════════════════
# 5.3 video 段端到端测试
# ════════════════════════════════════════════════════════════════════


async def test_video_segment_e2e():
    """video 段：OneBot {type:video} → 适配器 emit {type:video,data:""} → Host [视频] → prompt 含 [视频]。"""
    payload = _make_payload([{"type": "video", "data": {}}])
    msg, _ = await _e2e(payload)
    prompt = _render_prompt(msg)
    assert "[视频]" in prompt
    assert prompt.strip() != ""


# ════════════════════════════════════════════════════════════════════
# 5.4 @ 段端到端测试
# ════════════════════════════════════════════════════════════════════


async def test_at_segment_e2e():
    """@ 段：OneBot {qq:1001,name:小美} → 适配器 emit target_user_id/nickname → Host AtComponent → @小美。"""
    payload = _make_payload([
        {"type": "at", "data": {"qq": "1001", "name": "小美"}},
        {"type": "text", "data": "你好"},
    ])
    msg, _ = await _e2e(payload)
    prompt = _render_prompt(msg)
    assert "@小美" in prompt
    assert "@None" not in prompt
    assert prompt.count("@小美") == 1


async def test_at_segment_empty_name_fallback_text():
    """at_name 为空时适配器追加兜底 text 段 @qq（不渲染成 @None 噪声）。"""
    codec = _make_codec()
    payload = _make_payload([{"type": "at", "data": {"qq": "1001"}}])
    _, event_payload = await codec.build_event_payload(payload)
    segments = event_payload["segments"]
    assert any(s["type"] == "at" for s in segments)
    text_segs = [s for s in segments if s["type"] == "text"]
    assert any(s["data"] == "@1001" for s in text_segs)
    msg = NapCatPayloadConverter().convert(event_payload, "napcat.message")
    prompt = _render_prompt(msg)
    assert "@None" not in prompt


# ════════════════════════════════════════════════════════════════════
# 5.5 reply 段端到端测试
# ════════════════════════════════════════════════════════════════════


async def test_reply_segment_e2e_with_db():
    """reply 段：原消息在库 → prompt 含 [回复了{sender}的消息: {原内容}]，fallback 不触发。"""
    payload = _make_payload([
        {"type": "reply", "data": {"id": "12345"}},
        {"type": "text", "data": "你好"},
    ])
    msg, _ = await _e2e(payload)
    assert any(isinstance(c, ReplyComponent) for c in msg.raw_message.components)
    with _mock_reply_db(found=True, content="原内容", sender="原发送者"):
        prompt = _render_prompt(msg)
    assert "[回复了原发送者的消息: 原内容]" in prompt
    assert "你好" in prompt
    assert prompt.count("[回复了原发送者的消息: 原内容]") == 1


async def test_reply_segment_not_found_fallback():
    """reply 段：原消息查不到 → 降级 [回复了未知用户的消息: (原消息未找到)]。"""
    payload = _make_payload([{"type": "reply", "data": {"id": "12345"}}])
    msg, _ = await _e2e(payload)
    with _mock_reply_db(found=False):
        prompt = _render_prompt(msg)
    assert "[回复了未知用户的消息: (原消息未找到)]" in prompt


# ════════════════════════════════════════════════════════════════════
# 5.6 群名片与群名测试
# ════════════════════════════════════════════════════════════════════


async def test_group_card_available():
    """群名片可用：sender card="老张" → user_cardname="老张"。"""
    payload = _make_payload(
        [{"type": "text", "data": "你好"}],
        message_type="group",
        group_name="技术交流群",
        sender_nick="张三",
        sender_card="老张",
    )
    msg, _ = await _e2e(payload)
    assert msg.message_info.user_info.user_cardname == "老张"
    assert msg.message_info.user_info.user_nickname == "张三"


async def test_group_card_empty_fallback_nickname():
    """群名片未填：card="" → user_cardname=None，user_nickname 兜底。"""
    payload = _make_payload(
        [{"type": "text", "data": "你好"}],
        message_type="group",
        sender_nick="张三",
        sender_card="",
    )
    msg, _ = await _e2e(payload)
    assert msg.message_info.user_info.user_cardname is None
    assert msg.message_info.user_info.user_nickname == "张三"


async def test_group_name_available():
    """群名可用：group_name="技术交流群" → GroupInfo.group_name="技术交流群"。"""
    payload = _make_payload(
        [{"type": "text", "data": "你好"}],
        message_type="group",
        group_name="技术交流群",
    )
    msg, _ = await _e2e(payload)
    assert msg.message_info.group_info is not None
    assert msg.message_info.group_info.group_name == "技术交流群"


async def test_group_name_empty_fallback_group_id():
    """群名未填：Host 用 group_id 降级。"""
    payload = _make_payload(
        [{"type": "text", "data": "你好"}],
        message_type="group",
        group_id="2001",
        group_name=None,
    )
    msg, _ = await _e2e(payload)
    assert msg.message_info.group_info is not None
    assert msg.message_info.group_info.group_name == "2001"


def test_at_render_prefers_cardname():
    """@ 段渲染优先用 cardname（端到端链路中 cardname 由额外查询填充）。"""
    seq = MessageSequence(components=[
        AtComponent(target_user_id="1001", target_user_nickname="张三", target_user_cardname="老张"),
    ])
    msg = _build_message_from_sequence(RoleType.User, seq, "")
    assert msg is not None
    assert "@老张" in msg.get_text_content()


# ════════════════════════════════════════════════════════════════════
# 5.7 metadata 保留测试
# ════════════════════════════════════════════════════════════════════


async def test_metadata_with_at():
    """含 @ 段：at_user_ids 非空，is_mentioned=True 兼容。"""
    payload = _make_payload([{"type": "at", "data": {"qq": "1001", "name": "小美"}}])
    msg, _ = await _e2e(payload)
    assert msg.message_info.additional_config["at_user_ids"] == ["1001"]
    assert msg.is_mentioned is True


async def test_metadata_with_reply():
    """含 reply 段：reply_message_id 保留。"""
    payload = _make_payload([{"type": "reply", "data": {"id": "12345"}}])
    msg, _ = await _e2e(payload)
    assert msg.message_info.additional_config["reply_message_id"] == "12345"


async def test_metadata_no_at_empty_list():
    """无 @ 段：at_user_ids=[] 空列表非 None。"""
    payload = _make_payload([{"type": "text", "data": "你好"}])
    msg, _ = await _e2e(payload)
    assert msg.message_info.additional_config["at_user_ids"] == []
    assert msg.is_mentioned is False


async def test_metadata_no_reply_none():
    """无 reply 段：reply_message_id=None。"""
    payload = _make_payload([{"type": "text", "data": "你好"}])
    msg, _ = await _e2e(payload)
    assert msg.message_info.additional_config["reply_message_id"] is None


async def test_metadata_platform_card_payloads_is_list():
    """platform_card_payloads 字段始终为列表（json 卡片深度测试在 cards 单测）。"""
    payload = _make_payload([{"type": "text", "data": "你好"}])
    msg, _ = await _e2e(payload)
    assert msg.message_info.additional_config["platform_card_payloads"] == []


# ════════════════════════════════════════════════════════════════════
# 5.8 forward 预取与读缓存测试
# ════════════════════════════════════════════════════════════════════


async def test_forward_prefetch_failure_fallback():
    """①预取失败（port 抛错）→ 同步渲染降级占位 [合并转发(拉取失败)] 不阻塞 prompt 构建。"""
    reset_forward_cache()
    port = AsyncMock()
    port.fetch_forward_nodes = AsyncMock(side_effect=RuntimeError("模拟超时"))
    set_forward_fetch_port(port)
    try:
        payload = _make_payload([{"type": "forward", "data": {"id": "fwd1"}}])
        msg, _ = await _e2e(payload)
        assert any(isinstance(c, ForwardPlaceholderComponent) for c in msg.raw_message.components)
        port.fetch_forward_nodes.assert_not_called()
        await prefetch_forward_nodes_for_messages([msg])
        port.fetch_forward_nodes.assert_called_once_with("fwd1")
        prompt = _render_prompt(msg)
        assert "[合并转发(拉取失败)]" in prompt
    finally:
        reset_forward_fetch_port()
        reset_forward_cache()


async def test_forward_cache_hit_across_sessions():
    """②预取命中全局缓存 → 同一 forward_id 多次 prompt 构建 get_forward_msg 只调一次（跨会话命中）。"""
    reset_forward_cache()
    port = AsyncMock()
    port.fetch_forward_nodes = AsyncMock(return_value=[
        {"user_nickname": "用户A", "user_id": "u1", "user_cardname": None, "message_id": "n1",
         "content": [{"type": "text", "data": "内容A"}]},
    ])
    set_forward_fetch_port(port)
    try:
        payload1 = _make_payload([{"type": "forward", "data": {"id": "fwd1"}}], user_id="1001")
        payload2 = _make_payload([{"type": "forward", "data": {"id": "fwd1"}}], user_id="2002")
        msg1, _ = await _e2e(payload1)
        msg2, _ = await _e2e(payload2)
        await prefetch_forward_nodes_for_messages([msg1])
        await prefetch_forward_nodes_for_messages([msg2])
        assert port.fetch_forward_nodes.call_count == 1
        prompt1 = _render_prompt(msg1)
        assert "用户A" in prompt1
        assert "内容A" in prompt1
    finally:
        reset_forward_fetch_port()
        reset_forward_cache()


async def test_forward_sync_render_zero_network():
    """③同步渲染 forward 分支零网络调用：port 仅预取阶段调一次，渲染不增加调用。"""
    reset_forward_cache()
    port = AsyncMock()
    port.fetch_forward_nodes = AsyncMock(return_value=[
        {"user_nickname": "用户A", "user_id": "u1", "user_cardname": None, "message_id": "n1",
         "content": [{"type": "text", "data": "内容A"}]},
    ])
    set_forward_fetch_port(port)
    try:
        payload = _make_payload([{"type": "forward", "data": {"id": "fwd1"}}])
        msg, codec = await _e2e(payload)
        port.fetch_forward_nodes.assert_not_called()
        await prefetch_forward_nodes_for_messages([msg])
        assert port.fetch_forward_nodes.call_count == 1
        prompt = _render_prompt(msg)
        assert port.fetch_forward_nodes.call_count == 1
        assert "用户A" in prompt
        assert "内容A" in prompt
        assert not inspect.iscoroutinefunction(_build_message_from_sequence)
        codec._query_service.download_binary.assert_not_called()
    finally:
        reset_forward_fetch_port()
        reset_forward_cache()


# ════════════════════════════════════════════════════════════════════
# 5.9 回归测试
# ════════════════════════════════════════════════════════════════════


async def test_regression_plain_text_unchanged():
    """纯文本消息 prompt 仍为原文（100% 匹配不回归）。"""
    payload = _make_payload([{"type": "text", "data": "你好世界"}])
    msg, _ = await _e2e(payload)
    prompt = _render_prompt(msg)
    assert prompt == "你好世界"


async def test_regression_image_fallback_placeholder():
    """图片消息仍降级为 [图片，识别中.....]（本批不动图片链路）。"""
    payload = _make_payload([{"type": "image", "data": {"url": "http://x.com/1.png"}}])
    msg, _ = await _e2e(payload)
    prompt = _render_prompt(msg)
    assert "[图片，识别中.....]" in prompt


async def test_regression_mixed_reply_at_text_no_at_none_no_duplicate():
    """reply + @ + 文本混合：prompt 含 [回复了...] + @昵称 + 文本，无 @None 无双重输出。"""
    payload = _make_payload([
        {"type": "reply", "data": {"id": "12345"}},
        {"type": "at", "data": {"qq": "1001", "name": "小美"}},
        {"type": "text", "data": "你好"},
    ])
    msg, _ = await _e2e(payload)
    with _mock_reply_db(found=True, content="原内容", sender="原发送者"):
        prompt = _render_prompt(msg)
    assert "[回复了原发送者的消息: 原内容]" in prompt
    assert "@小美" in prompt
    assert "你好" in prompt
    assert "@None" not in prompt
    assert prompt.count("[回复了原发送者的消息: 原内容]") == 1


def test_regression_old_segment_type_no_crash_dict_component():
    """旧消息旧段类型解析不崩溃落 DictComponent。"""
    component = PluginMessageUtils._component_from_dict({"type": "unknown_old_type", "data": {"foo": "bar"}})
    assert isinstance(component, DictComponent)


async def test_regression_is_mentioned_compat():
    """is_mentioned 兼容：at_user_ids 非空时 is_mentioned=True 与现状一致。"""
    payload = _make_payload([{"type": "at", "data": {"qq": "1001", "name": "小美"}}])
    msg, _ = await _e2e(payload)
    assert msg.is_mentioned is True
    assert msg.message_info.additional_config["at_user_ids"] == ["1001"]