"""ZG-25 测试：P0 修复验证——Message 构造不崩。

验证 compaction.py message_factory 和 CompactionSummaryMessage.to_llm_message
用 parts=[TextMessagePart(text=...)] 构造 Message，不抛 TypeError。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart
from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import CompactionSummaryMessage


class TestMessageConstruction:
    """验证 Message 构造不崩（P0-1 修复）。"""

    async def test_message_factory_called_and_not_raises(self, compaction_config) -> None:
        """message_factory 被 LLMService 调用且不抛异常。"""
        from tests.test_zg25_b_layer_compaction.conftest import make_long_history

        history = make_long_history(count=20, text_size=200)

        call_tracker = {"factory_called": False}

        async def mock_generate(task_name, message_factory, options=None, **kwargs):
            messages = message_factory(MagicMock())
            call_tracker["factory_called"] = True
            assert isinstance(messages, list)
            assert isinstance(messages[0], Message)
            assert messages[0].role == RoleType.User
            assert len(messages[0].parts) == 1
            assert isinstance(messages[0].parts[0], TextMessagePart)
            result = MagicMock()
            result.response = "这是摘要"
            return result

        llm_service = MagicMock()
        llm_service.generate_response_with_messages = mock_generate

        result = await compact_selected_history(
            history,
            context_window=1000,
            session_id="test_session",
            llm_service=llm_service,
            config=compaction_config,
        )

        assert call_tracker["factory_called"] is True
        assert isinstance(result[0], CompactionSummaryMessage)

    def test_compaction_summary_to_llm_message_not_raises(self) -> None:
        """CompactionSummaryMessage.to_llm_message() 不抛异常。"""
        msg = CompactionSummaryMessage(
            summary_text="这是摘要内容",
            timestamp=datetime.now(),
            original_segment_count=10,
            original_time_range="2026-08-17 10:00 ~ 2026-08-17 11:00",
        )

        llm_msg = msg.to_llm_message()

        assert isinstance(llm_msg, Message)
        assert llm_msg.role == RoleType.User
        assert len(llm_msg.parts) == 1
        assert isinstance(llm_msg.parts[0], TextMessagePart)
        assert llm_msg.parts[0].text == "这是摘要内容"

    def test_compaction_summary_content_property_works(self) -> None:
        """CompactionSummaryMessage.to_llm_message() 返回的 Message.content 可读。"""
        msg = CompactionSummaryMessage(
            summary_text="摘要文本",
            timestamp=datetime.now(),
        )

        llm_msg = msg.to_llm_message()

        assert llm_msg.content == "摘要文本"

    def test_new_fields_default_backward_compatible(self) -> None:
        """ZG-25 升级：不传 tx_id / replace_generation → 默认值（向后兼容）。"""
        msg = CompactionSummaryMessage(
            summary_text="摘要",
            timestamp=datetime.now(),
        )
        assert msg.tx_id == ""
        assert msg.replace_generation == 0

    def test_new_fields_assignable(self) -> None:
        """ZG-25 升级：tx_id / replace_generation 可构造赋值。"""
        msg = CompactionSummaryMessage(
            summary_text="摘要",
            timestamp=datetime.now(),
            tx_id="abc-123",
            replace_generation=3,
        )
        assert msg.tx_id == "abc-123"
        assert msg.replace_generation == 3