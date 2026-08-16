"""ZH1-1a insert_mid_term_memory_message 重写测试 — 持久化与 insert 顺序 + 裁剪。

覆盖 spec 4.2 可靠性规则 7（持久化失败不 insert）、4.3 安全性、
max_summary_count 裁剪、已持久化跳过。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import (
    MidTermMemorySummaryModel,
    build_mid_term_memory_complex_message,
    insert_mid_term_memory_message,
    is_mid_term_memory_message,
)


def _make_summary_message(session_id: str = "sess1") -> object:
    """构造真实 ComplexSessionMessage（被 is_mid_term_memory_message 识别）。"""
    payload = MidTermMemorySummaryModel(summary="摘要内容", recall_cues=["线索"])
    source_msgs = [SimpleNamespace(timestamp=datetime(2024, 1, 1, 10, 0, 0))]
    return build_mid_term_memory_complex_message(
        payload,
        time_range="2024-01-01 10:00 ~ 11:00",
        participants=["alice"],
        source_messages=source_msgs,
        session_id=session_id,
    )


def _make_plain_msg(text: str = "普通消息") -> SimpleNamespace:
    """构造普通消息（非 mid_term_memory）。"""
    return SimpleNamespace(role="user", processed_plain_text=text, timestamp=datetime(2024, 1, 1))


class TestInsertMidTermMemoryMessage:
    """insert_mid_term_memory_message 测试。"""

    @pytest.mark.asyncio
    async def test_persist_before_insert(self) -> None:
        """持久化与 insert 顺序：持久化成功后才 insert（spec 4.2 规则 7）。"""
        history = [_make_plain_msg("msg1")]
        summary = _make_summary_message()
        mock_persistence = MagicMock()
        mock_persistence.persist_summary_to_db = AsyncMock(return_value=True)
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            result = await insert_mid_term_memory_message(
                history, summary, max_summary_count=5, session_id="sess1",
            )
        mock_persistence.persist_summary_to_db.assert_called_once_with(summary, "sess1")
        # insert 成功：result 含 summary
        assert summary in result

    @pytest.mark.asyncio
    async def test_persist_failure_not_insert(self) -> None:
        """持久化失败不 insert：返回原 history（spec 4.2 规则 7）。"""
        history = [_make_plain_msg("msg1"), _make_plain_msg("msg2")]
        summary = _make_summary_message()
        mock_persistence = MagicMock()
        mock_persistence.persist_summary_to_db = AsyncMock(return_value=False)
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            result = await insert_mid_term_memory_message(
                history, summary, max_summary_count=5, session_id="sess1",
            )
        assert result == list(history)
        assert summary not in result

    @pytest.mark.asyncio
    async def test_insert_position(self) -> None:
        """insert 位置：新 summary 插入在已有 mid_term_memory 之后。"""
        existing_summary = _make_summary_message()
        history = [_make_plain_msg("before"), existing_summary, _make_plain_msg("after")]
        new_summary = _make_summary_message()
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=None,
        ):
            result = await insert_mid_term_memory_message(
                history, new_summary, max_summary_count=5, session_id="sess1",
            )
        # new_summary 应在 existing_summary 之后
        assert new_summary in result
        idx_existing = result.index(existing_summary)
        idx_new = result.index(new_summary)
        assert idx_new == idx_existing + 1

    @pytest.mark.asyncio
    async def test_max_summary_count_trim(self) -> None:
        """max_summary_count 裁剪：超过上限的旧 mid_term 被移除。"""
        s1 = _make_summary_message()
        s2 = _make_summary_message()
        s3 = _make_summary_message()
        history = [s1, s2, s3, _make_plain_msg("plain")]
        new_summary = _make_summary_message()
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=None,
        ):
            result = await insert_mid_term_memory_message(
                history, new_summary, max_summary_count=2, session_id="sess1",
            )
        mid_term_count = sum(1 for m in result if is_mid_term_memory_message(m))
        assert mid_term_count <= 2

    @pytest.mark.asyncio
    async def test_max_summary_count_zero(self) -> None:
        """max_summary_count=0：全移除 mid_term_memory。"""
        s1 = _make_summary_message()
        history = [s1, _make_plain_msg("plain1"), _make_plain_msg("plain2")]
        new_summary = _make_summary_message()
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=None,
        ):
            result = await insert_mid_term_memory_message(
                history, new_summary, max_summary_count=0, session_id="sess1",
            )
        # 所有 mid_term_memory 被移除
        assert not any(is_mid_term_memory_message(m) for m in result)
        # 普通消息保留
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_already_persisted_skip(self) -> None:
        """已持久化跳过：无 session_id 时不调用持久化，直接 insert。"""
        history = [_make_plain_msg("msg1")]
        summary = _make_summary_message()
        # session_id="" 不进入持久化分支
        result = await insert_mid_term_memory_message(
            history, summary, max_summary_count=5, session_id="",
        )
        assert summary in result

    @pytest.mark.asyncio
    async def test_no_persistence_service_skip_persist(self) -> None:
        """持久化服务未初始化（None）跳过持久化，直接 insert。"""
        history = [_make_plain_msg("msg1")]
        summary = _make_summary_message()
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=None,
        ):
            result = await insert_mid_term_memory_message(
                history, summary, max_summary_count=5, session_id="sess1",
            )
        assert summary in result