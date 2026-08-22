"""Maisaka 聊天回想消息。"""

from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha1
from html import escape
from math import sqrt
from typing import Any, Sequence
from json_repair import repair_json
from pydantic import BaseModel
import json
import re
import time


from src.common.data_models.message_component_data_model import DictComponent, MessageSequence
from src.common.data_models.embedding_service_data_models import EmbeddingResult
from src.common.logger import get_logger
from src.llm_models.model_requirement import model_requirement
from src.common.prompt_i18n import load_prompt
from src.core.app_config_port_registry import get_app_config_port
from src.llm_models.payload_content.message import (
    ImageMessagePart,
    Message,
    MessageBuilder,
    RoleType,
    TextMessagePart,
)
from src.maisaka.context.messages import (
    ComplexSessionMessage,
    LLMContextMessage,
    ReferenceMessage,
    ReferenceMessageType,
    build_llm_message_from_context,
)
from src.maisaka.display.prompt_cli_renderer import PromptCLIVisualizer
from src.maisaka.visual.message_limiter import limit_latest_images_in_messages

MID_TERM_MEMORY_COMPONENT_TYPE = "mid_term_memory"
MID_TERM_MEMORY_SOURCE_KIND = "mid_term_memory"
MID_TERM_MEMORY_COMPLEX_TYPE = "mid_term_memory"
MID_TERM_MEMORY_USER_NAME = "聊天回想"
MID_TERM_MEMORY_REFERENCE_MARKER = "【聊天回想-内部参考】"
MAX_SUMMARY_INPUT_CHARS = 16000
MID_TERM_MEMORY_RECALL_CONTEXT_MESSAGE_LIMIT = 12
MID_TERM_MEMORY_RECALL_CONTEXT_TEXT_LIMIT = 2400
MID_TERM_MEMORY_RECALL_SUMMARY_TEXT_LIMIT = 1400
MID_TERM_MEMORY_DEFAULT_RECALL_THRESHOLD = 0.8


@dataclass
class RecallConfig:
    """recall 可调参数（从 app_config 读取，每轮新建轻量对象）。"""
    threshold: float
    top_k: int
    candidate_limit: int
    original_message_limit: int
    original_token_limit: int
    timeout_ms: int


def _get_recall_config() -> RecallConfig:
    """从 app_config 读取 recall 可调参数（未配置用默认值 + info 日志）。

    spec 9.5 静默失效禁令：配置缺失用默认值 + info 日志（非静默用默认）。
    """
    config_port = get_app_config_port()
    return RecallConfig(
        threshold=config_port.get_recall_threshold(),
        top_k=config_port.get_recall_top_k(),
        candidate_limit=config_port.get_recall_candidate_limit(),
        original_message_limit=config_port.get_recall_original_message_limit(),
        original_token_limit=config_port.get_recall_original_token_limit(),
        timeout_ms=config_port.get_recall_timeout_ms(),
    )


logger = get_logger("maisaka_mid_term_memory")


@model_requirement(capabilities=["text_generation"], critical=False)
class MidTermMemory:
    """中期记忆委派声明（ZG-12）：mid_memory 任务能力声明。"""


class MidTermMemorySummaryModel(BaseModel):
    """聊天记录压缩摘要。"""

    summary: str
    recall_cues: list[str] = []


@dataclass(slots=True)
class MidTermMemoryBuildResult:
    """聊天回想消息构建结果。"""

    message: ComplexSessionMessage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_name: str = ""


@dataclass(frozen=True, slots=True)
class MidTermMemoryRecallCandidate:
    """一条聊天回想匹配段的召回候选。"""

    message: ComplexSessionMessage
    payload: dict[str, Any]
    segment_text: str
    score: float


def is_mid_term_memory_message(message: LLMContextMessage) -> bool:
    """判断上下文消息是否为聊天回想消息。"""

    return (
        isinstance(message, ComplexSessionMessage)
        and message.source_kind == MID_TERM_MEMORY_SOURCE_KIND
        and message.complex_message_type == MID_TERM_MEMORY_COMPLEX_TYPE
    )


def is_mid_term_memory_reference_message(message: LLMContextMessage) -> bool:
    """判断上下文消息是否为聊天回想召回参考。"""

    return (
        isinstance(message, ReferenceMessage)
        and message.reference_type == ReferenceMessageType.MEMORY
        and message.content.startswith(MID_TERM_MEMORY_REFERENCE_MARKER)
    )


async def build_mid_term_memory_message(
    removed_messages: Sequence[LLMContextMessage],
    *,
    session_id: str,
    log_prefix: str = "",
) -> MidTermMemoryBuildResult | None:
    """将被裁切的聊天历史总结成一条聊天回想消息。"""

    summary_source_messages = _select_summary_source_messages(removed_messages)
    if not summary_source_messages:
        logger.debug(f"{log_prefix} 聊天回想跳过: 裁切消息中没有可摘要文本")
        return None

    time_range = _build_time_range(summary_source_messages)
    participants = _collect_participants(summary_source_messages)
    instruction_prompt = _build_summary_instruction_prompt(
        time_range=time_range,
        participants=participants,
    )
    text_prompt_messages = _build_summary_prompt_messages(
        summary_source_messages,
        instruction_prompt=instruction_prompt,
        enable_visual_message=False,
    )
    if len(text_prompt_messages) <= 1:
        logger.debug(f"{log_prefix} 聊天回想跳过: 摘要输入消息为空")
        return None

    # logger.info(
    #     f"{log_prefix} 聊天回想完整 Prompt Messages: "
    #     f"裁切消息数={len(summary_source_messages)} "
    #     f"发送消息数={len(text_prompt_messages)} "
    #     f"时间范围={time_range} "
    #     f"参与人物={'、'.join(participants) if participants else '未知'} "
    #     f"prompt_chars={_count_prompt_message_chars(text_prompt_messages)}\n"
    #     f"{_render_summary_prompt_messages_for_log(text_prompt_messages)}"
    # )
    from src.core.adapters.llm_service_port import get_llm_service

    request_prompt_messages: list[Message] = []

    def message_factory(_client: Any, model_info: Any = None) -> list[Message]:
        nonlocal request_prompt_messages
        request_prompt_messages = _build_summary_prompt_messages(
            summary_source_messages,
            instruction_prompt=instruction_prompt,
            enable_visual_message=_should_enable_visual_summary(model_info),
        )
        return request_prompt_messages

    result = await get_llm_service().generate_response_with_messages(
        "mid_memory", message_factory,
        capabilities=("text_generation",),
        request_type="maisaka.mid_term_memory",
        session_id=session_id,
    )
    _save_mid_term_memory_prompt_preview(
        request_prompt_messages,
        result=result,
        session_id=session_id,
        time_range=time_range,
        participants=participants,
        log_prefix=log_prefix,
    )
    summary_payload = _parse_summary_response(result.response)
    if summary_payload is None:
        logger.warning(
            f"{log_prefix} 聊天回想解析失败，已跳过本次插入: response={_truncate(result.response, 300)}"
        )
        return None

    recall_cue_embeddings = await _build_recall_cue_embeddings(
        summary_payload.recall_cues,
        session_id=session_id,
    )
    message = build_mid_term_memory_complex_message(
        summary_payload,
        time_range=time_range,
        participants=participants,
        source_messages=summary_source_messages,
        recall_cue_embeddings=recall_cue_embeddings,
        session_id=session_id,  # ZH1-1a：传 session_id 构造指针
    )
    logger.info(
        f"{log_prefix} 聊天回想生成内容: "
        f"msg_id={message.message_id} "
        f"时间范围={time_range} "
        f"参与人物={'、'.join(participants) if participants else '未知'} "
        f"召回线索={len(recall_cue_embeddings)} 条\n"
        f"summary:\n{summary_payload.summary.strip()}"
    )
    return MidTermMemoryBuildResult(
        message=message,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        model_name=result.model_name or "",
    )


