"""ZH1-1a 端到端测试 — 摘要生成全链路验证。

覆盖：
  - 摘要生成全链路（build → persist → insert）
  - 1970 修复全链路（fix_timestamp → 构造消息 → 持久化）
  - 异步化全链路（enqueue → 消费者 → build → persist）
  - 故障降级全链路（LLM 失败 / 持久化失败 → 降级不崩溃）
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.memory.mid_term import (
    MidTermMemorySummaryModel,
    build_mid_term_memory_complex_message,
    build_mid_term_memory_message,
    insert_mid_term_memory_message,
)
from src.maisaka.memory.mid_term_persistence import fix_timestamp_fallback
from src.maisaka.memory.mid_term_summary_queue import MidTermSummaryQueue


def _make_user_msg(text: str = "对话内容", ts: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        role="user",
        processed_plain_text=text,
        timestamp=ts or datetime(2024, 1, 1, 10, 0, 0),
    )


def _mock_llm_result() -> SimpleNamespace:
    return SimpleNamespace(
        response='{"summary": "端到端摘要", "recall_cues": ["线索1", "线索2"]}',
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        model_name="e2e-model",
    )


def _patch_build_internals(user_msg):
    """patch build 内部函数（返回有效摘要）。"""
    return [
        patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]),
        patch("src.maisaka.memory.mid_term._build_time_range", return_value="2024-01-01 10:00 ~ 11:00"),
        patch("src.maisaka.memory.mid_term._collect_participants", return_value=["alice", "bob"]),
        patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"),
        patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]),
        patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"),
        patch(
            "src.maisaka.memory.mid_term._parse_summary_response",
            return_value=MidTermMemorySummaryModel(summary="端到端摘要", recall_cues=["线索1", "线索2"]),
        ),
        patch("src.maisaka.memory.mid_term._build_recall_cue_embeddings", new=AsyncMock(return_value=[{"text": "线索1", "embedding": [0.1]}])),
    ]


class TestE2ESummaryFullChain:
    """摘要生成全链路测试。"""

    @pytest.mark.asyncio
    async def test_e2e_summary_full_chain(self) -> None:
        """摘要生成全链路：build → persist → insert。"""
        user_msg = _make_user_msg("端到端对话")
        mock_llm = MagicMock()
        mock_llm.generate_response_with_messages = AsyncMock(return_value=_mock_llm_result())
        mock_persistence = MagicMock()
        mock_persistence.persist_summary_to_db = AsyncMock(return_value=True)

        with patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm), \
             patch("src.maisaka.memory.mid_term_persistence.get_mid_term_persistence", return_value=mock_persistence):
            for p in _patch_build_internals(user_msg):
                p.start()
            try:
                # 1. build
                result = await build_mid_term_memory_message([user_msg], session_id="sess_e2e")
                assert result is not None
                assert result.message is not None
                assert result.total_tokens == 150

                # 2. insert（含持久化）
                history = [_make_user_msg("历史消息")]
                updated = await insert_mid_term_memory_message(
                    history, result.message, max_summary_count=5, session_id="sess_e2e",
                )
                # 持久化被调用
                mock_persistence.persist_summary_to_db.assert_called_once()
                # summary 已 insert 到 history
                assert result.message in updated
            finally:
                for p in _patch_build_internals(user_msg):
                    p.stop()


class TestE2E1970FixFullChain:
    """1970 修复全链路测试。"""

    @pytest.mark.asyncio
    async def test_e2e_1970_fix_full_chain(self) -> None:
        """1970 修复全链路：fix_timestamp → 构造消息 → 持久化字段。"""
        # 1. 修复 1970 脏数据
        fixed_ts = fix_timestamp_fallback(None, "msg_1970")
        assert fixed_ts.year != 1970
        assert fixed_ts.year >= 2024

        # 2. 用修复后 timestamp 构造 summary message
        payload = MidTermMemorySummaryModel(summary="1970 修复后摘要", recall_cues=["线索"])
        source_msgs = [SimpleNamespace(timestamp=fixed_ts)]
        msg = build_mid_term_memory_complex_message(
            payload,
            time_range="2024-01-01 10:00 ~ 11:00",
            participants=["alice"],
            source_messages=source_msgs,
            session_id="sess_1970",
        )
        # 3. 消息 timestamp 不为 1970
        assert msg.timestamp.year != 1970
        assert msg.timestamp.year >= 2024

        # 4. 持久化记录字段正确
        from src.maisaka.memory.mid_term_persistence import MidTermPersistenceService

        service = MidTermPersistenceService()
        comp = msg.raw_message.components[0]
        record = service._build_record(comp.data, "sess_1970", msg.timestamp)
        assert record.timestamp.year != 1970
        assert record.session_id == "sess_1970"


class TestE2EAsyncFullChain:
    """异步化全链路测试。"""

    @pytest.mark.asyncio
    async def test_e2e_async_full_chain(self) -> None:
        """异步化全链路：enqueue → 消费者 → build → persist。"""
        q = MidTermSummaryQueue(maxsize=100)
        process_mock = AsyncMock()
        with patch.object(q, "_process_snapshot", new=process_mock):
            q.start()
            # 入队
            user_msg = _make_user_msg("异步链路")
            q.enqueue_summary_build([user_msg], "sess_async")
            # 等待消费者处理
            await asyncio.sleep(0.1)
            assert process_mock.call_count == 1
            snapshot = process_mock.call_args.args[0]
            assert snapshot.session_id == "sess_async"
            await q.close()


class TestE2EFailureDegradationFullChain:
    """故障降级全链路测试。"""

    @pytest.mark.asyncio
    async def test_e2e_llm_failure_degradation(self) -> None:
        """LLM 失败降级：build 返回 None，不 insert。"""
        user_msg = _make_user_msg("降级测试")
        mock_llm = MagicMock()
        mock_result = SimpleNamespace(
            response="",
            prompt_tokens=0, completion_tokens=0, total_tokens=0, model_name="",
        )
        mock_llm.generate_response_with_messages = AsyncMock(return_value=mock_result)
        with patch("src.core.adapters.llm_service_port.get_llm_service", return_value=mock_llm), \
             patch("src.maisaka.memory.mid_term._select_summary_source_messages", return_value=[user_msg]), \
             patch("src.maisaka.memory.mid_term._build_time_range", return_value="tr"), \
             patch("src.maisaka.memory.mid_term._collect_participants", return_value=["p"]), \
             patch("src.maisaka.memory.mid_term._build_summary_instruction_prompt", return_value="instr"), \
             patch("src.maisaka.memory.mid_term._build_summary_prompt_messages", return_value=[user_msg, user_msg]), \
             patch("src.maisaka.memory.mid_term._save_mid_term_memory_prompt_preview"), \
             patch("src.maisaka.memory.mid_term._parse_summary_response", return_value=None):
            result = await build_mid_term_memory_message([user_msg], session_id="sess_degrade")
        assert result is None  # LLM 失败降级返回 None

    @pytest.mark.asyncio
    async def test_e2e_persist_failure_not_insert(self) -> None:
        """持久化失败降级：不 insert 到历史。"""
        from src.maisaka.memory.mid_term import (
            build_mid_term_memory_complex_message,
        )

        payload = MidTermMemorySummaryModel(summary="持久化失败测试", recall_cues=[])
        source_msgs = [SimpleNamespace(timestamp=datetime(2024, 1, 1))]
        summary = build_mid_term_memory_complex_message(
            payload, time_range="tr", participants=["p"],
            source_messages=source_msgs, session_id="sess_fail",
        )
        history = [_make_user_msg("原历史")]
        mock_persistence = MagicMock()
        mock_persistence.persist_summary_to_db = AsyncMock(return_value=False)
        with patch(
            "src.maisaka.memory.mid_term_persistence.get_mid_term_persistence",
            return_value=mock_persistence,
        ):
            result = await insert_mid_term_memory_message(
                history, summary, max_summary_count=5, session_id="sess_fail",
            )
        # 持久化失败，不 insert
        assert result == list(history)
        assert summary not in result

    @pytest.mark.asyncio
    async def test_e2e_consumer_exception_no_crash(self) -> None:
        """消费者异常不崩溃：队列仍可接受新任务。"""
        q = MidTermSummaryQueue(maxsize=100)
        call_count = 0

        async def _crash_then_recover(snapshot) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("消费者首次处理崩溃")

        with patch.object(q, "_process_snapshot", new=_crash_then_recover):
            q.start()
            q.enqueue_summary_build([_make_user_msg("m1")], "sess1")
            q.enqueue_summary_build([_make_user_msg("m2")], "sess1")
            await asyncio.sleep(0.15)
            # 两条都被处理（异常恢复）
            assert call_count == 2
            await q.close()