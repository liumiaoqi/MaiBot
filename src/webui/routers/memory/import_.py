"""import 端点（上传/粘贴/任务管理）。"""

from pathlib import Path
from typing import Any

import json
import shutil
import uuid

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile

from src.common.database.database import get_db_session
from src.common.logger import get_logger
from src.services.memory_service import memory_service
from src.webui.dependencies import require_auth
from src.webui.schemas.base import ApiResponse
from src.webui.schemas.memory import ImportChatTargetsResponse
from src.webui.services.memory_helper_service_web import (
    _import_chat_targets,
    _validate_import_chat_id,
)
from src.webui.routers.memory_helpers import _unwrap_payload

logger = get_logger("auto.memory")

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])
STAGING_ROOT = Path(__file__).resolve().parents[4] / "data" / "memory_upload_staging"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _build_import_guide_markdown(settings: dict[str, Any]) -> str:
    path_aliases_raw = settings.get("path_aliases")
    path_aliases = path_aliases_raw if isinstance(path_aliases_raw, dict) else {}
    alias_lines = [
        f"- `{name}` -> `{path}`"
        for name, path in sorted(path_aliases.items())
        if str(name).strip() and str(path).strip()
    ]
    if not alias_lines:
        alias_lines = ["- 当前未配置路径别名"]
    return "\n".join(
        [
            "# 长期记忆导入说明",
            "",
            "支持的导入方式：",
            "- 上传文件：适合零散文档、日志、聊天导出文本。",
            "- 粘贴文本：适合一次性导入少量整理好的内容。",
            "- Raw Scan：扫描白名单目录内的原始文本文件。",
            "- LPMM OpenIE / Convert：处理既有 LPMM 数据。",
            "- Temporal Backfill：补回已有数据中的时间信息。",
            "- MaiBot Migration：从宿主数据库迁移历史聊天记忆。",
            "",
            "当前路径别名：",
            *alias_lines,
            "",
            "执行建议：",
            "- 首次导入先小批量试跑，确认切分和抽取结果正常。",
            "- 大批量导入时优先关注任务状态、失败块与重试结果。",
            "- 若路径解析失败，请先检查路径别名与相对路径是否仍然有效。",
        ]
    )

async def _import_settings() -> dict:
    return await memory_service.import_admin(action="get_settings")

async def _import_path_aliases() -> dict:
    return await memory_service.import_admin(action="get_path_aliases")

async def _import_guide() -> dict:
    payload = await memory_service.import_admin(action="get_guide")
    if not isinstance(payload, dict):
        payload = {"success": False, "error": "invalid_payload"}
    if isinstance(payload.get("content"), str):
        return payload

    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else None
    if settings is None:
        settings_payload = await memory_service.import_admin(action="get_settings")
        settings = settings_payload.get("settings") if isinstance(settings_payload.get("settings"), dict) else {}

    return {
        "success": True,
        "source": "local",
        "path": "generated://memory_import_guide",
        "content": _build_import_guide_markdown(settings or {}),
        "settings": settings or {},
    }

async def _import_resolve_path(payload: dict[str, Any]) -> dict:
    return await memory_service.import_admin(action="resolve_path", **_unwrap_payload(payload))

async def _import_create(action: str, payload: dict[str, Any]) -> dict:
    with get_db_session() as session:
        validated = _validate_import_chat_id(session, _unwrap_payload(payload))
    return await memory_service.import_admin(action=action, **validated)

async def _import_list(limit: int) -> dict:
    listing = await memory_service.import_admin(action="list", limit=limit)
    if not isinstance(listing, dict):
        listing = {"success": False, "items": []}
    settings_payload = await memory_service.import_admin(action="get_settings")
    settings = settings_payload.get("settings") if isinstance(settings_payload.get("settings"), dict) else {}
    listing.setdefault("success", True)
    listing.setdefault("items", [])
    listing["settings"] = settings
    return listing

async def _import_get(task_id: str, include_chunks: bool) -> dict:
    return await memory_service.import_admin(action="get", task_id=task_id, include_chunks=include_chunks)

