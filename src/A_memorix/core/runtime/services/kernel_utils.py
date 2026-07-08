from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

_TOP_LEVEL_KEYS = frozenset({
    "storage", "embedding", "retrieval", "graph",
    "episode", "web", "advanced", "threshold",
    "summarization", "person_profile",
})


def cfg_get(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    current: Any = config
    if key in _TOP_LEVEL_KEYS and isinstance(current, dict):
        return current.get(key, default)
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def cfg_set(config: Dict[str, Any], key: str, value: Any) -> None:
    current: Dict[str, Any] = config
    parts = [part for part in str(key or "").split(".") if part]
    if not parts:
        return
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def tokens(values: Optional[Iterable[Any]]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in values or []:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def merge_tokens(*groups: Optional[Iterable[Any]]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for group in groups:
        for item in tokens(group):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


def argument_tokens(value: Any) -> List[str]:
    if isinstance(value, str):
        return tokens([value])
    return tokens(value)


def merge_argument_tokens(*groups: Any) -> List[str]:
    merged: List[str] = []
    seen = set()
    for group in groups:
        for item in argument_tokens(group):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


def chat_source(chat_id: str) -> Optional[str]:
    clean = str(chat_id or "").strip()
    return f"chat_summary:{clean}" if clean else None


def resolve_allowed_chat_ids(chat_id: str, shared_chat_ids: Sequence[str] = ()) -> set[str]:
    allowed_chat_ids = {str(item or "").strip() for item in shared_chat_ids if str(item or "").strip()}
    clean_chat_id = str(chat_id or "").strip()
    if clean_chat_id:
        allowed_chat_ids.add(clean_chat_id)
    return allowed_chat_ids


def selector_dict(selector: Any) -> Dict[str, Any]:
    if isinstance(selector, dict):
        return dict(selector)
    if isinstance(selector, (list, tuple)):
        return {"items": list(selector)}
    token = str(selector or "").strip()
    return {"query": token} if token else {}


def optional_float(value: Any) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except Exception:
        return None


def optional_int(value: Any) -> Optional[int]:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except Exception:
        return None


def table_has_column(metadata_store: Any, table: str, column: str) -> bool:
    if metadata_store is None:
        return False
    token = str(table or "").strip()
    col = str(column or "").strip()
    if token not in {"paragraphs", "entities", "relations"} or not col:
        return False
    rows = metadata_store.query(f"PRAGMA table_info({token})")
    return any(str(row.get("name", "") or "") == col for row in rows)


def active_row_filter_sql(metadata_store: Any, table: str, has_column_fn: Any = None) -> str:
    if str(table or "").strip() == "relations" and has_column_fn and has_column_fn("relations", "is_inactive"):
        return "is_inactive IS NULL OR is_inactive = 0"
    return "is_deleted IS NULL OR is_deleted = 0" if has_column_fn and has_column_fn(table, "is_deleted") else "1 = 1"