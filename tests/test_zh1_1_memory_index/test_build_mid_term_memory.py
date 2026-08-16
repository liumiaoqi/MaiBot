"""ZH1-1a build_mid_term_memory_message 重写测试 — 摘要生成核心流程。

覆盖 spec 6.1 指针构造、6.2 数据约束、LLM 调用 mid_memory 任务、
json_repair 兜底、recall_cue embedding、token 记录、LLM 失败降级。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import (
    MID_TERM_MEMORY_COMPLEX_TYPE,
    MID_TERM_MEMORY_SOURCE_KIND,
    MidTermMemorySummaryModel,
    _select_summary_source_messages,
    build_mid_term_memory_complex_message,
    build_mid_term_memory_message,
)


def _make_user_msg(text: str = "你好", ts: datetime | None = None) -> SimpleNamespace:
    """构造 mock user 消息（可被 _select_summary_source_messages 选中）。"""
    return SimpleNamespace(
        role="user",
        processed_plain_text=text,
        timestamp=ts or datetime(2024, 1, 1),
    )


def _make_assistant_msg(text: str = "回复") -> SimpleNamespace:
    """构造 mock assistant 消息（应被 _select 跳过）。"""
    return SimpleNamespace(role="assistant", processed_plain_text=text, timestamp=datetime(2024, 1, 1))


class TestSelectSummarySourceMessages:
    """可摘要消息筛选测试。"""

    def test_select_summary_source_messages(self) -> None:
        """可摘要消息筛选：仅 role=user 且有文本且非 mid_term_memory。"""
        msgs = [
            _make_user_msg("你好"),
            _make_assistant_msg("回复"),
            _make_user_msg(""),  # 空文本跳过
            _make_user_msg("   "),  # 空白跳过
        ]
        result = _select_summary_source_messages(msgs)
        assert len(result) == 1
        assert result[0].processed_plain_text == "你好"

    def test_all_assistant_skip(self) -> None:
        """全 assistant 消息筛选结果为空。"""
        msgs = [_make_assistant_msg(), _make_assistant_msg()]
        result = _select_summary_source_messages(msgs)
        assert result == []


class TestBuildMidTermMemoryMessage:
    """build_mid_term_memory_message 核心流程测试。"""

    @pytest.mark.asyncio
    async def test_all_assistant_skip_return_none(self) -> None:
        """全 assistant 跳过：build 返回 None。"""
        msgs = [_make_assistant_msg(), _make_assistant_msg()]
        result = await build_mid_term_memory_message(msgs, session_id="sess1")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_call_mid_memory(self) -> None:
        """LLM 调用 mid_memory 任务：generate_response_with_messages 首参为 mid_memory。"""
        mock_llm = MagicMock()
        mock_result = SimpleNamespace(
            response='{"summary": "s", "recall_cues": ["c"]}',
            prompt_tokens=10, completion_tokens=5, total_tokens=15, model_name="m",
        )
        mock_llm.generate_response_with_messages = AsyncMock(return_value=mock_result)
        user_msg = _make_user_msg("测试对话")
        with patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]), \
             patch("src.maisaka.memory.mid_term._build_time_range", return_value="tr"), \
             patch("src.maisaka.memory.mid_term._collect_participants", return_value=["p"]), \
             patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"), \
             patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]), \
             patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"), \
             patch("src.maisaka.memory.mid_term._parse_summary_response", return_value=MidTermMemorySummaryModel(summary="s", recall_cues=["c"])), \
             patch("src.maisaka.memory.mid_term._build_recall_cue_embeddings", new=AsyncMock(return_value=[])), \
             patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm):
            await build_mid_term_memory_message([user_msg], session_id="sess1")
        mock_llm.generate_response_with_messages.assert_called_once()
        call_args = mock_llm.generate_response_with_messages.call_args
        assert call_args.args[0] == "mid_memory"

    @pytest.mark.asyncio
    async def test_parse_response_failure_return_none(self) -> None:
        """响应解析失败（json_repair 兜底后仍无效）返回 None。"""
        mock_llm = MagicMock()
        mock_result = SimpleNamespace(
            response="not-json",
            prompt_tokens=10, completion_tokens=5, total_tokens=15, model_name="m",
        )
        mock_llm.generate_response_with_messages = AsyncMock(return_value=mock_result)
        user_msg = _make_user_msg("测试")
        with patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]), \
             patch("src.maisaka.memory.mid_term._build_time_range", return_value="tr"), \
             patch("src.maisaka.memory.mid_term._collect_participants", return_value=["p"]), \
             patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"), \
             patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]), \
             patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"), \
             patch("src.maisaka.memory.mid_term._parse_summary_response", return_value=None), \
             patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm):
            result = await build_mid_term_memory_message([user_msg], session_id="sess1")
        assert result is None

    @pytest.mark.asyncio
    async def test_recall_cue_embedding(self) -> None:
        """recall_cue embedding 生成：_build_recall_cue_embeddings 被调用。"""
        mock_llm = MagicMock()
        mock_result = SimpleNamespace(
            response='{"summary": "s", "recall_cues": ["c1", "c2"]}',
            prompt_tokens=10, completion_tokens=5, total_tokens=15, model_name="m",
        )
        mock_llm.generate_response_with_messages = AsyncMock(return_value=mock_result)
        user_msg = _make_user_msg("测试")
        embed_mock = AsyncMock(return_value=[{"text": "c1", "embedding": [0.1]}])
        with patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]), \
             patch("src.maisaka.memory.mid_term._build_time_range", return_value="tr"), \
             patch("src.maisaka.memory.mid_term._collect_participants", return_value=["p"]), \
             patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"), \
             patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]), \
             patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"), \
             patch("src.maisaka.memory.mid_term._parse_summary_response", return_value=MidTermMemorySummaryModel(summary="s", recall_cues=["c1", "c2"])), \
             patch("src.maisaka.memory.mid_term._build_recall_cue_embeddings", new=embed_mock), \
             patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm):
            await build_mid_term_memory_message([user_msg], session_id="sess1")
        embed_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_record(self) -> None:
        """token 记录：MidTermMemoryBuildResult 含 prompt/completion/total tokens。"""
        mock_llm = MagicMock()
        mock_result = SimpleNamespace(
            response='{"summary": "s", "recall_cues": ["c"]}',
            prompt_tokens=100, completion_tokens=50, total_tokens=150, model_name="test-model",
        )
        mock_llm.generate_response_with_messages = AsyncMock(return_value=mock_result)
        user_msg = _make_user_msg("测试")
        with patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]), \
             patch("src.maisaka.memory.mid_term._build_time_range", return_value="tr"), \
             patch("src.maisaka.memory.mid_term._collect_participants", return_value=["p"]), \
             patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"), \
             patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]), \
             patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"), \
             patch("src.maisaka.memory.mid_term._parse_summary_response", return_value=MidTermMemorySummaryModel(summary="s", recall_cues=["c"])), \
             patch("src.maisaka.memory.mid_term._build_recall_cue_embeddings", new=AsyncMock(return_value=[])), \
             patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm):
            result = await build_mid_term_memory_message([user_msg], session_id="sess1")
        assert result is not None
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50
        assert result.total_tokens == 150
        assert result.model_name == "test-model"

    @pytest.mark.asyncio
    async def test_llm_failure_return_none(self) -> None:
        """LLM 失败（返回空响应导致解析失败）返回 None。"""
        mock_llm = MagicMock()
        mock_result = SimpleNamespace(
            response="",
            prompt_tokens=0, completion_tokens=0, total_tokens=0, model_name="",
        )
        mock_llm.generate_response_with_messages = AsyncMock(return_value=mock_result)
        user_msg = _make_user_msg("测试")
        with patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]), \
             patch("src.maisaka.memory.mid_term._build_time_range", return_value="tr"), \
             patch("src.maisaka.memory.mid_term._collect_participants", return_value=["p"]), \
             patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"), \
             patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]), \
             patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"), \
             patch("src.maisaka.memory.mid_term._parse_summary_response", return_value=None), \
             patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm):
            result = await build_mid_term_memory_message([user_msg], session_id="sess1")
        assert result is None


class TestBuildMidTermMemoryComplexMessage:
    """build_mid_term_memory_complex_message 指针构造测试（纯函数）。"""

    def test_pointer_construction(self) -> None:
        """指针构造：payload.data 含 session_id + time_range_pointer（spec 6.2）。"""
        payload = MidTermMemorySummaryModel(summary="摘要内容", recall_cues=["线索"])
        source_msgs = [SimpleNamespace(timestamp=datetime(2024, 1, 1, 10, 0, 0))]
        msg = build_mid_term_memory_complex_message(
            payload,
            time_range="2024-01-01 10:00 ~ 2024-01-01 11:00",
            participants=["alice", "bob"],
            source_messages=source_msgs,
            session_id="group:12345",
        )
        comp = msg.raw_message.components[0]
        inner = comp.data["data"]
        assert inner["session_id"] == "group:12345"
        assert inner["time_range_pointer"] == "2024-01-01 10:00 ~ 2024-01-01 11:00"
        assert inner["time_range"] == "2024-01-01 10:00 ~ 2024-01-01 11:00"

    def test_message_type_marker(self) -> None:
        """消息类型标记：complex_message_type + source_kind 正确。"""
        payload = MidTermMemorySummaryModel(summary="s", recall_cues=[])
        source_msgs = [SimpleNamespace(timestamp=datetime(2024, 1, 1))]
        msg = build_mid_term_memory_complex_message(
            payload,
            time_range="tr",
            participants=["p"],
            source_messages=source_msgs,
            session_id="sess1",
        )
        assert msg.complex_message_type == MID_TERM_MEMORY_COMPLEX_TYPE
        assert msg.source_kind == MID_TERM_MEMORY_SOURCE_KIND

    def test_empty_session_id_pointer(self) -> None:
        """session_id 为空时指针字段为空字符串（向后兼容）。"""
        payload = MidTermMemorySummaryModel(summary="s", recall_cues=[])
        source_msgs = [SimpleNamespace(timestamp=datetime(2024, 1, 1))]
        msg = build_mid_term_memory_complex_message(
            payload,
            time_range="tr",
            participants=["p"],
            source_messages=source_msgs,
            session_id="",
        )
        comp = msg.raw_message.components[0]
        assert comp.data["data"]["session_id"] == ""