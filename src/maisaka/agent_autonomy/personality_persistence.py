"""性格持久化 — AgentSelfModification 表的读写。

保存运行时性格修改到数据库，启动时合并 YAML 初始值和数据库增量。
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentSelfModification
from src.common.logger import get_logger
from src.maisaka.agent.config import PersonalityLayer

logger = get_logger("maisaka.personality_persistence")


@dataclass
class AgentSelfModificationRead:
    """数据库修改记录的只读快照。"""
    id: int
    agent_id: str
    layer: str
    field: str
    modification_text: str
    trigger: str
    created_at: datetime | None = None


class PersonalityPersistence:
    """性格持久化服务 — AgentSelfModification 表的读写。"""

    async def save_modification(
        self,
        agent_id: str,
        layer: PersonalityLayer,
        field: str,
        modification_text: str,
        trigger: str,
    ) -> None:
        """写入 AgentSelfModification 表。

        计算 old_value_hash 和 new_value_hash（SHA-256）。
        数据库写入失败时：日志记录错误，修改仍在本会话内生效。
        """
        new_hash = hashlib.sha256(modification_text.encode()).hexdigest()

        try:
            async with get_db_session() as session:
                record = AgentSelfModification(
                    agent_id=agent_id,
                    layer=layer.value,
                    field=field,
                    modification_text=modification_text,
                    trigger=trigger,
                    old_value_hash="",
                    new_value_hash=new_hash,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(record)
                await session.commit()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '性格修改持久化失败: agent=%s layer=%s: %s', exception=exc)
            logger.error(
                "性格修改持久化失败: agent=%s layer=%s: %s",
                agent_id, layer.value, exc,
                exc_info=True,
            )

    async def load_modifications(
        self, agent_id: str,
    ) -> list[AgentSelfModificationRead]:
        """查询未覆盖的修改（overridden_by_yaml=False）。"""
        try:
            async with get_db_session() as session:
                result = await session.exec(
                    select(AgentSelfModification)
                    .where(AgentSelfModification.agent_id == agent_id)
                    .where(AgentSelfModification.overridden_by_yaml == False)  # noqa: E712
                    .order_by(AgentSelfModification.created_at)
                )
                rows = result.all()
                return [
                    AgentSelfModificationRead(
                        id=row.id or 0,
                        agent_id=str(row.agent_id),
                        layer=str(row.layer),
                        field=str(row.field),
                        modification_text=str(row.modification_text),
                        trigger=str(row.trigger),
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '性格修改加载失败: agent=%s: %s', exception=exc)
            logger.warning(
                "性格修改加载失败: agent=%s: %s", agent_id, exc,
            )
            return []

    def merge_with_yaml(
        self, yaml_text: str, db_modifications: list[AgentSelfModificationRead],
    ) -> str:
        """YAML 初始值 + 数据库增量合并。

        合并策略：YAML 文本在前，数据库增量追加（用"，"连接）。
        如果 YAML 文本为空，直接使用增量文本。
        """
        if not db_modifications:
            return yaml_text

        parts: list[str] = [yaml_text] if yaml_text.strip() else []
        for mod in db_modifications:
            text = mod.modification_text.strip()
            if not text:
                continue
            # 避免重复追加相同内容
            if not any(text in p for p in parts):
                parts.append(text)

        return "，".join(parts)

    async def mark_overridden_by_yaml(
        self, agent_id: str, layer: PersonalityLayer,
    ) -> None:
        """管理员修改 YAML 后标记旧数据库修改为已覆盖。"""
        try:
            async with get_db_session() as session:
                result = await session.exec(
                    select(AgentSelfModification)
                    .where(AgentSelfModification.agent_id == agent_id)
                    .where(AgentSelfModification.layer == layer.value)
                    .where(AgentSelfModification.overridden_by_yaml == False)  # noqa: E712
                )
                rows = result.all()
                for row in rows:
                    row.overridden_by_yaml = True
                await session.commit()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '标记覆盖失败: agent=%s layer=%s: %s', exception=exc)
            logger.error(
                "标记覆盖失败: agent=%s layer=%s: %s",
                agent_id, layer.value, exc,
                exc_info=True,
            )