def _select_summary_source_messages(messages: Sequence[LLMContextMessage]) -> list[LLMContextMessage]:
    """筛选真正参与聊天回想生成的历史消息。"""

    return [
        message
        for message in messages
        if message.role == "user"
        and not is_mid_term_memory_message(message)
        and str(message.processed_plain_text or "").strip()
    ]


def build_mid_term_memory_complex_message(
    summary_payload: MidTermMemorySummaryModel,
    *,
    time_range: str,
    participants: Sequence[str],
    source_messages: Sequence[LLMContextMessage],
    recall_cue_embeddings: Sequence[dict[str, Any]] | None = None,
    session_id: str = "",  # ZH1-1a 新增：构造指针用
) -> ComplexSessionMessage:
    """基于摘要内容构造聊天回想上下文消息（含指针）。

    ZH1-1a：payload.data 新增 session_id + time_range_pointer 指针字段，
    用于持久化隔离 + ZH1-1b 翻原文定位。
    """

    timestamp = _resolve_summary_timestamp(source_messages)
    participants_text = "、".join(participants) if participants else "未知"
    message_id = _build_summary_message_id(
        timestamp=timestamp,
        time_range=time_range,
        participants=participants,
        summary=summary_payload.summary,
    )
    payload = {
        "type": MID_TERM_MEMORY_COMPONENT_TYPE,
        "data": {
            "time_range": time_range,
            "participants": list(participants),
            "summary": summary_payload.summary.strip(),
            "recall_cues": list(recall_cue_embeddings or []),
            # ZH1-1a 指针字段（spec 6.2 数据约束）
            "session_id": session_id,
            "time_range_pointer": time_range,
        },
    }
    preview_text = build_mid_term_memory_preview_text(payload["data"])
    planner_prefix = _build_summary_planner_prefix(
        timestamp=timestamp,
        message_id=message_id,
    )
    visible_text = "\n".join(
        [
            f"[{MID_TERM_MEMORY_USER_NAME}]",
            f"时间范围: {time_range}",
            f"参与人物: {participants_text}",
            f"summary: {summary_payload.summary.strip()}",
        ]
    )
    return ComplexSessionMessage(
        raw_message=MessageSequence([DictComponent(payload)]),
        visible_text=visible_text,
        timestamp=timestamp,
        message_id=message_id,
        source_kind=MID_TERM_MEMORY_SOURCE_KIND,
        prompt_text=f"{planner_prefix}{preview_text}",
        complex_message_type=MID_TERM_MEMORY_COMPLEX_TYPE,
    )


def build_mid_term_memory_message_from_record(
    record: Any,
) -> ComplexSessionMessage:
    """从持久化记录 reconstruct 聊天回想消息（方案 A 加载，design 4.4）。

    chat_loop_service 构建上下文时调用：从 mid_term_memory_summaries 表加载记录
    → reconstruct 为 ComplexSessionMessage → insert 到历史 → planner 可见。

    Args:
        record: MidTermMemorySummaries SQLModel 记录。

    Returns:
        ComplexSessionMessage — 与 build_mid_term_memory_complex_message 构造格式一致。
    """
    participants = json.loads(record.participants) if record.participants else []
    recall_cues = json.loads(record.recall_cues) if record.recall_cues else []
    payload = {
        "type": MID_TERM_MEMORY_COMPONENT_TYPE,
        "data": {
            "time_range": record.time_range,
            "participants": participants,
            "summary": record.summary,
            "recall_cues": recall_cues,
            "session_id": record.session_id,
            "time_range_pointer": record.time_range,
        },
    }
    preview_text = build_mid_term_memory_preview_text(payload["data"])
    planner_prefix = _build_summary_planner_prefix(
        timestamp=record.timestamp,
        message_id=record.summary_id,
    )
    participants_text = "、".join(participants) if participants else "未知"
    visible_text = "\n".join(
        [
            f"[{MID_TERM_MEMORY_USER_NAME}]",
            f"时间范围: {record.time_range}",
            f"参与人物: {participants_text}",
            f"summary: {record.summary}",
        ]
    )
    return ComplexSessionMessage(
        raw_message=MessageSequence([DictComponent(payload)]),
        visible_text=visible_text,
        timestamp=record.timestamp,
        message_id=record.summary_id,
        source_kind=MID_TERM_MEMORY_SOURCE_KIND,
        prompt_text=f"{planner_prefix}{preview_text}",
        complex_message_type=MID_TERM_MEMORY_COMPLEX_TYPE,
    )


