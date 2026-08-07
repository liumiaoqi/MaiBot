"""表达方式管理 API 路由 — 薄包装层

ORM 操作已下沉至 src/webui/services/expression_service_web.py。
router 仅负责：HTTP 解析 + session 管理 + 响应包装 + 错误处理。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from src.common.database.database import get_db_session
from src.common.logger import get_logger
from src.core.session_port_registry import get_existing_session_info
from src.learners.expression_review_store import get_ai_review_log
from src.maisaka.replyer.expression_vector_index import normalize_text
from src.webui.dependencies import require_auth
from src.webui.services.expression_service_web import (
    BatchDeleteRequest,
    BatchReviewItem,
    BatchReviewRequest,
    BatchReviewResponse,
    BatchReviewResultItem,
    ChatInfo,
    ChatListResponse,
    ExpressionClearRequest,
    ExpressionClearResponse,
    ExpressionClusterListResponse,
    ExpressionClusterMemberListResponse,
    ExpressionClusterMemberResponse,
    ExpressionCreateRequest,
    ExpressionCreateResponse,
    ExpressionDeleteResponse,
    ExpressionDetailResponse,
    ExpressionExportItem,
    ExpressionExportRequest,
    ExpressionExportResponse,
    ExpressionGroupInfo,
    ExpressionGroupListResponse,
    ExpressionImportRequest,
    ExpressionImportResponse,
    ExpressionListResponse,
    ExpressionResponse,
    ExpressionReviewLogApproveResponse,
    ExpressionReviewLogListResponse,
    ExpressionReviewStatusRequest,
    ExpressionUpdateRequest,
    ExpressionUpdateResponse,
    LegacyExpressionImportPreviewRequest,
    LegacyExpressionImportPreviewResponse,
    LegacyExpressionImportRequest,
    LegacyExpressionImportResponse,
    ReviewListResponse,
    ReviewStatsResponse,
    approve_expression_review_log_data,
    build_legacy_preview,
    check_expression_exists,
    clear_expressions_data,
    connect_legacy_sqlite,
    create_expression_data,
    delete_expression_data,
    delete_expressions_by_ids,
    export_expressions_data,
    find_cluster_summary,
    find_expression_ids,
    get_chat_list_data,
    get_chat_targets_data,
    get_cluster_summaries,
    get_expression_detail_data,
    get_expression_groups_data,
    get_expression_list_data,
    get_expression_list_filter_ids,
    get_expression_review_logs_data,
    get_expression_stats_data,
    get_review_list_data,
    get_review_stats_data,
    import_expressions_data,
    import_legacy_expressions_data,
    load_legacy_expressions,
    read_expression_vector_index_payload,
    review_single_expression,
    save_legacy_db_upload,
    cleanup_legacy_db_upload,
    update_expression_data,
    expression_cluster_member_to_response,
)

logger = get_logger("webui.expression")
EXCLUDE_IDS_QUERY = Query(None, description="需要排除的表达方式 ID")
EXPRESSION_CHAT_IDS_QUERY = Query(None, description="multiple chat ids")
LEGACY_EXPRESSION_IMPORT_FILE = File(...)

# 创建路由器
router = APIRouter(prefix="/expression", tags=["Expression"], dependencies=[Depends(require_auth)])


def require_existing_chat_id(chat_id: Optional[str]) -> str:
    """校验资源归属的聊天流 ID 必须是真实存在的会话。"""

    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 ID")
    if get_existing_session_info(normalized_chat_id) is None:
        raise HTTPException(status_code=400, detail=f"聊天流不存在: {normalized_chat_id}")
    return normalized_chat_id


def require_non_empty_chat_id(chat_id: Optional[str]) -> str:
    """校验聊天流 ID 非空，不要求会话仍存在。"""

    normalized_chat_id = str(chat_id or "").strip()
    if not normalized_chat_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 ID")
    return normalized_chat_id


@router.get("/chats", response_model=ChatListResponse)
async def get_chat_list(
    include_legacy: bool = Query(False, description="是否显示旧格式/非当前账号的表达方式聊天流"),
) -> ChatListResponse:
    """获取所有聊天列表。

    Returns:
        ChatListResponse: 可用于下拉选择的聊天列表。
    """
    try:
        with get_db_session() as session:
            chat_list = get_chat_list_data(session, include_legacy)

        return ChatListResponse(success=True, data=chat_list)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取聊天列表失败', exception=e)
        logger.exception(f"获取聊天列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取聊天列表失败: {str(e)}") from e


@router.get("/chat-targets", response_model=ChatListResponse)
async def get_chat_targets(
    include_legacy: bool = Query(False, description="是否显示旧格式/非当前账号的聊天流"),
) -> ChatListResponse:
    """获取可作为导入目标的全部已知聊天流。"""

    try:
        with get_db_session() as session:
            chat_list = get_chat_targets_data(session, include_legacy)

        return ChatListResponse(success=True, data=chat_list)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取导入目标聊天流失败', exception=e)
        logger.exception(f"获取导入目标聊天流失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取导入目标聊天流失败: {str(e)}") from e


@router.get("/groups", response_model=ExpressionGroupListResponse)
async def get_expression_groups(
    include_legacy: bool = Query(False, description="是否显示旧格式/非当前账号的表达方式"),
) -> ExpressionGroupListResponse:
    """获取已解析的表达共享组。"""
    try:
        with get_db_session() as session:
            groups = get_expression_groups_data(session, include_legacy)

        return ExpressionGroupListResponse(success=True, data=groups)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取表达共享组失败', exception=e)
        logger.exception(f"获取表达共享组失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取表达共享组失败: {str(e)}") from e


@router.get("/clusters", response_model=ExpressionClusterListResponse)
async def get_expression_clusters() -> ExpressionClusterListResponse:
    """获取表达向量聚类摘要。"""

    try:
        index_path, payload = read_expression_vector_index_payload()
        if payload is None:
            return ExpressionClusterListResponse(index_exists=False, index_path=str(index_path))

        return ExpressionClusterListResponse(
            index_exists=True,
            index_path=str(index_path),
            generated_at=normalize_text(payload.get("generated_at")) or None,
            updated_at=normalize_text(payload.get("updated_at")) or None,
            embedding_model=normalize_text(payload.get("embedding_model")) or None,
            embedding_dimension=int(payload.get("embedding_dimension") or 0) or None,
            sample_count=int(payload.get("sample_count") or 0),
            clusters=get_cluster_summaries(payload),
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取表达聚类失败', exception=e)
        logger.exception(f"获取表达聚类失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取表达聚类失败: {str(e)}") from e


@router.get("/clusters/{cluster_id}/members", response_model=ExpressionClusterMemberListResponse)
async def get_expression_cluster_members(
    cluster_id: int,
    profile_marker: Optional[str] = Query(None, description="embedding profile marker"),
) -> ExpressionClusterMemberListResponse:
    """获取指定表达聚类的完整成员列表。"""

    try:
        _, payload = read_expression_vector_index_payload()
        if payload is None:
            return ExpressionClusterMemberListResponse(cluster=None, data=[])

        clusters = get_cluster_summaries(payload)
        cluster = find_cluster_summary(clusters, cluster_id=cluster_id, profile_marker=profile_marker)
        if cluster is None:
            raise HTTPException(status_code=404, detail=f"未找到表达聚类: {cluster_id}")

        members: List[ExpressionClusterMemberResponse] = []
        for raw_expression in payload.get("expressions") or []:
            if not isinstance(raw_expression, dict):
                continue
            if int(raw_expression.get("cluster_id") or 0) != cluster_id:
                continue
            raw_profile_marker = normalize_text(raw_expression.get("embedding_profile_marker"))
            if cluster.embedding_profile_marker and raw_profile_marker != cluster.embedding_profile_marker:
                continue
            members.append(expression_cluster_member_to_response(raw_expression))
        members.sort(key=lambda item: (-item.count, item.id))

        return ExpressionClusterMemberListResponse(cluster=cluster, data=members)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取表达聚类成员失败', exception=e)
        logger.exception(f"获取表达聚类成员失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取表达聚类成员失败: {str(e)}") from e


@router.get("/list", response_model=ExpressionListResponse)
async def get_expression_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    chat_id: Optional[str] = Query(None, description="聊天ID筛选"),
    chat_ids: Optional[List[str]] = EXPRESSION_CHAT_IDS_QUERY,
    review_filter: str = Query("all", description="表达方式筛选: all/user_checked/unchecked"),
    sort_by: str = Query("time", description="表达方式排序: time"),
    include_legacy: bool = Query(False, description="是否显示旧格式/非当前账号的表达方式"),
) -> ExpressionListResponse:
    """获取表达方式列表。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页数量，范围为 1-100。
        search: 搜索关键词，用于匹配情景和风格。
        chat_id: 聊天 ID 筛选条件。

    Returns:
        ExpressionListResponse: 分页后的表达方式列表。
    """
    try:
        # 构建查询
        if sort_by != "time":
            raise HTTPException(status_code=400, detail=f"不支持的表达方式排序: {sort_by}")

        visible_chat_ids: set[str] = set()
        valid_expression_chat_ids: set[str] = set()
        with get_db_session() as filter_session:
            visible_chat_ids, valid_expression_chat_ids = get_expression_list_filter_ids(
                filter_session, include_legacy
            )
        if not include_legacy:
            if chat_id:
                if chat_id not in visible_chat_ids:
                    return ExpressionListResponse(success=True, total=0, page=page, page_size=page_size, data=[])
            elif chat_ids:
                chat_ids = [item for item in chat_ids if item in visible_chat_ids]
                if not chat_ids:
                    return ExpressionListResponse(success=True, total=0, page=page, page_size=page_size, data=[])
            elif not visible_chat_ids:
                return ExpressionListResponse(success=True, total=0, page=page, page_size=page_size, data=[])

        with get_db_session() as session:
            data, total = get_expression_list_data(
                session,
                page,
                page_size,
                search,
                chat_id,
                chat_ids,
                review_filter,
                include_legacy,
                visible_chat_ids,
                valid_expression_chat_ids,
            )

        return ExpressionListResponse(success=True, total=total, page=page, page_size=page_size, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取表达方式列表失败', exception=e)
        logger.exception(f"获取表达方式列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取表达方式列表失败: {str(e)}") from e


@router.post("/export", response_model=ExpressionExportResponse)
async def export_expressions(request: ExpressionExportRequest) -> ExpressionExportResponse:
    """按单个聊天流导出表达方式，导出内容不包含 session_id。"""

    try:
        chat_id = require_non_empty_chat_id(request.chat_id)

        with get_db_session() as session:
            items, chat_name = export_expressions_data(session, chat_id, request.ids)

        return ExpressionExportResponse(
            exported_at=datetime.now().isoformat(),
            source_chat_name=chat_name,
            count=len(items),
            expressions=items,
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '导出表达方式失败', exception=e)
        logger.exception(f"导出表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出表达方式失败: {str(e)}") from e


@router.post("/import", response_model=ExpressionImportResponse)
async def import_expressions(request: ExpressionImportRequest) -> ExpressionImportResponse:
    """将表达方式 JSON 导入到指定聊天流。"""

    try:
        chat_id = require_existing_chat_id(request.chat_id)
        if not request.expressions:
            raise HTTPException(status_code=400, detail="导入文件中没有表达方式")

        with get_db_session() as session:
            imported_count, skipped_count, failed_count = import_expressions_data(
                session, chat_id, request.expressions
            )

        logger.info(
            f"导入表达方式完成: chat_id={chat_id}, imported={imported_count}, "
            f"skipped={skipped_count}, failed={failed_count}"
        )
        return ExpressionImportResponse(
            message=f"导入完成：成功 {imported_count} 个，跳过 {skipped_count} 个，失败 {failed_count} 个",
            imported_count=imported_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '导入表达方式失败', exception=e)
        logger.exception(f"导入表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"导入表达方式失败: {str(e)}") from e


@router.post("/clear", response_model=ExpressionClearResponse)
async def clear_expressions(request: ExpressionClearRequest) -> ExpressionClearResponse:
    """清除指定聊天流下的全部表达方式，允许清除旧的无效 session_id 数据。"""

    try:
        chat_id = require_non_empty_chat_id(request.chat_id)
        with get_db_session() as session:
            deleted_count = clear_expressions_data(session, chat_id)

        logger.info(f"清除聊天流表达方式完成: chat_id={chat_id}, deleted={deleted_count}")
        return ExpressionClearResponse(message=f"成功清除 {deleted_count} 个表达方式", deleted_count=deleted_count)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '清除表达方式失败', exception=e)
        logger.exception(f"清除表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"清除表达方式失败: {str(e)}") from e


@router.post("/legacy-import/preview", response_model=LegacyExpressionImportPreviewResponse)
async def preview_legacy_expression_import(
    request: LegacyExpressionImportPreviewRequest,
) -> LegacyExpressionImportPreviewResponse:
    """预览旧版数据库表达方式导入分组。"""

    try:
        return build_legacy_preview(request.db_path)
    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.exception(f"读取旧版表达方式数据库失败: {e}")
        raise HTTPException(status_code=400, detail=f"读取旧版表达方式数据库失败: {str(e)}") from e
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '预览旧版表达方式导入失败', exception=e)
        logger.exception(f"预览旧版表达方式导入失败: {e}")
        raise HTTPException(status_code=500, detail=f"预览旧版表达方式导入失败: {str(e)}") from e


@router.post("/legacy-import/preview-file", response_model=LegacyExpressionImportPreviewResponse)
async def preview_legacy_expression_import_file(
    file: UploadFile = LEGACY_EXPRESSION_IMPORT_FILE,
) -> LegacyExpressionImportPreviewResponse:
    """上传旧版数据库文件并预览表达方式导入分组。"""

    try:
        db_path = await save_legacy_db_upload(file)
        return build_legacy_preview(str(db_path))
    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.exception(f"读取上传的旧版表达方式数据库失败: {e}")
        raise HTTPException(status_code=400, detail=f"读取上传的旧版表达方式数据库失败: {str(e)}") from e
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '预览上传旧版表达方式导入失败', exception=e)
        logger.exception(f"预览上传旧版表达方式导入失败: {e}")
        raise HTTPException(status_code=500, detail=f"预览上传旧版表达方式导入失败: {str(e)}") from e


@router.post("/legacy-import/import", response_model=LegacyExpressionImportResponse)
async def import_legacy_expressions(request: LegacyExpressionImportRequest) -> LegacyExpressionImportResponse:
    """按预览后的映射从旧版数据库导入表达方式。"""

    try:
        mapping_by_old_chat_id: Dict[str, List[str]] = {}
        for mapping in request.mappings:
            target_chat_ids = mapping.target_chat_ids or ([mapping.target_chat_id] if mapping.target_chat_id else [])
            valid_target_chat_ids = []
            for target_chat_id in target_chat_ids:
                valid_chat_id = require_existing_chat_id(target_chat_id)
                if valid_chat_id not in valid_target_chat_ids:
                    valid_target_chat_ids.append(valid_chat_id)
            if valid_target_chat_ids:
                mapping_by_old_chat_id[mapping.old_chat_id] = valid_target_chat_ids
        if not mapping_by_old_chat_id:
            raise HTTPException(status_code=400, detail="没有可导入的聊天映射")

        with connect_legacy_sqlite(request.db_path) as connection:
            expression_rows, expression_columns = load_legacy_expressions(connection)

        with get_db_session() as session:
            imported_count, skipped_count, failed_count, ignored_group_count = import_legacy_expressions_data(
                session, expression_rows, expression_columns, mapping_by_old_chat_id
            )

        message = (
            f"旧版导入完成：成功 {imported_count} 个，跳过 {skipped_count} 个，"
            f"失败 {failed_count} 个，未导入分组 {ignored_group_count} 个"
        )
        logger.info(message)
        cleanup_legacy_db_upload(request.db_path)
        return LegacyExpressionImportResponse(
            message=message,
            imported_count=imported_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            ignored_group_count=ignored_group_count,
        )

    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.exception(f"读取旧版表达方式数据库失败: {e}")
        raise HTTPException(status_code=400, detail=f"读取旧版表达方式数据库失败: {str(e)}") from e
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '导入旧版表达方式失败', exception=e)
        logger.exception(f"导入旧版表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"导入旧版表达方式失败: {str(e)}") from e


@router.get("/{expression_id}", response_model=ExpressionDetailResponse)
async def get_expression_detail(expression_id: int) -> ExpressionDetailResponse:
    """获取表达方式详细信息。

    Args:
        expression_id: 表达方式 ID。

    Returns:
        ExpressionDetailResponse: 指定表达方式的详细信息。
    """
    try:
        with get_db_session() as session:
            data = get_expression_detail_data(session, expression_id)
            if not data:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {expression_id} 的表达方式")

        return ExpressionDetailResponse(success=True, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取表达方式详情失败', exception=e)
        logger.exception(f"获取表达方式详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取表达方式详情失败: {str(e)}") from e


@router.post("/", response_model=ExpressionCreateResponse)
async def create_expression(
    request: ExpressionCreateRequest,
) -> ExpressionCreateResponse:
    """创建新的表达方式。

    Args:
        request: 创建表达方式所需的请求数据。

    Returns:
        ExpressionCreateResponse: 创建结果和新表达方式数据。
    """
    try:
        current_time = datetime.now()
        chat_id = require_existing_chat_id(request.chat_id)

        # 创建表达方式
        with get_db_session() as session:
            expression_id, data = create_expression_data(
                session, request.situation, request.style, chat_id, current_time
            )

        logger.info(f"表达方式已创建: ID={expression_id}, situation={request.situation}")

        return ExpressionCreateResponse(success=True, message="表达方式创建成功", data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '创建表达方式失败', exception=e)
        logger.exception(f"创建表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建表达方式失败: {str(e)}") from e


@router.patch("/{expression_id}", response_model=ExpressionUpdateResponse)
async def update_expression(
    expression_id: int,
    request: ExpressionUpdateRequest,
) -> ExpressionUpdateResponse:
    """增量更新表达方式。

    Args:
        expression_id: 表达方式 ID。
        request: 只包含需要更新字段的请求数据。

    Returns:
        ExpressionUpdateResponse: 更新结果和更新后的表达方式数据。
    """
    try:
        # 只更新提供的字段
        update_data = request.model_dump(exclude_unset=True)

        # 映射 API 字段名到数据库字段名
        if "chat_id" in update_data:
            update_data["session_id"] = require_existing_chat_id(update_data.pop("chat_id"))

        if not update_data:
            raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")

        # 更新最后活跃时间
        update_data["last_active_time"] = datetime.now()

        # 执行更新
        with get_db_session() as session:
            data = update_expression_data(session, expression_id, update_data)
            if not data:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {expression_id} 的表达方式")

        logger.info(f"表达方式已更新: ID={expression_id}, 字段: {list(update_data.keys())}")

        return ExpressionUpdateResponse(success=True, message=f"成功更新 {len(update_data)} 个字段", data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '更新表达方式失败', exception=e)
        logger.exception(f"更新表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新表达方式失败: {str(e)}") from e


@router.patch("/{expression_id}/review-status", response_model=ExpressionUpdateResponse)
async def update_expression_review_status(
    expression_id: int,
    request: ExpressionReviewStatusRequest,
) -> ExpressionUpdateResponse:
    """切换表达方式的人工审核状态，不删除表达方式。"""

    try:
        current_time = datetime.now()
        with get_db_session() as session:
            data = update_expression_review_status_data(
                session, expression_id, request.approved, current_time
            )
            if not data:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {expression_id} 的表达方式")

        message = "已设为人工通过" if request.approved else "已设为拒绝"
        logger.info(f"表达方式审核状态已更新: ID={expression_id}, approved={request.approved}")
        return ExpressionUpdateResponse(success=True, message=message, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '更新表达方式审核状态失败', exception=e)
        logger.exception(f"更新表达方式审核状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新表达方式审核状态失败: {str(e)}") from e


@router.delete("/{expression_id}", response_model=ExpressionDeleteResponse)
async def delete_expression(expression_id: int) -> ExpressionDeleteResponse:
    """删除表达方式。

    Args:
        expression_id: 表达方式 ID。

    Returns:
        ExpressionDeleteResponse: 删除结果。
    """
    try:
        with get_db_session() as session:
            situation = delete_expression_data(session, expression_id)
            if situation is None:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {expression_id} 的表达方式")

        logger.info(f"表达方式已删除: ID={expression_id}, situation={situation}")

        return ExpressionDeleteResponse(success=True, message=f"成功删除表达方式: {situation}")

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '删除表达方式失败', exception=e)
        logger.exception(f"删除表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除表达方式失败: {str(e)}") from e


@router.post("/batch/delete", response_model=ExpressionDeleteResponse)
async def batch_delete_expressions(
    request: BatchDeleteRequest,
) -> ExpressionDeleteResponse:
    """批量删除表达方式。

    Args:
        request: 包含要删除表达方式 ID 列表的请求。

    Returns:
        ExpressionDeleteResponse: 批量删除结果。
    """
    try:
        if not request.ids:
            raise HTTPException(status_code=400, detail="未提供要删除的表达方式ID")

        # 查找所有要删除的表达方式
        with get_db_session() as session:
            found_ids = find_expression_ids(session, request.ids)

        # 检查是否有未找到的ID
        if not_found_ids := set(request.ids) - set(found_ids):
            logger.warning(f"部分表达方式未找到: {not_found_ids}")

        # 执行批量删除
        with get_db_session() as session:
            deleted_count = delete_expressions_by_ids(session, found_ids)

        logger.info(f"批量删除了 {deleted_count} 个表达方式")

        return ExpressionDeleteResponse(success=True, message=f"成功删除 {deleted_count} 个表达方式")

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '批量删除表达方式失败', exception=e)
        logger.exception(f"批量删除表达方式失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量删除表达方式失败: {str(e)}") from e


@router.get("/stats/summary")
async def get_expression_stats(
    include_legacy: bool = Query(False, description="是否显示旧格式/非当前账号的表达方式"),
) -> Dict[str, Any]:
    """获取表达方式统计数据。

    Returns:
        Dict[str, Any]: 表达方式数量、近期新增和聊天分布统计。
    """
    try:
        with get_db_session() as session:
            stats = get_expression_stats_data(session, include_legacy)

        return {"success": True, "data": stats}

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取统计数据失败', exception=e)
        logger.exception(f"获取统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}") from e


# ============ 审核相关接口 ============


@router.get("/review/stats", response_model=ReviewStatsResponse)
async def get_review_stats() -> ReviewStatsResponse:
    """获取审核统计数据。

    Returns:
        ReviewStatsResponse: 审核统计数据。
    """
    try:
        with get_db_session() as session:
            stats = get_review_stats_data(session)

        return stats

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取审核统计失败', exception=e)
        logger.exception(f"获取审核统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取审核统计失败: {str(e)}") from e


@router.get("/review/list", response_model=ReviewListResponse)
async def get_review_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    filter_type: str = Query("unchecked", description="筛选类型: unchecked/passed/all"),
    order: str = Query("latest", description="排序方式: latest/random"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    chat_id: Optional[str] = Query(None, description="聊天ID筛选"),
    exclude_ids: Optional[List[int]] = EXCLUDE_IDS_QUERY,
) -> ReviewListResponse:
    """获取待审核或已审核的表达方式列表。

    Args:
        page: 页码。
        page_size: 每页数量。
        filter_type: 筛选类型，可选 unchecked、passed 或 all。
        order: 排序方式，可选 latest 或 random。
        search: 搜索关键词。
        chat_id: 聊天 ID 筛选条件。
        exclude_ids: 需要排除的表达方式 ID。

    Returns:
        ReviewListResponse: 审核列表响应。
    """
    try:
        with get_db_session() as session:
            data, total = get_review_list_data(
                session, page, page_size, filter_type, order, search, chat_id, exclude_ids
            )

        return ReviewListResponse(
            success=True,
            total=total,
            page=page,
            page_size=page_size,
            data=data,
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取审核列表失败', exception=e)
        logger.exception(f"获取审核列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取审核列表失败: {str(e)}") from e


@router.get("/review/logs", response_model=ExpressionReviewLogListResponse)
async def get_expression_review_logs(
    limit: int = Query(50, ge=1, le=200, description="返回最近多少条 AI 审核记录"),
    passed: Optional[bool] = Query(None, description="按 AI 审核是否通过筛选"),
    chat_id: Optional[str] = Query(None, description="按聊天流 ID 筛选"),
) -> ExpressionReviewLogListResponse:
    """查看最近的表达方式 AI 审核记录。"""

    try:
        with get_db_session() as session:
            data = get_expression_review_logs_data(session, limit, passed, chat_id)
        return ExpressionReviewLogListResponse(total=len(data), data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取表达方式 AI 审核日志失败', exception=e)
        logger.exception(f"获取表达方式 AI 审核日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取表达方式 AI 审核日志失败: {str(e)}") from e


@router.post("/review/logs/{review_log_id}/approve", response_model=ExpressionReviewLogApproveResponse)
async def approve_expression_review_log(review_log_id: str) -> ExpressionReviewLogApproveResponse:
    """将 AI 审核日志中的表达方式设为人工审核通过，必要时从日志恢复记录。"""

    try:
        review_log = get_ai_review_log(review_log_id)
        if not review_log:
            raise HTTPException(status_code=404, detail=f"未找到审核日志: {review_log_id}")

        session_id = require_non_empty_chat_id(review_log.get("session_id"))
        situation = str(review_log.get("situation")).strip()
        style = str(review_log.get("style")).strip()
        if not situation or not style:
            raise HTTPException(status_code=400, detail="审核日志缺少表达方式内容，无法恢复")

        current_time = datetime.now()

        with get_db_session() as session:
            created, restored_expression_id, data = approve_expression_review_log_data(
                session, review_log, session_id, situation, style, current_time
            )

        if restored_expression_id is None:
            raise HTTPException(status_code=500, detail="表达方式恢复后缺少 ID")

        from src.learners.expression_review_store import append_manual_rescue_log

        append_manual_rescue_log(review_log_id=review_log_id, expression_id=restored_expression_id)
        message = "已从 AI 审核日志救回表达方式并设为人工通过" if created else "已设为人工审核通过"
        logger.info(
            f"表达方式审核日志已人工通过: review_log_id={review_log_id}, "
            f"expression_id={restored_expression_id}, session_id={session_id}"
        )
        return ExpressionReviewLogApproveResponse(message=message, data=data)

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '从表达方式 AI 审核日志恢复失败', exception=e)
        logger.exception(f"从表达方式 AI 审核日志恢复失败: {e}")
        raise HTTPException(status_code=500, detail=f"从表达方式 AI 审核日志恢复失败: {str(e)}") from e


@router.post("/review/batch", response_model=BatchReviewResponse)
async def batch_review_expressions(
    request: BatchReviewRequest,
) -> BatchReviewResponse:
    """批量审核表达方式。

    Args:
        request: 批量审核请求。

    Returns:
        BatchReviewResponse: 每条表达方式的审核结果。
    """
    try:
        if not request.items:
            raise HTTPException(status_code=400, detail="未提供要审核的表达方式")

        results = []
        succeeded = 0
        failed = 0

        for item in request.items:
            try:
                with get_db_session() as session:
                    exists = check_expression_exists(session, item.id)

                if not exists:
                    results.append(
                        BatchReviewResultItem(id=item.id, success=False, message=f"未找到 ID 为 {item.id} 的表达方式")
                    )
                    failed += 1
                    continue

                # 更新状态
                with get_db_session() as session:
                    success = review_single_expression(session, item.id, item.approved)
                    if not success:
                        results.append(
                            BatchReviewResultItem(
                                id=item.id, success=False, message=f"未找到 ID 为 {item.id} 的表达方式"
                            )
                        )
                        failed += 1
                        continue

                results.append(
                    BatchReviewResultItem(id=item.id, success=True, message="通过" if item.approved else "拒绝并删除")
                )
                succeeded += 1

            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '批量审核单项失败', exception=e)
                logger.warning(f"批量审核单项失败: {e}")
                results.append(BatchReviewResultItem(id=item.id, success=False, message=str(e)))
                failed += 1

        logger.info(f"批量审核完成: 成功 {succeeded}, 失败 {failed}")

        return BatchReviewResponse(
            success=True, total=len(request.items), succeeded=succeeded, failed=failed, results=results
        )

    except HTTPException:
        raise
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '批量审核失败', exception=e)
        logger.exception(f"批量审核失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量审核失败: {str(e)}") from e
