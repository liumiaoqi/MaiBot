from datetime import datetime

from sqlalchemy import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentInteractionRelationship as AIRTable
from src.common.logger import get_logger

from src.core.adapters.agent_config_port import get_agent_config_provider
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead

logger = get_logger("agent_interaction.relationship_manager")

# Hebbian 共激活参数（CC 原型实验推荐值）
_COACTIVATION_DELTA_COPRESENCE = 0.08
_COACTIVATION_DELTA_MENTION = 0.12
_COACTIVATION_DECAY_RATE = 0.02  # 每小时衰减率，半衰期 ~34.7h
_COACTIVATION_MAX = 1.0


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
        coactivation_strength=row.coactivation_strength,
        last_coactivation_at=row.last_coactivation_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentRelationshipManager:
    """智能体间交互关系管理"""

    def __init__(self) -> None:
        self._registry = get_agent_config_provider()

    async def initialize_from_config(self) -> None:
        agents = self._registry.list_agents()
        with get_db_session() as session:
            for agent in agents:
                for rel in agent.internal_relationships:
                    exists = session.execute(
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

    async def update_coactivation(
        self, agent_id: str, target_agent_id: str, delta: float
    ) -> None:
        """更新 Hebbian 共激活强度。

        delta 由交互类型决定：共在场 +0.08，互相提及 +0.12。
        先应用时间衰减，再累加增量，上限 1.0。
        """
        import time as _time

        now = _time.time()
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return

            # 先衰减
            hours_elapsed = (now - row.last_coactivation_at) / 3600.0
            if hours_elapsed > 0 and row.coactivation_strength > 0:
                import math
                row.coactivation_strength *= math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)

            # 累加增量
            row.coactivation_strength = min(_COACTIVATION_MAX, row.coactivation_strength + delta)
            row.last_coactivation_at = now
            row.updated_at = datetime.now()
            session.commit()

    async def decay_coactivations(self, agent_id: str) -> int:
        """批量衰减指定智能体所有关系的共激活强度。

        由心跳调度器定期调用。返回衰减的行数。
        """
        import math
        import time as _time

        now = _time.time()
        decayed = 0
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(AIRTable.agent_id == agent_id)
            )
            rows = result.scalars().all()
            for row in rows:
                if row.coactivation_strength <= 0:
                    continue
                hours_elapsed = (now - row.last_coactivation_at) / 3600.0
                if hours_elapsed <= 0:
                    continue
                new_strength = row.coactivation_strength * math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)
                # 低于 0.001 视为归零
                row.coactivation_strength = 0.0 if new_strength < 0.001 else new_strength
                row.last_coactivation_at = now
                row.updated_at = datetime.now()
                decayed += 1
            if decayed > 0:
                session.commit()
        return decayed

    async def get_coactivation(self, agent_id: str, target_agent_id: str) -> float:
        """获取共激活强度（先衰减再返回）。"""
        import math
        import time as _time

        now = _time.time()
        with get_db_session() as session:
            result = session.execute(
                select(AIRTable).where(
                    AIRTable.agent_id == agent_id,
                    AIRTable.target_agent_id == target_agent_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return 0.0
            hours_elapsed = (now - row.last_coactivation_at) / 3600.0
            if hours_elapsed > 0 and row.coactivation_strength > 0:
                return row.coactivation_strength * math.exp(-_COACTIVATION_DECAY_RATE * hours_elapsed)
            return row.coactivation_strength