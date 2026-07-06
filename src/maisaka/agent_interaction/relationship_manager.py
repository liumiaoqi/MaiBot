from datetime import datetime

from sqlalchemy import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentInteractionRelationship as AIRTable

from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead


def _table_to_read(row: AIRTable) -> AgentInteractionRelationshipRead:
    return AgentInteractionRelationshipRead(
        id=row.id,
        agent_id=row.agent_id,
        target_agent_id=row.target_agent_id,
        score=row.score,
        relationship_type=row.relationship_type,
        attitude=row.attitude,
        interaction_count=row.interaction_count,
        last_interaction_at=row.last_interaction_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentRelationshipManager:
    """智能体间交互关系管理"""

    def __init__(self) -> None:
        self._registry = AgentConfigRegistry.get_instance()

    async def initialize_from_config(self) -> None:
        agents = self._registry.list_agents()
        with get_db_session() as session:
            for agent in agents:
                for rel in agent.internal_relationships:
                    exists = await session.execute(
                        select(AIRTable).where(
                            AIRTable.agent_id == agent.agent_id,
                            AIRTable.target_agent_id == rel.target_agent_id,
                        )
                    )
                    if exists.scalar_one_or_none() is not None:
                        continue
                    row = AIRTable(
                        agent_id=agent.agent_id,
                        target_agent_id=rel.target_agent_id,
                        score=rel.mention_tendency * 300,
                        relationship_type=rel.relationship_type,
                        attitude=rel.attitude,
                    )
                    session.add(row)
            session.commit()

    async def get_relationship(
        self, agent_id: str, target_agent_id: str
    ) -> AgentInteractionRelationshipRead | None:
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _table_to_read(row)

    async def update_relationship(
        self, agent_id: str, target_agent_id: str, delta: float
    ) -> AgentInteractionRelationshipRead:
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = AIRTable(
                    agent_id=agent_id,
                    target_agent_id=target_agent_id,
                    score=max(0.0, min(1000.0, delta)),
                    interaction_count=1,
                    last_interaction_at=datetime.now(),
                )
                session.add(row)
            else:
                row.score = max(0.0, min(1000.0, row.score + delta))
                row.interaction_count += 1
                row.last_interaction_at = datetime.now()
                row.updated_at = datetime.now()
            session.commit()
            session.refresh(row)
            return _table_to_read(row)