async def _import_chunks(task_id: str, file_id: str, offset: int, limit: int) -> dict:
    return await memory_service.import_admin(
        action="get_chunks",
        task_id=task_id,
        file_id=file_id,
        offset=offset,
        limit=limit,
    )

async def _import_cancel(task_id: str) -> dict:
    return await memory_service.import_admin(action="cancel", task_id=task_id)

async def _import_retry(task_id: str, payload: dict[str, Any]) -> dict:
    raw = _unwrap_payload(payload)
    overrides = raw.get("overrides") if isinstance(raw.get("overrides"), dict) else raw
    return await memory_service.import_admin(action="retry_failed", task_id=task_id, overrides=overrides)

async def _stage_upload_files(files: list[UploadFile]) -> tuple[Path, list[dict[str, Any]]]:
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    staging_dir = STAGING_ROOT / uuid.uuid7().hex
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_files: list[dict[str, Any]] = []
    for index, upload in enumerate(files):
        filename = Path(upload.filename or f"upload_{index}.txt").name
        target = staging_dir / f"{index:03d}_{filename}"
        content = await upload.read()
        target.write_bytes(content)
        staged_files.append(
            {
                "filename": filename,
                "staged_path": str(target.resolve()),
                "size": len(content),
            }
        )
    return staging_dir, staged_files


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/import/settings")
async def get_memory_import_settings():
    return await _import_settings()

@router.get("/import/path-aliases")
async def get_memory_import_path_aliases():
    return await _import_path_aliases()

@router.get("/import/chat-targets", response_model=ApiResponse[ImportChatTargetsResponse])
async def get_memory_import_chat_targets():
    with get_db_session() as session:
        data = await _import_chat_targets(session)
    return ApiResponse(data=data)

@router.get("/import/guide")
async def get_memory_import_guide():
    return await _import_guide()

@router.post("/import/resolve-path")
async def resolve_memory_import_path(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_resolve_path(payload)

@router.post("/import/upload")
async def create_memory_import_upload(
    files: list[UploadFile] = File(...),  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    payload_json: str = Form("{}"),
):
    staging_dir, staged_files = await _stage_upload_files(files)
    try:
        try:
            payload = json.loads(payload_json or "{}")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '创建记忆导入上传失败', exception=exc)
            logger.warning("操作异常 in memory", exc_info=True)
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["staged_files"] = staged_files
        return await _import_create("create_upload", payload)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

@router.post("/import/paste")
async def create_memory_import_paste(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_paste", payload)

@router.post("/import/raw-scan")
async def create_memory_import_raw_scan(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_raw_scan", payload)

@router.post("/import/lpmm-openie")
async def create_memory_import_lpmm_openie(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_lpmm_openie", payload)

@router.post("/import/lpmm-convert")
async def create_memory_import_lpmm_convert(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_lpmm_convert", payload)

@router.post("/import/temporal-backfill")
async def create_memory_import_temporal_backfill(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_temporal_backfill", payload)

@router.post("/import/maibot-migration")
async def create_memory_import_maibot_migration(payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_create("create_maibot_migration", payload)

@router.get("/import/tasks")
async def list_memory_import_tasks(limit: int = Query(50, ge=1, le=200)):
    return await _import_list(limit)

@router.get("/import/tasks/{task_id}")
async def get_memory_import_task(task_id: str, include_chunks: bool = Query(False)):
    return await _import_get(task_id, include_chunks)

@router.get("/import/tasks/{task_id}/chunks/{file_id}")
async def get_memory_import_chunks(
    task_id: str,
    file_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    return await _import_chunks(task_id, file_id, offset, limit)

@router.post("/import/tasks/{task_id}/cancel")
async def cancel_memory_import_task(task_id: str):
    return await _import_cancel(task_id)

@router.post("/import/tasks/{task_id}/retry")
async def retry_memory_import_task(task_id: str, payload: dict[str, Any] = Body(default_factory=dict)):  # noqa: B008  # FastAPI Body/File 依赖注入默认值
    return await _import_retry(task_id, payload)