"""query_person_info 内置工具。"""

from typing import Any, Dict, List, Optional

import json

from sqlmodel import col, select

from src.common.database.database import get_db_session
from src.common.database.database_model import PersonInfo
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec

from .context import BuiltinToolRuntimeContext


def get_tool_spec(*, enabled: bool = False) -> ToolSpec:
    """获取 query_person_info 工具声明。"""

    return ToolSpec(
        name="query_person_info",
        brief_description="查询某个人的档案和相关记忆信息。",
        detailed_description=(
            "参数说明：\n"
            "- person_name：string，必填。人物名称、昵称或用户 ID。\n"
            "- limit：integer，可选。最多返回多少条匹配记录，默认 3。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "person_name": {
                    "type": "string",
                    "description": "人物名称、昵称或用户 ID。",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少条匹配记录。",
                    "default": 3,
                },
            },
            "required": ["person_name"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
        enabled=enabled,
    )


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 query_person_info 内置工具。"""

    del context
    raw_person_name = invocation.arguments.get("person_name")
    raw_limit = invocation.arguments.get("limit", 3)

    if not isinstance(raw_person_name, str):
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "查询人物信息工具需要提供字符串类型的 `person_name` 参数。",
        )

    person_name = raw_person_name.strip()
    if not person_name:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "查询人物信息工具需要提供非空的 `person_name` 参数。",
        )

    try:
        limit = max(1, min(int(raw_limit), 10))
    except (TypeError, ValueError):
        limit = 3

    persons = _query_person_records(person_name, limit)
    result: Dict[str, Any] = {
        "query": person_name,
        "persons": persons,
    }
    return tool_ctx.build_success_result(
        invocation.tool_name,
        json.dumps(result, ensure_ascii=False),
        structured_content=result,
    )


def _query_person_records(person_name: str, limit: int) -> List[Dict[str, Any]]:
    """按名称、昵称或用户 ID 查询人物档案。"""

    with get_db_session() as session:
        records = session.exec(
            select(PersonInfo)
            .where(
                col(PersonInfo.person_name).contains(person_name)
                | col(PersonInfo.user_nickname).contains(person_name)
                | col(PersonInfo.user_id).contains(person_name)
            )
            .order_by(col(PersonInfo.last_known_time).desc(), col(PersonInfo.id).desc())
            .limit(limit)
        ).all()
        persons: List[Dict[str, Any]] = []
        for record in records:
            memory_points: List[str] = []
            if record.memory_points:
                try:
                    parsed_points = json.loads(record.memory_points)
                    if isinstance(parsed_points, list):
                        memory_points = [str(point).strip() for point in parsed_points if str(point).strip()]
                except (json.JSONDecodeError, TypeError, ValueError):
                    memory_points = []

            persons.append(
                {
                    "person_id": record.person_id,
                    "person_name": record.person_name or "",
                    "user_nickname": record.user_nickname,
                    "user_id": record.user_id,
                    "platform": record.platform,
                    "name_reason": record.name_reason or "",
                    "is_known": record.is_known,
                    "know_counts": record.know_counts,
                    "memory_points": memory_points[:20],
                    "last_known_time": record.last_known_time.isoformat() if record.last_known_time is not None else None,
                }
            )

        return persons