async def insert_mid_term_memory_message(
    history: Sequence[LLMContextMessage],
    summary_message: ComplexSessionMessage,
    *,
    max_summary_count: int,
    session_id: str = "",  # ZH1-1a 新增：持久化用
) -> list[LLMContextMessage]:
    """将新的聊天回想插入到上一条聊天回想之后，并维护最大保留数量。

    ZH1-1a：先持久化到新表（mid_term_memory_summaries），持久化成功后才 insert 到历史。
    持久化失败不 insert（避免历史有摘要但数据库无记录，spec 4.2 可靠性规则 7）。
    """

    # ZH1-1a：先持久化到数据库（spec 4.2 可靠性规则 7）
    if session_id:
        from src.maisaka.memory.mid_term_persistence import get_mid_term_persistence

        persistence = get_mid_term_persistence()
        if persistence is not None:
            persist_ok = await persistence.persist_summary_to_db(summary_message, session_id)
            if not persist_ok:
                logger.warning(f"摘要持久化失败，跳过 insert 到历史: session_id={session_id}")
                return list(history)

    if max_summary_count <= 0:
        return [message for message in history if not is_mid_term_memory_message(message)]

    updated_history = list(history)
    insert_index = _find_last_mid_term_memory_index(updated_history)
    updated_history.insert(insert_index + 1, summary_message)
    _trim_mid_term_memory_messages(updated_history, max_summary_count=max_summary_count)
    return updated_history


def build_mid_term_memory_preview_text(payload: dict[str, Any]) -> str:
    """构造聊天回想在 Prompt 中未展开时可见的内容。"""

    time_range = str(payload.get("time_range") or "未知").strip()
    participants = _coerce_str_list(payload.get("participants"))
    summary = _resolve_payload_summary(payload) or "无"
    return "\n".join(
        [
            "[聊天回想]",
            f"时间范围: {time_range}",
            f"参与人物: {'、'.join(participants) if participants else '未知'}",
            f"summary: {summary}",
        ]
    )


def build_mid_term_memory_full_text(payload: dict[str, Any]) -> str:
    """构造聊天回想的完整内容。"""

    time_range = str(payload.get("time_range") or "未知").strip()
    participants = _coerce_str_list(payload.get("participants"))
    summary = _resolve_payload_summary(payload) or "无"
    recall_cues = _extract_recall_cue_texts(payload)
    recall_cue_lines = ["召回线索:"] + [f"- {cue}" for cue in recall_cues]
    return "\n".join(
        [
            "【聊天回想】",
            f"时间范围: {time_range}",
            f"参与人物: {'、'.join(participants) if participants else '未知'}",
            "",
            "summary:",
            summary,
            "",
            *(recall_cue_lines if recall_cues else []),
        ]
    ).strip()


async def build_mid_term_memory_reference_message(
    *,
    history: Sequence[LLMContextMessage],
    selected_history: Sequence[LLMContextMessage],
    session_id: str,
    existing_summary_ids: set[str] | None = None,
    log_prefix: str = "",
) -> list[ReferenceMessage]:
    """ZH1-1b：recall + 按需翻原文（Top-K + 双向去重 + 翻原文 + 观测点 + 超时降级）。

    spec 4.2 可靠性规则 1：失败降级返回空列表（不抛异常，不阻塞主流程）。
    spec 5.5.3 场景 2：超时降级返回已构造的 ReferenceMessage + warning。
    """
    if not get_app_config_port().get_chat_mid_term_memory():
        return []

    recall_config = _get_recall_config()
    start_time = time.monotonic()
    summary_ids = existing_summary_ids or set()

    query_text = _build_mid_term_memory_recall_query_text(selected_history)
    if not query_text:
        return []

    candidates = _collect_mid_term_memory_recall_candidates(
        session_id=session_id,
        candidate_limit=recall_config.candidate_limit,
    )
    if not candidates:
        _log_recall_observation(
            hit_count=0,
            appended_tokens=0,
            latency_ms=int((time.monotonic() - start_time) * 1000),
            threshold=recall_config.threshold,
            top_k=recall_config.top_k,
            session_id=session_id,
            hit_summaries=[],
            degradation={"stage": "候选源加载", "reason": "候选为空或加载失败"},
        )
        return []

    recalled_keys, recalled_segments = _collect_recalled_mid_term_memory_reference_identities(selected_history)
    candidates = [
        candidate
        for candidate in candidates
        if not _is_mid_term_memory_candidate_already_recalled(
            candidate,
            recalled_keys=recalled_keys,
            recalled_segments=recalled_segments,
            existing_summary_ids=summary_ids,
        )
    ]
    if not candidates:
        if recalled_keys or recalled_segments or summary_ids:
            logger.debug(f"{log_prefix} 当前上下文已包含全部匹配的聊天回想参考，跳过重复召回")
        return []

    from src.services.embedding_service import EmbeddingServiceClient

    embedding_client = EmbeddingServiceClient(
        capabilities=["embedding"],
        request_type="maisaka.mid_term_memory_recall",
        session_id=session_id,
    )
    try:
        query_result = await embedding_client.embed_text(query_text, session_id=session_id)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, f"{log_prefix} query embedding 失败，recall 降级", exception=exc)
        logger.warning(f"{log_prefix} query embedding 失败，recall 降级: {exc}")
        _log_recall_observation(
            hit_count=0,
            appended_tokens=0,
            latency_ms=int((time.monotonic() - start_time) * 1000),
            threshold=recall_config.threshold,
            top_k=recall_config.top_k,
            session_id=session_id,
            hit_summaries=[],
            degradation={"stage": "query embedding", "reason": str(exc)},
        )
        return []

    hit_candidates = _select_top_k_recall_candidates(
        candidates,
        query_embedding=query_result.embedding,
        threshold=recall_config.threshold,
        top_k=recall_config.top_k,
    )
    if not hit_candidates:
        logger.debug(f"{log_prefix} 聊天回想召回未命中阈值")
        return []

    references: list[ReferenceMessage] = []
    total_appended_tokens = 0
    for candidate in hit_candidates:
        original_text = _fetch_original_messages_for_candidate(
            candidate,
            session_id=session_id,
            message_limit=recall_config.original_message_limit,
            token_limit=recall_config.original_token_limit,
        )
        content = _format_mid_term_memory_reference(candidate, original_messages_text=original_text)
        reference = ReferenceMessage(
            content=content,
            timestamp=datetime.now(),
            reference_type=ReferenceMessageType.MEMORY,
            remaining_uses_value=None,
            display_prefix="[参考消息]",
        )
        references.append(reference)
        total_appended_tokens += len(content) // 2

    latency_ms = int((time.monotonic() - start_time) * 1000)
    _log_recall_observation(
        hit_count=len(hit_candidates),
        appended_tokens=total_appended_tokens,
        latency_ms=latency_ms,
        threshold=recall_config.threshold,
        top_k=recall_config.top_k,
        session_id=session_id,
        hit_summaries=[
            {
                "summary_id": c.message.message_id,
                "score": c.score,
                "time_range": str(c.payload.get("time_range", "")),
            }
            for c in hit_candidates
        ],
    )
    if latency_ms > recall_config.timeout_ms:
        logger.warning(
            f"{log_prefix} recall 超时: latency_ms={latency_ms} timeout_ms={recall_config.timeout_ms}"
        )
    return references


