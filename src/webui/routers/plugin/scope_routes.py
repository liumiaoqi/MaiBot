"""Scope 审批 API — 用户通过 WebUI 管理插件的 scope 授权。

提供插件列表、scope 查询、审批/撤销、Token 签发功能。
插件发现通过扫描 plugins/ 目录的 _manifest.json。
"""


import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.common.logger import get_logger
from src.plugin_runtime_v2.scope.vocabulary import ScopeVocabulary
from src.webui.dependencies import require_auth

logger = get_logger("plugin_runtime_v2.scope.webui")

router = APIRouter(prefix="/plugins", tags=["plugin-scopes"], dependencies=[Depends(require_auth)])

_PLUGINS_DIR = Path("plugins")


class ScopeStatus(BaseModel):
    scope: str
    description: str
    risk_level: str
    approval_required: bool
    granted: bool


class PluginScopeInfo(BaseModel):
    plugin_id: str
    plugin_name: str
    plugin_version: str
    requested_scopes: list[ScopeStatus]
    has_token: bool


class ApproveRequest(BaseModel):
    scope: str


class TokenResponse(BaseModel):
    token: str
    plugin_id: str
    expires_in_seconds: int


# ── 插件发现 ──


def _discover_plugins() -> dict[str, dict[str, Any]]:
    """扫描 plugins/ 目录下 _manifest.json，返回 {plugin_id: manifest_data}。"""
    plugins: dict[str, dict[str, Any]] = {}
    if not _PLUGINS_DIR.exists():
        return plugins
    for manifest_path in _PLUGINS_DIR.rglob("_manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # P0-5: manifest 解析失败出声（debug 防刷屏，跳过）（ZG-31）
            logger.debug("manifest 解析失败，跳过 %s: %s", manifest_path, exc)
            continue
        pid = manifest.get("id", "")
        if pid:
            plugins[pid] = manifest
    return plugins


def _get_scope_store(request: Request):
    """从 app.state 获取 ScopeApprovalStore。"""
    return getattr(request.app.state, "scope_store", None)


def _get_token_service(request: Request):
    """从 app.state 获取 TokenService。"""
    return getattr(request.app.state, "token_service", None)


# ── Scope 查询 ──


@router.get("/scopes")
async def list_all_plugin_scopes(request: Request) -> list[PluginScopeInfo]:
    """列出所有已发现插件及其 scope 审批状态。"""
    scope_store = _get_scope_store(request)
    if scope_store is None:
        return JSONResponse(status_code=503, content={"detail": "v2 插件运行时未启用"})
    plugins = _discover_plugins()
    result: list[PluginScopeInfo] = []

    for plugin_id, manifest in plugins.items():
        requested_scopes: list[str] = manifest.get("scopes", [])
        granted = scope_store.get_granted_scopes(plugin_id) if scope_store else set()

        scope_statuses: list[ScopeStatus] = []
        for scope in requested_scopes:
            entry = None
            try:
                entry = ScopeVocabulary.lookup(scope)
            except KeyError as exc:
                # P0-5: scope 查找失败出声（debug 防刷屏，跳过未知 scope）（ZG-31）
                logger.debug("scope 查找失败，跳过 %s: %s", scope, exc)
                continue
            scope_statuses.append(ScopeStatus(
                scope=scope,
                description=entry.description,
                risk_level=entry.risk_level,
                approval_required=entry.approval_required,
                granted=scope in granted,
            ))

        result.append(PluginScopeInfo(
            plugin_id=plugin_id,
            plugin_name=manifest.get("name", plugin_id),
            plugin_version=manifest.get("version", "0.0.0"),
            requested_scopes=scope_statuses,
            has_token=False,
        ))

    return result


@router.get("/{plugin_id}/scopes")
async def get_plugin_scopes(plugin_id: str, request: Request) -> PluginScopeInfo | None:
    """查询单个插件的 scope 审批状态。"""
    scope_store = _get_scope_store(request)
    if scope_store is None:
        return JSONResponse(status_code=503, content={"detail": "v2 插件运行时未启用"})
    plugins = _discover_plugins()
    manifest = plugins.get(plugin_id)
    if manifest is None:
        return None

    requested_scopes: list[str] = manifest.get("scopes", [])
    granted = scope_store.get_granted_scopes(plugin_id)

    scope_statuses: list[ScopeStatus] = []
    for scope in requested_scopes:
        try:
            entry = ScopeVocabulary.lookup(scope)
        except KeyError as exc:
            # P0-5: scope 查找失败出声（debug 防刷屏，跳过未知 scope）（ZG-31）
            logger.debug("scope 查找失败，跳过 %s: %s", scope, exc)
            continue
        scope_statuses.append(ScopeStatus(
            scope=scope,
            description=entry.description,
            risk_level=entry.risk_level,
            approval_required=entry.approval_required,
            granted=scope in granted,
        ))

    return PluginScopeInfo(
        plugin_id=plugin_id,
        plugin_name=manifest.get("name", plugin_id),
        plugin_version=manifest.get("version", "0.0.0"),
        requested_scopes=scope_statuses,
        has_token=False,
    )


# ── Scope 审批操作 ──


@router.post("/{plugin_id}/scopes/approve")
async def approve_scope_endpoint(plugin_id: str, body: ApproveRequest, request: Request) -> dict[str, Any]:
    """批准单个 scope。"""
    scope_store = _get_scope_store(request)
    if scope_store is None:
        return JSONResponse(status_code=503, content={"detail": "v2 插件运行时未启用"})
    scope_store.approve_scope(plugin_id, body.scope, operator="user")
    return {"success": True}


@router.post("/{plugin_id}/scopes/revoke")
async def revoke_scope_endpoint(plugin_id: str, body: ApproveRequest, request: Request) -> dict[str, Any]:
    """撤销单个 scope。"""
    scope_store = _get_scope_store(request)
    if scope_store is None:
        return JSONResponse(status_code=503, content={"detail": "v2 插件运行时未启用"})
    scope_store.revoke_scope(plugin_id, body.scope, operator="user")
    return {"success": True}


@router.post("/{plugin_id}/scopes/approve-all")
async def approve_all_pending_endpoint(plugin_id: str, request: Request) -> dict[str, Any]:
    """自动批准所有 approval_required=False 的 scope。"""
    scope_store = _get_scope_store(request)
    if scope_store is None:
        return JSONResponse(status_code=503, content={"detail": "v2 插件运行时未启用"})
    plugins = _discover_plugins()
    manifest = plugins.get(plugin_id, {})
    count = scope_store.approve_all_pending(
        plugin_id, manifest.get("scopes", []),
    )
    return {"success": True, "approved_count": count}


# ── Token 签发 ──


@router.post("/{plugin_id}/token")
async def issue_token_endpoint(plugin_id: str, request: Request) -> dict[str, Any]:
    """为插件签发一次性 session_token。"""
    token_service = _get_token_service(request)
    if token_service is None:
        return JSONResponse(status_code=503, content={"detail": "v2 插件运行时未启用"})
    token = token_service.issue(plugin_id)
    return {"success": True, "token": token, "plugin_id": plugin_id}
