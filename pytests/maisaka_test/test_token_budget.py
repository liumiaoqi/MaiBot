"""token_budget 单元测试。

覆盖 select_by_token_budget 及其 sanitize 辅助逻辑的
正常、边界与异常输入（引用保留、尾部 retain、头部丢弃、非法参数兜底）。
"""

from types import SimpleNamespace

from src.maisaka.context.token_budget import select_by_token_budget


def _make_message(text: str, count_in_context: bool = True) -> SimpleNamespace:
    """构造轻量消息替身（带 processed_plain_text 与 count_in_context）。"""
    msg = SimpleNamespace(processed_plain_text=text)
    if not count_in_context:
        msg.count_in_context = False
    return msg


class TestSelectByTokenBudgetBasic:
    """select_by_token_budget 基本行为测试。"""

    def test_empty_history_returns_empty(self):
        indices, tokens = select_by_token_budget(
            filtered_history=[],
            context_window=1000,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        assert indices == []
        assert tokens == 0

    def test_single_message_within_budget(self):
        msg = _make_message("hello")
        indices, tokens = select_by_token_budget(
            filtered_history=[msg],
            context_window=1000,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        assert indices == [0]
        assert tokens > 0

    def test_indices_sorted_and_deduplicated(self):
        msgs = [_make_message(f"t{i}") for i in range(3)]
        indices, _ = select_by_token_budget(
            filtered_history=msgs,
            context_window=10000,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[2, 0, 2],
            enable_visual_message=True,
        )
        # 排序去重
        assert indices == sorted(set(indices))
        assert 0 in indices and 2 in indices


class TestAlwaysSelectedIndices:
    """引用消息始终保留测试。"""

    def test_always_selected_index_preserved(self):
        msgs = [_make_message("x" * 100) for _ in range(5)]
        # 强制保留索引 0（头部，通常先被丢弃）
        indices, _ = select_by_token_budget(
            filtered_history=msgs,
            context_window=100,
            threshold_ratio=0.1,
            retain_ratio=0.0,
            always_selected_indices=[0],
            enable_visual_message=True,
        )
        assert 0 in indices

    def test_always_selected_out_of_range_ignored(self):
        msgs = [_make_message("ab") for _ in range(2)]
        indices, _ = select_by_token_budget(
            filtered_history=msgs,
            context_window=10000,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[99],
            enable_visual_message=True,
        )
        assert 99 not in indices


class TestRetainAndBudget:
    """尾部 retain 与预算裁切测试。"""

    def test_tail_retain_keeps_recent_messages(self):
        # 极小预算，但仍应保留尾部 retain 消息
        msgs = [_make_message("abcd") for _ in range(10)]
        indices, _ = select_by_token_budget(
            filtered_history=msgs,
            context_window=100,
            threshold_ratio=0.05,  # budget_limit=5
            retain_ratio=0.5,  # retain_budget=50
            always_selected_indices=[],
            enable_visual_message=True,
        )
        # 最后一条始终保留
        assert 9 in indices

    def test_count_in_context_false_does_not_consume_budget(self):
        # count_in_context=False 的消息不占预算但仍计入 token
        msgs = [_make_message("ab", count_in_context=False) for _ in range(5)]
        indices, tokens = select_by_token_budget(
            filtered_history=msgs,
            context_window=10000,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        # 全部选中（不占预算）
        assert indices == [0, 1, 2, 3, 4]
        assert tokens > 0


class TestSanitizeParameters:
    """非法参数兜底测试。"""

    def test_invalid_context_window_falls_back_to_default(self):
        msg = _make_message("ab")
        indices_valid, tokens_valid = select_by_token_budget(
            filtered_history=[msg],
            context_window=65536,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        indices_invalid, tokens_invalid = select_by_token_budget(
            filtered_history=[msg],
            context_window=0,  # 非法
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        # 兜底到 DEFAULT_CONTEXT_WINDOW，结果应一致
        assert indices_valid == indices_invalid
        assert tokens_valid == tokens_invalid

    def test_negative_context_window_falls_back(self):
        msg = _make_message("ab")
        indices, _ = select_by_token_budget(
            filtered_history=[msg],
            context_window=-1,
            threshold_ratio=0.8,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        assert indices == [0]

    def test_invalid_threshold_ratio_falls_back(self):
        msg = _make_message("ab")
        # ratio > 1 兜底默认 0.8
        indices, _ = select_by_token_budget(
            filtered_history=[msg],
            context_window=10000,
            threshold_ratio=1.5,
            retain_ratio=0.16,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        assert indices == [0]

    def test_invalid_retain_ratio_falls_back(self):
        msg = _make_message("ab")
        indices, _ = select_by_token_budget(
            filtered_history=[msg],
            context_window=10000,
            threshold_ratio=0.8,
            retain_ratio=-0.5,  # 非法
            always_selected_indices=[],
            enable_visual_message=True,
        )
        assert indices == [0]


class TestEmptySelectionFallback:
    """空选中兜底测试。"""

    def test_no_selection_keeps_last_message(self):
        # 极小预算 + retain=0，至少保留最后一条
        msgs = [_make_message("x" * 1000) for _ in range(3)]
        indices, _ = select_by_token_budget(
            filtered_history=msgs,
            context_window=100,
            threshold_ratio=0.01,  # budget_limit=1
            retain_ratio=0.0,
            always_selected_indices=[],
            enable_visual_message=True,
        )
        # 至少保留最后一条
        assert 2 in indices
        assert len(indices) >= 1