def _find_last_mid_term_memory_index(history: Sequence[LLMContextMessage]) -> int:
    last_index = -1
    for index, message in enumerate(history):
        if is_mid_term_memory_message(message):
            last_index = index
    return last_index


def _trim_mid_term_memory_messages(
    history: list[LLMContextMessage],
    *,
    max_summary_count: int,
) -> None:
    summary_indexes = [index for index, message in enumerate(history) if is_mid_term_memory_message(message)]
    excess_count = len(summary_indexes) - max_summary_count
    if excess_count <= 0:
        return

    for index in reversed(summary_indexes[:excess_count]):
        del history[index]


def _build_summary_instruction_prompt(
    *,
    time_range: str,
    participants: Sequence[str],
) -> str:
    participants_text = "、".join(participants) if participants else "未知"
    return load_prompt(
        "mid_term_memory_summary",
        time_range=time_range,
        participants_text=participants_text,
    )


def _build_summary_prompt_messages(
    source_messages: Sequence[LLMContextMessage],
    *,
    instruction_prompt: str,
    enable_visual_message: bool = False,
) -> list[Message]:
    prompt_messages = [MessageBuilder().set_role(RoleType.System).add_text_content(instruction_prompt).build()]
    total_source_chars = 0
    for source_message in source_messages:
        llm_message = build_llm_message_from_context(
            source_message,
            enable_visual_message=enable_visual_message,
        )
        if llm_message is None:
            continue

        message_text = llm_message.get_text_content().strip()
        if not message_text and not _message_has_visual_content(llm_message):
            continue

        remaining_chars = MAX_SUMMARY_INPUT_CHARS - total_source_chars
        if remaining_chars <= 0:
            break
        if len(message_text) > remaining_chars:
            llm_message = _truncate_message_text(llm_message, remaining_chars)
            prompt_messages.append(llm_message)
            break

        prompt_messages.append(llm_message)
        total_source_chars += len(message_text)

    if enable_visual_message:
        return limit_latest_images_in_messages(
            prompt_messages,
                max_image_num=get_app_config_port().get_visual_max_image_num(),
        )
    return prompt_messages


def _save_mid_term_memory_prompt_preview(
    request_prompt_messages: Sequence[Message],
    *,
    result: Any,
    session_id: str,
    time_range: str,
    participants: Sequence[str],
    log_prefix: str,
) -> None:
    """保存聊天回想生成 Prompt 到 Maisaka Prompt 预览目录。"""

    if not get_app_config_port().get_debug_show_maisaka_thinking():
        return
    if not request_prompt_messages:
        return

    participants_text = "、".join(participants) if participants else "未知"
    selection_reason = (
        f"会话ID: {session_id or 'unknown'}\n"
        f"时间范围: {time_range}\n"
        f"参与人物: {participants_text}\n"
        f"构建消息数: {len(request_prompt_messages)}\n"
        f"请求模型: {str(getattr(result, 'model_name', '') or 'unknown')}\n"
        f"Token: prompt={int(getattr(result, 'prompt_tokens', 0) or 0)} "
        f"completion={int(getattr(result, 'completion_tokens', 0) or 0)} "
        f"total={int(getattr(result, 'total_tokens', 0) or 0)}"
    )
    try:
        PromptCLIVisualizer.build_prompt_preview_access(
            list(request_prompt_messages),
            category="mid_term_memory",
            chat_id=session_id or "unknown",
            request_kind="mid_term_memory",
            selection_reason=selection_reason,
            output_content=str(getattr(result, "response", "")),
            output_title="聊天回想生成结果",
            metadata={
                "model_name": str(getattr(result, "model_name", "")),
            },
        )
        logger.debug(f"{log_prefix} 聊天回想生成 Prompt 预览已保存")
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "聊天回想生成 Prompt 预览保存失败，已跳过", exception=exc)
        logger.warning(f"{log_prefix} 聊天回想生成 Prompt 预览保存失败，已跳过: {exc}")


def _count_prompt_message_chars(messages: Sequence[Message]) -> int:
    return sum(len(message.get_text_content()) for message in messages)


def _should_enable_visual_summary(model_info: Any) -> bool:
    return bool(getattr(model_info, "visual", False))


def _message_has_visual_content(message: Message) -> bool:
    return any(isinstance(part, ImageMessagePart) for part in message.parts)


def _truncate_message_text(message: Message, max_text_chars: int) -> Message:
    remaining_chars = max(0, int(max_text_chars))
    truncated_parts = []
    for part in message.parts:
        if isinstance(part, TextMessagePart):
            if remaining_chars <= 0:
                continue

            truncated_text = part.text[:remaining_chars]
            if truncated_text:
                truncated_parts.append(TextMessagePart(truncated_text))
                remaining_chars -= len(truncated_text)
            continue

        truncated_parts.append(part)

    if not truncated_parts:
        return (
            MessageBuilder()
            .set_role(message.role)
            .add_text_content(message.get_text_content()[:max_text_chars])
            .build()
        )
    return Message(
        role=message.role,
        parts=truncated_parts,
        tool_call_id=message.tool_call_id,
        tool_name=message.tool_name,
        tool_calls=message.tool_calls,
        reasoning_content=message.reasoning_content,
    )


