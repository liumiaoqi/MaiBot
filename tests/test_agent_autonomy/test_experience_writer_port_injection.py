"""MF-P0-001 验收：ExperienceWriter memory_port 必选注入（禁止 None 静默降级）。

对应 tasks.md 1.1：构造不传 memory_port 抛 TypeError；显式 None 抛 ValueError；
有效端口构造成功且 write_experience 正常调用 observe_experience。
"""

import asyncio
import pytest
from unittest.mock import MagicMock

from src.maisaka.agent_autonomy.experience_writer import ExperienceWriter
from src.core.types import SilenceReason, ThinkAction, ThinkResult


def _valid_memory_port() -> MagicMock:
    port = MagicMock()
    port.observe_experience.return_value = MagicMock(success=True)
    return port


def test_construct_without_memory_port_raises_type_error() -> None:
    """必选参数缺失 → TypeError（agent 初始化必须注入端口）。"""
    with pytest.raises(TypeError):
        ExperienceWriter()


def test_construct_with_explicit_none_raises_value_error() -> None:
    """显式传 None → ValueError（禁止 memory_port=None 静默降级）。"""
    with pytest.raises(ValueError, match="注入失败"):
        ExperienceWriter(memory_port=None)


def test_construct_with_valid_port_succeeds() -> None:
    """有效端口构造成功。"""
    writer = ExperienceWriter(memory_port=_valid_memory_port())
    assert writer._memory_port is not None


async def test_write_experience_calls_observe_with_valid_port() -> None:
    """有效端口下 write_experience 不再跳过，调用 observe_experience。"""
    port = _valid_memory_port()
    writer = ExperienceWriter(memory_port=port)
    result = ThinkResult(
        action=ThinkAction.REPLY,
        text="今天天气不错，我们一起去公园散步吧。",
        silence_reason=SilenceReason.NO_CONTENT,
        thought_summary="",
        emotion_type="joy",
    )
    writer.write_experience(result, session_id="s1", agent_id="test_agent")
    await asyncio.sleep(0)  # 让 fire-and-forget 任务执行完
    port.observe_experience.assert_called_once()
    request = port.observe_experience.call_args.args[0]
    assert request.agent_id == "test_agent"
    assert "回复:" in request.text


def test_should_write_gates_by_rule() -> None:
    """规则门控：短文本不写，长回复与 INTENTIONAL 深思写。"""
    short = ThinkResult(
        action=ThinkAction.REPLY, text="hi", silence_reason=SilenceReason.NO_CONTENT,
        thought_summary="", emotion_type="neutral",
    )
    assert ExperienceWriter.should_write(short) is False

    long_reply = ThinkResult(
        action=ThinkAction.REPLY, text="x" * 30, silence_reason=SilenceReason.NO_CONTENT,
        thought_summary="", emotion_type="neutral",
    )
    assert ExperienceWriter.should_write(long_reply) is True

    intentional = ThinkResult(
        action=ThinkAction.SILENT, silence_reason=SilenceReason.INTENTIONAL,
        text="", thought_summary="深思熟虑之后，决定此刻安静不打扰对方更好", emotion_type="neutral",
    )
    assert ExperienceWriter.should_write(intentional) is True

    brief_intentional = ThinkResult(
        action=ThinkAction.SILENT, silence_reason=SilenceReason.INTENTIONAL,
        text="", thought_summary="不回", emotion_type="neutral",
    )
    assert ExperienceWriter.should_write(brief_intentional) is False
