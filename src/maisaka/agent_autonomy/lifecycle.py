"""智能体生命周期状态机——5 状态 6 转换。"""

from __future__ import annotations

from enum import Enum

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

logger = get_logger("agent_autonomy.lifecycle")


class AgentLifecycleState(Enum):
    """智能体生命周期状态。"""

    REGISTERED = "registered"
    STANDBY = "standby"
    ACTIVE = "active"
    EXITING = "exiting"
    DESTROYED = "destroyed"


_TRANSITIONS: dict[AgentLifecycleState, set[AgentLifecycleState]] = {
    AgentLifecycleState.REGISTERED: {AgentLifecycleState.STANDBY},
    AgentLifecycleState.STANDBY: {AgentLifecycleState.ACTIVE, AgentLifecycleState.DESTROYED},
    AgentLifecycleState.ACTIVE: {AgentLifecycleState.STANDBY, AgentLifecycleState.EXITING},
    AgentLifecycleState.EXITING: {AgentLifecycleState.DESTROYED},
    AgentLifecycleState.DESTROYED: set(),
}

_STATE_TO_ACTIVITY_STATE: dict[AgentLifecycleState, str] = {
    AgentLifecycleState.REGISTERED: "registered",
    AgentLifecycleState.STANDBY: "standby",
    AgentLifecycleState.ACTIVE: "active",
    AgentLifecycleState.EXITING: "exiting",
    AgentLifecycleState.DESTROYED: "destroyed",
}

_ACTIVITY_STATE_TO_LIFECYCLE: dict[str, AgentLifecycleState] = {
    "registered": AgentLifecycleState.REGISTERED,
    "standby": AgentLifecycleState.STANDBY,
    "active": AgentLifecycleState.ACTIVE,
    "exiting": AgentLifecycleState.EXITING,
    "destroyed": AgentLifecycleState.DESTROYED,
    "dormant": AgentLifecycleState.DESTROYED,
}


class AgentLifecycleManager:
    """智能体生命周期状态机管理器。"""

    def __init__(self, activity_store: AgentActivityStore) -> None:
        self._store = activity_store

    def current_state(self, agent_id: str, session_id: str) -> AgentLifecycleState:
        """查询智能体当前生命周期状态。"""
        activities = self._store.get_active_agents(session_id)
        for a in activities:
            if a.agent_id == agent_id:
                activity_state = getattr(a, "state", None)
                if activity_state:
                    return _ACTIVITY_STATE_TO_LIFECYCLE.get(activity_state, AgentLifecycleState.REGISTERED)
                return AgentLifecycleState.ACTIVE
        return AgentLifecycleState.REGISTERED

    def can_transition(
        self, agent_id: str, session_id: str, target: AgentLifecycleState
    ) -> bool:
        """检查从当前状态到目标状态的转换是否合法。"""
        current = self.current_state(agent_id, session_id)
        return target in _TRANSITIONS.get(current, set())

    def transition(
        self,
        agent_id: str,
        session_id: str,
        target: AgentLifecycleState,
        reason: str = "",
    ) -> bool:
        """执行状态转换。合法时持久化到 ActivityStore 并记录日志。

        当前状态与目标状态相同时视为幂等成功（不报错，不重复持久化）。
        """
        current = self.current_state(agent_id, session_id)
        if current == target:
            return True

        if target not in _TRANSITIONS.get(current, set()):
            logger.warning(
                "非法状态转换: agent=%s %s→%s reason=%s",
                agent_id, current.value, target.value, reason,
            )
            return False

        self._apply_transition(agent_id, session_id, current, target, reason)
        logger.info(
            "状态转换: agent=%s %s→%s reason=%s",
            agent_id, current.value, target.value, reason,
        )
        return True

    def _apply_transition(
        self,
        agent_id: str,
        session_id: str,
        current: AgentLifecycleState,
        target: AgentLifecycleState,
        reason: str,
    ) -> None:
        """将状态转换持久化到 ActivityStore。"""
        if target == AgentLifecycleState.STANDBY:
            if current == AgentLifecycleState.ACTIVE:
                self._store.fallback_to_standby(session_id, agent_id, 0.0)
            else:
                self._store.save_standby_activity(session_id, agent_id, 0.0, reason or "lifecycle_transition")

        elif target == AgentLifecycleState.ACTIVE:
            self._store.activate_from_standby(session_id, agent_id)

        elif target == AgentLifecycleState.EXITING:
            self._store.deactivate(session_id, agent_id, reason or "lifecycle_exiting")

        elif target == AgentLifecycleState.DESTROYED:
            if current == AgentLifecycleState.STANDBY:
                self._store.exit_standby(session_id, agent_id, reason or "lifecycle_destroyed")
            else:
                self._store.deactivate(session_id, agent_id, reason or "lifecycle_destroyed")

