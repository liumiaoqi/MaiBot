"""maisaka.emotion 不变量 — emotions 各维在 [0, 100]。

只读 _state.emotions（不触发 decay 副作用），遍历所有活跃 agent。
"""

from src.core.invariant_registry import invariant


@invariant("maisaka.emotion")
def check_emotion_range(fail) -> None:
    """检查所有活跃 agent 的 emotion 值在 [0, 100] 区间。"""
    from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

    managers = AgentEmotionManagerRegistry._shared_managers
    if managers is None:
        return
    for agent_id, mgr in managers.items():
        # 直接读 _state.emotions 避免 property 触发 decay（只读不重算）
        for emo_type, value in mgr._state.emotions.items():
            if not (0.0 <= value <= 100.0):
                fail(f"agent={agent_id} emotion={emo_type} value={value} 超出 [0,100]")