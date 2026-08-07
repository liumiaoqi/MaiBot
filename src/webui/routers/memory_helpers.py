"""memory.py 拆分后的跨域共享辅助函数。

本模块只包含纯工具函数与 timeline collector 函数，不 import 任何子 router，
子 router 单向 import 本模块。import 方向无环。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import json

from src.common.database.database import get_db_session
from src.common.database.database_model import ChatSession
from src.common.logger import get_logger
from src.services.memory_service import memory_service
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.memory import (
    MemoryTimelineChat,
    MemoryTimelineEvent,
    MemoryTimelineJumpTarget,
    MemoryTimelineRange,
    MemoryTimelineResponse,
)
from src.webui.services.memory_helper_service_web import (
    _find_real_chat_session,
    _get_chat_name,
    _timeline_chat_from_session,
)

logger = get_logger("auto.memory")


# ---------------------------------------------------------------------------
# 通用纯工具函数
# ---------------------------------------------------------------------------

def _unwrap_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    nested = raw.get("payload")
    if isinstance(nested, dict):
        return dict(nested)
    return dict(raw)




def _normalize_chat_lookup_token(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())

def _compact_chat_lookup_tokens(parts: list[Any]) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for part in parts:
        token = str(part or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens

def _get_chat_session_lookup_tokens(
    chat_session: ChatSession,
    latest_messages: dict[str, dict[str, Any]],
) -> list[str]:
    chat_id = str(chat_session.session_id or "").strip()
    latest_message = latest_messages.get(chat_id) or {}
    group_id = str(chat_session.group_id or latest_message.get("group_id")).strip()
    user_id = str(chat_session.user_id or latest_message.get("user_id")).strip()
    group_name = str(chat_session.group_name or latest_message.get("group_name")).strip()
    private_name = str(
        chat_session.user_cardname
        or chat_session.user_nickname
        or latest_message.get("user_cardname")
        or latest_message.get("user_nickname")
        or ""
    ).strip()
    chat_name = _get_chat_name(chat_session, latest_messages)

    return _compact_chat_lookup_tokens(
        [
            chat_id,
            chat_name,
            chat_session.platform,
            chat_session.account_id,
            chat_session.scope,
            group_id,
            group_name,
            f"群聊{group_id}" if group_id else "",
            user_id,
            private_name,
            f"用户{user_id}" if user_id else "",
            f"{private_name}的私聊" if private_name else "",
        ]
    )

def _score_chat_session_lookup(query_token: str, tokens: list[str]) -> int:
    normalized_tokens = [_normalize_chat_lookup_token(token) for token in tokens]
    normalized_tokens = [token for token in normalized_tokens if token]
    if not query_token or not normalized_tokens:
        return 0
    if query_token in normalized_tokens:
        return 100
    if any(token.startswith(query_token) for token in normalized_tokens):
        return 85
    if any(len(token) >= 4 and query_token.startswith(token) for token in normalized_tokens):
        return 75
    if any(query_token in token for token in normalized_tokens):
        return 65
    if any(len(token) >= 4 and token in query_token for token in normalized_tokens):
        return 55
    return 0

def _format_chat_session_lookup_label(chat_session: ChatSession, latest_messages: dict[str, dict[str, Any]]) -> str:
    chat_id = str(chat_session.session_id or "").strip()
    chat_name = _get_chat_name(chat_session, latest_messages)
    group_id = str(chat_session.group_id or "").strip()
    user_id = str(chat_session.user_id or "").strip()
    identifier = group_id or user_id or chat_id
    return f"{chat_name}({identifier})" if identifier and identifier != chat_name else chat_name


def _timeline_sources_for_chat(chat_id: str) -> set[str]:
    token = str(chat_id or "").strip()
    if not token:
        return set()
    return {
        f"chat_summary:{token}",
        f"maibot.chat_history:{token}",
    }

def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed

def _first_float(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None

def _decode_metadata_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, bytes):
        try:
            decoded = json.loads(raw.decode("utf-8"))
            return dict(decoded) if isinstance(decoded, dict) else {}
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '解析元数据 payload 失败', exception=exc)
            logger.warning("操作异常 in memory", exc_info=True)
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            return dict(decoded) if isinstance(decoded, dict) else {}
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '解析元数据 payload 失败', exception=exc)
            logger.warning("操作异常 in memory", exc_info=True)
    return {}

def _decode_json_payload(raw: Any, fallback: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '解析 JSON payload 失败', exception=exc)
            logger.warning("操作异常 in memory", exc_info=True)
            return fallback
    return fallback

def _extend_metadata_chat_tokens(tokens: set[str], value: Any) -> None:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _extend_metadata_chat_tokens(tokens, item)
        return

    token = str(value or "").strip()
    if token:
        tokens.add(token)

def _metadata_chat_tokens(metadata: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("chat_id", "session_id", "stream_id", "chat_ids", "session_ids", "stream_ids"):
        _extend_metadata_chat_tokens(tokens, metadata.get(key))
    return tokens

def _metadata_matches_chat(metadata: dict[str, Any], chat_id: str) -> bool:
    token = str(chat_id or "").strip()
    if not token:
        return False
    if token in _metadata_chat_tokens(metadata):
        return True
    nested_candidates = [
        metadata.get("chat"),
        metadata.get("chat_target"),
        metadata.get("source_context"),
        metadata.get("import_context"),
    ]
    for candidate in nested_candidates:
        if isinstance(candidate, dict) and token in _metadata_chat_tokens(candidate):
            return True
    return False

def _source_matches_chat(source: Any, chat_id: str) -> bool:
    token = str(source or "").strip()
    return bool(token and token in _timeline_sources_for_chat(chat_id))

def _paragraph_matches_chat(row: dict[str, Any], chat_id: str) -> tuple[bool, str]:
    metadata = _decode_metadata_payload(row.get("metadata"))
    if _metadata_matches_chat(metadata, chat_id):
        return True, "metadata.chat_id"
    if _source_matches_chat(row.get("source"), chat_id):
        return True, "source"
    return False, ""

def _event_in_range(occurred_at: float, time_start: Optional[float], time_end: Optional[float]) -> bool:
    if time_start is not None and occurred_at < time_start:
        return False
    if time_end is not None and occurred_at > time_end:
        return False
    return True

def _types_match(event: MemoryTimelineEvent, accepted_types: set[str]) -> bool:
    if not accepted_types:
        return True
    return event.event_type in accepted_types or event.category in accepted_types

def _timeline_event(
    *,
    event_type: str,
    category: str,
    occurred_at: float,
    chat: MemoryTimelineChat,
    title: str,
    summary: str,
    jump_target: dict[str, Any],
    object_count: int = 1,
    key_id: str = "",
    source: str = "",
    attribution: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> MemoryTimelineEvent:
    safe_key = key_id or source or title
    event_id = f"{event_type}:{safe_key}:{occurred_at:.3f}"
    return MemoryTimelineEvent(
        event_id=event_id,
        event_type=event_type,
        category=category,
        occurred_at=occurred_at,
        chat_id=chat.chat_id,
        chat_name=chat.chat_name,
        title=title,
        summary=summary,
        object_count=max(1, int(object_count or 1)),
        key_id=str(key_id or ""),
        source=str(source or ""),
        attribution=str(attribution or ""),
        metadata=metadata or {},
        jump_target=MemoryTimelineJumpTarget(
            tab=str(jump_target.get("tab") or "timeline"),
            params=dict(jump_target.get("params") or {}),
        ),
    )

def _paragraph_jump_target(paragraph_hash: str) -> dict[str, Any]:
    token = str(paragraph_hash or "").strip()
    return {"tab": "graph", "params": {"paragraph_hash": token}}

async def _delete_jump_target_for_paragraph(paragraph_hash: str, source: str = "") -> dict[str, Any]:
    token = str(paragraph_hash or "").strip()
    if token:
        rows = await _query_memory_rows(
            """
            SELECT operation_id
            FROM delete_operation_items
            WHERE item_hash = ?
               OR item_key = ?
               OR payload_json LIKE ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (token, token, f"%{token}%"),
        )
        operation_id = str((rows[0] if rows else {}).get("operation_id") or "").strip()
        if operation_id:
            return {"tab": "delete", "params": {"operation_id": operation_id}}

    params = {"paragraph_hash": token}
    clean_source = str(source or "").strip()
    if clean_source:
        params["source"] = clean_source
    return {"tab": "delete", "params": params}

