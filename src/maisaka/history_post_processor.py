"""Maisaka 历史消息轮次结束后处理。"""

from dataclasses import dataclass
from math import ceil

from .context_messages import AssistantMessage, LLMContextMessage
from .history_utils import drop_leading_orphan_tool_results, drop_orphan_tool_results, normalize_tool_result_order

EARLY_TRIM_RATIO = 0.3
TRIM_THRESHOLD_RATIO = 1.2


@dataclass(slots=True)
class HistoryPostProcessResult:
    """历史后处理结果。"""

    history: list[LLMContextMessage]
    removed_count: int
    changed_count: int
    remaining_context_count: int


def process_chat_history_after_cycle(
    chat_history: list[LLMContextMessage],
    *,
    max_context_size: int,
) -> HistoryPostProcessResult:
    """在每轮结束后统一执行历史裁切与清理。"""

    processed_history = list(chat_history)
    processed_history, normalized_removed_count, moved_tool_result_count = _normalize_history_structure(
        processed_history
    )
    remaining_context_count = sum(1 for message in processed_history if message.count_in_context)

    compact_removed_count = 0
    trim_threshold = ceil(max_context_size * TRIM_THRESHOLD_RATIO)
    if remaining_context_count > trim_threshold:
        removed_early_message_count = _remove_early_history_messages(processed_history)
        processed_history, removed_after_message_trim_count, moved_after_message_trim_count = (
            _normalize_history_structure(processed_history)
        )
        removed_assistant_thought_count = _remove_early_assistant_thoughts(processed_history)
        processed_history, removed_after_thought_trim_count, moved_after_thought_trim_count = (
            _normalize_history_structure(processed_history)
        )
        compact_removed_count = (
            removed_early_message_count
            + removed_after_message_trim_count
            + removed_assistant_thought_count
            + removed_after_thought_trim_count
        )
        moved_tool_result_count += moved_after_message_trim_count + moved_after_thought_trim_count

    remaining_context_count = sum(1 for message in processed_history if message.count_in_context)
    removed_count = normalized_removed_count + compact_removed_count
    changed_count = removed_count + moved_tool_result_count
    return HistoryPostProcessResult(
        history=processed_history,
        removed_count=removed_count,
        changed_count=changed_count,
        remaining_context_count=remaining_context_count,
    )


def _normalize_history_structure(
    chat_history: list[LLMContextMessage],
) -> tuple[list[LLMContextMessage], int, int]:
    """规范化历史消息结构，保证工具调用链符合 LLM 消息协议。"""

    processed_history, orphan_removed_count = drop_orphan_tool_results(chat_history)
    processed_history, moved_tool_result_count = normalize_tool_result_order(processed_history)
    processed_history, leading_orphan_removed_count = drop_leading_orphan_tool_results(processed_history)
    return (
        processed_history,
        orphan_removed_count + leading_orphan_removed_count,
        moved_tool_result_count,
    )


def _remove_early_history_messages(chat_history: list[LLMContextMessage]) -> int:
    """移除最早 30% 的全部历史消息。"""

    remove_count = int(len(chat_history) * EARLY_TRIM_RATIO)
    if remove_count <= 0:
        return 0

    del chat_history[:remove_count]
    return remove_count


def _remove_early_assistant_thoughts(chat_history: list[LLMContextMessage]) -> int:
    """移除最早 30% 的非工具 assistant 思考内容。"""

    candidate_indexes = [
        index
        for index, message in enumerate(chat_history)
        if isinstance(message, AssistantMessage)
        and not message.tool_calls
        and message.source_kind != "perception"
        and bool(message.content.strip())
    ]
    remove_count = int(len(candidate_indexes) * EARLY_TRIM_RATIO)
    if remove_count <= 0:
        return 0

    removed_indexes = set(candidate_indexes[:remove_count])
    filtered_history: list[LLMContextMessage] = []
    removed_total = 0
    for index, message in enumerate(chat_history):
        if index in removed_indexes:
            removed_total += 1
            continue
        filtered_history.append(message)

    chat_history[:] = filtered_history
    return removed_total


