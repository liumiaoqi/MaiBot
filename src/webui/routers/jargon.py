"""黑话（俚语）管理 API 路由 — 薄包装层

ORM 操作已下沉至 src/webui/services/jargon_service_web.py。
router 仅负责：HTTP 解析 + session 管理 + 响应包装 + 错误处理。
"""

from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.common.database.database import get_db_session
from src.common.logger import get_logger
from src.webui.dependencies import require_auth
from src.webui.services.jargon_service_web import (
    BatchDeleteRequest,
    ChatInfoResponse,
    ChatListResponse,
    JargonCreateRequest,
    JargonCreateResponse,
    JargonDeleteResponse,
    JargonDetailResponse,
    JargonListResponse,
    JargonResponse,
    JargonStatsResponse,
    JargonUpdateRequest,
    JargonUpdateResponse,
    batch_delete_jargons as _batch_delete_jargons,
    batch_set_jargon_status as _batch_set_jargon_status,
    create_jargon as _create_jargon,
    delete_jargon as _delete_jargon,
    get_chat_list as _get_chat_list,
    get_jargon_detail as _get_jargon_detail,
    get_jargon_list as _get_jargon_list,
    get_jargon_stats as _get_jargon_stats,
    require_existing_session_ids,
    update_jargon as _update_jargon,
)

logger = get_logger("webui.jargon")

router = APIRouter(prefix="/jargon", tags=["Jargon"], dependencies=[Depends(require_auth)])


# ==================== API 端点 ====================


@router.get("/list", response_model=JargonListResponse)
async def get_jargon_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    session_id: Optional[str] = Query(None, description="按聊天流ID筛选"),
    jargon_status: Optional[Literal["confirmed_jargon", "confirmed_not_jargon", "manual_jargon", "pending"]] = Query(
        None,
        description="按黑话判定状态筛选",
    ),
    is_jargon: Optional[bool] = Query(None, description="按是否是黑话筛选"),
    is_complete: Optional[bool] = Query(None, description="按是否推断完成筛选"),
    is_global: Optional[bool] = Query(None, description="按是否全局筛选"),
) -> JargonListResponse:
    """获取黑话列表。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页数量，范围为 1-100。
        search: 搜索关键词。
        session_id: 聊天流 ID 筛选条件。
        jargon_status: 黑话判定状态筛选条件。
        is_jargon: 是否为黑话的筛选条件。
        is_complete: 是否推断完成的筛选条件。
        is_global: 是否为全局黑话的筛选条件。

    Returns:
        JargonListResponse: 分页后的黑话列表。
    """
    try:
        with get_db_session() as session:
            data, total = _get_jargon_list(
                session,
                page,
                page_size,
                search,
                session_id,
                jargon_status,
                is_jargon,
                is_complete,
                is_global,
            )

        return JargonListResponse(
            success=True,
            total=total,
            page=page,
            page_size=page_size,
            data=data,
        )

    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "获取黑话列表失败", exception=e)
        logger.error(f"获取黑话列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取黑话列表失败: {str(e)}") from e


@router.get("/chats", response_model=ChatListResponse)
async def get_chat_list(include_empty: bool = Query(False, description="是否包含没有黑话记录的聊天流")) -> ChatListResponse:
    """获取可用于黑话新增、编辑和筛选的聊天流列表。

    Returns:
        ChatListResponse: 已知真实聊天流，以及旧黑话记录中保留的聊天流。
    """
    try:
        with get_db_session() as session:
            data = _get_chat_list(session, include_empty)

        return ChatListResponse(success=True, data=data)

    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "获取聊天列表失败", exception=e)
        logger.error(f"获取聊天列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取聊天列表失败: {str(e)}") from e


@router.get("/stats/summary", response_model=JargonStatsResponse)
async def get_jargon_stats() -> JargonStatsResponse:
    """获取黑话统计数据。

    Returns:
        JargonStatsResponse: 黑话总数、确认状态和聊天分布统计。
    """
    try:
        with get_db_session() as session:
            stats = _get_jargon_stats(session)

        return JargonStatsResponse(success=True, data=stats)

    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "获取黑话统计失败", exception=e)
        logger.error(f"获取黑话统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取黑话统计失败: {str(e)}") from e


