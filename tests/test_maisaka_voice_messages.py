from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.data_models.message_component_data_model import MessageSequence, TextComponent, VoiceComponent
from src.llm_models.payload_content.message import RoleType
from src.maisaka.context_messages import _build_message_from_sequence
from src.maisaka.history_utils import build_prefixed_message_sequence
from src.maisaka.message_adapter import build_visible_text_from_sequence


def test_visible_text_keeps_transcribed_voice_content() -> None:
    message_sequence = MessageSequence(
        [
            TextComponent("[msg_id:voice-1][用户]"),
            VoiceComponent(binary_hash="voice-hash", content="[语音: 麦麦睡了吗？]"),
        ]
    )

    assert build_visible_text_from_sequence(message_sequence) == "[msg_id:voice-1][用户][语音: 麦麦睡了吗？]"


def test_prefixed_voice_message_reaches_llm_text_content() -> None:
    message_sequence = MessageSequence(
        [VoiceComponent(binary_hash="voice-hash", content="[语音: 麦麦睡了吗？]")]
    )
    prefixed_sequence = build_prefixed_message_sequence(
        message_sequence,
        "[msg_id]voice-1\n[时间]04:21:36\n[用户名]用户\n[发言内容]\n",
    )

    llm_message = _build_message_from_sequence(
        RoleType.User,
        prefixed_sequence,
        fallback_text="",
        enable_visual_message=False,
    )

    assert llm_message is not None
    assert llm_message.get_text_content().endswith("[发言内容]\n[语音: 麦麦睡了吗？]")


def test_empty_voice_message_uses_stable_placeholder() -> None:
    message_sequence = MessageSequence([VoiceComponent(binary_hash="voice-hash")])

    assert build_visible_text_from_sequence(message_sequence) == "[语音消息]"

    llm_message = _build_message_from_sequence(
        RoleType.User,
        message_sequence,
        fallback_text="",
        enable_visual_message=False,
    )
    assert llm_message is not None
    assert llm_message.get_text_content() == "[语音消息]"
