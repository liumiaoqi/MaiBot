"""compat_router - 旧版 /api 前缀兼容端点。

委托各子 router 的 `_` 辅助函数和 memory_helpers.py 中的共享函数。
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile

from src.webui.dependencies import require_auth
from src.webui.schemas.base import ApiResponse
from src.webui.schemas.memory import (
    AutoSaveRequest,
    EdgeCreateRequest,
    EdgeDeleteRequest,
    EdgeWeightRequest,
    EpisodeProcessPendingRequest,
    EpisodeRebuildRequest,
    MaintainRequest,
    MemoryTimelineResponse,
    NodeRenameRequest,
    NodeRequest,
    ProfileOverrideRequest,
    SourceBatchDeleteRequest,
    SourceDeleteRequest,
    TuningApplyBestRequest,
    TuningApplyProfileRequest,
    VectorRebuildRequest,
)
from src.webui.routers.memory.graph import (
    _graph_create_edge,
    _graph_create_node,
    _graph_delete_edge,
    _graph_delete_node,
    _graph_get,
    _graph_rename_node,
    _graph_update_edge_weight,
    _query_aggregate,
)
from src.webui.routers.memory.episode import (
    _episode_get,
    _episode_list,
    _episode_process_pending,
    _episode_rebuild,
    _episode_status,
)
from src.webui.routers.memory.profile import (
    _profile_delete_override,
    _profile_list,
    _profile_query,
    _profile_search,
    _profile_set_override,
)
from src.webui.routers.memory.import_ import (
    create_memory_import_upload,
    _import_cancel,
    _import_chunks,
    _import_create,
    _import_get,
    _import_guide,
    _import_list,
    _import_path_aliases,
    _import_resolve_path,
    _import_retry,
    _import_settings,
)
from src.webui.routers.memory.tuning import (
    _tuning_apply_best,
    _tuning_apply_profile,
    _tuning_cancel,
    _tuning_create_task,
    _tuning_export_profile,
    _tuning_get_rounds,
    _tuning_get_task,
    _tuning_list_tasks,
    _tuning_profile,
    _tuning_report,
    _tuning_rollback_profile,
    _tuning_settings,
)
from src.webui.routers.memory.maintenance import (
    _maintenance_freeze,
    _maintenance_protect,
    _maintenance_reinforce,
    _maintenance_recycle_bin,
    _maintenance_restore,
    _runtime_auto_save,
    _runtime_config,
    _runtime_rebuild_vectors,
    _runtime_save,
    _runtime_self_check,
)
from src.webui.routers.memory.delete import (
    _source_batch_delete,
    _source_delete,
    _source_list,
)
from src.webui.routers.memory_helpers import _memory_timeline

compat_router = APIRouter(prefix="/api", tags=["memory-compat"], dependencies=[Depends(require_auth)])


@compat_router.get("/graph")
async def compat_get_graph(limit: int = Query(200, ge=1, le=5000)):
    return await _graph_get(limit)

@compat_router.post("/node")
async def compat_create_node(payload: NodeRequest):
    return await _graph_create_node(payload)

@compat_router.delete("/node")
async def compat_delete_node(payload: NodeRequest):
    return await _graph_delete_node(payload)

@compat_router.post("/node/rename")
async def compat_rename_node(payload: NodeRenameRequest):
    return await _graph_rename_node(payload)

@compat_router.post("/edge")
async def compat_create_edge(payload: EdgeCreateRequest):
    return await _graph_create_edge(payload)

@compat_router.delete("/edge")
async def compat_delete_edge(payload: EdgeDeleteRequest):
    return await _graph_delete_edge(payload)

@compat_router.post("/edge/weight")
async def compat_update_edge_weight(payload: EdgeWeightRequest):
    return await _graph_update_edge_weight(payload)

@compat_router.get("/source/list")
async def compat_list_sources():
    return await _source_list()

@compat_router.post("/source/delete")
async def compat_delete_source(payload: SourceDeleteRequest):
    return await _source_delete(payload)

@compat_router.post("/source/batch_delete")
async def compat_batch_delete_sources(payload: SourceBatchDeleteRequest):
    return await _source_batch_delete(payload)

@compat_router.get("/query/aggregate")
async def compat_query_aggregate(
    query: str = Query(""),
    limit: int = Query(20, ge=1, le=200),
    chat_id: str = Query(""),
    person_id: str = Query(""),
    time_start: float | None = Query(None),
    time_end: float | None = Query(None),
):
    return await _query_aggregate(
        query,
        limit=limit,
        chat_id=chat_id,
        person_id=person_id,
        time_start=time_start,
        time_end=time_end,
    )

@compat_router.get("/timeline", response_model=ApiResponse[MemoryTimelineResponse])
async def compat_get_memory_timeline(
    chat_id: str = Query(..., min_length=1),
    time_start: float | None = Query(None),
    time_end: float | None = Query(None),
    types: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
):
    return await _memory_timeline(
        chat_id=chat_id,
        time_start=time_start,
        time_end=time_end,
        types=types,
        limit=limit,
    )

@compat_router.get("/episodes")
async def compat_list_episodes(
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

@compat_router.get("/episodes/status")
async def compat_episode_status(limit: int = Query(20, ge=1, le=200)):
    return await _episode_status(limit)

@compat_router.get("/episodes/{episode_id}")
async def compat_get_episode(episode_id: str):
    return await _episode_get(episode_id)

@compat_router.post("/episodes/rebuild")
async def compat_rebuild_episodes(payload: EpisodeRebuildRequest):
    return await _episode_rebuild(payload)

@compat_router.post("/episodes/process_pending")
async def compat_process_episode_pending(payload: EpisodeProcessPendingRequest):
    return await _episode_process_pending(payload)

@compat_router.get("/person_profile/query")
async def compat_profile_query(
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

@compat_router.get("/person_profile/list")
async def compat_profile_list(limit: int = Query(50, ge=1, le=200)):
    return await _profile_list(limit)

@compat_router.get("/person_profile/search")
async def compat_profile_search(
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

@compat_router.post("/person_profile/override")
async def compat_set_profile_override(payload: ProfileOverrideRequest):
    return await _profile_set_override(payload)

@compat_router.delete("/person_profile/override/{person_id}")
async def compat_delete_profile_override(person_id: str):
    return await _profile_delete_override(person_id)

@compat_router.post("/save")
async def compat_runtime_save():
    return await _runtime_save()

@compat_router.get("/config")
async def compat_runtime_config():
    return await _runtime_config()

@compat_router.get("/runtime/self_check")
async def compat_runtime_self_check():
    return await _runtime_self_check(False)

@compat_router.post("/runtime/self_check/refresh")
async def compat_refresh_runtime_self_check():
    return await _runtime_self_check(True)

@compat_router.get("/config/auto_save")
async def compat_runtime_auto_save():
    return await _runtime_auto_save(None)

@compat_router.post("/config/auto_save")
async def compat_set_runtime_auto_save(payload: AutoSaveRequest):
    return await _runtime_auto_save(payload.enabled)

@compat_router.post("/runtime/vectors/rebuild")
async def compat_rebuild_runtime_vectors(payload: VectorRebuildRequest):
    return await _runtime_rebuild_vectors(payload)

@compat_router.get("/memory/recycle_bin")
async def compat_get_recycle_bin(limit: int = Query(50, ge=1, le=200)):
    return await _maintenance_recycle_bin(limit)

@compat_router.post("/memory/restore")
async def compat_restore_memory(payload: MaintainRequest):
    return await _maintenance_restore(payload)

@compat_router.post("/memory/reinforce")
async def compat_reinforce_memory(payload: MaintainRequest):
    return await _maintenance_reinforce(payload)

@compat_router.post("/memory/freeze")
async def compat_freeze_memory(payload: MaintainRequest):
    return await _maintenance_freeze(payload)

@compat_router.post("/memory/protect")
async def compat_protect_memory(payload: MaintainRequest):
    return await _maintenance_protect(payload)

@compat_router.get("/import/settings")
async def compat_import_settings():
    return await _import_settings()

@compat_router.get("/import/path_aliases")
async def compat_import_path_aliases():
    return await _import_path_aliases()

@compat_router.get("/import/guide")
async def compat_import_guide():
    return await _import_guide()

@compat_router.post("/import/resolve_path")
async def compat_import_resolve_path(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_resolve_path(payload)

@compat_router.post("/import/upload")
async def compat_import_upload(
    files: list[UploadFile] = File(...),  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    payload_json: str = Form("{}"),
):
    return await create_memory_import_upload(files=files, payload_json=payload_json)

@compat_router.post("/import/tasks/upload")
async def compat_import_upload_task(
    files: list[UploadFile] = File(...),  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    payload_json: str = Form("{}"),
):
    return await create_memory_import_upload(files=files, payload_json=payload_json)

@compat_router.post("/import/paste")
async def compat_import_paste(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_paste", payload)

@compat_router.post("/import/tasks/paste")
async def compat_import_paste_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_paste", payload)

@compat_router.post("/import/raw_scan")
async def compat_import_raw_scan(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_raw_scan", payload)

@compat_router.post("/import/tasks/raw_scan")
async def compat_import_raw_scan_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_raw_scan", payload)

@compat_router.post("/import/lpmm_openie")
async def compat_import_lpmm_openie(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_lpmm_openie", payload)

@compat_router.post("/import/tasks/lpmm_openie")
async def compat_import_lpmm_openie_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_lpmm_openie", payload)

@compat_router.post("/import/lpmm_convert")
async def compat_import_lpmm_convert(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_lpmm_convert", payload)

@compat_router.post("/import/tasks/lpmm_convert")
async def compat_import_lpmm_convert_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_lpmm_convert", payload)

@compat_router.post("/import/temporal_backfill")
async def compat_import_temporal_backfill(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_temporal_backfill", payload)

@compat_router.post("/import/tasks/temporal_backfill")
async def compat_import_temporal_backfill_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_temporal_backfill", payload)

@compat_router.post("/import/maibot_migration")
async def compat_import_maibot_migration(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_maibot_migration", payload)

@compat_router.post("/import/tasks/maibot_migration")
async def compat_import_maibot_migration_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_maibot_migration", payload)

@compat_router.get("/import/tasks")
async def compat_import_list(limit: int = Query(50, ge=1, le=200)):
    return await _import_list(limit)

@compat_router.get("/import/tasks/{task_id}")
async def compat_import_get(task_id: str, include_chunks: bool = Query(False)):
    return await _import_get(task_id, include_chunks)

@compat_router.get("/import/tasks/{task_id}/chunks/{file_id}")
async def compat_import_chunks(
    task_id: str,
    file_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await _import_chunks(task_id, file_id, offset, limit)

@compat_router.get("/import/tasks/{task_id}/files/{file_id}/chunks")
async def compat_import_file_chunks(
    task_id: str,
    file_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await _import_chunks(task_id, file_id, offset, limit)

@compat_router.post("/import/tasks/{task_id}/cancel")
async def compat_import_cancel(task_id: str):
    return await _import_cancel(task_id)

@compat_router.post("/import/tasks/{task_id}/retry")
async def compat_import_retry(task_id: str, payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_retry(task_id, payload)

@compat_router.post("/import/tasks/{task_id}/retry_failed")
async def compat_import_retry_failed(task_id: str, payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_retry(task_id, payload)

@compat_router.get("/retrieval_tuning/settings")
async def compat_tuning_settings():
    return await _tuning_settings()

@compat_router.get("/retrieval_tuning/profile")
async def compat_tuning_profile():
    return await _tuning_profile()

@compat_router.post("/retrieval_tuning/profile/apply")
async def compat_apply_tuning_profile(payload: TuningApplyProfileRequest):
    return await _tuning_apply_profile(payload)

@compat_router.post("/retrieval_tuning/profile/rollback")
async def compat_rollback_tuning_profile():
    return await _tuning_rollback_profile()

@compat_router.get("/retrieval_tuning/profile/export")
async def compat_export_tuning_profile():
    return await _tuning_export_profile()

@compat_router.get("/retrieval_tuning/profile/export_toml")
async def compat_export_tuning_profile_toml():
    return await _tuning_export_profile()

@compat_router.post("/retrieval_tuning/tasks")
async def compat_create_tuning_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _tuning_create_task(payload)

@compat_router.get("/retrieval_tuning/tasks")
async def compat_list_tuning_tasks(limit: int = Query(50, ge=1, le=200)):
    return await _tuning_list_tasks(limit)

@compat_router.get("/retrieval_tuning/tasks/{task_id}")
async def compat_get_tuning_task(task_id: str, include_rounds: bool = Query(False)):
    return await _tuning_get_task(task_id, include_rounds)

@compat_router.get("/retrieval_tuning/tasks/{task_id}/rounds")
async def compat_get_tuning_rounds(
    task_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await _tuning_get_rounds(task_id, offset, limit)

@compat_router.post("/retrieval_tuning/tasks/{task_id}/cancel")
async def compat_cancel_tuning_task(task_id: str):
    return await _tuning_cancel(task_id)

@compat_router.post("/retrieval_tuning/tasks/{task_id}/apply_best")
async def compat_apply_best_tuning_profile(
    task_id: str,
    payload: TuningApplyBestRequest = Body(default_factory=TuningApplyBestRequest),  # noqa: B008  # FastAPI Body/File 依赖注入默认值
):
    return await _tuning_apply_best(task_id, payload)

@compat_router.post("/retrieval_tuning/tasks/{task_id}/apply-best")
async def compat_apply_best_tuning_profile_kebab(
    task_id: str,
    payload: TuningApplyBestRequest = Body(default_factory=TuningApplyBestRequest),  # noqa: B008  # FastAPI Body/File 依赖注入默认值
):
    return await _tuning_apply_best(task_id, payload)

@compat_router.get("/retrieval_tuning/tasks/{task_id}/report")
async def compat_get_tuning_report(task_id: str, format: str = Query("md")):
    return await _tuning_report(task_id, format)
