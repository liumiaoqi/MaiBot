from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("agent_autonomy.standby_registry")


@dataclass
class StandbyAgentInfo:
    """待命智能体信息。"""

    agent_id: str
    session_id: str
    vitality_value: float = 0.0
    last_stimulus_at: Optional[datetime] = None
    activated_to_active_at: Optional[datetime] = None
    fallback_to_standby_at: Optional[datetime] = None
    inner_need_summary: str = ""


class StandbyAgentRegistry:
    """待命智能体内存注册表。"""

    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], StandbyAgentInfo] = {}

    def add(self, info: StandbyAgentInfo) -> None:
        """幂等添加待命智能体，已存在时更新。"""
        key = (info.agent_id, info.session_id)
        self._agents[key] = info
        logger.debug(
            "待命注册表添加",
            agent_id=info.agent_id,
            session_id=info.session_id,
            vitality=info.vitality_value,
        )

    def remove(self, agent_id: str, session_id: str) -> Optional[StandbyAgentInfo]:
        """移除并返回待命智能体信息。"""
        key = (agent_id, session_id)
        return self._agents.pop(key, None)

    def get(self, agent_id: str, session_id: str) -> Optional[StandbyAgentInfo]:
        """查询单个待命智能体。"""
        return self._agents.get((agent_id, session_id))

    def get_by_session(self, session_id: str) -> list[StandbyAgentInfo]:
        """查询会话所有待命智能体。"""
        return [info for info in self._agents.values() if info.session_id == session_id]

    def update_vitality(self, agent_id: str, session_id: str, new_value: float) -> None:
        """更新生命力值。"""
        key = (agent_id, session_id)
        info = self._agents.get(key)
        if info is not None:
            info.vitality_value = max(0.0, min(100.0, new_value))

    def contains(self, agent_id: str, session_id: str) -> bool:
        """检查是否在待命列表中。"""
        return (agent_id, session_id) in self._agents

    def all_agents(self) -> list[StandbyAgentInfo]:
        """获取所有待命智能体。"""
        return list(self._agents.values())

    def clear(self) -> None:
        """清空注册表。"""
        self._agents.clear()