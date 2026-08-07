"""retrieval_tuning 端点（profile/tasks）+ config 端点。"""

from typing import Any

import tomlkit

from fastapi import APIRouter, Body, Depends, Query

from src.common.logger import get_logger
from src.services.memory_service import memory_service
from src.webui.dependencies import require_auth
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.memory import (
    MemoryConfigUpdateRequest,
    MemoryRawConfigUpdateRequest,
    TuningApplyBestRequest,
    TuningApplyProfileRequest,
)
from src.webui.routers.memory_helpers import _unwrap_payload

logger = get_logger("auto.memory")

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# config 辅助函数
# ---------------------------------------------------------------------------

async def _memory_config_schema() -> dict:
    return {
        "success": True,
        "schema": memory_service.get_config_schema(),
        "path": str(memory_service.get_config_path()),
    }

async def _memory_config_get() -> dict:
    return {
        "success": True,
        "config": memory_service.get_config(),
        "path": str(memory_service.get_config_path()),
    }

async def _memory_config_get_raw() -> dict:
    raw_payload = memory_service.get_raw_config_with_meta()
    return {
        "success": True,
        "config": str(raw_payload.get("config", "")),
        "exists": bool(raw_payload.get("exists", False)),
        "using_default": bool(raw_payload.get("using_default", False)),
        "path": str(memory_service.get_config_path()),
    }

async def _memory_config_update(payload: MemoryConfigUpdateRequest) -> dict:
    return await memory_service.update_config(payload.config)

async def _memory_config_update_raw(payload: MemoryRawConfigUpdateRequest) -> dict:
    try:
        tomlkit.loads(payload.config)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '更新记忆配置原始内容失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
        raise AppError(ErrorCode.PARAM_INVALID, f"TOML 格式错误: {exc}", http_status=400) from exc
    return await memory_service.update_raw_config(payload.config)


# ---------------------------------------------------------------------------
# tuning 辅助函数
# ---------------------------------------------------------------------------

async def _tuning_settings() -> dict:
    return await memory_service.tuning_admin(action="get_settings")

async def _tuning_profile() -> dict:
    profile = await memory_service.tuning_admin(action="get_profile")
    if not isinstance(profile, dict):
        profile = {"success": False, "profile": {}}
    if not isinstance(profile.get("settings"), dict):
        settings = await memory_service.tuning_admin(action="get_settings")
        profile["settings"] = settings.get("settings") if isinstance(settings.get("settings"), dict) else {}
    return profile

async def _tuning_apply_profile(payload: TuningApplyProfileRequest) -> dict:
    return await memory_service.tuning_admin(
        action="apply_profile",
        profile=payload.profile,
        reason=payload.reason,
        validate=payload.validate_result,
    )

async def _tuning_rollback_profile() -> dict:
    return await memory_service.tuning_admin(action="rollback_profile")

async def _tuning_export_profile() -> dict:
    return await memory_service.tuning_admin(action="export_profile")

async def _tuning_create_task(payload: dict[str, Any]) -> dict:
    return await memory_service.tuning_admin(action="create_task", payload=_unwrap_payload(payload))

async def _tuning_list_tasks(limit: int) -> dict:
    return await memory_service.tuning_admin(action="list_tasks", limit=limit)

async def _tuning_get_task(task_id: str, include_rounds: bool) -> dict:
    return await memory_service.tuning_admin(action="get_task", task_id=task_id, include_rounds=include_rounds)

async def _tuning_get_rounds(task_id: str, offset: int, limit: int) -> dict:
    return await memory_service.tuning_admin(action="get_rounds", task_id=task_id, offset=offset, limit=limit)

async def _tuning_cancel(task_id: str) -> dict:
    return await memory_service.tuning_admin(action="cancel", task_id=task_id)

