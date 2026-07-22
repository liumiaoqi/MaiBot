"""记忆结果转换工具 — 将 A_memorix 的原始响应转换为核心类型。

_memory_service 和 migration_router 共享这些函数，避免代码重复。
"""

from __future__ import annotations

from typing import Any, List

from src.core.types import MemoryHit, MemorySearchResult, MemoryWriteResult


def coerce_write_result(payload: Any) -> MemoryWriteResult:
    if not isinstance(payload, dict):
        return MemoryWriteResult(success=False, detail="invalid_payload")
    stored_ids = [str(item) for item in (payload.get("stored_ids") or []) if str(item).strip()]
    skipped_ids = [str(item) for item in (payload.get("skipped_ids") or []) if str(item).strip()]
    detail = str(payload.get("detail") or payload.get("reason") or "")
    if stored_ids or skipped_ids:
        success = True
    elif "success" in payload:
        success = bool(payload.get("success"))
    else:
        success = not bool(detail)
    return MemoryWriteResult(
        success=success,
        stored_ids=stored_ids,
        skipped_ids=skipped_ids,
        detail=detail,
    )


def coerce_search_result(payload: Any) -> MemorySearchResult:
    if not isinstance(payload, dict):
        return MemorySearchResult(success=False, error="invalid_payload")
    hits: List[MemoryHit] = []
    for item in payload.get("hits", []) or []:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if "source_branches" in item and "source_branches" not in metadata:
            metadata["source_branches"] = item.get("source_branches") or []
        if "rank" in item and "rank" not in metadata:
            metadata["rank"] = item.get("rank")
        hits.append(
            MemoryHit(
                content=item.get("content", ""),
                score=float(item.get("score", 0.0) or 0.0),
                hit_type=item.get("type", ""),
                source=item.get("source", ""),
                hash_value=item.get("hash", ""),
                metadata=metadata,
                episode_id=item.get("episode_id", ""),
                title=item.get("title", ""),
            )
        )
    success_raw = payload.get("success")
    error = payload.get("error", "")
    success = (not bool(error)) if success_raw is None else bool(success_raw)
    return MemorySearchResult(
        summary=payload.get("summary", ""),
        hits=hits,
        filtered=bool(payload.get("filtered", False)),
        success=success,
        error=error,
    )
