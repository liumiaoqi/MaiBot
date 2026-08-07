"""本地聊天室路由 - WebUI 与麦麦直接对话。

ORM 操作已下沉至 src/webui/services/chat_session_service_web.py。
router 仅负责：HTTP 解析 + session 管理 + 响应包装 + 错误处理。
"""

from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.common.database.database import get_db_session
from src.common.logger import get_logger
from src.core.bot_config_port_registry import get_bot_config_port
from src.webui.dependencies import require_auth
from src.webui.services.chat_session_service_web import (
    ChatPromptUpdateRequest,
    ChatTargetResolveBatchRequest,
    ChatTargetResolveItem,
    LearningUpdateRequest,
    TalkFrequencyUpdateRequest,
    chat_session_detail_to_response as _chat_session_detail_to_response,
    delete_chat_prompt_rule as _delete_chat_prompt_rule,
    delete_chat_session_scope as _delete_chat_session_scope,
    delete_chat_talk_frequency_rule as _delete_chat_talk_frequency_rule,
    find_chat_session as _find_chat_session,
    get_available_platforms as _get_available_platforms,
    get_chat_sessions as _get_chat_sessions,
    get_persons_by_platform as _get_persons_by_platform,
    release_deleted_chat_runtime as _release_deleted_chat_runtime,
    resolve_chat_targets as _resolve_chat_targets,
    save_chat_learning_rule as _save_chat_learning_rule,
    save_chat_prompt_rule as _save_chat_prompt_rule,
    save_chat_talk_frequency_rule as _save_chat_talk_frequency_rule,
)

from .service import (
    WEBUI_CHAT_PLATFORM,
    chat_history,
    chat_manager,
    normalize_webui_user_id,
)

logger = get_logger("webui.chat")

router = APIRouter(prefix="/api/webui/chat", tags=["LocalChat"], dependencies=[Depends(require_auth)])


@router.get("/history")
async def get_chat_history(
    limit: int = Query(default=50, ge=1, le=200),
    user_id: Optional[str] = Query(default=None),
    group_id: Optional[str] = Query(default=None),
) -> Dict[str, object]:
    """获取聊天历史记录。

    优先按 ``group_id`` 加载虚拟群聊历史；未提供时使用规范化后的 ``user_id`` 加载 WebUI 私聊历史。
    """
    if group_id:
        history = chat_history.get_history(limit, group_id=group_id)
    else:
        normalized_user_id = normalize_webui_user_id(user_id)
        history = chat_history.get_history(limit, user_id=normalized_user_id)
    return {"success": True, "messages": history, "total": len(history)}


@router.get("/platforms")
async def get_available_platforms() -> Dict[str, object]:
    """获取可用平台列表。"""
    try:
        with get_db_session() as session:
            result = _get_available_platforms(session)

        return {"success": True, "platforms": result}
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取平台列表失败', exception=e)
        logger.error(f"获取平台列表失败: {e}")
        return {"success": False, "error": str(e), "platforms": []}


