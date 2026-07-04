"""DeepSeek 模型分层调度器。

根据任务类型、复杂度和智能体级模型调度偏好在 deepseek-v4-pro/flash/think 之间自动选择。
"""

from __future__ import annotations

from enum import Enum

from src.common.logger import get_logger

logger = get_logger("maisaka_deepseek_model_scheduler")


class ModelTier(str, Enum):
    """模型层级。"""

    PRO = "pro"
    FLASH = "flash"
    THINK = "think"


class TaskComplexity(str, Enum):
    """任务复杂度。"""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


_TASK_TIER_DEFAULTS: dict[str, ModelTier] = {
    "planner": ModelTier.FLASH,
    "replyer": ModelTier.PRO,
    "dream_consolidation": ModelTier.PRO,
    "compaction_summary": ModelTier.PRO,
    "emotion_analysis": ModelTier.FLASH,
    "profile_update": ModelTier.FLASH,
}

_COMPLEXITY_TIER_MAP: dict[TaskComplexity, ModelTier] = {
    TaskComplexity.SIMPLE: ModelTier.FLASH,
    TaskComplexity.MODERATE: ModelTier.PRO,
    TaskComplexity.COMPLEX: ModelTier.THINK,
}


class ModelScheduler:
    """DeepSeek 模型分层调度器。"""

    def select_model(
        self,
        agent_id: str,
        task_type: str,
        complexity: TaskComplexity = TaskComplexity.MODERATE,
    ) -> ModelTier:
        """根据任务类型和智能体偏好选择模型层级。"""
        preference = self._get_agent_preference(agent_id)

        if preference == "pro":
            return ModelTier.PRO
        if preference == "flash":
            return ModelTier.FLASH

        if task_type == "replyer" and complexity == TaskComplexity.COMPLEX:
            return ModelTier.THINK

        task_default = _TASK_TIER_DEFAULTS.get(task_type)
        if task_default is not None:
            return task_default

        return _COMPLEXITY_TIER_MAP.get(complexity, ModelTier.PRO)

    @staticmethod
    def _get_agent_preference(agent_id: str) -> str:
        """获取智能体的模型调度偏好。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if registry.has_agent(agent_id):
                return registry.get_agent(agent_id).deepseek.model_scheduling_preference
        except Exception:
            pass
        return "auto"