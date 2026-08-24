"""ZG-25 B 层替换式 compaction——select 后对 selected_history 做摘要替换。

对标 dsh compactSurfaceRegion（region.ts:152-254）：
prepareCompaction → summarizeCompaction → commitCompactionBody 三阶段。

作用于临时列表 selected_history，不写回 _chat_history，不污染共享历史。

0824 升级：对接 N5 surface 替换（SurfaceReplacer）+ tool-pairing（ToolPairingBalancer）+ N6 token meter 统一会计。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from src.common.data_models.llm_service_data_models import LLMGenerationOptions
from src.common.logger import get_logger
from src.core.token_meter.service import get_token_meter
from src.llm_models.payload_content.message import Message, RoleType, TextMessagePart
from src.maisaka.context.compaction_adapter import (
    get_surface_replacer,
    get_tool_pairing_balancer,
    to_n5_events,
)
from src.maisaka.context.messages import (
    CompactionSummaryMessage,
    LLMContextMessage,
    ReferenceMessage,
    ReferenceMessageType,
)

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
        segment = _select_compactable_range(selected_history, session_id=session_id, config=config)
        if segment is None:
            logger.debug(f"B 层 compaction 跳过: session={session_id} 无满足条件的可压缩段")
            return selected_history
        segment_start, segment_end = segment
        segment_messages = selected_history[segment_start:segment_end]

        # N5 稳定性校验：摘要生成前记录 expected_generation
        surface_replacer = get_surface_replacer(selected_history, session_id)
        expected_generation = await surface_replacer.current_generation(session_id)

        summary_text = await _summarize_segment(
            segment_messages,
            llm_service=llm_service,
            config=config,
            session_id=session_id,
        )
        if summary_text is None:
            return selected_history

        # N5 稳定性校验：摘要生成后确认 surface 未变
        surface_unchanged = await surface_replacer.assert_surface_unchanged(session_id, expected_generation)
        if not surface_unchanged:
            logger.warning(f"B 层 compaction 降级: session={session_id} surface 在摘要期间已变")
            return selected_history

        meter = get_token_meter()
        before_tokens = sum(meter.estimate(msg) for msg in segment_messages)
        summary_msg_preview = CompactionSummaryMessage(summary_text=summary_text, timestamp=datetime.now())
        summary_tokens = meter.estimate(summary_msg_preview)
        if summary_tokens >= before_tokens:
            logger.debug(f"B 层 compaction 跳过: session={session_id} 摘要 token={summary_tokens} >= 原段 token={before_tokens}（无收益）")
            return selected_history

        compacted, tx_id, replace_generation = await _commit_compaction(
            selected_history, segment_start, segment_end, summary_text, session_id
        )
        after_tokens = sum(meter.estimate(msg) for msg in compacted)

        # N5 缓存失效：压缩替换完成后使 balancer cache 失效
        get_tool_pairing_balancer().invalidate_cache(session_id)

        logger.info(
            f"B 层 compaction: session={session_id} "
            f"before_tokens={before_tokens} "
            f"after_tokens={after_tokens} "
            f"segment_count={segment_end - segment_start} "
            f"summary_tokens={summary_tokens} "
            f"net_release={before_tokens - after_tokens} "
            f"tx_id={tx_id} "
            f"replace_generation={replace_generation}"
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
    """判断是否应触发 compaction（N6 token meter 统一会计）。"""

    meter = get_token_meter()
    current_tokens = sum(meter.estimate(msg) for msg in history)
    threshold = int(context_window * config.threshold_ratio)
    if current_tokens > threshold:
        return True
    logger.debug(f"B 层 compaction 跳过: current_tokens={current_tokens} threshold={threshold}")
    return False


def _select_compactable_range(
    history: list[LLMContextMessage],
    *,
    session_id: str,
    config: CompactionConfig,
) -> Optional[tuple[int, int]]:
    """段识别——从头部找连续可压缩段（N5 tool-pairing balancer + N6 token meter）。

    段内不含 ReferenceMessage(CONTEXT_RESTORE) 和 is_mid_term_memory_message（整体扫描）。
    段尾到 history 尾部保留 retain_budget token。
    段内不破坏工具配对（N5 ToolPairingBalancer 边界平衡检查）。
    """

    from src.maisaka.memory.mid_term import is_mid_term_memory_message

    meter = get_token_meter()
    total_tokens = sum(meter.estimate(msg) for msg in history)
    retain_budget = int(total_tokens * config.retain_ratio)

    # 从尾部累计 token 找 retain_budget 边界（N6 token meter）
    accumulated = 0
    retain_index = len(history)
    for i in range(len(history) - 1, -1, -1):
        msg_tokens = meter.estimate(history[i])
        accumulated += msg_tokens
        if accumulated >= retain_budget:
            retain_index = i
            break

    # 可压缩范围 = history[0 : retain_index]
    if retain_index <= 0:
        return None

    # N5 ToolPairingBalancer 边界平衡检查
    balancer = get_tool_pairing_balancer()
    events = to_n5_events(history)
    surface_nodes = list(range(len(history)))
    generation = 0  # 临时列表 generation 固定 0

    balanced_seq = balancer.adjust_to_nearest_balanced(
        session_id, surface_nodes, generation, events, ideal_idx=retain_index - 1
    )
    if balanced_seq is None:
        return None

    boundary = balanced_seq + 1  # balanced_seq 是 seq，boundary 是切片端点
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
    segment_tokens = sum(meter.estimate(msg) for msg in segment)
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


async def _commit_compaction(
    history: list[LLMContextMessage],
    segment_start: int,
    segment_end: int,
    summary_text: str,
    session_id: str,
) -> tuple[list[LLMContextMessage], str, int]:
    """替换执行——N5 SurfaceReplacer 替换 + 事务身份 + 代数递增。

    Returns:
        (compacted_history, tx_id, replace_generation)
    """

    from src.A_memorix.core.runtime.services.compaction.types import (  # noqa: TID251 — ZG-25 升级复用 N5 成果
        CompactionId,
        CompactionRange,
        ModelRoute,
        SummaryNode,
    )

    segment = history[segment_start:segment_end]
    first_ts = segment[0].timestamp if segment else datetime.now()
    last_ts = segment[-1].timestamp if segment else datetime.now()
    time_range = f"{first_ts.strftime('%Y-%m-%d %H:%M')} ~ {last_ts.strftime('%Y-%m-%d %H:%M')}"

    # N5 事务身份
    tx_id_obj = CompactionId.generate()
    tx_id = tx_id_obj.value

    # N5 SurfaceReplacer 替换
    surface_replacer = get_surface_replacer(history, session_id)
    compaction_range = CompactionRange(
        start=segment_start,
        end=segment_end,
        start_idx=segment_start,
        end_idx=segment_end,
        shadowed_seqs=tuple(range(segment_start, segment_end)),
    )
    summary_node = SummaryNode(
        node_id=f"summary-{tx_id}",
        summary=summary_text,
        tx_id=tx_id_obj,
        model_route=ModelRoute(provider="internal", model="compaction", max_tokens=500),
        generated_at=datetime.now(),
    )
    replace_result = await surface_replacer.replace(session_id, compaction_range, summary_node)

    summary_msg = CompactionSummaryMessage(
        summary_text=summary_text,
        timestamp=datetime.now(),
        original_segment_count=len(segment),
        original_time_range=time_range,
        tx_id=tx_id,
        replace_generation=replace_result.new_generation,
    )

    compacted = [summary_msg] + list(history[segment_end:])
    return (compacted, tx_id, replace_result.new_generation)