async def _query_memory_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return await memory_service.query_metadata(sql, params)

def _timeline_query_limit(limit: int, multiplier: int, minimum: int) -> Optional[int]:
    if limit <= 0:
        return None
    return max(limit * multiplier, minimum)

def _append_limit(sql: str, limit: Optional[int]) -> str:
    if limit is None:
        return sql
    return f"{sql}\n        LIMIT ?"

# ---------------------------------------------------------------------------
# timeline collector 函数（涉及数据库查询，但仅 timeline 端点使用）
# ---------------------------------------------------------------------------

async def _timeline_paragraph_events(
    *,
    chat: MemoryTimelineChat,
    time_start: Optional[float],
    time_end: Optional[float],
    accepted_types: set[str],
    limit: int,
) -> list[MemoryTimelineEvent]:
    query_limit = _timeline_query_limit(limit, 5, 200)
    rows = await _query_memory_rows(
        _append_limit(
            """
        SELECT hash, content, created_at, updated_at, metadata, source, is_deleted, deleted_at
        FROM paragraphs
        ORDER BY COALESCE(updated_at, created_at, 0) DESC
        """,
            query_limit,
        ),
        (query_limit,) if query_limit is not None else (),
    )
    events: list[MemoryTimelineEvent] = []
    for row in rows:
        matched, attribution = _paragraph_matches_chat(row, chat.chat_id)
        if not matched:
            continue
        paragraph_hash = str(row.get("hash")).strip()
        source = str(row.get("source")).strip()
        content = str(row.get("content")).strip()
        preview = content[:80] + ("..." if len(content) > 80 else "")
        created_at = _safe_float(row.get("created_at"))
        updated_at = _safe_float(row.get("updated_at"))
        deleted_at = _safe_float(row.get("deleted_at"))
        is_deleted = bool(int(row.get("is_deleted") or 0))
        paragraph_jump_target = (
            await _delete_jump_target_for_paragraph(paragraph_hash, source)
            if is_deleted
            else _paragraph_jump_target(paragraph_hash)
        )
        if created_at is not None and _event_in_range(created_at, time_start, time_end):
            events.append(
                _timeline_event(
                    event_type="paragraph_created",
                    category="paragraph",
                    occurred_at=created_at,
                    chat=chat,
                    title="段落新增",
                    summary=preview or "新增长期记忆段落",
                    key_id=paragraph_hash,
                    source=source,
                    attribution=attribution,
                    metadata={"paragraph_hash": paragraph_hash},
                    jump_target=paragraph_jump_target,
                )
            )
        if (
            updated_at is not None
            and created_at is not None
            and abs(updated_at - created_at) > 1.0
            and _event_in_range(updated_at, time_start, time_end)
        ):
            events.append(
                _timeline_event(
                    event_type="paragraph_updated",
                    category="paragraph",
                    occurred_at=updated_at,
                    chat=chat,
                    title="段落更新",
                    summary=preview or "长期记忆段落内容或元数据更新",
                    key_id=paragraph_hash,
                    source=source,
                    attribution=attribution,
                    metadata={"paragraph_hash": paragraph_hash},
                    jump_target=paragraph_jump_target,
                )
            )
        if is_deleted and deleted_at is not None and _event_in_range(deleted_at, time_start, time_end):
            events.append(
                _timeline_event(
                    event_type="paragraph_deleted",
                    category="paragraph",
                    occurred_at=deleted_at,
                    chat=chat,
                    title="段落被标记删除",
                    summary=preview or "长期记忆段落进入删除状态",
                    key_id=paragraph_hash,
                    source=source,
                    attribution=attribution,
                    metadata={"paragraph_hash": paragraph_hash},
                    jump_target=await _delete_jump_target_for_paragraph(paragraph_hash, source),
                )
            )
    return [event for event in events if _types_match(event, accepted_types)]