def _render_summary_prompt_messages_for_log(messages: Sequence[Message]) -> str:
    rendered_messages: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = message.role.value if hasattr(message.role, "value") else str(message.role)
        rendered_messages.append(f"[{index}][{role}]\n{message.get_text_content()}")
    return "\n\n".join(rendered_messages).strip()


def _build_summary_planner_prefix(
    *,
    timestamp: datetime,
    message_id: str,
) -> str:
    return (
        f'<message msg_id="{escape(message_id, quote=True)}" '
        f'time="{escape(timestamp.strftime("%H:%M:%S"), quote=True)}">\n'
    )


def _build_time_range(messages: Sequence[LLMContextMessage]) -> str:
    timestamps = [message.timestamp for message in messages]
    if not timestamps:
        return "未知"

    start_time = min(timestamps)
    end_time = max(timestamps)
    return f"{start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%Y-%m-%d %H:%M:%S')}"


def _collect_participants(messages: Sequence[LLMContextMessage]) -> list[str]:
    participants: list[str] = []
    seen: set[str] = set()
    for message in messages:
        participant = _resolve_participant_name(message)
        if not participant or participant in seen:
            continue
        seen.add(participant)
        participants.append(participant)
    return participants


def _resolve_participant_name(message: LLMContextMessage) -> str:
    original_message = getattr(message, "original_message", None)
    message_info = getattr(original_message, "message_info", None)
    user_info = getattr(message_info, "user_info", None)
    if user_info is not None:
        user_name = (
            getattr(user_info, "user_cardname", None)
            or getattr(user_info, "user_nickname", None)
            or getattr(user_info, "user_id", None)
        )
        if str(user_name or "").strip():
            return str(user_name).strip()

    if message.role == "assistant":
        return "麦麦"
    if isinstance(message, ComplexSessionMessage) and message.source_kind == "optimized_tool_history":
        return "历史工具调用"
    return str(message.source or "").strip()


def _parse_summary_response(response: str) -> MidTermMemorySummaryModel | None:
    payload = _load_json_payload(response)
    if not isinstance(payload, dict):
        return None

    summary = _resolve_payload_summary(payload)
    recall_cues = _normalize_recall_cues(payload.get("recall_cues") or payload.get("match_segments"))
    if not summary:
        return None
    return MidTermMemorySummaryModel(
        summary=summary,
        recall_cues=recall_cues,
    )


def _load_json_payload(response: str) -> Any:
    normalized_response = str(response or "").strip()
    if not normalized_response:
        return None

    candidates = [normalized_response]
    if fence_match := re.search(r"```(?:json)?\s*(.*?)\s*```", normalized_response, flags=re.S | re.I):
        candidates.append(fence_match.group(1).strip())

    object_start = normalized_response.find("{")
    object_end = normalized_response.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(normalized_response[object_start : object_end + 1])

    seen_candidates: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)
        parsed_payload = _parse_json_candidate(candidate)
        if isinstance(parsed_payload, dict):
            return parsed_payload

    return None


def _parse_json_candidate(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        # P0-5: JSON 解析失败出声（debug 防刷屏，尝试 repair_json）（ZG-31）
        logger.debug("json.loads 失败，尝试 repair_json: %s", exc)

    try:
        return repair_json(candidate, return_objects=True, logging=False)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "解析 JSON 候选失败", exception=exc)
        logger.warning("操作异常 in mid_term.py", exc_info=True)


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized_values: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized_values.append(text)
    return normalized_values


async def _build_recall_cue_embeddings(
    recall_cues: Sequence[str],
    *,
    session_id: str,
) -> list[dict[str, Any]]:
    normalized_cues = _normalize_recall_cues(list(recall_cues))
    if not normalized_cues:
        return []

    from src.services.embedding_service import EmbeddingServiceClient

    embedding_client = EmbeddingServiceClient(
        capabilities=["embedding"],
        request_type="maisaka.mid_term_memory_recall_cue",
        session_id=session_id,
    )
    embedding_results = await embedding_client.embed_texts(
        normalized_cues,
        max_concurrent=2,
        session_id=session_id,
    )
    return [
        _build_recall_cue_payload(cue, embedding_result)
        for cue, embedding_result in zip(normalized_cues, embedding_results, strict=True)
    ]


def _build_recall_cue_payload(cue: str, embedding_result: EmbeddingResult) -> dict[str, Any]:
    return {
        "text": cue,
        "embedding": [float(value) for value in embedding_result.embedding],
        "model_name": embedding_result.model_name,
    }


