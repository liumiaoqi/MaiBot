"""/proc/health 端点 — 系统健康内省（对标 Linux /proc）。

GET /proc/health — 聚合健康状态（用缓存，不触发检查）
GET /proc/health/detail — 详细健康状态（含各检查器结果）
"""

from fastapi import APIRouter, Depends

from src.webui.dependencies import require_auth
from src.webui.schemas.base import ApiResponse

router = APIRouter(prefix="/proc", tags=["health"], dependencies=[Depends(require_auth)])


@router.get("/health")
async def get_health() -> ApiResponse:
    """聚合健康状态（用缓存，不触发检查）。"""
    from src.core.health_check import get_health_service

    service = get_health_service()
    health = await service.get_health()
    # ⚠️ 这里原来是 `ApiResponse.success(data=...)` —— `ApiResponse` 没有 `success`（只有 code/data/message），
    # 两个 /proc/health 端点因此**自建立起必 500**（2026-10-16 真机探针实测 AttributeError: success）。
    # 全仓同形写法是 `ApiResponse(data=...)`。
    return ApiResponse(
        data={
            "status": health.status.name.lower(),
            "timestamp": health.timestamp,
        }
    )


@router.get("/health/detail")
async def get_health_detail() -> ApiResponse:
    """详细健康状态（含各检查器结果）。"""
    from src.core.health_check import get_health_service

    service = get_health_service()
    detail = await service.get_health_detail()
    return ApiResponse(data=detail)