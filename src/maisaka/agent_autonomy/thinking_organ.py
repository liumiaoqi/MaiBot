from src.common.logger import get_logger
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

logger = get_logger("agent_autonomy.thinking_organ")


class ThinkingOrgan:
    """思维器官——以角色内部视角运行 Planner。"""

    def __init__(self, agent_id: str, prompt_builder: EmbodiedPlannerPromptBuilder) -> None:
        self._agent_id = agent_id
        self._prompt_builder = prompt_builder
        self._autonomy_logger = AutonomyLogger.get()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_degraded(self) -> bool:
        return self._prompt_builder.is_degraded

    def build_system_prompt(self, tools_section: str = "") -> str:
        """构建角色化系统提示词。"""
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            "构建角色化系统提示词",
            level="debug",
        )
        return self._prompt_builder.build_system_prompt(tools_section)

    def build_personality_prompt(self) -> str:
        """构建角色化人格提示词。"""
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.THINKING,
            "开始角色化思考",
        )
        return self._prompt_builder.build_personality_prompt()

    def get_prompt_template_name(self) -> str:
        """获取当前使用的提示词模板名。"""
        return self._prompt_builder.get_prompt_template_name()