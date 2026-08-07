"""episode 端点（列表/状态/详情/重建/处理）。"""

from fastapi import APIRouter, Depends, Query

from src.common.database.database import get_db_session
from src.person_info.person_info import resolve_person_id_for_memory
from src.services.memory_service import memory_service
from src.webui.dependencies import require_auth
from src.webui.schemas.memory import (
    EpisodeProcessPendingRequest,
    EpisodeRebuildRequest,
)
from src.webui.services.memory_helper_service_web import _get_person_name_for_person_id

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _enrich_episode_person_name(item: dict) -> dict:
    enriched = dict(item)
    item_person_id = str(enriched.get("person_id", "")).strip()

    participants = enriched.get("participants")
    if not item_person_id and isinstance(participants, list):
        for participant in participants:
            if isinstance(participant, dict):
                candidate = str(participant.get("person_id", "") or participant.get("id", "") or "").strip()
            else:
                candidate = str(participant or "").strip()
            if candidate:
                item_person_id = candidate
                break

    enriched["person_id"] = item_person_id
    with get_db_session(auto_commit=False) as session:
        enriched["person_name"] = _get_person_name_for_person_id(session, item_person_id)
    return enriched

async def _episode_list(
    *,
    query: str,
    limit: int,
    source: str,
    person_id: str,
    platform: str,
    user_id: str,
    time_start: float | None,
    time_end: float | None,
) -> dict:
    clean_person_id = str(person_id or "").strip()
    if not clean_person_id and str(platform or "").strip() and str(user_id or "").strip():
        clean_person_id = resolve_person_id_for_memory(
            platform=str(platform or "").strip(),
            user_id=str(user_id or "").strip(),
            strict_known=False,
        )

    payload = await memory_service.episode_admin(
        action="list",
        query=query,
        limit=limit,
        source=source,
        person_id=clean_person_id,
        time_start=time_start,
        time_end=time_end,
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return payload

    items = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            items.append(item)
            continue
        items.append(_enrich_episode_person_name(item))

    payload = dict(payload)
    payload["items"] = items
    return payload

async def _episode_get(episode_id: str) -> dict:
    payload = await memory_service.episode_admin(action="get", episode_id=episode_id)
    if isinstance(payload, dict) and isinstance(payload.get("episode"), dict):
        payload = dict(payload)
        payload["episode"] = _enrich_episode_person_name(payload["episode"])
    return payload

async def _episode_rebuild(payload: EpisodeRebuildRequest) -> dict:
    return await memory_service.episode_admin(
        action="rebuild",
        source=payload.source,
        sources=payload.sources,
        all=payload.all,
    )

async def _episode_status(limit: int) -> dict:
    return await memory_service.episode_admin(action="status", limit=limit)

async def _episode_process_pending(payload: EpisodeProcessPendingRequest) -> dict:
    return await memory_service.episode_admin(
        action="process_pending",
        limit=payload.limit,
        max_retry=payload.max_retry,
    )


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/episodes")
async def list_memory_episodes(
    query: str = Query(""),
    limit: int = Query(20, ge=1, le=200),
    source: str = Query(""),
    person_id: str = Query(""),
    platform: str = Query(""),
    user_id: str = Query(""),
    time_start: float | None = Query(None),
    time_end: float | None = Query(None),
):
    return await _episode_list(
        query=query,
        limit=limit,
        source=source,
        person_id=person_id,
        platform=platform,
        user_id=user_id,
        time_start=time_start,
        time_end=time_end,
    )

@router.get("/episodes/status")
async def get_memory_episode_status(limit: int = Query(20, ge=1, le=200)):
    return await _episode_status(limit)

@router.get("/episodes/{episode_id}")
async def get_memory_episode(episode_id: str):
    return await _episode_get(episode_id)

@router.post("/episodes/rebuild")
async def rebuild_memory_episodes(payload: EpisodeRebuildRequest):
    return await _episode_rebuild(payload)

@router.post("/episodes/process-pending")
async def process_memory_episode_pending(payload: EpisodeProcessPendingRequest):
    return await _episode_process_pending(payload)