async def _timeline_episode_events(
    *,
    chat: MemoryTimelineChat,
    time_start: Optional[float],
    time_end: Optional[float],
    accepted_types: set[str],
    limit: int,
) -> list[MemoryTimelineEvent]:
    sources = sorted(_timeline_sources_for_chat(chat.chat_id))
    if not sources:
        return []
    placeholders = ",".join("?" for _ in sources)
    query_limit = _timeline_query_limit(limit, 3, 100)
    rows = await _query_memory_rows(
        _append_limit(
            f"""
        SELECT episode_id, source, title, summary, paragraph_count, created_at, updated_at, event_time_start, event_time_end
        FROM episodes
        WHERE source IN ({placeholders})
        ORDER BY COALESCE(updated_at, created_at, event_time_start, 0) DESC
        """,
            query_limit,
        ),
        (*sources, *((query_limit,) if query_limit is not None else ())),
    )
    events: list[MemoryTimelineEvent] = []
    for row in rows:
        episode_id = str(row.get("episode_id")).strip()
        source = str(row.get("source")).strip()
        created_at = _safe_float(row.get("created_at"))
        updated_at = _safe_float(row.get("updated_at"))
        summary = str(row.get("summary") or row.get("title") or "Episode 已生成").strip()
        title = str(row.get("title") or "Episode").strip()
        paragraph_count = int(row.get("paragraph_count") or 1)
        if created_at is not None and _event_in_range(created_at, time_start, time_end):
            events.append(
                _timeline_event(
                    event_type="episode_created",
                    category="episode",
                    occurred_at=created_at,
                    chat=chat,
                    title=f"Episode 新增：{title}",
                    summary=summary,
                    object_count=paragraph_count,
                    key_id=episode_id,
                    source=source,
                    attribution="source",
                    metadata={"episode_id": episode_id},
                    jump_target={"tab": "episodes", "params": {"episode_id": episode_id, "source": source}},
                )
            )
        if (
            updated_at is not None
            and created_at is not None
            and abs(updated_at - created_at) > 1.0
            and _event_in_range(updated_at, time_start, time_end)
        ):
            events.append(
                _timeline_event(
                    event_type="episode_updated",
                    category="episode",
                    occurred_at=updated_at,
                    chat=chat,
                    title=f"Episode 更新：{title}",
                    summary=summary,
                    object_count=paragraph_count,
                    key_id=episode_id,
                    source=source,
                    attribution="source",
                    metadata={"episode_id": episode_id},
                    jump_target={"tab": "episodes", "params": {"episode_id": episode_id, "source": source}},
                )
            )
    return [event for event in events if _types_match(event, accepted_types)]

