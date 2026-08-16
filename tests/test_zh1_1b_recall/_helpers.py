"""ZH1-1b recall 测试公共工厂 — 构造 mock 对象 + 持久化记录 + 候选。"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.maisaka.context.messages import (
    ComplexSessionMessage,
    ReferenceMessage,
    ReferenceMessageType,
)
from src.maisaka.memory.mid_term import (
    MID_TERM_MEMORY_COMPONENT_TYPE,
    MID_TERM_MEMORY_COMPLEX_TYPE,
    MID_TERM_MEMORY_REFERENCE_MARKER,
    MID_TERM_MEMORY_SOURCE_KIND,
    MidTermMemoryRecallCandidate,
    RecallConfig,
)
from src.common.data_models.message_component_data_model import DictComponent, MessageSequence


def make_mock_app_config_port(
    *,
    chat_mid_term_memory: bool = True,
    recall_threshold: float = 0.65,
    recall_top_k: int = 3,
    recall_candidate_limit: int = 100,
    recall_original_message_limit: int = 20,
    recall_original_token_limit: int = 2000,
    recall_timeout_ms: int = 1000,
    debug_show_maisaka_thinking: bool = False,
    visual_max_image_num: int = 0,
) -> MagicMock:
    """构造 mock AppConfigPort（含 recall 全部 getter）。"""
    port = MagicMock()
    port.get_chat_mid_term_memory.return_value = chat_mid_term_memory
    port.get_recall_threshold.return_value = recall_threshold
    port.get_recall_top_k.return_value = recall_top_k
    port.get_recall_candidate_limit.return_value = recall_candidate_limit
    port.get_recall_original_message_limit.return_value = recall_original_message_limit
    port.get_recall_original_token_limit.return_value = recall_original_token_limit
    port.get_recall_timeout_ms.return_value = recall_timeout_ms
    port.get_debug_show_maisaka_thinking.return_value = debug_show_maisaka_thinking
    port.get_visual_max_image_num.return_value = visual_max_image_num
    return port


def make_recall_config(
    *,
    threshold: float = 0.65,
    top_k: int = 3,
    candidate_limit: int = 100,
    original_message_limit: int = 20,
    original_token_limit: int = 2000,
    timeout_ms: int = 1000,
) -> RecallConfig:
    return RecallConfig(
        threshold=threshold,
        top_k=top_k,
        candidate_limit=candidate_limit,
        original_message_limit=original_message_limit,
        original_token_limit=original_token_limit,
        timeout_ms=timeout_ms,
    )


def make_summary_record(
    *,
    summary_id: str = "mtm:abc:test1",
    session_id: str = "group:12345",
    time_range: str = "2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
    participants: list[str] | None = None,
    summary: str = "讨论了天气",
    recall_cues: list[dict] | None = None,
    recall_cue_embeddings: list[dict] | None = None,
    timestamp: datetime | None = None,
) -> SimpleNamespace:
    """构造 mock MidTermMemorySummaries 记录。

    recall_cues: list[dict]，每条含 text + embedding + model_name（持久化格式）。
    """
    if participants is None:
        participants = ["alice", "bob"]
    if recall_cues is None:
        recall_cues = [{"text": "天气", "embedding": [0.1, 0.2, 0.3], "model_name": "test-embed"}]
    if recall_cue_embeddings is None:
        recall_cue_embeddings = []
    if timestamp is None:
        timestamp = datetime(2024, 1, 1, 10, 30, 0)
    return SimpleNamespace(
        summary_id=summary_id,
        session_id=session_id,
        time_range=time_range,
        participants=json.dumps(participants, ensure_ascii=False),
        summary=summary,
        recall_cues=json.dumps(recall_cues, ensure_ascii=False),
        recall_cue_embeddings=json.dumps(recall_cue_embeddings, ensure_ascii=False),
        timestamp=timestamp,
    )


def make_mid_term_complex_message(
    *,
    message_id: str = "mtm:abc:test1",
    time_range: str = "2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
    participants: list[str] | None = None,
    summary: str = "讨论了天气",
    session_id: str = "group:12345",
    timestamp: datetime | None = None,
    recall_cues: list | None = None,
) -> ComplexSessionMessage:
    """构造聊天回想 ComplexSessionMessage（含指针 payload）。"""
    if participants is None:
        participants = ["alice", "bob"]
    if timestamp is None:
        timestamp = datetime(2024, 1, 1, 10, 30, 0)
    if recall_cues is None:
        recall_cues = [{"text": "天气", "embedding": [0.1, 0.2, 0.3], "model_name": "test-embed"}]
    payload = {
        "type": MID_TERM_MEMORY_COMPONENT_TYPE,
        "data": {
            "time_range": time_range,
            "participants": participants,
            "summary": summary,
            "recall_cues": recall_cues,
            "session_id": session_id,
            "time_range_pointer": time_range,
        },
    }
    return ComplexSessionMessage(
        raw_message=MessageSequence([DictComponent(payload)]),
        visible_text=f"[聊天回想]\n时间范围: {time_range}\nsummary: {summary}",
        timestamp=timestamp,
        message_id=message_id,
        source_kind=MID_TERM_MEMORY_SOURCE_KIND,
        prompt_text=f"<message>summary: {summary}</message>",
        complex_message_type=MID_TERM_MEMORY_COMPLEX_TYPE,
    )


def make_recall_candidate(
    *,
    message_id: str = "mtm:abc:test1",
    segment_text: str = "天气",
    embedding: list[float] | None = None,
    time_range: str = "2024-01-01 10:00:00 ~ 2024-01-01 11:00:00",
    participants: list[str] | None = None,
    summary: str = "讨论了天气",
    session_id: str = "group:12345",
    score: float = 0.0,
) -> MidTermMemoryRecallCandidate:
    """构造 recall 候选（payload 为内层 data dict，供 _iter_recall_cue_payloads / _format 直接读取）。"""
    if embedding is None:
        embedding = [0.1, 0.2, 0.3]
    if participants is None:
        participants = ["alice", "bob"]
    cue_payloads = [{"text": segment_text, "embedding": embedding, "model_name": "test-embed"}]
    message = make_mid_term_complex_message(
        message_id=message_id,
        time_range=time_range,
        participants=participants,
        summary=summary,
        session_id=session_id,
        recall_cues=cue_payloads,
    )
    # candidate.payload 用内层 data dict（与 _build_candidate_from_record 修复一致）
    payload = {
        "time_range": time_range,
        "participants": participants,
        "summary": summary,
        "recall_cues": cue_payloads,
        "session_id": session_id,
        "time_range_pointer": time_range,
    }
    return MidTermMemoryRecallCandidate(
        message=message,
        payload=payload,
        segment_text=segment_text,
        score=score,
    )


def make_user_msg(text: str = "你好", ts: datetime | None = None) -> SimpleNamespace:
    """构造 mock user 消息（可被 query text 构造选中）。"""
    return SimpleNamespace(
        role="user",
        processed_plain_text=text,
        timestamp=ts or datetime(2024, 1, 1),
        source="user",
    )


def make_reference_message(
    content: str = "",
    *,
    reference_type: ReferenceMessageType = ReferenceMessageType.MEMORY,
) -> ReferenceMessage:
    """构造 ReferenceMessage。"""
    return ReferenceMessage(
        content=content or f"{MID_TERM_MEMORY_REFERENCE_MARKER}\n测试参考",
        timestamp=datetime.now(),
        reference_type=reference_type,
        remaining_uses_value=None,
        display_prefix="[参考消息]",
    )


def make_mock_find_messages_result(
    count: int = 5,
    *,
    base_time: datetime | None = None,
) -> list[SimpleNamespace]:
    """构造 find_messages 返回的 mock 消息列表。"""
    if base_time is None:
        base_time = datetime(2024, 1, 1, 10, 0, 0)
    results = []
    for i in range(count):
        msg = SimpleNamespace()
        msg.timestamp = base_time.replace(minute=i)
        msg.processed_plain_text = f"消息内容{i}"
        msg.message_info = SimpleNamespace(
            user_info=SimpleNamespace(
                user_nickname=f"用户{i}",
                user_id=f"uid{i}",
                user_cardname=None,
            )
        )
        results.append(msg)
    return results