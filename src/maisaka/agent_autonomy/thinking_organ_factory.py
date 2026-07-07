"""思维管道工厂 — 为智能体创建 ThinkingOrgan 实例。

封装 ThinkingOrgan 的创建细节（提示词构建器、LLM 客户端注入等），
Orchestrator 不关心这些，只通过工厂获取实例。
"""

from __future__ import annotations

from src.common.logger import get_logger
from src.core.protocols import ThinkingOrgan as ThinkingOrganProtocol
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder
from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

logger = get_logger("agent_autonomy.thinking_organ_factory")


class ThinkingOrganFactory:
    """思维管道工厂 — 满足 ThinkingOrganFactory Protocol。

    封装 ThinkingOrgan 的创建细节，从 AutonomousAgent.__init__ 中提取创建逻辑。
    """

    def create(self, agent_id: str, session_id: str) -> ThinkingOrganProtocol:
        """为指定智能体创建思维管道。

        Args:
            agent_id: 智能体 ID
            session_id: 会话 ID（预留用于会话级上下文注入）

        Returns:
            ThinkingOrgan 实例
        """
        prompt_builder = EmbodiedPlannerPromptBuilder(agent_id)
        organ = ThinkingOrgan(agent_id, prompt_builder)

        logger.debug(
            f"[thinking_organ_factory] 创建思维管道: "
            f"agent={agent_id} session={session_id} "
            f"degraded={organ.is_degraded}"
        )
        return organ