async def _operation_payload_matches_chat(value: Any, chat_id: str) -> bool:
    if isinstance(value, dict):
        if _metadata_matches_chat(value, chat_id):
            return True
        source = value.get("source") or value.get("item_key")
        if _source_matches_chat(source, chat_id):
            return True
        paragraph_hash = str(value.get("paragraph_hash") or value.get("item_hash") or value.get("hash") or "").strip()
        if paragraph_hash:
            rows = await _query_memory_rows(
                "SELECT hash, metadata, source FROM paragraphs WHERE hash = ? LIMIT 1",
                (paragraph_hash,),
            )
            if rows and _paragraph_matches_chat(rows[0], chat_id)[0]:
                return True
        for item in value.values():
            if await _operation_payload_matches_chat(item, chat_id):
                return True
        return False
    if isinstance(value, list):
        for item in value:
            if await _operation_payload_matches_chat(item, chat_id):
                return True
        return False
    if isinstance(value, str):
        return _source_matches_chat(value, chat_id)
    return False

async def _timeline_delete_events(
    *,
    chat: MemoryTimelineChat,
    time_start: Optional[float],
    time_end: Optional[float],
    accepted_types: set[str],
    limit: int,
) -> list[MemoryTimelineEvent]:
    query_limit = _timeline_query_limit(limit, 4, 200)
    rows = await _query_memory_rows(
        _append_limit(
            """
        SELECT operation_id, mode, selector, reason, requested_by, status, created_at, restored_at, summary_json
        FROM delete_operations
        ORDER BY COALESCE(restored_at, created_at, 0) DESC
        """,
            query_limit,
        ),
        (query_limit,) if query_limit is not None else (),
    )
    operation_ids = [str(row.get("operation_id")).strip() for row in rows]
    operation_ids = [operation_id for operation_id in operation_ids if operation_id]
    items_by_operation: dict[str, list[dict[str, Any]]] = {operation_id: [] for operation_id in operation_ids}
    if operation_ids:
        placeholders = ",".join("?" for _ in operation_ids)
        item_rows = await _query_memory_rows(
            f"""
            SELECT operation_id, item_type, item_hash, item_key, payload_json, created_at
            FROM delete_operation_items
            WHERE operation_id IN ({placeholders})
            ORDER BY operation_id ASC, id ASC
            """,
            tuple(operation_ids),
        )
        for item in item_rows:
            operation_id = str(item.get("operation_id")).strip()
            if operation_id in items_by_operation:
                items_by_operation[operation_id].append(dict(item))

    events: list[MemoryTimelineEvent] = []
    for row in rows:
        operation_id = str(row.get("operation_id")).strip()
        if not operation_id:
            continue
        decoded_items = [
            {
                **dict(item),
                "payload": _decode_json_payload(item.get("payload_json"), {}),
            }
            for item in items_by_operation.get(operation_id, [])
        ]
        summary_payload = _decode_json_payload(row.get("summary_json"), {})
        selector_payload = _decode_json_payload(row.get("selector"), row.get("selector"))
        matched = False
        for candidate in (summary_payload, selector_payload, decoded_items):
            if await _operation_payload_matches_chat(candidate, chat.chat_id):
                matched = True
                break
        if not matched:
            continue
        item_count = max(1, len(decoded_items))
        created_at = _safe_float(row.get("created_at"))
        restored_at = _safe_float(row.get("restored_at"))
        mode = str(row.get("mode")).strip()
        reason = str(row.get("reason")).strip()
        if created_at is not None and _event_in_range(created_at, time_start, time_end):
            events.append(
                _timeline_event(
                    event_type="delete_executed",
                    category="delete",
                    occurred_at=created_at,
                    chat=chat,
                    title="删除操作执行",
                    summary=reason or f"删除模式：{mode or '未知'}",
                    object_count=item_count,
                    key_id=operation_id,
                    source=mode,
                    attribution="delete_operation.items",
                    metadata={"operation_id": operation_id, "mode": mode},
                    jump_target={"tab": "delete", "params": {"operation_id": operation_id}},
                )
            )
        if restored_at is not None and _event_in_range(restored_at, time_start, time_end):
            events.append(
                _timeline_event(
                    event_type="delete_restored",
                    category="delete",
                    occurred_at=restored_at,
                    chat=chat,
                    title="删除操作恢复",
                    summary=f"已恢复删除操作：{operation_id}",
                    object_count=item_count,
                    key_id=operation_id,
                    source=mode,
                    attribution="delete_operation.items",
                    metadata={"operation_id": operation_id, "mode": mode},
                    jump_target={"tab": "delete", "params": {"operation_id": operation_id}},
                )
            )
    return [event for event in events if _types_match(event, accepted_types)]