@router.get("/persons")
async def get_persons_by_platform(
    platform: str = Query(..., description="平台名称"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
    limit: int = Query(default=50, ge=1, le=200),
) -> Dict[str, object]:
    """获取指定平台的用户列表。"""
    try:
        with get_db_session() as session:
            result = _get_persons_by_platform(session, platform, search, limit)

        return {"success": True, "persons": result, "total": len(result)}
    except Exception as e:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取用户列表失败', exception=e)
        logger.error(f"获取用户列表失败: {e}")
        return {"success": False, "error": str(e), "persons": []}


@router.get("/sessions")
async def get_chat_sessions(
    limit: int = Query(default=200, ge=1, le=1000),
    agent_id: Optional[str] = Query(default=None, description="按智能体ID筛选聊天流"),
) -> Dict[str, object]:
    """获取已存在的聊天流列表。"""

    with get_db_session() as session:
        items = _get_chat_sessions(session, limit, agent_id)

    return {"success": True, "sessions": items, "total": len(items)}


@router.get("/resolve-target")
async def resolve_chat_target(
    platform: str = Query(..., description="平台名称"),
    item_id: str = Query(..., description="群号或用户 ID"),
    rule_type: str = Query(default="group", description="聊天类型：group/private"),
) -> Dict[str, object]:
    """按配置目标解析真实聊天流，用于配置页即时校验。"""

    with get_db_session() as session:
        result = _resolve_chat_targets(
            session,
            [ChatTargetResolveItem(platform=platform, item_id=item_id, rule_type=rule_type)]
        )[0]
    return {"success": True, **result}


@router.post("/resolve-targets")
async def resolve_chat_targets(request: ChatTargetResolveBatchRequest) -> Dict[str, object]:
    """批量按配置目标解析真实聊天流，用于配置页即时校验。"""

    with get_db_session() as session:
        results = _resolve_chat_targets(session, request.targets[:200])

    return {"success": True, "results": results}


@router.get("/sessions/{session_id}")
async def get_chat_session_detail(session_id: str) -> Dict[str, object]:
    """获取单个聊天流详情。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        chat_session = _find_chat_session(session, normalized_session_id)

    if chat_session is None:
        raise HTTPException(status_code=404, detail=f"聊天流不存在: {normalized_session_id}")

    return {"success": True, "detail": _chat_session_detail_to_response(chat_session)}


@router.delete("/sessions/{session_id}")
async def delete_chat_session(session_id: str) -> Dict[str, object]:
    """删除聊天流及所有与该 session_id 直接关联的数据。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        jargon_result, items, total_deleted = _delete_chat_session_scope(session, normalized_session_id)

    _release_deleted_chat_runtime(normalized_session_id)
    logger.warning(
        "已删除聊天流及关联数据: "
        f"session_id={normalized_session_id} total_deleted={total_deleted} items={items}"
    )
    return {
        "success": True,
        "session_id": normalized_session_id,
        "deleted_total": total_deleted,
        "jargons": jargon_result,
        "items": items,
    }


@router.put("/sessions/{session_id}/talk-frequency")
async def update_chat_session_talk_frequency(
    session_id: str,
    request: TalkFrequencyUpdateRequest,
) -> Dict[str, object]:
    """为当前聊天流新增或更新一条精确发言频率规则。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        chat_session = _find_chat_session(session, normalized_session_id)

    if chat_session is None:
        raise HTTPException(status_code=404, detail=f"聊天流不存在: {normalized_session_id}")

    await _save_chat_talk_frequency_rule(chat_session, request)
    return {"success": True, "detail": _chat_session_detail_to_response(chat_session)}


@router.delete("/sessions/{session_id}/talk-frequency")
async def delete_chat_session_talk_frequency(
    session_id: str,
    time: Optional[str] = Query(default=None),
) -> Dict[str, object]:
    """删除当前聊天流的一条精确发言频率规则。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        chat_session = _find_chat_session(session, normalized_session_id)

    if chat_session is None:
        raise HTTPException(status_code=404, detail=f"聊天流不存在: {normalized_session_id}")

    await _delete_chat_talk_frequency_rule(chat_session, time)
    return {"success": True, "detail": _chat_session_detail_to_response(chat_session)}


@router.put("/sessions/{session_id}/learning/{kind}")
async def update_chat_session_learning(
    session_id: str,
    kind: str,
    request: LearningUpdateRequest,
) -> Dict[str, object]:
    """为当前聊天流新增或更新一条精确学习配置。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        chat_session = _find_chat_session(session, normalized_session_id)

    if chat_session is None:
        raise HTTPException(status_code=404, detail=f"聊天流不存在: {normalized_session_id}")

    await _save_chat_learning_rule(chat_session, kind, request)
    return {"success": True, "detail": _chat_session_detail_to_response(chat_session)}


@router.put("/sessions/{session_id}/prompts")
async def upsert_chat_session_prompt(
    session_id: str,
    request: ChatPromptUpdateRequest,
    index: Optional[int] = Query(default=None, ge=0),
) -> Dict[str, object]:
    """为当前聊天流新增或更新一条专属 Prompt。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        chat_session = _find_chat_session(session, normalized_session_id)

    if chat_session is None:
        raise HTTPException(status_code=404, detail=f"聊天流不存在: {normalized_session_id}")

    await _save_chat_prompt_rule(chat_session, index, request)
    return {"success": True, "detail": _chat_session_detail_to_response(chat_session)}


@router.delete("/sessions/{session_id}/prompts/{index}")
async def delete_chat_session_prompt(session_id: str, index: int) -> Dict[str, object]:
    """删除当前聊天流的一条专属 Prompt。"""

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=400, detail="缺少聊天流 session_id")

    with get_db_session() as session:
        chat_session = _find_chat_session(session, normalized_session_id)

    if chat_session is None:
        raise HTTPException(status_code=404, detail=f"聊天流不存在: {normalized_session_id}")

    await _delete_chat_prompt_rule(chat_session, index)
    return {"success": True, "detail": _chat_session_detail_to_response(chat_session)}


@router.delete("/history")
async def clear_chat_history(
    user_id: Optional[str] = Query(default=None),
    group_id: Optional[str] = Query(default=None),
) -> Dict[str, object]:
    """清空聊天历史记录。

    优先按 ``group_id`` 清理虚拟群聊历史；未提供时使用规范化后的 ``user_id`` 清理 WebUI 私聊历史。
    """
    if group_id:
        deleted = chat_history.clear_history(group_id=group_id)
    else:
        normalized_user_id = normalize_webui_user_id(user_id)
        deleted = chat_history.clear_history(user_id=normalized_user_id)
    return {"success": True, "message": f"已清空 {deleted} 条聊天记录"}


@router.get("/info")
async def get_chat_info() -> Dict[str, object]:
    """获取聊天室信息。"""
    return {
        "bot_name": get_bot_config_port().get_bot_nickname(),
        "platform": WEBUI_CHAT_PLATFORM,
        "active_sessions": len(chat_manager.active_connections),
    }


compat_router = APIRouter(tags=["LocalChat (Compat)"], dependencies=[Depends(require_auth)])


def _build_compat_routes():
    for route in router.routes:
        compat_path = route.path.replace("/api/webui/chat", "/api/chat", 1) if route.path.startswith("/api/webui/chat") else route.path
        compat_router.add_api_route(
            path=compat_path,
            endpoint=route.endpoint,
            methods=list(route.methods),
        )


_build_compat_routes()