def _normalize_recall_cues(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_cues = re.split(r"\n+", value)
    elif isinstance(value, list):
        raw_cues = value
    else:
        raw_cues = []

    cues: list[str] = []
    seen: set[str] = set()
    for raw_cue in raw_cues:
        cue = _normalize_recall_cue_text(raw_cue)
        if not cue or cue in seen:
            continue
        seen.add(cue)
        cues.append(cue)
    return cues[:5]


def _normalize_recall_cue_text(value: Any) -> str:
    if isinstance(value, dict):
        text = value.get("text") or value.get("query") or value.get("content") or ""
        associations = _coerce_str_list(value.get("associations"))
        reason = str(value.get("reason")).strip()
        parts = [str(text or "").strip()]
        if associations:
            parts.append(f"关联: {'、'.join(associations)}")
        if reason:
            parts.append(f"原因: {reason}")
        return "；".join(part for part in parts if part)
    return " ".join(str(value or "").split()).strip()


def _get_mid_term_memory_payload(message: LLMContextMessage) -> dict[str, Any]:
    if not is_mid_term_memory_message(message):
        return {}

    raw_message = getattr(message, "raw_message", None)
    for component in getattr(raw_message, "components", []) or []:
        if not isinstance(component, DictComponent) or not isinstance(component.data, dict):
            continue
        raw_type = str(component.data.get("type")).strip()
        if raw_type != MID_TERM_MEMORY_COMPONENT_TYPE:
            continue
        payload = component.data.get("data", {})
        return payload if isinstance(payload, dict) else {}
    return {}


def _resolve_payload_summary(payload: dict[str, Any]) -> str:
    return str(
        payload.get("summary")
        or payload.get("long_summary")
        or payload.get("brief")
        or ""
    ).strip()


def _extract_recall_cue_texts(payload: dict[str, Any]) -> list[str]:
    return _normalize_recall_cues(payload.get("recall_cues") or payload.get("match_segments"))


def _build_payload_from_record(record: Any) -> dict[str, Any]:
    """从持久化记录构造 payload（对齐 ComplexSessionMessage payload 结构）。

    供候选收集 + 翻原文用（含 session_id + time_range_pointer 指针字段）。
    """
    return {
        "type": MID_TERM_MEMORY_COMPONENT_TYPE,
        "data": {
            "time_range": record.time_range,
            "participants": json.loads(record.participants) if record.participants else [],
            "summary": record.summary,
            "recall_cues": json.loads(record.recall_cues) if record.recall_cues else [],
            "recall_cue_embeddings": json.loads(record.recall_cue_embeddings) if record.recall_cue_embeddings else [],
            "session_id": record.session_id,
            "time_range_pointer": record.time_range,
            "summary_id": record.summary_id,
        },
    }


def _build_candidate_from_record(record: Any) -> list[MidTermMemoryRecallCandidate]:
    """从持久化记录构造候选（反序列化 recall_cue_embeddings，embedding 缺失跳过）。

    spec 5.1.1 规则 4：embedding 缺失的 cue 跳过不参与匹配。
    """
    full_payload = _build_payload_from_record(record)
    # candidate.payload 用内层 data dict（供 _iter_recall_cue_payloads / _format 直接读取）
    payload = full_payload["data"]
    virtual_message = build_mid_term_memory_message_from_record(record)
    candidates: list[MidTermMemoryRecallCandidate] = []
    for cue_payload in _iter_recall_cue_payloads(payload):
        if not isinstance(cue_payload, dict):
            continue
        segment_text = str(cue_payload.get("text", "")).strip()
        embedding = cue_payload.get("embedding")
        if not segment_text or not isinstance(embedding, list) or not embedding:
            continue
        candidates.append(MidTermMemoryRecallCandidate(
            message=virtual_message,
            payload=payload,
            segment_text=segment_text,
            score=0.0,
        ))
    return candidates


def _collect_mid_term_memory_recall_candidates(
    *,
    session_id: str,
    candidate_limit: int,
) -> list[MidTermMemoryRecallCandidate]:
    """从持久化表加载候选源（session_id 过滤 + 条数上限 + 失败降级）。

    ZH1-1b：候选源改从持久化表 load_summaries_by_session 加载，
    非旧实现的 history 参数收集（spec 5.1.1 规则 1）。
    """
    try:
        from src.maisaka.memory.mid_term_persistence import get_mid_term_persistence

        persistence = get_mid_term_persistence()
        if persistence is None:
            logger.warning("持久化服务未初始化，候选源加载跳过")
            return []
        records = persistence.load_summaries_by_session(session_id, limit=candidate_limit)
        candidates: list[MidTermMemoryRecallCandidate] = []
        for record in records:
            candidates.extend(_build_candidate_from_record(record))
        return candidates
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "候选源加载失败，降级返回空列表", exception=exc)
        logger.warning(f"候选源加载失败，降级返回空列表: {exc}")
        return []


def _iter_recall_cue_payloads(payload: dict[str, Any]) -> list[Any]:
    recall_cues = payload.get("recall_cues")
    if isinstance(recall_cues, list) and recall_cues:
        return recall_cues
    match_segments = payload.get("match_segments")
    return match_segments if isinstance(match_segments, list) else []


def _collect_recalled_mid_term_memory_reference_identities(
    messages: Sequence[LLMContextMessage],
) -> tuple[set[tuple[str, str]], set[str]]:
    recalled_keys: set[tuple[str, str]] = set()
    recalled_segments: set[str] = set()
    for message in messages:
        if not is_mid_term_memory_reference_message(message):
            continue

        message_id = _extract_labeled_reference_value(message.content, "摘要ID")
        segment_text = _extract_labeled_reference_value(message.content, "匹配段")
        normalized_segment = _normalize_reference_identity_text(segment_text)
        if not normalized_segment:
            continue

        recalled_segments.add(normalized_segment)
        normalized_message_id = _normalize_reference_identity_text(message_id)
        if normalized_message_id:
            recalled_keys.add((normalized_message_id, normalized_segment))
    return recalled_keys, recalled_segments


def _is_mid_term_memory_candidate_already_recalled(
    candidate: MidTermMemoryRecallCandidate,
    *,
    recalled_keys: set[tuple[str, str]],
    recalled_segments: set[str],
    existing_summary_ids: set[str] | None = None,
) -> bool:
    """双向去重：方向 1 排除已加载摘要（summary_id），方向 2 排除已 recall 原文。

    spec 5.4.1 规则 1：已加载摘要不 recall（summary_id 在 existing_summary_ids 中）。
    spec 5.4.1 规则 3：已 recall 原文不重复 append（(message_id, segment) 在 recalled_keys 中）。
    """
    summary_id = _normalize_reference_identity_text(candidate.message.message_id)
    if summary_id and existing_summary_ids and summary_id in existing_summary_ids:
        return True
    normalized_segment = _normalize_reference_identity_text(candidate.segment_text)
    if not normalized_segment:
        return False
    message_id = _normalize_reference_identity_text(candidate.message.message_id)
    if message_id and (message_id, normalized_segment) in recalled_keys:
        return True
    return normalized_segment in recalled_segments


def _extract_labeled_reference_value(content: str, label: str) -> str:
    prefix = f"{label}:"
    for line in str(content or "").splitlines():
        normalized_line = line.strip()
        if normalized_line.startswith(prefix):
            return normalized_line.removeprefix(prefix).strip()
    return ""


