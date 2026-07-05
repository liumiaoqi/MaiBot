import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from src.common.database.database import get_db_session
from src.common.database.database_model import InteractionCooldown as InteractionCooldownTable

logger = logging.getLogger(__name__)


def build_agent_pair_key(agent_a: str, agent_b: str) -> str:
    ids = sorted([agent_a, agent_b])
    return f"{ids[0]}:{ids[1]}"


class InteractionCooldownManager:
    """智能体间交互冷却控制"""

    async def can_trigger(
        self,
        agent_pair_key: str,
        cooldown_minutes: int = 30,
        max_per_hour: int = 2,
        max_per_day: int = 8,
    ) -> bool:
        row = await self._get_or_create(agent_pair_key)
        now = datetime.now()

        if row.hourly_reset_at and now >= row.hourly_reset_at:
            row.interaction_count_hourly = 0
            row.hourly_reset_at = now + timedelta(hours=1)
        if row.daily_reset_at and now >= row.daily_reset_at:
            row.interaction_count_daily = 0
            row.daily_reset_at = now + timedelta(days=1)

        if row.last_interaction_at:
            elapsed = (now - row.last_interaction_at).total_seconds()
            if elapsed < cooldown_minutes * 60:
                return False

        if row.interaction_count_hourly >= max_per_hour:
            return False
        if row.interaction_count_daily >= max_per_day:
            return False

        return True

    async def record_interaction(self, agent_pair_key: str) -> None:
        row = await self._get_or_create(agent_pair_key)
        now = datetime.now()

        row.last_interaction_at = now
        row.interaction_count_hourly += 1
        row.interaction_count_daily += 1

        if row.hourly_reset_at is None or now >= row.hourly_reset_at:
            row.interaction_count_hourly = 1
            row.hourly_reset_at = now + timedelta(hours=1)
        if row.daily_reset_at is None or now >= row.daily_reset_at:
            row.interaction_count_daily = 1
            row.daily_reset_at = now + timedelta(days=1)

        async with get_db_session() as session:
            session.add(row)
            await session.commit()

    async def get_cooldown_remaining(self, agent_pair_key: str, cooldown_minutes: int = 30) -> float:
        row = await self._get_or_create(agent_pair_key)
        if row.last_interaction_at is None:
            return 0.0
        elapsed = (datetime.now() - row.last_interaction_at).total_seconds()
        remaining = cooldown_minutes * 60 - elapsed
        return max(0.0, remaining)

    async def _get_or_create(self, agent_pair_key: str) -> InteractionCooldownTable:
        async with get_db_session() as session:
            result = await session.execute(
                select(InteractionCooldownTable).where(
                    InteractionCooldownTable.agent_pair_key == agent_pair_key
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = InteractionCooldownTable(
                    agent_pair_key=agent_pair_key,
                    interaction_count_hourly=0,
                    interaction_count_daily=0,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row
