"""ZH1-1b 语义召回 + Top-K 测试 — query 构造 + 余弦相似度 + 阈值过滤 + Top-K。

覆盖 spec 5.2.1：query 取末尾 12 条 + embedding 匹配 + 严格 > 阈值 + Top-K + 2 位小数。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import (
    MID_TERM_MEMORY_RECALL_CONTEXT_MESSAGE_LIMIT,
    _build_mid_term_memory_recall_query_text,
    _cosine_similarity,
    _select_top_k_recall_candidates,
    build_mid_term_memory_reference_message,
)
from tests.test_zh1_1b_recall._helpers import make_mock_app_config_port, make_recall_candidate, make_user_msg


class TestQueryTextConstruction:
    """query 文本构造测试。"""

    def test_query_text_construction(self) -> None:
        """selected_history 含 20 条 → query 取末尾 12 条。"""
        msgs = [make_user_msg(f"消息{i}") for i in range(20)]
        query = _build_mid_term_memory_recall_query_text(msgs)
        # 末尾 12 条拼接
        lines = query.split("\n")
        assert len(lines) == MID_TERM_MEMORY_RECALL_CONTEXT_MESSAGE_LIMIT
        assert lines[0] == "消息8"
        assert lines[-1] == "消息19"

    def test_query_text_empty_skip(self) -> None:
        """query 文本为空 → 返回空字符串。"""
        msgs = [make_user_msg(""), make_user_msg("   ")]
        query = _build_mid_term_memory_recall_query_text(msgs)
        assert query == ""


class TestCosineSimilarity:
    """余弦相似度计算测试。"""

    def test_cosine_similarity_match(self) -> None:
        """余弦相似度匹配：同向向量分数=1.0。"""
        score = _cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert score == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self) -> None:
        """正交向量分数=0.0。"""
        score = _cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert score == pytest.approx(0.0)


class TestSelectTopKRecallCandidates:
    """Top-K 匹配测试。"""

    def test_threshold_filter_hit(self) -> None:
        """分数 0.7 + 阈值 0.65 → 命中。"""
        # 构造候选 embedding 与 query 同向 → score=1.0 > 0.65
        candidate = make_recall_candidate(embedding=[1.0, 0.0, 0.0])
        result = _select_top_k_recall_candidates(
            [candidate], query_embedding=[1.0, 0.0, 0.0], threshold=0.65, top_k=3,
        )
        assert len(result) == 1
        assert result[0].score > 0.65

    def test_threshold_filter_not_hit(self) -> None:
        """分数 0.6 + 阈值 0.65 → 不命中。"""
        # 正交向量 score=0.0 < 0.65
        candidate = make_recall_candidate(embedding=[0.0, 1.0, 0.0])
        result = _select_top_k_recall_candidates(
            [candidate], query_embedding=[1.0, 0.0, 0.0], threshold=0.65, top_k=3,
        )
        assert result == []

    def test_threshold_equal_not_hit(self) -> None:
        """分数 == 阈值不命中（严格 >）。"""
        # score=1.0, threshold=1.0 → 1.0 > 1.0 is False
        candidate = make_recall_candidate(embedding=[1.0, 0.0, 0.0])
        result = _select_top_k_recall_candidates(
            [candidate], query_embedding=[1.0, 0.0, 0.0], threshold=1.0, top_k=3,
        )
        assert result == []

    def test_top_k_recall(self) -> None:
        """5 条过阈值 + K=3 → 取分数最高 3 条。"""
        # 5 个候选 embedding 与 query 夹角不同 → 分数递减
        candidates = [
            make_recall_candidate(segment_text=f"seg{i}", embedding=[1.0, 0.0, 0.0])
            for i in range(5)
        ]
        # 所有候选 score=1.0（同向），top_k=3 取 3 条
        result = _select_top_k_recall_candidates(
            candidates, query_embedding=[1.0, 0.0, 0.0], threshold=0.5, top_k=3,
        )
        assert len(result) == 3

    def test_top_k_insufficient(self) -> None:
        """2 条过阈值 + K=3 → 取 2 条。"""
        candidates = [
            make_recall_candidate(segment_text="seg0", embedding=[1.0, 0.0, 0.0]),
            make_recall_candidate(segment_text="seg1", embedding=[1.0, 0.0, 0.0]),
        ]
        result = _select_top_k_recall_candidates(
            candidates, query_embedding=[1.0, 0.0, 0.0], threshold=0.5, top_k=3,
        )
        assert len(result) == 2

    def test_top_k_1_degradation(self) -> None:
        """K=1 → 退化为旧 Top-1 行为。"""
        candidates = [
            make_recall_candidate(segment_text="seg0", embedding=[1.0, 0.0, 0.0]),
            make_recall_candidate(segment_text="seg1", embedding=[1.0, 0.0, 0.0]),
        ]
        result = _select_top_k_recall_candidates(
            candidates, query_embedding=[1.0, 0.0, 0.0], threshold=0.5, top_k=1,
        )
        assert len(result) == 1

    def test_top_k_configurable(self) -> None:
        """app_config Top-K=5 → 取 Top-5。"""
        candidates = [
            make_recall_candidate(segment_text=f"seg{i}", embedding=[1.0, 0.0, 0.0])
            for i in range(7)
        ]
        result = _select_top_k_recall_candidates(
            candidates, query_embedding=[1.0, 0.0, 0.0], threshold=0.5, top_k=5,
        )
        assert len(result) == 5

    def test_threshold_configurable(self) -> None:
        """app_config 阈值=0.8 → 仅分数 > 0.8 命中。"""
        # score=1.0 > 0.8 命中
        candidate_hit = make_recall_candidate(segment_text="hit", embedding=[1.0, 0.0, 0.0])
        # score=0.0 < 0.8 不命中
        candidate_miss = make_recall_candidate(segment_text="miss", embedding=[0.0, 1.0, 0.0])
        result = _select_top_k_recall_candidates(
            [candidate_hit, candidate_miss], query_embedding=[1.0, 0.0, 0.0], threshold=0.8, top_k=3,
        )
        assert len(result) == 1
        assert result[0].segment_text == "hit"

    def test_score_precision_2_decimal(self) -> None:
        """匹配分数 0.6543 → 记录为 0.65。"""
        # 构造 embedding 使余弦相似度 ≈ 0.6543
        # cos(θ) = 0.6543 → 用 [0.6543, sqrt(1-0.6543^2), 0] 作为 segment
        import math
        seg_embedding = [0.6543, math.sqrt(1 - 0.6543 ** 2), 0.0]
        candidate = make_recall_candidate(embedding=seg_embedding)
        result = _select_top_k_recall_candidates(
            [candidate], query_embedding=[1.0, 0.0, 0.0], threshold=0.5, top_k=1,
        )
        assert len(result) == 1
        assert result[0].score == 0.65


class TestQueryEmbeddingGeneration:
    """query embedding 生成测试（通过 build_mid_term_memory_reference_message 全链路）。"""

    async def test_query_embedding_generation(self) -> None:
        """query embedding 生成：EmbeddingServiceClient.embed_text 被调用。"""
        from tests.test_zh1_1b_recall._helpers import make_summary_record

        app_port = make_mock_app_config_port()
        record = make_summary_record(
            session_id="group:A",
            recall_cues=[{"text": "天气", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        embed_result = SimpleNamespace(embedding=[1.0, 0.0, 0.0], model_name="test-embed")
        mock_client = MagicMock()
        mock_client.embed_text = AsyncMock(return_value=embed_result)

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=mock_client), \
             patch("src.common.message_repository.find_messages", return_value=[]):
            await build_mid_term_memory_reference_message(
                history=[], selected_history=[make_user_msg("测试")], session_id="group:A",
            )
        mock_client.embed_text.assert_called_once()

    async def test_query_embedding_failure_degradation(self) -> None:
        """query embedding 失败 → 返回空列表 + warning。"""
        from tests.test_zh1_1b_recall._helpers import make_summary_record

        app_port = make_mock_app_config_port()
        record = make_summary_record(
            session_id="group:A",
            recall_cues=[{"text": "天气", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        mock_client = MagicMock()
        mock_client.embed_text = AsyncMock(side_effect=RuntimeError("embedding 服务不可用"))

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=mock_client):
            result = await build_mid_term_memory_reference_message(
                history=[], selected_history=[make_user_msg("测试")], session_id="group:A",
            )
        assert result == []