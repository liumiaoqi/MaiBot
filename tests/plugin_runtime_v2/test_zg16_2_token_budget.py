"""ZG16-2 token 预算选择器单元测试。

覆盖 select_by_token_budget 的从后往前累计、引用消息始终保留、
尾部 retain 优先、头部丢弃、context_window/ratio 越界 fallback、
count_in_context=False 不累加 token 等场景。
"""


from typing import List
from unittest.mock import MagicMock

from src.maisaka.context.token_budget import select_by_token_budget



def _make_mock_message(text: str, *, count_in_context: bool = True) -> MagicMock:
    """构造 mock 消息对象。

    Args:
        text: processed_plain_text 属性值。
        count_in_context: 是否计入上下文窗口。
    """
    msg = MagicMock()
    msg.processed_plain_text = text
    msg.count_in_context = count_in_context
    return msg


def _make_messages(count: int, text_len: int = 184) -> List[MagicMock]:
    """构造 count 条等长消息，每条 token = ceil(text_len/2) + 8。

    text_len=184 → token = 92 + 8 = 100。
    """
    return [_make_mock_message("x" * text_len) for _ in range(count)]


# ════════════════════════════════════════════════════════════════════
# 预算上限计算
# ════════════════════════════════════════════════════════════════════


def test_budget_limit_calculation():
    """预算上限 = context_window × threshold_ratio = 65536 × 0.8 = 52428。

    构造少量消息（token 总量远小于预算），验证全部选中不裁切。
    """
    msgs = _make_messages(3)  # 3 × 100 = 300 token
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2]


# ════════════════════════════════════════════════════════════════════
# 从后往前累计
# ════════════════════════════════════════════════════════════════════


def test_backward_accumulation_triggers_trimming():
    """10 条消息（每条 10000 token），累计到第 7 条达预算 → 选中第 4-10 条。

    budget_limit = int(65536 * 0.8) = 52428
    retain_budget = int(65536 * 0.16) = 10485
    从后往前：第 6-10 条在预算内（5×10000=50000 ≤ 52428）
    第 5 条超预算 → retain_budget=10485>0 → 选中，retain=485
    第 4 条超预算 → retain_budget=485>0 → 选中，retain=-9515
    第 3-1 条 → retain_budget≤0 → 丢弃
    """
    # 每条 token = 10000 → text_len = (10000-8)*2 = 19984
    msgs = _make_messages(10, text_len=19984)
    selected, total_tokens = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    # 选中第 4-10 条（索引 3-9）
    assert selected == [3, 4, 5, 6, 7, 8, 9]
    # 7 条 × 10000 = 70000
    assert total_tokens == 70000


# ════════════════════════════════════════════════════════════════════
# 引用消息始终保留
# ════════════════════════════════════════════════════════════════════


def test_reference_message_always_retained():
    """引用消息在头部 + 预算裁切到尾部 → 引用消息仍选中。"""
    msgs = _make_messages(10, text_len=19984)
    # 索引 0 是引用消息
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[0],
        enable_visual_message=True,
    )
    assert 0 in selected
    # 尾部消息也应保留
    assert 9 in selected


def test_reference_message_in_middle_retained():
    """引用消息在中间位置也始终保留。"""
    msgs = _make_messages(10, text_len=19984)
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[2],
        enable_visual_message=True,
    )
    assert 2 in selected


# ════════════════════════════════════════════════════════════════════
# 全部消息 token < 预算
# ════════════════════════════════════════════════════════════════════


def test_all_messages_within_budget():
    """全部消息 token < 预算 → 全部选中不裁切。"""
    msgs = _make_messages(5)  # 5 × 100 = 500 token
    selected, total_tokens = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2, 3, 4]
    assert total_tokens == 500


# ════════════════════════════════════════════════════════════════════
# 预算上限 < 单条消息
# ════════════════════════════════════════════════════════════════════


def test_budget_smaller_than_single_message():
    """预算上限 < 单条消息 → 仍保留最近一条。"""
    # 1 条超大消息，token = 100000
    msgs = [_make_mock_message("x" * 199984)]  # token = 99992 + 8 = 100000
    selected, total_tokens = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0]
    assert total_tokens == 100000


def test_multiple_oversized_messages_retain_latest():
    """多条超大消息 → 至少保留最近一条。"""
    msgs = _make_messages(3, text_len=199984)  # 每条 100000 token
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    # 最近一条（索引 2）必须保留
    assert 2 in selected


# ════════════════════════════════════════════════════════════════════
# 全部是引用消息
# ════════════════════════════════════════════════════════════════════


def test_all_reference_messages_retained():
    """全部是引用消息 → 全部保留（即使超预算）。"""
    msgs = _make_messages(5, text_len=19984)  # 每条 10000 token，总计 50000 > 52428？不，50000 < 52428
    # 用更大的消息确保超预算
    msgs = _make_messages(10, text_len=19984)  # 总计 100000 > 52428
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=list(range(10)),
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


# ════════════════════════════════════════════════════════════════════
# context_window 非法 fallback
# ════════════════════════════════════════════════════════════════════


