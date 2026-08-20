from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.common.database.database import get_db_session
from src.common.database.database_model import InteractionCooldown as InteractionCooldownTable

from src.common.logger import get_logger
logger = get_logger(__name__)


def build_agent_pair_key(agent_a: str, agent_b: str) -> str:
    ids = sorted([agent_a, agent_b])
    return f"{ids[0]}:{ids[1]}"


class InteractionCooldownManager:
    """智能体间交互冷却控制

    P0-3: 全部读写统一为「单 session 内查询-修改-退出自动提交」，
    杜绝 detached ORM 修改不落库问题（主键即 agent_pair_key）。
    """

    async def can_trigger(
        self,
        agent_pair_key: str,
        cooldown_minutes: int = 30,
        max_per_hour: int = 2,
        max_per_day: int = 8,
    ) -> bool:
        with get_db_session() as session:
            row = self._get_or_create_in_session(session, agent_pair_key)
            now = datetime.now()

            if row.hourly_reset_at and now >= row.hourly_reset_at:
                row.interaction_count_hourly = 0
                row.hourly_reset_at = now + timedelta(hours=1)
            if row.daily_reset_at and now >= row.daily_reset_at:
                row.interaction_count_daily = 0
                row.daily_reset_at = now + timedelta(days=1)

            # with 退出统一自动提交 —— 窗口重置修改真实落库
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
        now = datetime.now()
        with get_db_session() as session:
            row = self._get_or_create_in_session(session, agent_pair_key)

            row.last_interaction_at = now
            row.interaction_count_hourly += 1
            row.interaction_count_daily += 1

            if row.hourly_reset_at is None or now >= row.hourly_reset_at:
                row.interaction_count_hourly = 1
                row.hourly_reset_at = now + timedelta(hours=1)
            if row.daily_reset_at is None or now >= row.daily_reset_at:
                row.interaction_count_daily = 1
                row.daily_reset_at = now + timedelta(days=1)
            # with 退出——统一提交，计数/时间戳真实落库

    async def get_cooldown_remaining(self, agent_pair_key: str, cooldown_minutes: int = 30) -> float:
        with get_db_session() as session:
            row = self._get_or_create_in_session(session, agent_pair_key)
            if row.last_interaction_at is None:
                return 0.0
            elapsed = (datetime.now() - row.last_interaction_at).total_seconds()
            remaining = cooldown_minutes * 60 - elapsed
            return max(0.0, remaining)

    @staticmethod
    def _get_or_create_in_session(
        session: Session, agent_pair_key: str
    ) -> InteractionCooldownTable:
        """session 内主键直查 + 建行（P0-3: 不再返回 detached 行）。

        该辅助必须在 with get_db_session() 块内调用，退出自动提交。
        """
        row = session.get(InteractionCooldownTable, agent_pair_key)
        if row is None:
            row = InteractionCooldownTable(
                agent_pair_key=agent_pair_key,
                interaction_count_hourly=0,
                interaction_count_daily=0,
            )
            session.add(row)
            session.flush()  # 获得主键（autoflush=False 下显式 flush）
        return row
