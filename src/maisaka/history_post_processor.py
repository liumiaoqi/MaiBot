"""Maisaka 历史消息轮次结束后处理。"""

from dataclasses import dataclass

from .context_messages import AssistantMessage, LLMContextMessage, ToolResultMessage
from .history_utils import drop_leading_orphan_tool_results, drop_orphan_tool_results, normalize_tool_result_order

TIMING_HISTORY_TOOL_NAMES = {"continue", "finish", "no_reply", "wait"}
EARLY_TRIM_RATIO = 0.2


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
    removed_timing_tool_count = _remove_early_timing_tool_records(processed_history)
    removed_assistant_thought_count = _remove_early_assistant_thoughts(processed_history)

    processed_history, orphan_removed_count = drop_orphan_tool_results(processed_history)
    processed_history, moved_tool_result_count = normalize_tool_result_order(processed_history)
    remaining_context_count = sum(1 for message in processed_history if message.count_in_context)
    removed_overflow_count = 0

    while remaining_context_count > max_context_size and processed_history:
        removed_message = processed_history.pop(0)
        removed_overflow_count += 1
        if removed_message.count_in_context:
            remaining_context_count -= 1

    processed_history, leading_orphan_removed_count = drop_leading_orphan_tool_results(processed_history)
    removed_overflow_count += leading_orphan_removed_count
    remaining_context_count = sum(1 for message in processed_history if message.count_in_context)
    removed_count = (
        removed_timing_tool_count
        + removed_assistant_thought_count
        + orphan_removed_count
        + removed_overflow_count
    )
    changed_count = removed_count + moved_tool_result_count
    return HistoryPostProcessResult(
        history=processed_history,
        removed_count=removed_count,
        changed_count=changed_count,
        remaining_context_count=remaining_context_count,
    )


def _remove_early_timing_tool_records(chat_history: list[LLMContextMessage]) -> int:
    """移除最早 20% 的门控/结束类工具链记录。"""

    candidate_assistant_indexes = [
        index
        for index, message in enumerate(chat_history)
        if _is_timing_tool_assistant_message(message)
    ]
    remove_count = int(len(candidate_assistant_indexes) * EARLY_TRIM_RATIO)
    if remove_count <= 0:
        return 0

    removed_indexes = set(candidate_assistant_indexes[:remove_count])
    removed_tool_call_ids = {
        tool_call.call_id
        for index in removed_indexes
        for tool_call in chat_history[index].tool_calls
        if tool_call.call_id
    }

    filtered_history: list[LLMContextMessage] = []
    removed_total = 0
    for index, message in enumerate(chat_history):
        if index in removed_indexes:
            removed_total += 1
            continue
        if isinstance(message, ToolResultMessage) and message.tool_call_id in removed_tool_call_ids:
            removed_total += 1
            continue
        filtered_history.append(message)

    chat_history[:] = filtered_history
    return removed_total


def _remove_early_assistant_thoughts(chat_history: list[LLMContextMessage]) -> int:
    """移除最早 20% 的非工具 assistant 思考内容。"""

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


def _is_timing_tool_assistant_message(message: LLMContextMessage) -> bool:
    if not isinstance(message, AssistantMessage) or not message.tool_calls:
        return False

    return all(tool_call.func_name in TIMING_HISTORY_TOOL_NAMES for tool_call in message.tool_calls)
