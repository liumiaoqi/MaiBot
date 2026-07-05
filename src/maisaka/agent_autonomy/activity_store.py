from datetime import datetime

from src.common.database.database import get_db_session
from src.common.database.database_model import (
    AgentAutonomyActivity,
    AgentAutonomyBehaviorIntent,
    AgentAutonomyInterjectionEvent,
    AgentAutonomySpeakerChangeRecord,
)
from src.common.logger import get_logger

logger = get_logger("agent_autonomy.activity_store")


class AgentActivityStore:
    """智能体活跃状态持久化。"""

    def get_all_active_sessions(self) -> list[AgentAutonomyActivity]:
        """查询所有未退出的活跃记录（用于重启恢复）。"""
        with get_db_session() as session:
            return list(
                session.query(AgentAutonomyActivity)
                .filter(AgentAutonomyActivity.exited_at.is_(None))
                .all()
            )

    def save_activity(
        self,
        session_id: str,
        agent_id: str,
        is_primary: bool = False,
        activation_reason: str = "session_create",
    ) -> str:
        """持久化活跃状态记录。"""
        with get_db_session() as session:
            activity = AgentAutonomyActivity(
                session_id=session_id,
                agent_id=agent_id,
                is_primary=is_primary,
                activation_reason=activation_reason,
                activated_at=datetime.now(),
                last_spoke_at=datetime.now(),
            )
            session.add(activity)
            session.commit()
            return f"activity:{session_id}:{agent_id}"

    def get_active_agents(self, session_id: str) -> list[AgentAutonomyActivity]:
        """获取会话的活跃智能体列表。"""
        with get_db_session() as session:
            return list(
                session.query(AgentAutonomyActivity)
                .filter(
                    AgentAutonomyActivity.session_id == session_id,
                    AgentAutonomyActivity.exited_at.is_(None),
                )
                .all()
            )

    def get_primary_agent(self, session_id: str) -> AgentAutonomyActivity | None:
        """获取会话的主发言智能体。"""
        with get_db_session() as session:
            return (
                session.query(AgentAutonomyActivity)
                .filter(
                    AgentAutonomyActivity.session_id == session_id,
                    AgentAutonomyActivity.is_primary == True,  # noqa: E712
                    AgentAutonomyActivity.exited_at.is_(None),
                )
                .first()
            )

    def update_last_spoke(self, session_id: str, agent_id: str) -> None:
        """更新智能体最近发言时间。"""
        with get_db_session() as session:
            activity = (
                session.query(AgentAutonomyActivity)
                .filter(
                    AgentAutonomyActivity.session_id == session_id,
                    AgentAutonomyActivity.agent_id == agent_id,
                    AgentAutonomyActivity.exited_at.is_(None),
                )
                .first()
            )
            if activity is not None:
                activity.last_spoke_at = datetime.now()
                session.commit()

    def deactivate(self, session_id: str, agent_id: str, reason: str) -> None:
        """记录智能体退场。"""
        with get_db_session() as session:
            activity = (
                session.query(AgentAutonomyActivity)
                .filter(
                    AgentAutonomyActivity.session_id == session_id,
                    AgentAutonomyActivity.agent_id == agent_id,
                    AgentAutonomyActivity.exited_at.is_(None),
                )
                .first()
            )
            if activity is not None:
                activity.exit_reason = reason
                activity.exited_at = datetime.now()
                session.commit()

    def set_primary(self, session_id: str, agent_id: str) -> None:
        """设置主发言智能体。"""
        with get_db_session() as session:
            # 先取消当前主发言
            current_primary = (
                session.query(AgentAutonomyActivity)
                .filter(
                    AgentAutonomyActivity.session_id == session_id,
                    AgentAutonomyActivity.is_primary == True,  # noqa: E712
                    AgentAutonomyActivity.exited_at.is_(None),
                )
                .first()
            )
            if current_primary is not None:
                current_primary.is_primary = False

            # 设置新主发言
            new_primary = (
                session.query(AgentAutonomyActivity)
                .filter(
                    AgentAutonomyActivity.session_id == session_id,
                    AgentAutonomyActivity.agent_id == agent_id,
                    AgentAutonomyActivity.exited_at.is_(None),
                )
                .first()
            )
            if new_primary is not None:
                new_primary.is_primary = True

            session.commit()

    def save_speaker_change(
        self,
        session_id: str,
        from_agent_id: str,
        to_agent_id: str,
        change_type: str,
        change_reason: str,
    ) -> str:
        """持久化发言权变更记录。"""
        import time

        record_id = f"sc:{session_id}:{format(int(time.time()), 'x')}"
        with get_db_session() as session:
            record = AgentAutonomySpeakerChangeRecord(
                record_id=record_id,
                session_id=session_id,
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                change_type=change_type,
                change_reason=change_reason,
            )
            session.add(record)
            session.commit()
            return record_id

    def save_interjection_event(
        self,
        event_id: str,
        agent_id: str,
        session_id: str,
        primary_agent_id: str,
        interjection_type: str,
        trigger_reason: str,
        intent_strength: float,
        content_summary: str = "",
    ) -> str:
        """持久化插话事件记录。"""
        with get_db_session() as session:
            event = AgentAutonomyInterjectionEvent(
                event_id=event_id,
                agent_id=agent_id,
                session_id=session_id,
                primary_agent_id=primary_agent_id,
                interjection_type=interjection_type,
                trigger_reason=trigger_reason,
                intent_strength=intent_strength,
                content_summary=content_summary,
            )
            session.add(event)
            session.commit()
            return event_id

    def save_behavior_intent(
        self,
        intent_id: str,
        agent_id: str,
        session_id: str,
        intent_type: str,
        intent_strength: float,
        intent_source: str,
        source_description: str,
        expired_at: datetime | None = None,
    ) -> str:
        """持久化行为意图记录。"""
        with get_db_session() as session:
            intent = AgentAutonomyBehaviorIntent(
                intent_id=intent_id,
                agent_id=agent_id,
                session_id=session_id,
                intent_type=intent_type,
                intent_strength=intent_strength,
                intent_source=intent_source,
                source_description=source_description,
                expired_at=expired_at,
            )
            session.add(intent)
            session.commit()
            return intent_id