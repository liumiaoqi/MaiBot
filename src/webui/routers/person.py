"""人物信息管理 API 路由 — 薄包装层

ORM 操作已下沉至 src/webui/services/person_service_web.py。
router 仅负责：HTTP 解析 + session 管理 + 响应包装 + 错误处理。
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.common.database.database import get_db_session
from src.common.logger import get_logger
from src.webui.dependencies import require_auth
from src.webui.services.person_service_web import (
    BatchDeleteRequest,
    BatchDeleteResponse,
    PersonDeleteResponse,
    PersonDetailResponse,
    PersonListResponse,
    PersonUpdateRequest,
    PersonUpdateResponse,
    batch_delete_persons,
    delete_person as _delete_person,
    get_person_detail as _get_person_detail,
    get_person_list as _get_person_list,
    get_person_stats as _get_person_stats,
    update_person as _update_person,
)

logger = get_logger("webui.person")

router = APIRouter(prefix="/person", tags=["Person"], dependencies=[Depends(require_auth)])


@router.get("/list", response_model=PersonListResponse)
async def get_person_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    is_known: Optional[bool] = Query(None, description="是否已认识筛选"),
    platform: Optional[str] = Query(None, description="平台筛选"),
) -> PersonListResponse:
    """获取人物信息列表。"""
    try:
        with get_db_session() as session:
            data, total = _get_person_list(session, page, page_size, search, is_known, platform)

        return PersonListResponse(success=True, total=total, page=page, page_size=page_size, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "获取人物列表失败", exception=e)
        logger.exception(f"获取人物列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取人物列表失败: {str(e)}") from e


@router.get("/stats/summary")
async def get_person_stats() -> dict:
    """获取人物信息统计数据。"""
    try:
        with get_db_session() as session:
            stats = _get_person_stats(session)

        return {"success": True, "data": stats}

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "获取统计数据失败", exception=e)
        logger.exception(f"获取统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}") from e


@router.get("/{person_id}", response_model=PersonDetailResponse)
async def get_person_detail(person_id: str) -> PersonDetailResponse:
    """获取人物详细信息。"""
    try:
        with get_db_session() as session:
            data = _get_person_detail(session, person_id)
            if not data:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {person_id} 的人物信息")

        return PersonDetailResponse(success=True, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, f"获取人物详情失败: person_id={person_id}", exception=e)
        logger.exception(f"获取人物详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取人物详情失败: {str(e)}") from e


@router.patch("/{person_id}", response_model=PersonUpdateResponse)
async def update_person(
    person_id: str,
    request: PersonUpdateRequest,
) -> PersonUpdateResponse:
    """增量更新人物信息。"""
    try:
        update_data = request.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")

        update_data["last_known_time"] = datetime.now()

        with get_db_session() as session:
            data = _update_person(session, person_id, update_data)
            if not data:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {person_id} 的人物信息")

        logger.info(f"人物信息已更新: {person_id}, 字段: {list(update_data.keys())}")

        return PersonUpdateResponse(success=True, message=f"成功更新 {len(update_data)} 个字段", data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, f"更新人物信息失败: person_id={person_id}", exception=e)
        logger.exception(f"更新人物信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新人物信息失败: {str(e)}") from e


@router.delete("/{person_id}", response_model=PersonDeleteResponse)
async def delete_person(person_id: str) -> PersonDeleteResponse:
    """删除人物信息。"""
    try:
        with get_db_session() as session:
            person_name = _delete_person(session, person_id)
            if person_name is None:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {person_id} 的人物信息")

        logger.info(f"人物信息已删除: {person_id} ({person_name})")

        return PersonDeleteResponse(success=True, message=f"成功删除人物信息: {person_name}")

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, f"删除人物信息失败: person_id={person_id}", exception=e)
        logger.exception(f"删除人物信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除人物信息失败: {str(e)}") from e


@router.post("/batch/delete", response_model=BatchDeleteResponse)
async def batch_delete_persons(
    request: BatchDeleteRequest,
) -> BatchDeleteResponse:
    """批量删除人物信息。"""
    try:
        if not request.person_ids:
            raise HTTPException(status_code=400, detail="未提供要删除的人物ID")

        with get_db_session() as session:
            deleted_count, failed_count, failed_ids = batch_delete_persons(session, request.person_ids)

        message = f"成功删除 {deleted_count} 个人物"
        if failed_count > 0:
            message += f"，{failed_count} 个失败"

        return BatchDeleteResponse(
            success=True,
            message=message,
            deleted_count=deleted_count,
            failed_count=failed_count,
            failed_ids=failed_ids,
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "批量删除人物信息失败", exception=e)
        logger.exception(f"批量删除人物信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}") from e