async def _timeline_profile_events(
    *,
    chat: MemoryTimelineChat,
    time_start: Optional[float],
    time_end: Optional[float],
    accepted_types: set[str],
    limit: int,
) -> list[MemoryTimelineEvent]:
    query_limit = _timeline_query_limit(limit, 3, 100)
    rows = await _query_memory_rows(
        _append_limit(
            """
        SELECT DISTINCT pps.person_id, pps.profile_version, pps.updated_at, pps.source_note
        FROM person_profile_snapshots pps
        JOIN paragraph_entities pe ON pe.entity_hash = pps.person_id OR pe.entity_hash IN (
            SELECT hash FROM entities WHERE name = pps.person_id
        )
        JOIN paragraphs p ON p.hash = pe.paragraph_hash
        ORDER BY pps.updated_at DESC
        """,
            query_limit,
        ),
        (query_limit,) if query_limit is not None else (),
    )
    person_ids = [str(row.get("person_id")).strip() for row in rows]
    person_ids = [person_id for person_id in person_ids if person_id]
    paragraphs_by_person: dict[str, list[dict[str, Any]]] = {person_id: [] for person_id in person_ids}
    if person_ids:
        placeholders = ",".join("?" for _ in person_ids)
        paragraph_rows = await _query_memory_rows(
            f"""
            SELECT pe.entity_hash, e.name AS entity_name, p.hash, p.metadata, p.source
            FROM paragraph_entities pe
            LEFT JOIN entities e ON e.hash = pe.entity_hash
            JOIN paragraphs p ON p.hash = pe.paragraph_hash
            WHERE pe.entity_hash IN ({placeholders}) OR e.name IN ({placeholders})
            """,
            (*person_ids, *person_ids),
        )
        person_id_set = set(person_ids)
        for paragraph in paragraph_rows:
            entity_hash = str(paragraph.get("entity_hash")).strip()
            entity_name = str(paragraph.get("entity_name")).strip()
            for candidate in (entity_hash, entity_name):
                if candidate in person_id_set:
                    paragraphs_by_person[candidate].append(dict(paragraph))

    events: list[MemoryTimelineEvent] = []
    for row in rows:
        person_id = str(row.get("person_id")).strip()
        paragraph_rows = paragraphs_by_person.get(person_id, [])
        if not any(_paragraph_matches_chat(paragraph, chat.chat_id)[0] for paragraph in paragraph_rows):
            continue
        updated_at = _safe_float(row.get("updated_at"))
        if updated_at is None or not _event_in_range(updated_at, time_start, time_end):
            continue
        events.append(
            _timeline_event(
                event_type="profile_updated",
                category="profile",
                occurred_at=updated_at,
                chat=chat,
                title="相关画像变更",
                summary="人物画像证据包含该聊天流的长期记忆段落",
                object_count=max(1, len(paragraph_rows)),
                key_id=person_id,
                source=str(row.get("source_note")),
                attribution="profile.evidence_paragraph",
                metadata={"person_id": person_id, "profile_version": row.get("profile_version")},
                jump_target={"tab": "profiles", "params": {"person_id": person_id}},
            )
        )
    override_limit = _timeline_query_limit(limit, 1, 100)
    override_rows = await _query_memory_rows(
        _append_limit(
            """
        SELECT person_id, updated_at, updated_by, source
        FROM person_profile_overrides
        ORDER BY updated_at DESC
        """,
            override_limit,
        ),
        (override_limit,) if override_limit is not None else (),
    )
    for row in override_rows:
        source = str(row.get("source")).strip()
        person_id = str(row.get("person_id")).strip()
        updated_at = _safe_float(row.get("updated_at"))
        if updated_at is None or not _event_in_range(updated_at, time_start, time_end):
            continue
        if not _source_matches_chat(source, chat.chat_id) and chat.chat_id not in source:
            continue
        events.append(
            _timeline_event(
                event_type="profile_override_set",
                category="profile",
                occurred_at=updated_at,
                chat=chat,
                title="画像覆写设置",
                summary="人物画像手动覆写与该聊天流来源相关",
                key_id=person_id,
                source=source,
                attribution="profile.override.source",
                metadata={"person_id": person_id},
                jump_target={"tab": "profiles", "params": {"person_id": person_id}},
            )
        )
    return [event for event in events if _types_match(event, accepted_types)]

