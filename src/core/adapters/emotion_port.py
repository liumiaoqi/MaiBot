"""EmotionPortAdapter — 从 AgentEmotionManagerRegistry 读取情绪值。

适配器层是唯一允许访问 AgentEmotionManagerRegistry 私有属性的地方。
"""



class EmotionPortAdapter:
    """通过 AgentEmotionManagerRegistry 实现 EmotionPort Protocol。

    只读 _state.emotions 避免 property 触发 decay（只读不重算）。
    """

    def get_all_emotion_values(self) -> dict[str, dict[str, float]]:
        """返回所有活跃 agent 的 emotion 值。"""
        from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

        managers = AgentEmotionManagerRegistry._shared_managers
        if managers is None:
            return {}
        result: dict[str, dict[str, float]] = {}
        for agent_id, mgr in managers.items():
            # 直接读 _state.emotions 避免 property 触发 decay（只读不重算）
            result[agent_id] = dict(mgr._state.emotions)
        return result