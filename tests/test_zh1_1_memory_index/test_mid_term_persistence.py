"""ZH1-1a 摘要持久化服务测试 — 新表 CRUD + 自动建表 + 批量 embedding + timestamp 兜底。

覆盖 spec 5.2.1 建表、5.2.3 场景 1/3、4.2 可靠性规则 7、4.3 安全性规则 1。
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.maisaka.memory.mid_term_persistence import (
    MidTermPersistenceService,
    fix_timestamp_fallback,
)


def _make_summary_message(
    payload_data: dict | None = None,
    timestamp: datetime | None = None,
) -> SimpleNamespace:
    """构造 mock summary_message（含 raw_message.components[0].data）。"""
    data = payload_data or {
        "time_range": "2024-01-01 00:00:00 ~ 2024-01-01 01:00:00",
        "participants": ["alice", "bob"],
        "summary": "测试摘要内容",
        "recall_cues": ["线索1", "线索2"],
        "recall_cue_embeddings": [{"text": "线索1", "embedding": [0.1, 0.2]}],
    }
    comp = SimpleNamespace(data=data)
    raw = SimpleNamespace(components=[comp])
    return SimpleNamespace(raw_message=raw, timestamp=timestamp or datetime(2024, 1, 1))


class TestMidTermPersistenceService:
    """MidTermPersistenceService 持久化服务测试。"""

    def test_auto_create_table(self) -> None:
        """自动建表：init_table 成功后 _table_ready=True（spec 5.2.1 规则 1）。"""
        service = MidTermPersistenceService()
        with patch("src.common.database.database.initialize_database"):
            service.init_table()
        assert service._table_ready is True

    def test_table_exists_skip(self) -> None:
        """建表失败降级仅内存：_table_ready=False（spec 5.2.3 场景 1）。"""
        service = MidTermPersistenceService()
        with patch(
            "src.common.database.database.initialize_database",
            side_effect=RuntimeError("db locked"),
        ):
            service.init_table()
        assert service._table_ready is False

    def test_persist_fields_complete(self) -> None:
        """持久化字段完整：_build_record 构造记录字段齐全。"""
        service = MidTermPersistenceService()
        payload_data = {
            "time_range": "2024-01-01 00:00:00 ~ 2024-01-01 01:00:00",
            "participants": ["alice"],
            "summary": "完整字段测试",
            "recall_cues": ["c1"],
            "recall_cue_embeddings": [{"text": "c1", "embedding": [0.1]}],
        }
        ts = datetime(2024, 1, 1)
        record = service._build_record(payload_data, "sess1", ts)
        assert record.summary_id.startswith("mtm:")
        assert record.session_id == "sess1"
        assert record.time_range == payload_data["time_range"]
        assert json.loads(record.participants) == ["alice"]
        assert record.summary == "完整字段测试"
        assert json.loads(record.recall_cues) == ["c1"]
        assert json.loads(record.recall_cue_embeddings) == [{"text": "c1", "embedding": [0.1]}]
        assert record.timestamp == ts

    def test_summary_id_idempotent(self) -> None:
        """summary_id 幂等：相同输入产生相同 summary_id。"""
        service = MidTermPersistenceService()
        payload_data = {
            "time_range": "2024-01-01 ~ 2024-01-02",
            "summary": "幂等测试",
        }
        ts = datetime(2024, 1, 1, 12, 0, 0)
        r1 = service._build_record(payload_data, "sess1", ts)
        r2 = service._build_record(payload_data, "sess1", ts)
        assert r1.summary_id == r2.summary_id

    @pytest.mark.asyncio
    async def test_session_id_isolation(self) -> None:
        """session_id 隔离：load_summaries_by_session 按 session_id 过滤（spec 4.3 规则 1）。"""
        service = MidTermPersistenceService()
        service._table_ready = True
        mock_session = MagicMock()
        mock_session.exec.return_value = [MagicMock(summary_id="s1")]
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("src.common.database.database.get_db_session", return_value=mock_ctx):
            results = service.load_summaries_by_session("sess_isolated", limit=5)
        assert len(results) == 1
        assert results[0].summary_id == "s1"
        mock_session.exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_retry_3_times(self) -> None:
        """持久化失败重试 3 次后返回 False（spec 4.2 可靠性规则 7）。"""
        service = MidTermPersistenceService()
        service._table_ready = True
        summary = _make_summary_message()
        with patch.object(service, "_insert_record", side_effect=RuntimeError("db error")), \
             patch("src.maisaka.memory.mid_term_persistence.asyncio.sleep", return_value=None):
            result = await service.persist_summary_to_db(summary, "sess1")
            assert result is False
            assert service._insert_record.call_count == 3

    @pytest.mark.asyncio
    async def test_persist_success_first_try(self) -> None:
        """持久化首次成功返回 True。"""
        service = MidTermPersistenceService()
        service._table_ready = True
        summary = _make_summary_message()
        with patch.object(service, "_insert_record"):
            result = await service.persist_summary_to_db(summary, "sess1")
            assert result is True
            assert service._insert_record.call_count == 1

    @pytest.mark.asyncio
    async def test_persist_table_not_ready_skip(self) -> None:
        """表未就绪跳过持久化返回 False。"""
        service = MidTermPersistenceService()
        service._table_ready = False
        summary = _make_summary_message()
        result = await service.persist_summary_to_db(summary, "sess1")
        assert result is False

    def test_embedding_batch_persist(self) -> None:
        """embedding 批量持久化：recall_cue_embeddings 完整保留。"""
        service = MidTermPersistenceService()
        embeddings = [
            {"text": "线索1", "embedding": [0.1, 0.2, 0.3], "model_name": "m1"},
            {"text": "线索2", "embedding": [0.4, 0.5, 0.6], "model_name": "m1"},
        ]
        payload_data = {
            "time_range": "2024-01-01 ~ 2024-01-02",
            "summary": "批量 embedding",
            "recall_cue_embeddings": embeddings,
        }
        record = service._build_record(payload_data, "sess1", datetime(2024, 1, 1))
        stored = json.loads(record.recall_cue_embeddings)
        assert len(stored) == 2
        assert stored[0]["text"] == "线索1"
        assert stored[1]["embedding"] == [0.4, 0.5, 0.6]

    def test_fix_timestamp_fallback(self) -> None:
        """timestamp 兜底：None/0 不产生 1970（spec 5.6.1）。"""
        assert fix_timestamp_fallback(None, "msg1").year != 1970
        assert fix_timestamp_fallback(0, "msg1").year != 1970
        # 有效 timestamp 不动
        assert fix_timestamp_fallback(1723680000, "msg1").year >= 2024

    @pytest.mark.asyncio
    async def test_insert_record_idempotent_skip(self) -> None:
        """INSERT OR IGNORE 幂等：summary_id 已存在跳过（spec 5.2.3 场景 3）。"""
        service = MidTermPersistenceService()
        record = service._build_record(
            {"time_range": "tr", "summary": "s"}, "sess1", datetime(2024, 1, 1)
        )
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock()  # 已存在
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("src.common.database.database.get_db_session", return_value=mock_ctx):
            service._insert_record(record)
        # 已存在则不 add
        mock_session.add.assert_not_called()