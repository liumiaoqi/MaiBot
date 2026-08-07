"""delete 端点（preview/execute/restore/operations/purge）+ sources。"""

from fastapi import APIRouter, Depends, Query

from src.services.memory_service import memory_service
from src.webui.dependencies import require_auth
from src.webui.schemas.memory import (
    DeleteActionRequest,
    DeletePurgeRequest,
    DeleteRestoreRequest,
    SourceBatchDeleteRequest,
    SourceDeleteRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# sources 辅助函数
# ---------------------------------------------------------------------------

async def _source_list() -> dict:
    return await memory_service.source_admin(action="list")

async def _source_delete(payload: SourceDeleteRequest) -> dict:
    return await memory_service.source_admin(action="delete", source=payload.source)

async def _source_batch_delete(payload: SourceBatchDeleteRequest) -> dict:
    return await memory_service.source_admin(action="batch_delete", sources=payload.sources)


# ---------------------------------------------------------------------------
# delete 辅助函数
# ---------------------------------------------------------------------------

async def _delete_preview(payload: DeleteActionRequest) -> dict:
    return await memory_service.delete_admin(action="preview", mode=payload.mode, selector=payload.selector)

async def _delete_execute(payload: DeleteActionRequest) -> dict:
    return await memory_service.delete_admin(
        action="execute",
        mode=payload.mode,
        selector=payload.selector,
        reason=payload.reason,
        requested_by=payload.requested_by,
    )

async def _delete_restore(payload: DeleteRestoreRequest) -> dict:
    return await memory_service.delete_admin(
        action="restore",
        mode=payload.mode,
        selector=payload.selector,
        operation_id=payload.operation_id,
        reason=payload.reason,
        requested_by=payload.requested_by,
    )

async def _delete_list(limit: int, mode: str) -> dict:
    return await memory_service.delete_admin(action="list_operations", limit=limit, mode=mode)

async def _delete_get(operation_id: str) -> dict:
    return await memory_service.delete_admin(action="get_operation", operation_id=operation_id)

async def _delete_purge(payload: DeletePurgeRequest) -> dict:
    return await memory_service.delete_admin(
        action="purge",
        grace_hours=payload.grace_hours,
        limit=payload.limit,
    )


# ---------------------------------------------------------------------------
# sources 端点
# ---------------------------------------------------------------------------

@router.get("/sources")
async def list_memory_sources():
    return await _source_list()

@router.delete("/sources/{id}")
async def delete_memory_source(id: str):
    return await memory_service.source_admin(action="delete", source=id)

@router.delete("/sources")
async def batch_delete_memory_sources(payload: SourceBatchDeleteRequest):
    return await _source_batch_delete(payload)


# ---------------------------------------------------------------------------
# delete 端点
# ---------------------------------------------------------------------------

@router.post("/delete/preview")
async def preview_memory_delete(payload: DeleteActionRequest):
    return await _delete_preview(payload)

@router.post("/episodes/{id}/delete")
async def execute_memory_delete(id: str, payload: DeleteActionRequest):
    return await _delete_execute(payload)

@router.post("/delete/restore")
async def restore_memory_delete(payload: DeleteRestoreRequest):
    return await _delete_restore(payload)

@router.get("/delete/operations")
async def list_memory_delete_operations(
    limit: int = Query(50, ge=1, le=200),
    mode: str = Query(""),
):
    return await _delete_list(limit, mode)

@router.get("/delete/operations/{operation_id}")
async def get_memory_delete_operation(operation_id: str):
    return await _delete_get(operation_id)

@router.post("/maintenance/purge")
async def purge_memory_delete(payload: DeletePurgeRequest):
    return await _delete_purge(payload)