def _normalize_reference_identity_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _select_best_recall_candidate(
    candidates: Sequence[MidTermMemoryRecallCandidate],
    *,
    query_embedding: Sequence[float],
    threshold: float,
) -> MidTermMemoryRecallCandidate | None:
    best_candidate: MidTermMemoryRecallCandidate | None = None
    for candidate in candidates:
        segment_embedding = _get_candidate_embedding(candidate.payload, candidate.segment_text)
        if not segment_embedding:
            continue
        score = _cosine_similarity(query_embedding, segment_embedding)
        scored_candidate = MidTermMemoryRecallCandidate(
            message=candidate.message,
            payload=candidate.payload,
            segment_text=candidate.segment_text,
            score=score,
        )
        if best_candidate is None or scored_candidate.score > best_candidate.score:
            best_candidate = scored_candidate

    if best_candidate is None or best_candidate.score <= threshold:
        return None
    return best_candidate


def _select_top_k_recall_candidates(
    candidates: Sequence[MidTermMemoryRecallCandidate],
    *,
    query_embedding: Sequence[float],
    threshold: float,
    top_k: int,
) -> list[MidTermMemoryRecallCandidate]:
    """Top-K 匹配（遍历候选计算余弦相似度 → 筛选分数 > 阈值 → 按分数降序取 Top-K）。

    spec 5.2.1 规则 5：Top-K 召回（K=3 起步可配置）。
    spec 5.2.1 规则 9：匹配分数保留 2 位小数（避免每轮抖动）。
    spec 5.2.1 规则 11：严格分数 > 阈值（非 ≥）。
    spec 4.5 兼容性规则 3：K=1 退化为旧 Top-1 行为。
    """
    scored: list[tuple[float, MidTermMemoryRecallCandidate]] = []
    for candidate in candidates:
        segment_embedding = _get_candidate_embedding(candidate.payload, candidate.segment_text)
        if not segment_embedding:
            continue
        try:
            score = _cosine_similarity(query_embedding, segment_embedding)
        except ValueError:
            logger.warning(f"候选 embedding 维度不一致，跳过: {candidate.segment_text[:50]}")
            continue
        score = round(score, 2)
        scored_candidate = replace(candidate, score=score)
        scored.append((score, scored_candidate))
    hit = [(s, c) for s, c in scored if s > threshold]
    hit.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in hit[:top_k]]


def _parse_candidate_pointer(
    candidate: MidTermMemoryRecallCandidate,
) -> tuple[str, float, float] | None:
    """解析候选指针（session_id + time_range → start_time + end_time epoch）。

    spec 5.3.1 规则 2：从 candidate.payload 解析 session_id + time_range_pointer。
    spec 5.3.3 场景 1：指针缺失返回 None（调用方降级跳过）。
    """
    data = candidate.payload
    if not isinstance(data, dict):
        return None
    session_id = str(data.get("session_id") or "").strip()
    time_range = str(data.get("time_range_pointer") or data.get("time_range") or "").strip()
    if not session_id or not time_range or time_range == "未知":
        return None

    parts = time_range.split("~")
    if len(parts) != 2:
        return None
    try:
        start_time = datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M:%S").timestamp()
        end_time = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None
    return session_id, start_time, end_time


def _truncate_original_messages(
    text: str,
    token_limit: int,
) -> str:
    """估算 token 数（1 token ≈ 2 字符），超限截断保留首尾（首部 40% + 省略号 + 尾部 40%）。

    spec 5.3.1 规则 5：原文 token 硬上限截断。
    spec 5.3.1 规则 6：截断保留首尾，不丢失上下文边界信息。
    spec 5.6.1 规则 8：截断日志含原 token + 截断后 token。
    """
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return ""
    char_limit = token_limit * 2
    if len(normalized_text) <= char_limit:
        return normalized_text

    original_tokens = len(normalized_text) // 2
    head_size = int(char_limit * 0.4)
    tail_size = char_limit - head_size
    truncated_text = normalized_text[:head_size] + "\n...(原文过长，已截断中间部分)...\n" + normalized_text[-tail_size:]
    truncated_tokens = len(truncated_text) // 2
    logger.info(f"recall 截断: original_tokens={original_tokens} truncated_tokens={truncated_tokens}")
    return truncated_text


def _fetch_original_messages_for_candidate(
    candidate: MidTermMemoryRecallCandidate,
    *,
    session_id: str,
    message_limit: int,
    token_limit: int,
) -> str:
    """按需翻原文：解析指针 → find_messages 拉原始消息 → 拼接文本 → 截断。

    spec 5.3.1 规则 3：find_messages(session_id, start_time, end_time, limit=20)。
    spec 5.3.1 规则 4：原文条数上限（limit_mode="latest" 取最近 N 条）。
    spec 5.3.3 场景 1：指针缺失返回空字符串 + warning。
    spec 5.3.3 场景 3：时间范围内无消息返回空字符串。
    spec 5.3.3 场景 5：raw_content 反序列化失败跳过该条 + warning。
    """
    pointer = _parse_candidate_pointer(candidate)
    if pointer is None:
        logger.warning(
            f"翻原文跳过: 候选无有效指针, summary_id={candidate.message.message_id} session_id={session_id}"
        )
        return ""
    pointer_session_id, start_time, end_time = pointer
    try:
        from src.common.message_repository import find_messages

        messages = find_messages(
            session_id=pointer_session_id,
            start_time=start_time,
            end_time=end_time,
            limit=message_limit,
            limit_mode="latest",
        )
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, f"翻原文失败: find_messages 异常, session_id={pointer_session_id}", exception=exc)
        logger.warning(f"翻原文失败: find_messages 异常, session_id={pointer_session_id}: {exc}")
        return ""
    if not messages:
        return ""

    lines: list[str] = []
    for message in messages:
        try:
            sender = "未知"
            user_info = getattr(getattr(message, "message_info", None), "user_info", None)
            if user_info is not None:
                sender = user_info.user_nickname or user_info.user_id or "未知"
            text = str(getattr(message, "processed_plain_text", "") or "").strip()
            if not text:
                continue
            timestamp_text = message.timestamp.strftime("%H:%M:%S")
            lines.append(f"[{timestamp_text}] {sender}: {text}")
        except Exception as exc:
            logger.warning(f"翻原文跳过单条: raw_content 反序列化失败: {exc}")
            continue
    if not lines:
        return ""
    return _truncate_original_messages("\n".join(lines), token_limit)


