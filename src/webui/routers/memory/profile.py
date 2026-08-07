"""profile 端点（查询/覆盖/证据）。"""

from fastapi import APIRouter, Depends, Query

from src.common.database.database import get_db_session
from src.person_info.person_info import resolve_person_id_for_memory
from src.services.memory_service import memory_service
from src.webui.dependencies import require_auth
from src.webui.schemas.memory import (
    ProfileEvidenceCorrectRequest,
    ProfileOverrideRequest,
)
from src.webui.services.memory_helper_service_web import _get_person_name_for_person_id

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

async def _profile_query(
    *,
    person_id: str,
    person_keyword: str,
    platform: str,
    user_id: str,
    limit: int,
    force_refresh: bool,
) -> dict:
    clean_person_id = str(person_id or "").strip()
    if not clean_person_id and str(platform or "").strip() and str(user_id or "").strip():
        clean_person_id = resolve_person_id_for_memory(
            platform=str(platform or "").strip(),
            user_id=str(user_id or "").strip(),
            strict_known=False,
        )
    return await memory_service.profile_admin(
        action="query",
        person_id=clean_person_id,
        person_keyword=person_keyword,
        limit=limit,
        force_refresh=force_refresh,
    )

async def _profile_list(limit: int) -> dict:
    payload = await memory_service.profile_admin(action="list", limit=limit)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return payload

    items = []
    with get_db_session(auto_commit=False) as session:
        for item in payload["items"]:
            if not isinstance(item, dict):
                items.append(item)
                continue
            enriched = dict(item)
            person_id = str(enriched.get("person_id", "")).strip()
            enriched["person_name"] = _get_person_name_for_person_id(session, person_id)
            items.append(enriched)

    payload = dict(payload)
    payload["items"] = items
    return payload

async def _profile_search(
    *,
    person_id: str,
    person_keyword: str,
    platform: str,
    user_id: str,
    limit: int,
) -> dict:
    clean_person_id = str(person_id or "").strip()
    if not clean_person_id and str(platform or "").strip() and str(user_id or "").strip():
        clean_person_id = resolve_person_id_for_memory(
            platform=str(platform or "").strip(),
            user_id=str(user_id or "").strip(),
            strict_known=False,
        )

    payload = await _profile_list(max(limit, 200))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return payload

    keyword = str(person_keyword or "").strip().lower()

    def _matches(item: dict) -> bool:
        if clean_person_id and str(item.get("person_id", "")).strip() != clean_person_id:
            return False
        if not keyword:
            return True

        override = item.get("manual_override")
        override_text = ""
        if isinstance(override, dict):
            override_text = str(override.get("override_text", "") or override.get("text", "") or "")
        elif isinstance(override, str):
            override_text = override

        haystack = "\n".join(
            [
                str(item.get("person_id", "")),
                str(item.get("person_name", "")),
                str(item.get("profile_text", "")),
                str(item.get("source_note", "")),
                override_text,
            ]
        ).lower()
        return keyword in haystack

    items = [item for item in payload["items"] if isinstance(item, dict) and _matches(item)]
    items = items[:limit]
    return {
        "success": True,
        "items": items,
        "count": len(items),
        "query": {
            "person_id": clean_person_id,
            "person_keyword": person_keyword,
            "platform": platform,
            "user_id": user_id,
        },
    }

async def _profile_set_override(payload: ProfileOverrideRequest) -> dict:
    return await memory_service.profile_admin(
        action="set_override",
        person_id=payload.person_id,
        override_text=payload.override_text,
        updated_by=payload.updated_by,
        source=payload.source,
    )

async def _profile_delete_override(person_id: str) -> dict:
    return await memory_service.profile_admin(action="delete_override", person_id=person_id)

async def _profile_evidence(person_id: str, limit: int, force_refresh: bool) -> dict:
    return await memory_service.profile_admin(
        action="evidence",
        person_id=person_id,
        limit=limit,
        force_refresh=force_refresh,
    )

async def _profile_correct_evidence(person_id: str, payload: ProfileEvidenceCorrectRequest) -> dict:
    return await memory_service.profile_admin(
        action="correct_evidence",
        person_id=person_id,
        evidence_type=payload.evidence_type,
        hash=payload.hash,
        requested_by=payload.requested_by,
        reason=payload.reason,
        refresh=payload.refresh,
        limit=payload.limit,
    )


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/profiles/query")
async def query_memory_profile(
    person_id: str = Query(""),
    person_keyword: str = Query(""),
    platform: str = Query(""),
    user_id: str = Query(""),
    limit: int = Query(12, ge=1, le=100),
    force_refresh: bool = Query(False),
):
    return await _profile_query(
        person_id=person_id,
        person_keyword=person_keyword,
        platform=platform,
        user_id=user_id,
        limit=limit,
        force_refresh=force_refresh,
    )

@router.get("/profiles")
async def list_memory_profiles(limit: int = Query(50, ge=1, le=200)):
    return await _profile_list(limit)

@router.get("/profiles/search")
async def search_memory_profiles(
    person_id: str = Query(""),
    person_keyword: str = Query(""),
    platform: str = Query(""),
    user_id: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
):
    return await _profile_search(
        person_id=person_id,
        person_keyword=person_keyword,
        platform=platform,
        user_id=user_id,
        limit=limit,
    )

@router.post("/profiles/override")
async def set_memory_profile_override(payload: ProfileOverrideRequest):
    return await _profile_set_override(payload)

@router.delete("/profiles/override/{person_id}")
async def delete_memory_profile_override(person_id: str):
    return await _profile_delete_override(person_id)

@router.get("/profiles/{person_id}/evidence")
async def get_memory_profile_evidence(
    person_id: str,
    limit: int = Query(12, ge=1, le=100),
    force_refresh: bool = Query(False),
):
    return await _profile_evidence(person_id, limit, force_refresh)

@router.post("/profiles/{person_id}/evidence/correct")
async def correct_memory_profile_evidence(person_id: str, payload: ProfileEvidenceCorrectRequest):
    return await _profile_correct_evidence(person_id, payload)