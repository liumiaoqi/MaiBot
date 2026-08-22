"""记忆管理辅助 Service 层（WebUI 专用）

从 routers/memory.py 下沉的 ORM 辅助函数 + 聊天名称解析。
router 层退化为薄包装：HTTP 解析 + session 管理 + 响应包装。
"""

from typing import Any, Optional

from sqlmodel import col, select

from src.common.database.database_model import ChatSession, Messages, PersonInfo
from src.common.logger import get_logger
from src.core.session_port_registry import (
    get_existing_session_info,
    get_session_name as _get_session_name_via_port,
)
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.memory import (
    ImportChatTarget,
    ImportChatTargetsResponse,
    MemoryTimelineChat,
)

logger = get_logger("auto.memory")


# ── 聊天名称解析辅助 ──────────────────────────────────────────────

def _get_chat_name_from_latest_message(message: Optional[dict[str, Any]]) -> Optional[str]:
    if not message:
        return None
    group_id = str(message.get("group_id") or "").strip()
    if group_id:
        return str(message.get("group_name") or "").strip() or f"群聊{group_id}"
    user_id = str(message.get("user_id")).strip()
    private_name = str(
        message.get("user_cardname") or message.get("user_nickname") or (f"用户{user_id}" if user_id else "")
    ).strip()
    return f"{private_name}的私聊" if private_name else None

def _get_chat_name(chat_session: ChatSession, latest_messages: dict[str, dict[str, Any]]) -> str:
    chat_id = str(chat_session.session_id or "").strip()
    try:
        name = _get_session_name_via_port(chat_id)
        if name and name != chat_id:
            return name
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '获取聊天名称失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
    if name := _get_chat_name_from_latest_message(latest_messages.get(chat_id)):
        return name
    if chat_session.group_name:
        return chat_session.group_name
    if chat_session.group_id:
        return f"群聊{chat_session.group_id}"
    private_name = chat_session.user_cardname or chat_session.user_nickname or (
        f"用户{chat_session.user_id}" if chat_session.user_id else ""
    )
    return f"{private_name}的私聊" if private_name else chat_id


# ── ORM 辅助函数（接收 session 参数，不自行创建 session）──────────

def _prefetch_latest_messages_by_session(db_session: Any, session_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not session_ids:
        return {}

    statement = (
        select(Messages)
        .where(col(Messages.session_id).in_(session_ids))
        .order_by(col(Messages.session_id).asc(), col(Messages.timestamp).desc())
    )
    latest: dict[str, dict[str, Any]] = {}
    for message in db_session.exec(statement).all():
        chat_id = str(message.session_id or "").strip()
        if chat_id and chat_id not in latest:
            latest[chat_id] = {
                "group_id": message.group_id,
                "group_name": message.group_name,
                "user_id": message.user_id,
                "user_cardname": message.user_cardname,
                "user_nickname": message.user_nickname,
            }
    return latest

def _validate_import_chat_id(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    # str(None) 陷阱：缺 chat_id 时 str(None)="None" 非空，误入存在性校验（踩坑 16 第 5 次）
    chat_id = str(normalized.get("chat_id") or "").strip()
    if not chat_id:
        normalized.pop("chat_id", None)
        return normalized
    try:
        if get_existing_session_info(chat_id) is not None:
            normalized["chat_id"] = chat_id
            return normalized
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '校验导入聊天流 ID 失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
    chat_session = session.exec(select(ChatSession).where(col(ChatSession.session_id) == chat_id)).first()
    if chat_session is None:
        raise AppError(ErrorCode.PARAM_INVALID, f"聊天流不存在: {chat_id}", http_status=400)
    normalized["chat_id"] = chat_id
    return normalized

def _find_real_chat_session(session: Any, chat_id: str) -> Optional[ChatSession]:
    token = str(chat_id or "").strip()
    if not token:
        return None
    try:
        managed_session = get_existing_session_info(token)
        if managed_session is not None:
            return session.exec(select(ChatSession).where(col(ChatSession.session_id) == token)).first()
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '查找真实聊天流失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
    return session.exec(select(ChatSession).where(col(ChatSession.session_id) == token)).first()

def _timeline_chat_from_session(session: Any, chat_session: ChatSession) -> MemoryTimelineChat:
    chat_id = str(chat_session.session_id or "").strip()
    latest_messages: dict[str, dict[str, Any]] = {}
    try:
        latest_messages = _prefetch_latest_messages_by_session(session, [chat_id])
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '构建时间线聊天记录失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
        latest_messages = {}
    return MemoryTimelineChat(
        chat_id=chat_id,
        chat_name=_get_chat_name(chat_session, latest_messages),
        platform=getattr(chat_session, "platform", None),
        group_id=getattr(chat_session, "group_id", None),
        user_id=getattr(chat_session, "user_id", None),
        is_group=bool(getattr(chat_session, "group_id", None)),
    )

async def _import_chat_targets(session: Any) -> ImportChatTargetsResponse:
    try:
        rows = list(
            session.exec(
                select(ChatSession).order_by(
                    col(ChatSession.last_active_timestamp).desc(),
                    col(ChatSession.created_timestamp).desc(),
                )
            ).all()
        )
        session_ids = [str(chat_session.session_id or "").strip() for chat_session in rows]
        latest_messages = _prefetch_latest_messages_by_session(session, [item for item in session_ids if item])
        targets = [
            ImportChatTarget(
                chat_id=chat_session.session_id,
                chat_name=_get_chat_name(chat_session, latest_messages),
                platform=chat_session.platform,
                group_id=chat_session.group_id,
                user_id=chat_session.user_id,
                account_id=chat_session.account_id,
                scope=chat_session.scope,
                is_group=bool(chat_session.group_id),
                last_active_at=chat_session.last_active_timestamp.timestamp()
                if chat_session.last_active_timestamp
                else None,
            )
            for chat_session in rows
            if str(chat_session.session_id or "").strip()
        ]
        return ImportChatTargetsResponse(success=True, data=targets)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, '获取导入聊天流失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
        raise AppError(ErrorCode.SYS_INTERNAL_ERROR, f"获取导入聊天流失败: {exc}", http_status=500) from exc

def _get_person_name_for_person_id(session: Any, person_id: str) -> str:
    clean_person_id = str(person_id or "").strip()
    if not clean_person_id:
        return ""
    try:
        statement = select(PersonInfo.person_name).where(col(PersonInfo.person_id) == clean_person_id).limit(1)
        person_name = session.exec(statement).first()
        return str(person_name or "").strip()
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, '获取人物名称失败', exception=exc)
        logger.warning("操作异常 in memory", exc_info=True)
        return ""