async def _timeline_maintenance_events(
    *,
    chat: MemoryTimelineChat,
    time_start: Optional[float],
    time_end: Optional[float],
    accepted_types: set[str],
    limit: int,
) -> list[MemoryTimelineEvent]:
    query_limit = _timeline_query_limit(limit, 4, 200)
    rows = await _query_memory_rows(
        _append_limit(
            """
        SELECT r.hash, r.subject, r.predicate, r.object, r.source_paragraph, r.last_reinforced,
               r.inactive_since, r.protected_until, r.metadata, p.source, p.metadata AS paragraph_metadata
        FROM relations r
        LEFT JOIN paragraphs p ON p.hash = r.source_paragraph
        ORDER BY COALESCE(r.last_reinforced, r.inactive_since, r.protected_until, r.created_at, 0) DESC
        """,
            query_limit,
        ),
        (query_limit,) if query_limit is not None else (),
    )
    events: list[MemoryTimelineEvent] = []
    for row in rows:
        paragraph_row = {"metadata": row.get("paragraph_metadata"), "source": row.get("source")}
        relation_hash = str(row.get("hash")).strip()
        matched, attribution = _paragraph_matches_chat(paragraph_row, chat.chat_id)
        if not matched:
            continue
        relation_text = " ".join(str(row.get(key)).strip() for key in ("subject", "predicate", "object")).strip()
        source = str(row.get("source")).strip()
        for event_type, timestamp_key, title in (
            ("relation_reinforced", "last_reinforced", "关系强化"),
            ("relation_frozen", "inactive_since", "关系冻结"),
            ("relation_protected", "protected_until", "关系保护"),
        ):
            occurred_at = _safe_float(row.get(timestamp_key))
            if occurred_at is None or not _event_in_range(occurred_at, time_start, time_end):
                continue
            events.append(
                _timeline_event(
                    event_type=event_type,
                    category="maintenance",
                    occurred_at=occurred_at,
                    chat=chat,
                    title=title,
                    summary=relation_text or "维护操作影响了该聊天流证据关系",
                    key_id=relation_hash,
                    source=source,
                    attribution=attribution,
                    metadata={"relation_hash": relation_hash, "source_paragraph": row.get("source_paragraph")},
                    jump_target={"tab": "maintenance", "params": {"target": relation_hash or relation_text}},
                )
            )
    return [event for event in events if _types_match(event, accepted_types)]

