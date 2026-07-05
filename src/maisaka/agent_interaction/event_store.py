
import logging
import time
from datetime import datetime

from sqlalchemy import select

from src.common.database.database import get_db_session
from src.common.database.database_model import InteractionEvent as InteractionEventTable
from src.maisaka.agent_interaction.models import (
    InteractionEventCreate,
    InteractionEventRead,
)

logger = logging.getLogger(__name__)


def _generate_event_id(agent_id: str) -> str:
    ts = format(int(time.time()), "x")
    rnd = format(hash(f"{agent_id}:{time.time_ns()}") & 0xFFFFFF, "x")
    return f"ie:{agent_id}:{ts}:{rnd}"


def _table_to_read(row: InteractionEventTable) -> InteractionEventRead:
    return InteractionEventRead(
        event_id=row.event_id,
        initiator_agent_id=row.initiator_agent_id,
        target_agent_id=row.target_agent_id,
        interaction_type=row.interaction_type,
        trigger_reason=row.trigger_reason,
        content_summary=row.content_summary,
        emotion_effects=row.emotion_effects,
        relationship_effect=row.relationship_effect,
        memory_write_status=row.memory_write_status,
        echo_depth=row.echo_depth,
        echo_parent_event_id=row.echo_parent_event_id,
        metadata=row.event_metadata,
        created_at=row.created_at,
    )


class InteractionEventStore:
    """智能体间交互事件持久化与查询"""

    async def save_event(self, event_data: InteractionEventCreate) -> str:
        event_id = _generate_event_id(event_data.initiator_agent_id)
        row = InteractionEventTable(
            event_id=event_id,
            initiator_agent_id=event_data.initiator_agent_id,
            target_agent_id=event_data.target_agent_id,
            interaction_type=event_data.interaction_type,
            trigger_reason=event_data.trigger_reason,
            content_summary=event_data.content_summary,
            emotion_effects=event_data.emotion_effects,
            relationship_effect=event_data.relationship_effect,
            memory_write_status=event_data.memory_write_status,
            echo_depth=event_data.echo_depth,
            echo_parent_event_id=event_data.echo_parent_event_id,
            event_metadata=event_data.metadata,
        )
        with get_db_session() as session:
            session.add(row)
            session.commit()

        logger.info(
            "[agent_interaction] %s→%s type=%s reason=%s",
            event_data.initiator_agent_id,
            event_data.target_agent_id,
            event_data.interaction_type,
            event_data.trigger_reason[:80],
        )
        return event_id

    async def get_event(self, event_id: str) -> InteractionEventRead | None:
        with get_db_session() as session:
            result = session.execute(
                select(InteractionEventTable).where(InteractionEventTable.event_id == event_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _table_to_read(row)

    async def query_events(
        self,
        *,
        agent_id: str = "",
        target_agent_id: str = "",
        interaction_type: str = "",
        time_start: datetime | None = None,
        time_end: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InteractionEventRead]:
        with get_db_session() as session:
            stmt = select(InteractionEventTable).order_by(InteractionEventTable.created_at.desc())
            if agent_id:
                stmt = stmt.where(InteractionEventTable.initiator_agent_id == agent_id)
            if target_agent_id:
                stmt = stmt.where(InteractionEventTable.target_agent_id == target_agent_id)
            if interaction_type:
                stmt = stmt.where(InteractionEventTable.interaction_type == interaction_type)
            if time_start:
                stmt = stmt.where(InteractionEventTable.created_at >= time_start)
            if time_end:
                stmt = stmt.where(InteractionEventTable.created_at <= time_end)
            stmt = stmt.limit(limit).offset(offset)
            result = session.execute(stmt)
            rows = result.scalars().all()
            return [_table_to_read(r) for r in rows]

    async def get_recent_events(self, limit: int = 20) -> list[InteractionEventRead]:
        with get_db_session() as session:
            stmt = (
                select(InteractionEventTable)
                .order_by(InteractionEventTable.created_at.desc())
                .limit(limit)
            )
            result = session.execute(stmt)
            rows = result.scalars().all()
            return [_table_to_read(r) for r in rows]