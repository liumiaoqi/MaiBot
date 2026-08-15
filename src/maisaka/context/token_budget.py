"""token 预算选择器——ZG16-2 design 模块 B。

从后往前累计 token，引用消息始终保留，尾部 retain 优先，头部丢弃。
优先级：引用消息 > 尾部保留 > 头部丢弃（dsh 补充意见 3）。
"""


from typing import TYPE_CHECKING, List, Tuple

from src.maisaka.context.token_estimator import (
    DEFAULT_CONTEXT_WINDOW,
    estimate_message,
)

if TYPE_CHECKING:
    from src.maisaka.context.messages import LLMContextMessage

_DEFAULT_THRESHOLD_RATIO = 0.8
_DEFAULT_RETAIN_RATIO = 0.16


def _sanitize_context_window(context_window: int) -> int:
    """context_window 非法（≤0）时 fallback 全局默认。"""
    if context_window is None or context_window <= 0:
        return DEFAULT_CONTEXT_WINDOW
    return context_window


def _sanitize_ratio(ratio: float, default: float) -> float:
    """ratio 越界（>1 或 <0）时 fallback 默认值。"""
    if ratio is None or ratio < 0 or ratio > 1:
        return default
    return ratio


def select_by_token_budget(
    filtered_history: List["LLMContextMessage"],
    *,
    context_window: int,
    threshold_ratio: float,
    retain_ratio: float,
    always_selected_indices: List[int],
    enable_visual_message: bool,
) -> Tuple[List[int], int]:
    """按 token 预算从后往前选择消息。

    Args:
        filtered_history: 已过滤的历史消息列表。
        context_window: 模型输入窗口大小（token 数）。
        threshold_ratio: 触发裁切阈值比例（预算上限 = context_window × ratio）。
        retain_ratio: 尾部保留比例（尾部 context_window × ratio 逐字保留）。
        always_selected_indices: 引用消息索引（始终保留，不计预算）。
        enable_visual_message: 视觉消息开关。

    Returns:
        (选中索引列表排序去重, 估算 token 总量)。
    """
    cw = _sanitize_context_window(context_window)
    tr = _sanitize_ratio(threshold_ratio, _DEFAULT_THRESHOLD_RATIO)
    rr = _sanitize_ratio(retain_ratio, _DEFAULT_RETAIN_RATIO)

    budget_limit = int(cw * tr)
    retain_budget = int(cw * rr)

    always_set = set(always_selected_indices)
    selected_indices: List[int] = []
    accumulated_tokens = 0
    total_estimated_tokens = 0

    for index in range(len(filtered_history) - 1, -1, -1):
        message = filtered_history[index]
        msg_tokens = estimate_message(message, enable_visual_message=enable_visual_message)

        if index in always_set:
            selected_indices.append(index)
            total_estimated_tokens += msg_tokens
            continue

        count_in_context = getattr(message, "count_in_context", True)
        if not count_in_context:
            if accumulated_tokens + msg_tokens <= budget_limit:
                selected_indices.append(index)
                total_estimated_tokens += msg_tokens
            continue

        if accumulated_tokens + msg_tokens <= budget_limit:
            selected_indices.append(index)
            accumulated_tokens += msg_tokens
            total_estimated_tokens += msg_tokens
        elif retain_budget > 0:
            selected_indices.append(index)
            retain_budget -= msg_tokens
            total_estimated_tokens += msg_tokens
        else:
            pass

    if not selected_indices and filtered_history:
        last_index = len(filtered_history) - 1
        selected_indices.append(last_index)
        total_estimated_tokens = estimate_message(
            filtered_history[last_index],
            enable_visual_message=enable_visual_message,
        )

    for idx in always_set:
        if 0 <= idx < len(filtered_history) and idx not in selected_indices:
            selected_indices.append(idx)

    selected_indices = sorted(set(selected_indices))
    return selected_indices, total_estimated_tokens