def _get_candidate_embedding(payload: dict[str, Any], segment_text: str) -> list[float]:
    for cue_payload in _iter_recall_cue_payloads(payload):
        if not isinstance(cue_payload, dict):
            continue
        if str(cue_payload.get("text")).strip() != segment_text:
            continue
        embedding = cue_payload.get("embedding")
        if not isinstance(embedding, list):
            return []
        return [float(value) for value in embedding]
    return []


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError(f"聊天回想召回 embedding 维度不一致: query={len(left)} segment={len(right)}")
    if not left:
        return 0.0

    dot_product = sum(
        float(left_value) * float(right_value)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_norm = sqrt(sum(float(value) * float(value) for value in left))
    right_norm = sqrt(sum(float(value) * float(value) for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _build_mid_term_memory_recall_query_text(selected_history: Sequence[LLMContextMessage]) -> str:
    query_items: list[str] = []
    for message in selected_history:
        if is_mid_term_memory_message(message) or is_mid_term_memory_reference_message(message):
            continue
        if isinstance(message, ReferenceMessage):
            continue

        text = " ".join(str(message.processed_plain_text or "").split()).strip()
        if not text:
            continue
        if len(text) > 360:
            text = text[-360:].strip()
        query_items.append(text)

    query_text = "\n".join(query_items[-MID_TERM_MEMORY_RECALL_CONTEXT_MESSAGE_LIMIT:])
    if len(query_text) <= MID_TERM_MEMORY_RECALL_CONTEXT_TEXT_LIMIT:
        return query_text
    return query_text[-MID_TERM_MEMORY_RECALL_CONTEXT_TEXT_LIMIT:]


def _format_mid_term_memory_reference(
    candidate: MidTermMemoryRecallCandidate,
    *,
    original_messages_text: str = "",
) -> str:
    payload = candidate.payload
    message_id = str(candidate.message.message_id or "").strip()
    time_range = str(payload.get("time_range") or "未知").strip()
    participants = _coerce_str_list(payload.get("participants"))
    summary = _resolve_payload_summary(payload) or "无"
    if len(summary) > MID_TERM_MEMORY_RECALL_SUMMARY_TEXT_LIMIT:
        summary = summary[:MID_TERM_MEMORY_RECALL_SUMMARY_TEXT_LIMIT].rstrip() + "..."

    lines = [
        MID_TERM_MEMORY_REFERENCE_MARKER,
        "以下是根据当前上下文匹配到的一条聊天回想，只作为内部参考；仅在自然相关时使用，不要生硬复述。",
        *([f"摘要ID: {message_id}"] if message_id else []),
        f"匹配分数: {candidate.score:.2f}",
        f"匹配段: {candidate.segment_text}",
        f"时间范围: {time_range}",
        f"参与人物: {'、'.join(participants) if participants else '未知'}",
        "",
        "summary:",
        summary,
    ]
    # 原始消息段（spec 5.3.1 规则 8：翻原文后追加；时间范围内无消息时跳过）
    if original_messages_text:
        lines.extend(["", "---", "原始消息:", original_messages_text])
    return "\n".join(lines).strip()


def _log_recall_observation(
    *,
    hit_count: int,
    appended_tokens: int,
    latency_ms: int,
    threshold: float,
    top_k: int,
    session_id: str,
    hit_summaries: list[dict[str, Any]],
    truncation: dict[str, int] | None = None,
    degradation: dict[str, str] | None = None,
) -> None:
    """输出 recall 观测日志（固定字段，不泄露原始消息全文）。

    spec 5.6.1 规则 1-5：固定观测字段——命中数 + token 数 + 耗时 + 阈值 + Top-K。
    spec 5.6.1 规则 6：降级日志含环节 + 原因 + session_id。
    spec 5.6.1 规则 7：命中摘要日志含 summary_id + score + time_range。
    spec 5.6.1 规则 8：截断日志含原 token + 截断后 token。
    spec 5.6.1 规则 9：不泄露原始消息全文（仅含统计字段）。
    spec 5.6.3 场景 1：日志失败跳过不影响主流程。
    """
    try:
        logger.info(
            f"recall 观测: "
            f"recall_hit_count={hit_count} "
            f"recall_appended_tokens={appended_tokens} "
            f"recall_latency_ms={latency_ms} "
            f"recall_threshold={threshold} "
            f"recall_top_k={top_k} "
            f"recall_session_id={session_id}"
        )
        for hit in hit_summaries:
            logger.info(
                f"recall 命中: "
                f"summary_id={hit.get('summary_id', '')} "
                f"score={hit.get('score', 0.0)} "
                f"time_range={hit.get('time_range', '')}"
            )
        if truncation is not None:
            logger.info(
                f"recall 截断: "
                f"original_tokens={truncation.get('original_tokens', 0)} "
                f"truncated_tokens={truncation.get('truncated_tokens', 0)}"
            )
        if degradation is not None:
            logger.warning(
                f"recall 降级: "
                f"stage={degradation.get('stage', '')} "
                f"reason={degradation.get('reason', '')} "
                f"session_id={session_id}"
            )
    except Exception as exc:
        logger.debug(f"recall 观测日志写入失败，跳过: {exc}")


def _resolve_summary_timestamp(messages: Sequence[LLMContextMessage]) -> datetime:
    timestamps = [message.timestamp for message in messages]
    if not timestamps:
        return datetime.now()
    return max(timestamps)


def _build_summary_message_id(
    *,
    timestamp: datetime,
    time_range: str,
    participants: Sequence[str],
    summary: str,
) -> str:
    digest_source = "\n".join([time_range, "、".join(participants), summary])
    digest = sha1(digest_source.encode("utf-8")).hexdigest()[:8]
    return f"mtm:{_to_base36(int(timestamp.timestamp() * 1000))}:{digest}"


def _to_base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    normalized_value = max(0, int(value))
    if normalized_value == 0:
        return "0"

    digits: list[str] = []
    while normalized_value:
        normalized_value, remainder = divmod(normalized_value, 36)
        digits.append(alphabet[remainder])
    return "".join(reversed(digits))


def _truncate(text: str, max_length: int) -> str:
    normalized_text = str(text or "").strip()
    if len(normalized_text) <= max_length:
        return normalized_text
    return normalized_text[:max_length] + "..."
