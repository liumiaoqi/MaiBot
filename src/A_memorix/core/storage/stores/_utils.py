"""
共享工具函数 — 从 metadata_store.py 提取的静态/独立辅助方法。

各子 Store 均通过本模块引用，避免在多个 Store 中重复定义。
"""

import json
import pickle
from typing import Any, Dict, List, Optional, Sequence

from src.common.logger import get_logger

logger = get_logger("A_Memorix.StoreUtils")


# ---------------------------------------------------------------------------
# 序列化 / 反序列化
# ---------------------------------------------------------------------------

def decode_metadata(value: Any) -> Dict[str, Any]:
    """解码 pickle 编码的 metadata 字段。"""
    if value in {None, ""}:
        return {}
    if isinstance(value, dict):
        return dict(value)
    decoded = pickle.loads(value)
    if not isinstance(decoded, dict):
        raise TypeError("metadata 字段必须解码为 dict")
    return decoded


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: Any, default: Any) -> Any:
    if value in {None, ""}:
        return default
    try:
        return json.loads(value)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '解析 JSON 值失败', exception=exc)
        logger.warning(f"解析 JSON 值失败: {exc}")
        return default


def as_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '转换 float 值失败', exception=exc)
        logger.warning(f"转换 float 值失败: {exc}")
        return None


# ---------------------------------------------------------------------------
# 字典合并
# ---------------------------------------------------------------------------

def deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def append_metadata_tokens(tokens: List[str], value: Any) -> None:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            append_metadata_tokens(tokens, item)
        return
    token = str(value or "").strip()
    if token and token not in tokens:
        tokens.append(token)


def merge_metadata_binding_ids(
    merged: Dict[str, Any],
    base: Dict[str, Any],
    patch: Dict[str, Any],
    scalar_key: str,
    list_key: str,
) -> None:
    tokens: List[str] = []
    for metadata in (base, patch):
        append_metadata_tokens(tokens, metadata.get(scalar_key))
        append_metadata_tokens(tokens, metadata.get(list_key))
    if not tokens:
        return
    preferred_scalar = str(
        patch.get(scalar_key) or merged.get(scalar_key) or base.get(scalar_key) or tokens[0]
    ).strip()
    merged[scalar_key] = preferred_scalar
    merged[list_key] = tokens


def merge_paragraph_metadata(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = deep_merge_dict(base, patch)
    for scalar_key, list_key in (
        ("chat_id", "chat_ids"),
        ("session_id", "session_ids"),
        ("stream_id", "stream_ids"),
    ):
        merge_metadata_binding_ids(merged, base, patch, scalar_key, list_key)
    return merged


# ---------------------------------------------------------------------------
# 名称 / Hash 工具
# ---------------------------------------------------------------------------

def canonicalize_name(name: str) -> str:
    """规范化名称 (统一小写并去除首尾空格)。"""
    if not name:
        return ""
    return name.strip().lower()


def normalize_hash_sequence(hash_values: Sequence[str]) -> List[str]:
    """规范化 hash 列表并保持首次出现顺序。"""
    normalized: List[str] = []
    seen = set()
    for item in hash_values or []:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def iter_sql_batches(items: Sequence[str], batch_size: int = 900) -> List[List[str]]:
    """按 SQLite 参数数量限制切分批量查询。"""
    safe_batch_size = max(1, int(batch_size))
    return [
        list(items[index : index + safe_batch_size])
        for index in range(0, len(items), safe_batch_size)
    ]


# ---------------------------------------------------------------------------
# 行 → 字典
# ---------------------------------------------------------------------------

def row_to_dict(row: Any, _row_type: str = "") -> Dict[str, Any]:
    """将 sqlite3.Row 转换为字典，自动解码 pickle 字段。"""
    import sqlite3

    if isinstance(row, sqlite3.Row):
        d = dict(row)
    elif isinstance(row, dict):
        d = dict(row)
    else:
        d = dict(row)
    if "metadata" in d and d["metadata"]:
        try:
            d["metadata"] = pickle.loads(d["metadata"])
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '反序列化元数据失败', exception=exc)
            logger.warning(f"反序列化元数据失败: {exc}")
            pass
    return d


# ---------------------------------------------------------------------------
# 文本处理
# ---------------------------------------------------------------------------

def normalize_episode_source(source: Any) -> str:
    return str(source or "").strip()


def dedupe_episode_sources(sources: List[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for item in sources or []:
        token = normalize_episode_source(item)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


# ---------------------------------------------------------------------------
# 段落 N-gram / FTS 辅助（与 jieba 相关的静态工具）
# ---------------------------------------------------------------------------

def char_ngrams(text: str, n: int) -> List[str]:
    compact = "".join(str(text or "").lower().split())
    if not compact:
        return []
    if len(compact) < n:
        return [compact]
    return [compact[i : i + n] for i in range(0, len(compact) - n + 1)]


def _paragraph_phrase_tokens(text: str) -> List[str]:
    import re
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_]+|[一-鿿]{2,}", str(text or ""))
    ]
