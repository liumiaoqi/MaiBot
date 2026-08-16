"""ZH1-1b 候选源改造测试 — 候选从持久化表加载（非 history 参数）。

覆盖 spec 5.1.1：候选源改从 load_summaries_by_session 加载，
session_id 过滤 + 条数上限 + embedding 缺失跳过 + 失败降级。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import _collect_mid_term_memory_recall_candidates
from tests.test_zh1_1b_recall._helpers import make_summary_record


class TestCandidateSource:
    """候选源改造测试。"""

    def test_source_from_persistence_not_history(self) -> None:
        """候选源从 load_summaries_by_session 加载，非 history 参数。"""
        record = make_summary_record(session_id="group:A")
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        # load_summaries_by_session 被调用（候选源来自持久化表）
        mock_persistence.load_summaries_by_session.assert_called_once_with("group:A", limit=100)
        assert len(candidates) >= 1

    def test_history_10_db_50_covers_50(self) -> None:
        """history 仅 10 条但持久化表 50 条，候选源覆盖 50 条。"""
        records = [
            make_summary_record(summary_id=f"mtm:rec{i}", session_id="group:A")
            for i in range(50)
        ]
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = records
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        # 50 条记录每条至少 1 个候选 → 候选源覆盖 50 条记录
        assert len(candidates) >= 50

    def test_session_id_filter(self) -> None:
        """会话 A recall → 候选源仅含 session_id=A 摘要。"""
        record_a = make_summary_record(summary_id="mtm:A", session_id="group:A")
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record_a]
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        # load_summaries_by_session 用 session_id="group:A" 过滤
        call_args = mock_persistence.load_summaries_by_session.call_args
        assert call_args.args[0] == "group:A"
        for c in candidates:
            assert c.payload["session_id"] == "group:A"

    def test_candidate_limit(self) -> None:
        """持久化表 1000 条 + 上限 100 → 加载最近 100 条。"""
        records = [
            make_summary_record(summary_id=f"mtm:rec{i}", session_id="group:A")
            for i in range(100)
        ]
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = records
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        call_args = mock_persistence.load_summaries_by_session.call_args
        assert call_args.kwargs["limit"] == 100

    def test_embedding_missing_skip(self) -> None:
        """recall_cue_embeddings 为空 → 不参与 recall 匹配。"""
        # recall_cues 中 embedding 缺失（空 list）
        record = make_summary_record(
            recall_cues=[{"text": "线索", "embedding": [], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        # embedding 为空 → 候选被跳过
        assert candidates == []

    def test_load_failure_degradation(self) -> None:
        """load_summaries_by_session 报错 → 返回空列表 + warning。"""
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.side_effect = RuntimeError("DB连接失败")
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        assert candidates == []

    def test_table_not_exist_degradation(self) -> None:
        """表未建 → 降级跳过 + warning（load 抛异常被捕获）。"""
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.side_effect = RuntimeError("no such table")
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        assert candidates == []

    def test_persistence_uninit_skip(self) -> None:
        """get_mid_term_persistence() 返回 None → 返回空列表。"""
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=None,
        ):
            candidates = _collect_mid_term_memory_recall_candidates(
                session_id="group:A", candidate_limit=100,
            )
        assert candidates == []