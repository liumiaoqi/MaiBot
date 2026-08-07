"""人物信息管理 Service 层（WebUI 专用）

从 routers/person.py 下沉的 ORM 操作函数 + Pydantic 响应模型。
router 层退化为薄包装：HTTP 解析 + session 管理 + 响应包装。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import case
from sqlmodel import col, delete, select

from src.common.database.database_model import PersonInfo


# ── Pydantic 响应模型 ──────────────────────────────────────────────

class PersonInfoResponse(BaseModel):
    """人物信息响应"""

    id: int
    is_known: bool
    person_id: str
    person_name: Optional[str]
    name_reason: Optional[str]
    platform: str
    user_id: str
    nickname: Optional[str]
    group_nick_name: Optional[List[Dict[str, str]]]
    memory_points: Optional[str]
    know_times: Optional[int]
    know_since: Optional[float]
    last_know: Optional[float]


class PersonListResponse(BaseModel):
    """人物列表响应"""

    success: bool
    total: int
    page: int
    page_size: int
    data: List[PersonInfoResponse]


class PersonDetailResponse(BaseModel):
    """人物详情响应"""

    success: bool
    data: PersonInfoResponse


class PersonUpdateRequest(BaseModel):
    """人物信息更新请求"""

    person_name: Optional[str] = None
    name_reason: Optional[str] = None
    nickname: Optional[str] = None
    memory_points: Optional[str] = None
    is_known: Optional[bool] = None


class PersonUpdateResponse(BaseModel):
    """人物信息更新响应"""

    success: bool
    message: str
    data: Optional[PersonInfoResponse] = None


class PersonDeleteResponse(BaseModel):
    """人物删除响应"""

    success: bool
    message: str


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""

    person_ids: List[str]


class BatchDeleteResponse(BaseModel):
    """批量删除响应"""

    success: bool
    message: str
    deleted_count: int
    failed_count: int
    failed_ids: List[str] = []


# ── 纯转换函数 ──────────────────────────────────────────────────────

def parse_group_nick_name(group_nick_name_str: Optional[str]) -> Optional[List[Dict[str, str]]]:
    """解析群昵称 JSON 字符串。"""
    if not group_nick_name_str:
        return None
    try:
        return json.loads(group_nick_name_str)
    except (json.JSONDecodeError, TypeError):
        return None


def person_to_response(person: PersonInfo) -> PersonInfoResponse:
    """将人物信息模型转换为响应对象。"""
    know_since = person.first_known_time.timestamp() if person.first_known_time else None
    last_know = person.last_known_time.timestamp() if person.last_known_time else None
    return PersonInfoResponse(
        id=person.id or 0,
        is_known=person.is_known,
        person_id=person.person_id,
        person_name=person.person_name,
        name_reason=person.name_reason,
        platform=person.platform,
        user_id=person.user_id,
        nickname=person.user_nickname,
        group_nick_name=parse_group_nick_name(person.group_cardname),
        memory_points=person.memory_points,
        know_times=person.know_counts,
        know_since=know_since,
        last_know=last_know,
    )


# ── ORM 操作函数（接收 session 参数，不自行创建 session）──────────

def get_person_list(
    session: Any,
    page: int,
    page_size: int,
    search: Optional[str],
    is_known: Optional[bool],
    platform: Optional[str],
) -> tuple[list[PersonInfoResponse], int]:
    """获取人物信息列表（分页）。

    Returns:
        (data, total): data 为 PersonInfoResponse 列表，total 为总条数。
    """
    statement = select(PersonInfo)

    if search:
        statement = statement.where(
            (col(PersonInfo.person_name).contains(search))
            | (col(PersonInfo.user_nickname).contains(search))
            | (col(PersonInfo.user_id).contains(search))
        )

    if is_known is not None:
        statement = statement.where(col(PersonInfo.is_known) == is_known)

    if platform:
        statement = statement.where(col(PersonInfo.platform) == platform)

    statement = statement.order_by(
        case((col(PersonInfo.last_known_time).is_(None), 1), else_=0),
        col(PersonInfo.last_known_time).desc(),
    )

    offset = (page - 1) * page_size
    statement = statement.offset(offset).limit(page_size)

    persons = session.exec(statement).all()

    count_statement = select(PersonInfo.id)
    if search:
        count_statement = count_statement.where(
            (col(PersonInfo.person_name).contains(search))
            | (col(PersonInfo.user_nickname).contains(search))
            | (col(PersonInfo.user_id).contains(search))
        )
    if is_known is not None:
        count_statement = count_statement.where(col(PersonInfo.is_known) == is_known)
    if platform:
        count_statement = count_statement.where(col(PersonInfo.platform) == platform)
    total = len(session.exec(count_statement).all())
    data = [person_to_response(person) for person in persons]

    return data, total


def get_person_stats(session: Any) -> Dict[str, Any]:
    """获取人物信息统计数据。

    Returns:
        Dict[str, Any]: 人物总数、已认识数量和平台分布统计。
    """
    total = len(session.exec(select(PersonInfo.id)).all())
    known = len(session.exec(select(PersonInfo.id).where(col(PersonInfo.is_known))).all())
    unknown = total - known

    platforms: Dict[str, int] = {}
    for platform in session.exec(select(PersonInfo.platform)).all():
        if platform:
            platforms[platform] = platforms.get(platform, 0) + 1

    return {"total": total, "known": known, "unknown": unknown, "platforms": platforms}


def get_person_detail(session: Any, person_id: str) -> Optional[PersonInfoResponse]:
    """获取人物详细信息。

    Returns:
        PersonInfoResponse 或 None（未找到时）。
    """
    statement = select(PersonInfo).where(col(PersonInfo.person_id) == person_id).limit(1)
    person = session.exec(statement).first()
    if not person:
        return None
    return person_to_response(person)


def update_person(session: Any, person_id: str, update_data: Dict[str, Any]) -> Optional[PersonInfoResponse]:
    """增量更新人物信息。

    Args:
        session: 数据库会话。
        person_id: 人物唯一 ID。
        update_data: 需要更新的字段字典。

    Returns:
        更新后的 PersonInfoResponse 或 None（未找到时）。
    """
    db_person = session.exec(select(PersonInfo).where(col(PersonInfo.person_id) == person_id).limit(1)).first()
    if not db_person:
        return None
    if "person_name" in update_data:
        db_person.person_name = update_data["person_name"]
    if "name_reason" in update_data:
        db_person.name_reason = update_data["name_reason"]
    if "nickname" in update_data:
        db_person.user_nickname = update_data["nickname"]
    if "memory_points" in update_data:
        db_person.memory_points = update_data["memory_points"]
    if "is_known" in update_data:
        db_person.is_known = update_data["is_known"]
    db_person.last_known_time = update_data["last_known_time"]
    session.add(db_person)
    return person_to_response(db_person)


def delete_person(session: Any, person_id: str) -> Optional[str]:
    """删除人物信息。

    Returns:
        被删除人物的显示名称，或 None（未找到时）。
    """
    statement = select(PersonInfo).where(col(PersonInfo.person_id) == person_id).limit(1)
    person = session.exec(statement).first()
    if not person:
        return None

    person_name = person.person_name or person.user_nickname or person.user_id
    session.exec(delete(PersonInfo).where(col(PersonInfo.person_id) == person_id))
    return person_name


def batch_delete_persons(
    session: Any,
    person_ids: List[str],
) -> tuple[int, int, list[str]]:
    """批量删除人物信息。

    Returns:
        (deleted_count, failed_count, failed_ids)
    """
    deleted_count = 0
    failed_count = 0
    failed_ids: list[str] = []

    for person_id in person_ids:
        person = session.exec(
            select(PersonInfo).where(col(PersonInfo.person_id) == person_id).limit(1)
        ).first()
        if person:
            session.exec(delete(PersonInfo).where(col(PersonInfo.person_id) == person_id))
            deleted_count += 1
        else:
            failed_count += 1
            failed_ids.append(person_id)

    return deleted_count, failed_count, failed_ids