async def _tuning_apply_best(task_id: str, payload: TuningApplyBestRequest | None = None) -> dict:
    body = payload or TuningApplyBestRequest()
    result = await memory_service.tuning_admin(
        action="apply_best",
        task_id=task_id,
        validate=body.validate_result,
    )
    if not isinstance(result, dict):
        return {"success": False, "error": "invalid_payload", "persisted": False}
    result.setdefault("persisted", False)
    if not bool(result.get("success", False)) or not body.persist:
        return result

    runtime_payload = await memory_service.runtime_admin(action="get_config")
    runtime_config = runtime_payload.get("config") if isinstance(runtime_payload, dict) else None
    if not isinstance(runtime_config, dict):
        result["persisted"] = False
        result["persist_error"] = "runtime_config_unavailable"
        return result

    try:
        persist_payload = await memory_service.update_config(runtime_config)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '应用记忆调优配置失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
        result["persisted"] = False
        result["persist_error"] = f"persist_failed: {exc}"
        return result
    result["persisted"] = bool(isinstance(persist_payload, dict) and persist_payload.get("success", False))
    result["persist_result"] = persist_payload
    return result

async def _tuning_report(task_id: str, fmt: str) -> dict:
    payload_raw = await memory_service.tuning_admin(action="get_report", task_id=task_id, format=fmt)
    payload = payload_raw if isinstance(payload_raw, dict) else {}
    report_raw = payload.get("report")
    report = report_raw if isinstance(report_raw, dict) else {}
    return {
        "success": bool(payload.get("success", False)),
        "format": report.get("format", fmt),
        "content": report.get("content", ""),
        "path": report.get("path", ""),
        "error": payload.get("error", ""),
    }


# ---------------------------------------------------------------------------
# config 端点
# ---------------------------------------------------------------------------

@router.get("/config/schema")
async def get_memory_config_schema():
    return await _memory_config_schema()

@router.get("/config")
async def get_memory_config():
    return await _memory_config_get()

# C1 raw 例外：结构化配置写入，保留 PUT 语义（整体替换）
@router.put("/config")
async def update_memory_config(payload: MemoryConfigUpdateRequest):
    return await _memory_config_update(payload)

@router.get("/config/raw")
async def get_memory_config_raw():
    return await _memory_config_get_raw()

# C1 raw 例外：原始 TOML 配置写入，合并到单一 raw 例外分类
@router.put("/config/raw")
async def update_memory_config_raw(payload: MemoryRawConfigUpdateRequest):
    return await _memory_config_update_raw(payload)


# ---------------------------------------------------------------------------
# tuning 端点
# ---------------------------------------------------------------------------

@router.get("/retrieval_tuning/settings")
async def get_memory_tuning_settings():
    return await _tuning_settings()

@router.get("/retrieval_tuning/profile")
async def get_memory_tuning_profile():
    return await _tuning_profile()

@router.post("/retrieval_tuning/profile/apply")
async def apply_memory_tuning_profile(payload: TuningApplyProfileRequest):
    return await _tuning_apply_profile(payload)

@router.post("/retrieval_tuning/profile/rollback")
async def rollback_memory_tuning_profile():
    return await _tuning_rollback_profile()

@router.get("/retrieval_tuning/profile/export")
async def export_memory_tuning_profile():
    return await _tuning_export_profile()

@router.post("/retrieval_tuning/tasks")
async def create_memory_tuning_task(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _tuning_create_task(payload)

@router.get("/retrieval_tuning/tasks")
async def list_memory_tuning_tasks(limit: int = Query(50, ge=1, le=200)):
    return await _tuning_list_tasks(limit)

@router.get("/retrieval_tuning/tasks/{task_id}")
async def get_memory_tuning_task(task_id: str, include_rounds: bool = Query(False)):
    return await _tuning_get_task(task_id, include_rounds)

@router.get("/retrieval_tuning/tasks/{task_id}/rounds")
async def get_memory_tuning_rounds(
    task_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await _tuning_get_rounds(task_id, offset, limit)

@router.post("/retrieval_tuning/tasks/{task_id}/cancel")
async def cancel_memory_tuning_task(task_id: str):
    return await _tuning_cancel(task_id)

@router.post("/retrieval_tuning/tasks/{task_id}/apply-best")
async def apply_best_memory_tuning_profile(
    task_id: str,
    payload: TuningApplyBestRequest = Body(default_factory=TuningApplyBestRequest),  # noqa: B008  # FastAPI Body/File 依赖注入默认值
):
    return await _tuning_apply_best(task_id, payload)

@router.get("/retrieval_tuning/tasks/{task_id}/report")
async def get_memory_tuning_report(task_id: str, format: str = Query("md")):
    return await _tuning_report(task_id, format)