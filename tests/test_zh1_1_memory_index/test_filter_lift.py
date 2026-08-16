"""ZH1-1a 过滤解除测试 — planner 可见回想消息 + 方案 A 从持久化表加载摘要。

覆盖 spec 5.5.1 规则 1-2：planner 和非 planner 分支不再过滤 mid_term_memory，
expression_selector 过滤不变，load_summaries_by_session 从新表加载。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from src.maisaka.chat_loop_service import MaisakaChatLoopService
from src.maisaka.memory.mid_term import (
    MidTermMemorySummaryModel,
    build_mid_term_memory_complex_message,
)


def _make_summary_message() -> object:
    """构造真实 ComplexSessionMessage（聊天回想消息）。"""
    payload = MidTermMemorySummaryModel(summary="回想摘要", recall_cues=["线索"])
    source_msgs = [SimpleNamespace(timestamp=datetime(2024, 1, 1, 10, 0, 0))]
    return build_mid_term_memory_complex_message(
        payload,
        time_range="2024-01-01 10:00 ~ 11:00",
        participants=["alice"],
        source_messages=source_msgs,
        session_id="sess1",
    )


def _make_plain_msg() -> SimpleNamespace:
    """构造普通消息（非 SessionBackedMessage）。"""
    return SimpleNamespace(role="user", processed_plain_text="普通消息")


class TestFilterLift:
    """过滤解除测试。"""

    def test_planner_sees_summary(self) -> None:
        """planner 可见回想消息：request_kind=planner 返回全部含 summary。"""
        summary = _make_summary_message()
        plain = _make_plain_msg()
        history = [plain, summary]
        result = MaisakaChatLoopService._filter_history_for_request_kind(
            history, request_kind="planner",
        )
        # planner 不再过滤 mid_term_memory，summary 可见
        assert summary in result
        assert len(result) == len(history)

    def test_non_planner_sees_summary(self) -> None:
        """非 planner 可见回想消息：request_kind=reply 返回全部含 summary。"""
        summary = _make_summary_message()
        plain = _make_plain_msg()
        history = [plain, summary]
        result = MaisakaChatLoopService._filter_history_for_request_kind(
            history, request_kind="reply",
        )
        assert summary in result
        assert len(result) == len(history)

    def test_expression_selector_filter_unchanged(self) -> None:
        """expression_selector 过滤不变：只保留 SessionBackedMessage。"""
        summary = _make_summary_message()  # ComplexSessionMessage 是 SessionBackedMessage
        plain = _make_plain_msg()  # SimpleNamespace 不是 SessionBackedMessage
        history = [plain, summary]
        result = MaisakaChatLoopService._filter_history_for_request_kind(
            history, request_kind="expression_selector",
        )
        # summary（SessionBackedMessage）保留，plain（非 SessionBackedMessage）过滤
        assert summary in result
        assert plain not in result

    def test_load_summaries_from_db(self) -> None:
        """方案 A 从持久化表加载摘要：load_summaries_by_session 返回摘要列表。"""
        from src.maisaka.memory.mid_term_persistence import MidTermPersistenceService

        service = MidTermPersistenceService()
        service._table_ready = True
        mock_session = MagicMock()
        mock_record = MagicMock()
        mock_record.summary_id = "mtm:abc:123"
        mock_record.session_id = "sess_load"
        mock_record.summary = "加载的摘要"
        mock_session.exec.return_value = [mock_record]
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("src.common.database.database.get_db_session", return_value=mock_ctx):
            results = service.load_summaries_by_session("sess_load", limit=10)
        assert len(results) == 1
        assert results[0].summary_id == "mtm:abc:123"
        assert results[0].summary == "加载的摘要"

    def test_load_summaries_table_not_ready_empty(self) -> None:
        """表未就绪时 load_summaries 返回空列表。"""
        from src.maisaka.memory.mid_term_persistence import MidTermPersistenceService

        service = MidTermPersistenceService()
        service._table_ready = False
        results = service.load_summaries_by_session("sess1")
        assert results == []

    def test_persist_then_load_into_history(self) -> None:
        """集成测试：persist → load → reconstruct → insert 到历史 → planner 可见。

        dsh review P0：验证方案 A 全链路（persist 后 load_summaries_by_session
        → build_mid_term_memory_message_from_record → _load_summaries_into_history
        → 摘要消息出现在 chat_history 中）。
        """
        from src.maisaka.memory.mid_term import (
            build_mid_term_memory_message_from_record,
            is_mid_term_memory_message,
        )

        # 1. 构造 mock 持久化记录（模拟 persist 后的数据库记录）
        record = SimpleNamespace(
            summary_id="mtm:18f5c2a0:abc12345",
            session_id="sess_integration",
            time_range="2024-01-01 10:00 ~ 11:00",
            time_range_start=datetime(2024, 1, 1, 10, 0, 0),
            time_range_end=datetime(2024, 1, 1, 11, 0, 0),
            participants='["alice", "bob"]',
            summary="讨论了项目架构和测试方案",
            recall_cues='["架构", "测试"]',
            recall_cue_embeddings="[]",
            timestamp=datetime(2024, 1, 1, 11, 0, 0),
        )

        # 2. reconstruct 为 ComplexSessionMessage
        msg = build_mid_term_memory_message_from_record(record)
        assert is_mid_term_memory_message(msg)
        assert msg.message_id == "mtm:18f5c2a0:abc12345"
        assert "讨论了项目架构和测试方案" in msg.visible_text

        # 3. mock _load_summaries_into_history 验证摘要进历史
        mock_service = MagicMock()
        mock_service._session_id = "sess_integration"
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        original_history = [_make_plain_msg()]

        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            result = MaisakaChatLoopService._load_summaries_into_history(
                mock_service, original_history,
            )

        # 4. 摘要消息出现在历史开头，planner 可见
        assert len(result) == 2
        assert is_mid_term_memory_message(result[0])
        assert result[1] == original_history[0]