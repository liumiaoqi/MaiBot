"""ZG-25 测试：段识别跳过 ReferenceMessage(CONTEXT_RESTORE)。

验证 spec 4.3.1/4.3.2：段内含 ReferenceMessage(CONTEXT_RESTORE) → 段识别返回 None。
使用真实 ReferenceMessage（非 MagicMock）——P1-1 修复验证。
"""

from datetime import datetime
from unittest.mock import MagicMock

from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import (
    AssistantMessage,
    CompactionSummaryMessage,
    ReferenceMessage,
    ReferenceMessageType,
)

from .conftest import make_mock_llm_service


def _make_real_history(count: int = 20, text_size: int = 200) -> list:
    """用真实 AssistantMessage 构造 history。"""
    base_ts = datetime(2026, 8, 17, 10, 0, 0)
    return [
        AssistantMessage(content=f"消息{i}_" + "x" * text_size, timestamp=base_ts)
        for i in range(count)
    ]


def _make_context_restore_ref(timestamp: datetime) -> ReferenceMessage:
    """构造真实 ReferenceMessage(CONTEXT_RESTORE)。"""
    return ReferenceMessage(
        content="context_restore_content",
        timestamp=timestamp,
        reference_type=ReferenceMessageType.CONTEXT_RESTORE,
    )


class TestSkipsReferenceMessages:
    """验证段识别跳过 ReferenceMessage（真实消息类型）。"""

    async def test_ref_in_middle_returns_original(self, compaction_config) -> None:
        """段中间含 ReferenceMessage(CONTEXT_RESTORE) → 返回原 history。"""
        history = _make_real_history(count=20, text_size=200)
        base_ts = datetime(2026, 8, 17, 10, 0, 0)
        history.insert(5, _make_context_restore_ref(base_ts))

        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is history

    async def test_ref_at_head_returns_original(self, compaction_config) -> None:
        """段头部含 ReferenceMessage(CONTEXT_RESTORE) → 返回原 history。"""
        history = _make_real_history(count=20, text_size=200)
        base_ts = datetime(2026, 8, 17, 10, 0, 0)
        history.insert(0, _make_context_restore_ref(base_ts))

        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert result is history

    async def test_no_ref_compaction_triggers(self, compaction_config) -> None:
        """无 ReferenceMessage → compaction 正常触发。"""
        history = _make_real_history(count=20, text_size=200)
        llm_service = make_mock_llm_service(summary_text="摘要")

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert isinstance(result[0], CompactionSummaryMessage)