@router.get("/{jargon_id}", response_model=JargonDetailResponse)
async def get_jargon_detail(jargon_id: int) -> JargonDetailResponse:
    """获取黑话详情。

    Args:
        jargon_id: 黑话记录 ID。

    Returns:
        JargonDetailResponse: 指定黑话记录的详细信息。
    """
    try:
        with get_db_session() as session:
            data = _get_jargon_detail(session, jargon_id)
            if not data:
                raise HTTPException(status_code=404, detail="黑话不存在")

        return JargonDetailResponse(success=True, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "获取黑话详情失败", exception=e)
        logger.error(f"获取黑话详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取黑话详情失败: {str(e)}") from e


@router.post("/", response_model=JargonCreateResponse)
async def create_jargon(request: JargonCreateRequest) -> JargonCreateResponse:
    """创建黑话。

    Args:
        request: 创建黑话所需的请求数据。

    Returns:
        JargonCreateResponse: 创建结果和新黑话数据。
    """
    try:
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="黑话内容不能为空")
        meaning = (request.meaning or "").strip()

        raw_session_ids = request.session_ids if request.session_ids is not None else [request.session_id]
        session_ids = require_existing_session_ids(raw_session_ids)

        with get_db_session() as session:
            data = _create_jargon(session, content, meaning, session_ids, request.is_global)

        return JargonCreateResponse(success=True, message="创建成功", data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "创建黑话失败", exception=e)
        logger.error(f"创建黑话失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建黑话失败: {str(e)}") from e


@router.patch("/{jargon_id}", response_model=JargonUpdateResponse)
async def update_jargon(jargon_id: int, request: JargonUpdateRequest) -> JargonUpdateResponse:
    """增量更新黑话。

    Args:
        jargon_id: 黑话记录 ID。
        request: 只包含需要更新字段的请求数据。

    Returns:
        JargonUpdateResponse: 更新结果和更新后的黑话数据。
    """
    try:
        update_data = request.model_dump(exclude_unset=True)

        with get_db_session() as session:
            data = _update_jargon(session, jargon_id, update_data)
            if not data:
                raise HTTPException(status_code=404, detail="黑话不存在")

        return JargonUpdateResponse(success=True, message="更新成功", data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "更新黑话失败", exception=e)
        logger.error(f"更新黑话失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新黑话失败: {str(e)}") from e


@router.delete("/{jargon_id}", response_model=JargonDeleteResponse)
async def delete_jargon(jargon_id: int) -> JargonDeleteResponse:
    """删除黑话。

    Args:
        jargon_id: 黑话记录 ID。

    Returns:
        JargonDeleteResponse: 删除结果。
    """
    try:
        with get_db_session() as session:
            success = _delete_jargon(session, jargon_id)
            if not success:
                raise HTTPException(status_code=404, detail="黑话不存在")

        return JargonDeleteResponse(success=True, message="删除成功", deleted_count=1)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "删除黑话失败", exception=e)
        logger.error(f"删除黑话失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除黑话失败: {str(e)}") from e


@router.post("/batch/delete", response_model=JargonDeleteResponse)
async def batch_delete_jargons(request: BatchDeleteRequest) -> JargonDeleteResponse:
    """批量删除黑话。

    Args:
        request: 包含要删除黑话 ID 列表的请求。

    Returns:
        JargonDeleteResponse: 批量删除结果。
    """
    try:
        if not request.ids:
            raise HTTPException(status_code=400, detail="ID列表不能为空")

        with get_db_session() as session:
            deleted_count = _batch_delete_jargons(session, request.ids)

        return JargonDeleteResponse(
            success=True,
            message=f"成功删除 {deleted_count} 条黑话",
            deleted_count=deleted_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "批量删除黑话失败", exception=e)
        logger.error(f"批量删除黑话失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除黑话失败: {str(e)}") from e


@router.post("/batch/set-jargon", response_model=JargonUpdateResponse)
async def batch_set_jargon_status(
    ids: Annotated[List[int], Query(description="黑话ID列表")],
    is_jargon: Annotated[bool, Query(description="是否是黑话")],
) -> JargonUpdateResponse:
    """批量设置黑话状态。

    Args:
        ids: 需要更新状态的黑话 ID 列表。
        is_jargon: 目标黑话状态。

    Returns:
        JargonUpdateResponse: 批量更新结果。
    """
    try:
        if not ids:
            raise HTTPException(status_code=400, detail="ID列表不能为空")

        with get_db_session() as session:
            updated_count = _batch_set_jargon_status(session, ids, is_jargon)

        return JargonUpdateResponse(success=True, message=f"成功更新 {updated_count} 条黑话状态")

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "批量更新黑话状态失败", exception=e)
        logger.error(f"批量更新黑话状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量更新黑话状态失败: {str(e)}") from e
