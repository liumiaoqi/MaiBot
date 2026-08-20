
from src.maisaka.agent.emotion import EmotionManager
from src.core.adapters.agent_config_port import get_agent_config_provider


class AgentEmotionManagerRegistry:
    """为每个智能体维护一个全局 EmotionManager 实例。

    单例语义：全进程共享同一份 _managers，避免各模块各自 new 导致情绪状态分裂。
    构造时若已有全局实例，复用其 _managers 字典。
    """

    _shared_managers: dict[str, EmotionManager] | None = None

    def __init__(self) -> None:
        if AgentEmotionManagerRegistry._shared_managers is None:
            AgentEmotionManagerRegistry._shared_managers = {}
        self._managers = AgentEmotionManagerRegistry._shared_managers
        self._registry = get_agent_config_provider()

    def get_emotion_manager(self, agent_id: str) -> EmotionManager:
        if agent_id not in self._managers:
            config = self._registry.get_agent(agent_id)
            self._managers[agent_id] = EmotionManager(config)
        return self._managers[agent_id]

    def get_emotion_state(self, agent_id: str):
        return self.get_emotion_manager(agent_id).state

    def apply_trigger(self, agent_id: str, emotion_type: str, delta: float) -> None:
        self.get_emotion_manager(agent_id).apply_trigger(emotion_type, delta)