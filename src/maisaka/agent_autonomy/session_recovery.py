"""会话恢复服务——重启时从数据库恢复智能体与会话的关联。"""

from __future__ import annotations

from typing import Any

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

logger = get_logger("agent_autonomy.session_recovery")


class SessionRecoveryService:
    """重启时从数据库恢复智能体与会话的关联。

    核心约束：恢复是纯状态重建，不触发任何智能体行为。
    """

    def __init__(self) -> None:
        self._activity_store = AgentActivityStore()
        self._autonomy_logger = AutonomyLogger.get()

    async def recover_all(self, chat_manager: Any) -> dict[str, list[str]]:
        """恢复所有活跃会话的智能体关联（含待命状态恢复）。

        Args:
            chat_manager: ChatManager 实例，用于验证 ChatSession 存在性

        Returns:
            {session_id: [agent_id, ...]} 成功恢复的映射
        """
        active_records = self._activity_store.get_all_active_sessions()

        if not active_records:
            logger.info("[agent_autonomy] 无活跃会话需要恢复")
            return {}

        # 按 session_id 分组
        sessions: dict[str, list[Any]] = {}
        for record in active_records:
            # 验证 ChatSession 仍存在
            chat_session = chat_manager.get_existing_session_by_session_id(record.session_id)
            if chat_session is None:
                self._activity_store.deactivate(
                    record.session_id, record.agent_id, "session_deleted"
                )
                logger.debug(
                    f"[agent_autonomy] 清理已删除会话的活跃记录: "
                    f"session={record.session_id} agent={record.agent_id}"
                )
                continue

            if record.session_id not in sessions:
                sessions[record.session_id] = []
            sessions[record.session_id].append(record)

        # 为每个会话恢复智能体关联
        recovered: dict[str, list[str]] = {}
        for session_id, records in sessions.items():
            try:
                orch = AgentOrchestrator.get_by_session(session_id)
                if orch is None:
                    logger.debug(
                        f"[agent_autonomy] 跳过恢复(无Orchestrator实例，等待runtime初始化): "
                        f"session={session_id}"
                    )
                    continue


                for record in records:
                    # 待命状态的智能体恢复到待命列表
                    if record.state == "standby":
                        orch._vitality_manager.add_to_standby(
                            record.agent_id,
                            session_id,
                            "session_recovery",
                            initial_vitality=record.vitality_value,
                        )
                    else:
                        orch.restore_agent(record.agent_id, record.is_primary)

                    if session_id not in recovered:
                        recovered[session_id] = []
                    recovered[session_id].append(record.agent_id)

            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 恢复会话失败: "
                    f"session={session_id} error={exc}"
                )

        # 日志记录恢复结果
        total_agents = sum(len(v) for v in recovered.values())
        self._autonomy_logger.log(
            "system",
            AutonomyEventType.ORCHESTRATION,
            f"会话恢复完成: {len(recovered)} 个会话, {total_agents} 个智能体",
        )

        return recovered