def _dedupe_timeline_events(events: list[MemoryTimelineEvent]) -> list[MemoryTimelineEvent]:
    seen: set[str] = set()
    deduped: list[MemoryTimelineEvent] = []
    for event in events:
        key = event.event_id
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped

async def _memory_timeline(
    *,
    chat_id: str,
    time_start: Optional[float],
    time_end: Optional[float],
    types: str,
    limit: int,
) -> MemoryTimelineResponse:
    clean_chat_id = str(chat_id or "").strip()
    if not clean_chat_id:
        raise AppError(ErrorCode.PARAM_INVALID, "chat_id 不能为空")
    with get_db_session() as session:
        chat_session = _find_real_chat_session(session, clean_chat_id)
    if chat_session is None:
        raise AppError(ErrorCode.PARAM_INVALID, f"聊天流不存在: {clean_chat_id}", http_status=400)
    if time_start is not None and time_end is not None and time_start > time_end:
        raise AppError(ErrorCode.PARAM_INVALID, "time_start 不能晚于 time_end")

    with get_db_session() as session:
        chat = _timeline_chat_from_session(session, chat_session)
    safe_limit = max(1, min(500, int(limit or 100)))
    accepted_types = {
        token.strip()
        for token in str(types or "").split(",")
        if token.strip() and token.strip() != "all"
    }
    collectors = (
        _timeline_paragraph_events,
        _timeline_episode_events,
        _timeline_delete_events,
        _timeline_profile_events,
        _timeline_maintenance_events,
    )
    bound_events: list[MemoryTimelineEvent] = []
    for collector in collectors:
        bound_events.extend(
            await collector(
                chat=chat,
                time_start=None,
                time_end=None,
                accepted_types=set(),
                limit=0,
            )
        )
    bound_events = _dedupe_timeline_events(bound_events)
    bound_times = [event.occurred_at for event in bound_events if event.occurred_at is not None]
    min_time = min(bound_times) if bound_times else None
    max_time = max(bound_times) if bound_times else None

    events: list[MemoryTimelineEvent] = []
    for collector in collectors:
        events.extend(
            await collector(
                chat=chat,
                time_start=time_start,
                time_end=time_end,
                accepted_types=accepted_types,
                limit=safe_limit,
            )
        )

    events = _dedupe_timeline_events(events)
    events.sort(key=lambda item: item.occurred_at, reverse=True)
    items = events[:safe_limit]
    by_type: dict[str, int] = {}
    for event in items:
        by_type[event.category] = by_type.get(event.category, 0) + 1
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1

    if min_time is None or max_time is None:
        now = datetime.now(tz=timezone.utc)
        fallback_start = (now - timedelta(days=7)).timestamp()
        fallback_end = now.timestamp()
        min_time = min_time or fallback_start
        max_time = max_time or fallback_end

    return MemoryTimelineResponse(
        success=True,
        chat=chat,
        range=MemoryTimelineRange(
            time_start=time_start,
            time_end=time_end,
            min_time=min_time,
            max_time=max_time,
        ),
        items=items,
        summary={
            "total": len(items),
            "by_type": by_type,
        },
    )


# ---------------------------------------------------------------------------
# graph 纯工具函数
# ---------------------------------------------------------------------------

def _trim_memory_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    return text[:limit] + ("..." if len(text) > limit else "")

def _format_memory_relation(subject: Any, predicate: Any, obj: Any) -> str:
    return " ".join(str(item or "").strip() for item in (subject, predicate, obj) if str(item or "").strip())

def _format_graph_paragraph(row: dict[str, Any], entities: list[str], relations: list[dict[str, Any]]) -> dict[str, Any]:
    content = str(row.get("content")).strip()
    return {
        "hash": str(row.get("hash")).strip(),
        "content": content,
        "preview": _trim_memory_text(content),
        "source": str(row.get("source")).strip(),
        "created_at": _safe_float(row.get("created_at")),
        "updated_at": _safe_float(row.get("updated_at")),
        "entity_count": len(entities),
        "relation_count": len(relations),
        "entities": entities,
        "relations": [_format_memory_relation(item.get("subject"), item.get("predicate"), item.get("object")) for item in relations],
    }