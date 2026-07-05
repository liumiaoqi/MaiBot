
from src.maisaka.agent.emotion import EmotionManager
from src.maisaka.agent.registry import AgentConfigRegistry


class AgentEmotionManagerRegistry:
    """为每个智能体维护一个全局 EmotionManager 实例"""

    def __init__(self) -> None:
        self._managers: dict[str, EmotionManager] = {}
        self._registry = AgentConfigRegistry()

    def get_emotion_manager(self, agent_id: str) -> EmotionManager:
        if agent_id not in self._managers:
            config = self._registry.get_agent(agent_id)
            self._managers[agent_id] = EmotionManager(config)
        return self._managers[agent_id]

    def get_emotion_state(self, agent_id: str):
        return self.get_emotion_manager(agent_id).state

    def apply_trigger(self, agent_id: str, emotion_type: str, delta: float) -> None:
        self.get_emotion_manager(agent_id).apply_trigger(emotion_type, delta)