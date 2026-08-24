"""ZG-25 升级测试：N5 tool-pairing 边界平衡验证（spec 15.2）。

验证 compaction.py 委托 N5 ToolPairingBalancer 做边界平衡，
不切断 tool_call / tool_result 配对。
"""

from datetime import datetime
from unittest.mock import MagicMock, patch


from src.llm_models.payload_content.tool_option import ToolCall
from src.maisaka.context.compaction import compact_selected_history
from src.maisaka.context.messages import (
    AssistantMessage,
    CompactionSummaryMessage,
    ToolResultMessage,
)

from .conftest import make_mock_llm_service


def _make_history_with_tool_pair(
    *,
    pre_count: int = 6,
    text_size: int = 200,
) -> list:
    """构造含 tool_call + tool_result 配对的历史。

    结构：[user/assistant × pre_count] + [assistant(tool_call)] + [tool_result] + [user] + [assistant]
    段尾 tool_call 在可压缩段内，tool_result 在保留段 → 边界需调整。
    """
    from .conftest import make_assistant_message, make_user_message

    history: list = []
    base_ts = datetime(2026, 8, 17, 10, 0, 0)
    for i in range(pre_count):
        content = f"消息{i}_" + "x" * text_size
        if i % 2 == 0:
            history.append(make_user_message(content, timestamp=base_ts))
        else:
            history.append(make_assistant_message(content, timestamp=base_ts))

    tool_call = ToolCall(call_id="tc-1", func_name="search", args={})
    assistant_with_tool = AssistantMessage(
        content="调用搜索工具",
        timestamp=base_ts,
        tool_calls=[tool_call],
    )
    history.append(assistant_with_tool)

    tool_result = ToolResultMessage(
        content="搜索结果",
        timestamp=base_ts,
        tool_call_id="tc-1",
        tool_name="search",
    )
    history.append(tool_result)

    history.append(make_user_message("后续问题_" + "x" * text_size, timestamp=base_ts))
    history.append(make_assistant_message("后续回答_" + "x" * text_size, timestamp=base_ts))
    return history


class TestToolPairingBoundary:
    """N5 tool-pairing 边界平衡验证。"""

    async def test_boundary_adjusts_to_balanced_point(self, compaction_config) -> None:
        """用例1：段尾存在未配对 tool_call → 边界向前调整到最近平衡点。"""
        history = _make_history_with_tool_pair(pre_count=8)
        llm_service = make_mock_llm_service(summary_text="摘要")

        mock_balancer = MagicMock()
        mock_balancer.adjust_to_nearest_balanced = MagicMock(return_value=5)
        mock_balancer.invalidate_cache = MagicMock()

        with patch(
            "src.maisaka.context.compaction.get_tool_pairing_balancer",
            return_value=mock_balancer,
        ):
            result = await compact_selected_history(
                history, context_window=1000, session_id="test",
                llm_service=llm_service, config=compaction_config,
            )

        assert isinstance(result[0], CompactionSummaryMessage)
        mock_balancer.adjust_to_nearest_balanced.assert_called_once()

    async def test_no_balanced_point_returns_original(self, compaction_config) -> None:
        """用例2：所有切分点都切断配对 → 不压缩，返回原 history。"""
        history = _make_history_with_tool_pair(pre_count=8)
        llm_service = make_mock_llm_service(summary_text="摘要")

        mock_balancer = MagicMock()
        mock_balancer.adjust_to_nearest_balanced = MagicMock(return_value=None)
        mock_balancer.invalidate_cache = MagicMock()

        with patch(
            "src.maisaka.context.compaction.get_tool_pairing_balancer",
            return_value=mock_balancer,
        ):
            result = await compact_selected_history(
                history, context_window=1000, session_id="test",
                llm_service=llm_service, config=compaction_config,
            )

        assert result is history
        mock_balancer.invalidate_cache.assert_not_called()

    async def test_second_compaction_reuses_balancer_singleton(self, compaction_config) -> None:
        """用例3：连续两次压缩 → balancer 单例复用（同一实例）。"""
        from src.maisaka.context import compaction_adapter

        compaction_adapter._balancer_singleton = None

        history = _make_history_with_tool_pair(pre_count=8)
        llm_service = make_mock_llm_service(summary_text="摘要")

        await compact_selected_history(
            history, context_window=1000, session_id="test",
            llm_service=llm_service, config=compaction_config,
        )
        balancer1 = compaction_adapter._balancer_singleton
        assert balancer1 is not None

        history2 = _make_history_with_tool_pair(pre_count=8)
        llm_service2 = make_mock_llm_service(summary_text="摘要")
        await compact_selected_history(
            history2, context_window=1000, session_id="test",
            llm_service=llm_service2, config=compaction_config,
        )
        balancer2 = compaction_adapter._balancer_singleton
        assert balancer2 is balancer1

    async def test_invalidate_cache_called_after_compaction(self, compaction_config) -> None:
        """用例4：压缩完成 → invalidate_cache 被调用。"""
        history = _make_history_with_tool_pair(pre_count=8)
        llm_service = make_mock_llm_service(summary_text="摘要")

        mock_balancer = MagicMock()
        mock_balancer.adjust_to_nearest_balanced = MagicMock(return_value=5)
        mock_balancer.invalidate_cache = MagicMock()

        with patch(
            "src.maisaka.context.compaction.get_tool_pairing_balancer",
            return_value=mock_balancer,
        ):
            result = await compact_selected_history(
                history, context_window=1000, session_id="test",
                llm_service=llm_service, config=compaction_config,
            )

        assert isinstance(result[0], CompactionSummaryMessage)
        mock_balancer.invalidate_cache.assert_called_once_with("test")

    async def test_compacted_history_no_orphan_tool_call(self, compaction_config) -> None:
        """用例5：compacted_history → 无孤立 tool_call 或 tool_result。"""
        history = _make_history_with_tool_pair(pre_count=8)
        llm_service = make_mock_llm_service(summary_text="摘要")

        mock_balancer = MagicMock()
        mock_balancer.adjust_to_nearest_balanced = MagicMock(return_value=5)
        mock_balancer.invalidate_cache = MagicMock()

        with patch(
            "src.maisaka.context.compaction.get_tool_pairing_balancer",
            return_value=mock_balancer,
        ):
            result = await compact_selected_history(
                history, context_window=1000, session_id="test",
                llm_service=llm_service, config=compaction_config,
            )

        tool_call_ids: set[str] = set()
        tool_result_ids: set[str] = set()
        for msg in result:
            if isinstance(msg, AssistantMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_ids.add(tc.call_id)
            elif isinstance(msg, ToolResultMessage):
                tool_result_ids.add(msg.tool_call_id)

        orphan_calls = tool_call_ids - tool_result_ids
        orphan_results = tool_result_ids - tool_call_ids
        assert not orphan_calls, f"孤立 tool_call: {orphan_calls}"
        assert not orphan_results, f"孤立 tool_result: {orphan_results}"