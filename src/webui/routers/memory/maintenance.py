"""maintenance + runtime + v5 退役端点。"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from src.services.memory_service import memory_service
from src.webui.dependencies import require_auth
from src.webui.schemas.memory import (
    AutoSaveRequest,
    MaintainRequest,
    V5ActionRequest,
    VectorRebuildRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# runtime 辅助函数
# ---------------------------------------------------------------------------

async def _runtime_save() -> dict:
    return await memory_service.runtime_admin(action="save")

async def _runtime_config() -> dict:
    return await memory_service.runtime_admin(action="get_config")

async def _runtime_self_check(refresh: bool) -> dict:
    return await memory_service.runtime_admin(action="refresh_self_check" if refresh else "self_check")

async def _runtime_auto_save(enabled: bool | None = None) -> dict:
    if enabled is None:
        config = await memory_service.runtime_admin(action="get_config")
        return {"success": bool(config.get("success", False)), "auto_save": bool(config.get("auto_save", False))}
    return await memory_service.runtime_admin(action="set_auto_save", enabled=enabled)

async def _runtime_rebuild_vectors(payload: VectorRebuildRequest) -> dict:
    return await memory_service.runtime_admin(
        action="rebuild_all_vectors",
        timeout_ms=600000,
        dry_run=payload.dry_run,
        batch_size=payload.batch_size,
        include_relations=payload.include_relations,
    )


# ---------------------------------------------------------------------------
# maintenance 辅助函数
# ---------------------------------------------------------------------------

async def _maintenance_recycle_bin(limit: int) -> dict:
    return await memory_service.get_recycle_bin(limit=limit)

async def _maintenance_restore(payload: MaintainRequest) -> dict:
    return (await memory_service.restore_memory(target=payload.target)).to_dict()

async def _maintenance_reinforce(payload: MaintainRequest) -> dict:
    return (await memory_service.reinforce_memory(target=payload.target)).to_dict()

async def _maintenance_freeze(payload: MaintainRequest) -> dict:
    return (await memory_service.freeze_memory(target=payload.target)).to_dict()

async def _maintenance_protect(payload: MaintainRequest) -> dict:
    return (await memory_service.protect_memory(target=payload.target, hours=payload.hours)).to_dict()


# ---------------------------------------------------------------------------
# v5 辅助函数
# ---------------------------------------------------------------------------

async def _v5_status(target: str, limit: int) -> dict:
    return await memory_service.v5_admin(action="status", target=target, limit=limit)

async def _v5_recycle_bin(limit: int) -> dict:
    return await memory_service.v5_admin(action="recycle_bin", limit=limit)

async def _v5_action(action: str, payload: V5ActionRequest) -> dict:
    kwargs: dict[str, Any] = {
        "target": payload.target,
        "reason": payload.reason,
        "updated_by": payload.updated_by,
    }
    if payload.strength is not None:
        kwargs["strength"] = payload.strength
    return await memory_service.v5_admin(action=action, **kwargs)


# ---------------------------------------------------------------------------
# runtime 端点
# ---------------------------------------------------------------------------

@router.post("/runtime/save")
async def save_memory_runtime():
    return await _runtime_save()

@router.get("/runtime/config")
async def get_memory_runtime_config():
    return await _runtime_config()

@router.get("/runtime/self-check")
async def get_memory_runtime_self_check():
    return await _runtime_self_check(False)

@router.post("/runtime/self-check/refresh")
async def refresh_memory_runtime_self_check():
    return await _runtime_self_check(True)

@router.get("/runtime/auto-save")
async def get_memory_runtime_auto_save():
    return await _runtime_auto_save(None)

@router.post("/runtime/auto-save")
async def set_memory_runtime_auto_save(payload: AutoSaveRequest):
    return await _runtime_auto_save(payload.enabled)

@router.post("/runtime/vectors/rebuild")
async def rebuild_memory_runtime_vectors(payload: VectorRebuildRequest):
    return await _runtime_rebuild_vectors(payload)


# ---------------------------------------------------------------------------
# maintenance 端点
# ---------------------------------------------------------------------------

@router.get("/maintenance/recycle-bin")
async def get_memory_recycle_bin(limit: int = Query(50, ge=1, le=200)):
    return await _maintenance_recycle_bin(limit)

@router.post("/maintenance/restore")
async def restore_memory_relation(payload: MaintainRequest):
    return await _maintenance_restore(payload)

@router.post("/maintenance/reinforce")
async def reinforce_memory_relation(payload: MaintainRequest):
    return await _maintenance_reinforce(payload)

@router.post("/maintenance/freeze")
async def freeze_memory_relation(payload: MaintainRequest):
    return await _maintenance_freeze(payload)

@router.post("/maintenance/protect")
async def protect_memory_relation(payload: MaintainRequest):
    return await _maintenance_protect(payload)


# ---------------------------------------------------------------------------
# v5 退役端点
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_memory_v5_status(
    target: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
):
    return await _v5_status(target, limit)


@router.post("/v5/reinforce")
async def reinforce_memory_v5(payload: V5ActionRequest):
    return await _v5_action("reinforce", payload)

@router.post("/v5/weaken")
async def weaken_memory_v5(payload: V5ActionRequest):
    return await _v5_action("weaken", payload)

@router.post("/v5/remember-forever")
async def remember_forever_memory_v5(payload: V5ActionRequest):
    return await _v5_action("remember_forever", payload)

@router.delete("/episodes/{id}")
async def forget_memory_episode(id: str, payload: V5ActionRequest):
    payload.target = id
    return await _v5_action("forget", payload)

@router.post("/episodes/{id}/restore")
async def restore_memory_episode(id: str, payload: V5ActionRequest):
    payload.target = id
    return await _v5_action("restore", payload)