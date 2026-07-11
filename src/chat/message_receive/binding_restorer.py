from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentAutonomyActivity, ChatSession
from src.common.logger import get_logger
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent.router import AgentRouter

logger = get_logger("binding_restorer")


class BindingRestorer:
    """智能体绑定恢复 — 启动时从数据库恢复绑定和 Orchestrator 状态。"""

    def __init__(self, agent_router: AgentRouter) -> None:
        self._agent_router = agent_router

    def restore_bindings(self) -> None:
        """从数据库恢复会话-智能体绑定关系到内存路由器。

        两阶段恢复：
        1. 从 ChatSession.agent_id 恢复主发言智能体
        2. 从 AgentAutonomyActivity 恢复所有共居智能体（含手动绑定）
        """
        registry = AgentConfigRegistry()
        restored = 0
        skipped = 0

        with get_db_session() as db:
            statement = select(ChatSession).filter(ChatSession.agent_id.isnot(None))
            for session in db.exec(statement):
                if not registry.has_agent(session.agent_id):
                    logger.warning(f"启动恢复绑定跳过：智能体不存在 session={session.session_id}, agent={session.agent_id}")
                    skipped += 1
                    continue
                try:
                    self._agent_router.bind_session(session.session_id, session.agent_id)
                    restored += 1
                except Exception as e:
                    logger.warning(f"启动恢复绑定失败：session={session.session_id}, agent={session.agent_id}, error={e}")

        cohabitant_restored = 0
        with get_db_session() as db:
            statement = select(AgentAutonomyActivity).filter(
                AgentAutonomyActivity.exited_at.is_(None),
                AgentAutonomyActivity.activation_reason == "manual_binding",
            )
            for activity in db.exec(statement):
                all_agents = self._agent_router.get_session_all_agents(activity.session_id)
                if activity.agent_id in all_agents:
                    continue
                if not registry.has_agent(activity.agent_id):
                    logger.warning(f"启动恢复共居绑定跳过：智能体不存在 session={activity.session_id}, agent={activity.agent_id}")
                    continue
                try:
                    self._agent_router.bind_session(activity.session_id, activity.agent_id)
                    cohabitant_restored += 1
                except Exception as e:
                    logger.warning(f"启动恢复共居绑定失败：session={activity.session_id}, agent={activity.agent_id}, error={e}")

        logger.info(f"启动恢复绑定完成：主发言={restored}, 共居={cohabitant_restored}, 跳过={skipped}")

    def restore_orchestrator(self) -> None:
        """从数据库恢复 Orchestrator 活跃状态"""
        from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        activity_store = AgentActivityStore()
        active_records = activity_store.get_all_active_sessions()

        session_groups: dict[str, list] = {}
        for record in active_records:
            session_groups.setdefault(record.session_id, []).append(record)

        restored_agents = 0
        for session_id, records in session_groups.items():
            orchestrator = AgentOrchestrator.get_by_session(session_id)
            if orchestrator is None:
                continue
            for record in records:
                try:
                    orchestrator.restore_agent(record.agent_id, is_primary=record.is_primary)
                    restored_agents += 1
                except Exception as e:
                    logger.warning(f"启动恢复Orchestrator失败：session={session_id}, agent={record.agent_id}, error={e}")

        logger.info(f"启动恢复Orchestrator完成：恢复智能体={restored_agents}")