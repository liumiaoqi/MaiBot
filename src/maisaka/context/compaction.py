"""ZG-25 B 层替换式 compaction——select 后对 selected_history 做摘要替换。

对标 dsh compactSurfaceRegion（region.ts:152-254）：
prepareCompaction → summarizeCompaction → commitCompactionBody 三阶段。

作用于临时列表 selected_history，不写回 _chat_history，不污染共享历史。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from src.common.data_models.llm_service_data_models import LLMGenerationOptions
from src.common.logger import get_logger
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart
from src.maisaka.context.messages import (
    AssistantMessage,
    CompactionSummaryMessage,
    LLMContextMessage,
    ReferenceMessage,
    ReferenceMessageType,
    ToolResultMessage,
)
from src.maisaka.context.token_estimator import estimate_messages

if TYPE_CHECKING:
    from src.core.protocols import LLMService

logger = get_logger("maisaka.compaction")


@dataclass
class CompactionConfig:
    """B 层 compaction 可调参数。"""

    enable: bool = False
    threshold_ratio: float = 0.72
    retain_ratio: float = 0.32
    min_segment_size: int = 6
    min_segment_tokens: int = 500
    timeout_ms: int = 3000
    summary_max_tokens: int = 500


async def compact_selected_history(
    selected_history: list[LLMContextMessage],
    *,
    context_window: int,
    session_id: str,
    llm_service: "LLMService",
    config: CompactionConfig,
) -> list[LLMContextMessage]:
    """B 层替换式 compaction——select 后对 selected_history 做摘要替换。

    返回 compacted_history（不修改输入 selected_history）。
    失败降级返回原 selected_history。
    """

    if not config.enable or not selected_history:
        return selected_history
    try:
        if not _should_trigger_compaction(selected_history, context_window=context_window, config=config):
            return selected_history
        segment = _select_compactable_range(selected_history, config=config)
        if segment is None:
            logger.debug(f"B 层 compaction 跳过: session={session_id} 无满足条件的可压缩段")
            return selected_history
        segment_start, segment_end = segment
        segment_messages = selected_history[segment_start:segment_end]
        summary_text = await _summarize_segment(
            segment_messages,
            llm_service=llm_service,
            config=config,
            session_id=session_id,
        )
        if summary_text is None:
            return selected_history
        before_tokens = estimate_messages(segment_messages)
        summary_tokens = estimate_messages([CompactionSummaryMessage(
            summary_text=summary_text,
            timestamp=datetime.now(),
        )])
        if summary_tokens >= before_tokens:
            logger.debug(f"B 层 compaction 跳过: session={session_id} 摘要 token={summary_tokens} >= 原段 token={before_tokens}（无收益）")
            return selected_history
        compacted = _commit_compaction(selected_history, segment_start, segment_end, summary_text)
        after_tokens = estimate_messages(compacted)
        logger.info(
            f"B 层 compaction: session={session_id} "
            f"before_tokens={before_tokens} "
            f"after_tokens={after_tokens} "
            f"segment_count={segment_end - segment_start} "
            f"summary_tokens={summary_tokens} "
            f"net_release={before_tokens - after_tokens}"
        )
        return compacted
    except Exception as exc:
        # P1: 补 port.report 双通道上报
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        _port = get_error_escalation_port()
        if _port is not None:
            _port.report(ErrorLevel.WARNING, f"B 层 compaction 失败，降级返回原 history: {exc}", exception=exc)
        logger.warning(f"B 层 compaction 失败，降级返回原 history: {exc}")
        return selected_history


def _should_trigger_compaction(
    history: list[LLMContextMessage],
    *,
    context_window: int,
    config: CompactionConfig,
) -> bool:
    """判断是否应触发 compaction（token 估算超阈值）。"""

    current_tokens = estimate_messages(history)
    threshold = int(context_window * config.threshold_ratio)
    if current_tokens > threshold:
        return True
    logger.debug(f"B 层 compaction 跳过: current_tokens={current_tokens} threshold={threshold}")
    return False


def _select_compactable_range(
    history: list[LLMContextMessage],
    *,
    config: CompactionConfig,
) -> Optional[tuple[int, int]]:
    """段识别——从头部找连续可压缩段。

    段内不含 ReferenceMessage(CONTEXT_RESTORE) 和 is_mid_term_memory_message（整体扫描）。
    段尾到 history 尾部保留 retain_budget token。
    段内不破坏工具配对。
    """

    from src.maisaka.memory.mid_term import is_mid_term_memory_message

    total_tokens = estimate_messages(history)
    retain_budget = int(total_tokens * config.retain_ratio)

    # 从尾部累计 token 找 retain_budget 边界
    accumulated = 0
    retain_index = len(history)
    for i in range(len(history) - 1, -1, -1):
        msg_tokens = estimate_messages([history[i]])
        accumulated += msg_tokens
        if accumulated >= retain_budget:
            retain_index = i
            break

    # 可压缩范围 = history[0 : retain_index]
    if retain_index <= 0:
        return None

    # 从可压缩范围尾部往前找工具配对完整边界
    boundary = retain_index
    for i in range(retain_index - 1, -1, -1):
        msg = history[i]
        # 工具配对边界：ToolResultMessage 或带 tool_calls 的 AssistantMessage → 继续往前
        if isinstance(msg, ToolResultMessage):
            boundary = i
            continue
        if isinstance(msg, AssistantMessage) and msg.tool_calls:
            boundary = i
            continue
        # 普通消息 → 边界确定
        boundary = i + 1
        break

    if boundary <= 0:
        return None

    # 整体扫描：段内不含 ReferenceMessage(CONTEXT_RESTORE) 和 mid_term_memory_message
    segment = history[0:boundary]
    for msg in segment:
        if isinstance(msg, ReferenceMessage) and msg.reference_type == ReferenceMessageType.CONTEXT_RESTORE:
            return None
        if is_mid_term_memory_message(msg):
            return None

    if len(segment) < config.min_segment_size:
        return None
    segment_tokens = estimate_messages(segment)
    if segment_tokens < config.min_segment_tokens:
        return None

    return (0, boundary)


async def _summarize_segment(
    segment: list[LLMContextMessage],
    *,
    llm_service: "LLMService",
    config: CompactionConfig,
    session_id: str,
) -> Optional[str]:
    """摘要生成——对段内 user/assistant 消息提取文本并调 LLM 生成摘要。"""

    texts = []
    for msg in segment:
        text = msg.processed_plain_text
        if text and text.strip():
            texts.append(f"[{msg.role}]: {text}")

    if not texts:
        return None

    combined = "\n".join(texts)
    prompt = (
        "请将以下对话历史压缩为一段简洁的摘要，保留关键信息（讨论主题、重要决定、用户意图），"
        f"不超过 {config.summary_max_tokens} token：\n\n{combined}"
    )

    def message_factory(_client: Any, _model_info: Any = None) -> list[Message]:
        return [Message(role=RoleType.User, parts=[TextMessagePart(text=prompt)])]

    options = LLMGenerationOptions(
        max_tokens=config.summary_max_tokens,
        temperature=0.0,
    )

    try:
        result = await asyncio.wait_for(
            llm_service.generate_response_with_messages(
                "planner",
                message_factory,
                options,
                request_type="maisaka.b_layer_compaction",
                session_id=session_id,
            ),
            timeout=config.timeout_ms / 1000,
        )
        summary = result.response or ""
        if not summary.strip():
            return None
        return summary.strip()
    except asyncio.TimeoutError as exc:
        # P1: 补 port.report 双通道上报
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        _port = get_error_escalation_port()
        if _port is not None:
            _port.report(ErrorLevel.WARNING, f"B 层 compaction 摘要生成超时: session={session_id}", exception=exc)
        logger.warning(f"B 层 compaction 摘要生成超时: session={session_id}")
        return None
    except Exception as exc:
        # P1: 补 port.report 双通道上报
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        _port = get_error_escalation_port()
        if _port is not None:
            _port.report(ErrorLevel.WARNING, f"B 层 compaction 摘要生成失败: session={session_id} error={exc}", exception=exc)
        logger.warning(f"B 层 compaction 摘要生成失败: session={session_id} error={exc}")
        return None


def _commit_compaction(
    history: list[LLMContextMessage],
    segment_start: int,
    segment_end: int,
    summary_text: str,
) -> list[LLMContextMessage]:
    """替换执行——将可压缩段替换为一条 CompactionSummaryMessage。"""

    segment = history[segment_start:segment_end]
    first_ts = segment[0].timestamp if segment else datetime.now()
    last_ts = segment[-1].timestamp if segment else datetime.now()
    time_range = f"{first_ts.strftime('%Y-%m-%d %H:%M')} ~ {last_ts.strftime('%Y-%m-%d %H:%M')}"

    summary_msg = CompactionSummaryMessage(
        summary_text=summary_text,
        timestamp=datetime.now(),
        original_segment_count=len(segment),
        original_time_range=time_range,
    )

    return [summary_msg] + list(history[segment_end:])