def test_context_window_none_fallback():
    """context_window=None → fallback 65536。"""
    msgs = _make_messages(3)
    selected, _ = select_by_token_budget(
        msgs,
        context_window=None,  # type: ignore[arg-type]
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    # fallback 65536，3 × 100 = 300 << 52428，全部选中
    assert selected == [0, 1, 2]


def test_context_window_zero_fallback():
    """context_window=0 → fallback 65536。"""
    msgs = _make_messages(3)
    selected, _ = select_by_token_budget(
        msgs,
        context_window=0,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2]


def test_context_window_negative_fallback():
    """context_window=-1 → fallback 65536。"""
    msgs = _make_messages(3)
    selected, _ = select_by_token_budget(
        msgs,
        context_window=-1,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2]


# ════════════════════════════════════════════════════════════════════
# ratio 越界 fallback
# ════════════════════════════════════════════════════════════════════


def test_threshold_ratio_out_of_bounds_fallback():
    """threshold_ratio > 1 → fallback 0.8。"""
    msgs = _make_messages(3)
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=1.5,  # 越界 → fallback 0.8
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2]


def test_retain_ratio_negative_fallback():
    """retain_ratio < 0 → fallback 0.16。"""
    msgs = _make_messages(3)
    selected, _ = select_by_token_budget(
        msgs,
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=-0.5,  # 越界 → fallback 0.16
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0, 1, 2]


# ════════════════════════════════════════════════════════════════════
# count_in_context=False
# ════════════════════════════════════════════════════════════════════


def test_count_in_context_false_no_accumulation():
    """count_in_context=False → 不累加 token 但若在选中范围内仍进 prompt。

    构造 4 条消息：第 1-2 条 count_in_context=False，第 3-4 条 count_in_context=True。
    context_window=400, threshold_ratio=0.8 → budget_limit=320。
    从后往前：
    - 第 4 条（True）：100 ≤ 320 → 选中，accumulated=100
    - 第 3 条（True）：200 ≤ 320 → 选中，accumulated=200
    - 第 2 条（False）：200+100=300 ≤ 320 → 选中，不累加 accumulated
    - 第 1 条（False）：200+100=300 ≤ 320 → 选中，不累加 accumulated
    全部选中，因为 False 消息不累加 accumulated。
    """
    msgs = [
        _make_mock_message("x" * 184, count_in_context=False),
        _make_mock_message("x" * 184, count_in_context=False),
        _make_mock_message("x" * 184, count_in_context=True),
        _make_mock_message("x" * 184, count_in_context=True),
    ]
    selected, _ = select_by_token_budget(
        msgs,
        context_window=400,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    # False 消息不累加 accumulated，所以全部选中
    assert selected == [0, 1, 2, 3]


def test_count_in_context_false_comparison_with_true():
    """对比验证：count_in_context=False 不累加 token，True 会累加导致裁切。

    构造 4 条消息全 count_in_context=True：
    context_window=400, threshold_ratio=0.8 → budget_limit=320。
    - 第 4 条：100 ≤ 320 → 选中，accumulated=100
    - 第 3 条：200 ≤ 320 → 选中，accumulated=200
    - 第 2 条：300 ≤ 320 → 选中，accumulated=300
    - 第 1 条：400 > 320 → retain_budget=64>0 → 选中
    全部选中（retain_budget 兜底）。

    但如果 context_window=300 → budget_limit=240：
    - 第 4 条：100 ≤ 240 → 选中，accumulated=100
    - 第 3 条：200 ≤ 240 → 选中，accumulated=200
    - 第 2 条：300 > 240 → retain_budget=48>0 → 选中，retain=-52
    - 第 1 条：300 > 240 → retain=-52≤0 → 丢弃
    选中 [1, 2, 3]。
    """
    msgs_true = _make_messages(4)
    selected_true, _ = select_by_token_budget(
        msgs_true,
        context_window=300,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    # 全 True 时第 1 条被丢弃
    assert selected_true == [1, 2, 3]

    # 将第 1-2 条改为 False → 不累加 → 全部选中
    msgs_mixed = [
        _make_mock_message("x" * 184, count_in_context=False),
        _make_mock_message("x" * 184, count_in_context=False),
        _make_mock_message("x" * 184, count_in_context=True),
        _make_mock_message("x" * 184, count_in_context=True),
    ]
    selected_mixed, _ = select_by_token_budget(
        msgs_mixed,
        context_window=300,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    # False 消息不累加 accumulated，第 3-4 条 accumulated=200
    # 第 2 条（False）：200+100=300 > 240 → 不选中
    # 第 1 条（False）：200+100=300 > 240 → 不选中
    assert selected_mixed == [2, 3]


# ════════════════════════════════════════════════════════════════════
# 空列表
# ════════════════════════════════════════════════════════════════════


def test_empty_history():
    """空历史 → 空选中，0 token。"""
    selected, total_tokens = select_by_token_budget(
        [],
        context_window=65536,
        threshold_ratio=0.8,
        retain_ratio=0.16,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == []
    assert total_tokens == 0


# ════════════════════════════════════════════════════════════════════
# 全部超预算且 retain_budget=0 → 兜底保留最近一条
# ════════════════════════════════════════════════════════════════════


def test_all_over_budget_retain_zero_fallback_latest():
    """全部消息超预算 + retain_ratio=0 → 兜底保留最近一条。

    context_window=100, threshold_ratio=0.8 → budget_limit=80
    retain_ratio=0 → retain_budget=0
    1 条消息 token=100 > 80 → 丢弃 → selected_indices 为空
    → 兜底保留最近一条（索引 0）。
    """
    msgs = [_make_mock_message("x" * 184)]  # token=100
    selected, total_tokens = select_by_token_budget(
        msgs,
        context_window=100,
        threshold_ratio=0.8,
        retain_ratio=0.0,
        always_selected_indices=[],
        enable_visual_message=True,
    )
    assert selected == [0]
    assert total_tokens == 100