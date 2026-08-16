"""ZH1-1b 端到端测试 — recall 全链路 + 多命中 + 降级 + 去重 + 截断 + 配置可调。

覆盖 spec 5.7：build_mid_term_memory_reference_message 全链路集成。
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import build_mid_term_memory_reference_message
from tests.test_zh1_1b_recall._helpers import (
    make_mock_app_config_port,
    make_mock_find_messages_result,
    make_summary_record,
    make_user_msg,
)


def _patch_e2e(
    *,
    app_port=None,
    persistence=None,
    embed_result=None,
    find_messages_result=None,
):
    """构造 e2e 测试常用 patch 上下文管理器组合。"""
    if app_port is None:
        app_port = make_mock_app_config_port()
    patches = [
        patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port),
    ]
    if persistence is not None:
        patches.append(
            patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=persistence)
        )
    if embed_result is not None:
        mock_client = MagicMock()
        mock_client.embed_text = AsyncMock(return_value=embed_result)
        patches.append(
            patch("src.services.embedding_service.EmbeddingServiceClient", return_value=mock_client)
        )
    if find_messages_result is not None:
        patches.append(
            patch("src.common.message_repository.find_messages", return_value=find_messages_result)
        )
    return patches


class TestE2ERecall:
    """端到端测试。"""

    async def test_e2e_recall_full_chain(self) -> None:
        """recall 全链路：候选加载 → query embedding → 匹配 → 翻原文 → ReferenceMessage。"""
        app_port = make_mock_app_config_port()
        # 候选 embedding 与 query 同向 → score=1.0 > 0.65 命中
        record = make_summary_record(
            summary_id="mtm:test1",
            session_id="group:A",
            recall_cues=[{"text": "天气", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        embed_result = SimpleNamespace(embedding=[1.0, 0.0, 0.0], model_name="test-embed")
        mock_messages = make_mock_find_messages_result(3)

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=MagicMock(embed_text=AsyncMock(return_value=embed_result))), \
             patch("src.common.message_repository.find_messages", return_value=mock_messages):
            result = await build_mid_term_memory_reference_message(
                history=[],
                selected_history=[make_user_msg("今天天气怎么样")],
                session_id="group:A",
            )
        assert len(result) >= 1
        assert result[0].reference_type.value == "memory"

    async def test_e2e_multi_hit_full_chain(self) -> None:
        """多命中全链路：2 条候选过阈值 → 2 条 ReferenceMessage。"""
        app_port = make_mock_app_config_port(recall_top_k=5)
        records = [
            make_summary_record(
                summary_id=f"mtm:multi{i}",
                session_id="group:A",
                recall_cues=[{"text": f"topic{i}", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
            )
            for i in range(2)
        ]
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = records
        embed_result = SimpleNamespace(embedding=[1.0, 0.0, 0.0], model_name="test-embed")
        mock_messages = make_mock_find_messages_result(2)

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=MagicMock(embed_text=AsyncMock(return_value=embed_result))), \
             patch("src.common.message_repository.find_messages", return_value=mock_messages):
            result = await build_mid_term_memory_reference_message(
                history=[],
                selected_history=[make_user_msg("测试对话")],
                session_id="group:A",
            )
        assert len(result) == 2

    async def test_e2e_degradation_full_chain(self) -> None:
        """降级全链路：候选加载失败 → 返回空列表。"""
        app_port = make_mock_app_config_port()
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.side_effect = RuntimeError("DB失败")

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence):
            result = await build_mid_term_memory_reference_message(
                history=[],
                selected_history=[make_user_msg("测试")],
                session_id="group:A",
            )
        assert result == []

    async def test_e2e_dedup_full_chain(self) -> None:
        """去重全链路：existing_summary_ids 含候选 ID → 该候选被排除。"""
        app_port = make_mock_app_config_port()
        record = make_summary_record(
            summary_id="mtm:dedup1",
            session_id="group:A",
            recall_cues=[{"text": "天气", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        embed_result = SimpleNamespace(embedding=[1.0, 0.0, 0.0], model_name="test-embed")

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=MagicMock(embed_text=AsyncMock(return_value=embed_result))):
            result = await build_mid_term_memory_reference_message(
                history=[],
                selected_history=[make_user_msg("测试")],
                session_id="group:A",
                existing_summary_ids={"mtm:dedup1"},
            )
        # 候选被去重排除 → 返回空
        assert result == []

    async def test_e2e_truncation_full_chain(self) -> None:
        """截断全链路：原文超 token 上限 → 截断后追加。"""
        app_port = make_mock_app_config_port(recall_original_token_limit=100)
        record = make_summary_record(
            summary_id="mtm:trunc1",
            session_id="group:A",
            recall_cues=[{"text": "天气", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        embed_result = SimpleNamespace(embedding=[1.0, 0.0, 0.0], model_name="test-embed")
        # 构造超长原文消息（token_limit=100 → char_limit=200）
        long_messages = []
        for i in range(10):
            msg = SimpleNamespace()
            msg.timestamp = datetime(2024, 1, 1, 10, i, 0)
            msg.processed_plain_text = "X" * 100
            msg.message_info = SimpleNamespace(
                user_info=SimpleNamespace(user_nickname=f"u{i}", user_id=f"uid{i}", user_cardname=None)
            )
            long_messages.append(msg)

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=MagicMock(embed_text=AsyncMock(return_value=embed_result))), \
             patch("src.common.message_repository.find_messages", return_value=long_messages):
            result = await build_mid_term_memory_reference_message(
                history=[],
                selected_history=[make_user_msg("测试")],
                session_id="group:A",
            )
        assert len(result) >= 1
        # 截断标记存在
        assert "截断" in result[0].content

    async def test_e2e_config_tunable_full_chain(self) -> None:
        """配置可调全链路：threshold=0.99 → 无命中。"""
        app_port = make_mock_app_config_port(recall_threshold=0.99)
        record = make_summary_record(
            summary_id="mtm:cfg1",
            session_id="group:A",
            recall_cues=[{"text": "天气", "embedding": [1.0, 0.0, 0.0], "model_name": "m"}],
        )
        mock_persistence = MagicMock()
        mock_persistence.load_summaries_by_session.return_value = [record]
        # query embedding 正交 → score=0.0 < 0.99
        embed_result = SimpleNamespace(embedding=[0.0, 1.0, 0.0], model_name="test-embed")

        with patch("src.maisaka.memory.mid_term.get_app_config_port", return_value=app_port), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence), \
             patch("src.services.embedding_service.EmbeddingServiceClient", return_value=MagicMock(embed_text=AsyncMock(return_value=embed_result))):
            result = await build_mid_term_memory_reference_message(
                history=[],
                selected_history=[make_user_msg("测试")],
                session_id="group:A",
            )
        assert result == []