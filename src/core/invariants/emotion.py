"""maisaka.emotion 不变量 — emotions 各维在 [0, 100]。

通过 EmotionPort 读取情绪值（不触发 decay 副作用），遍历所有活跃 agent。
"""

from src.core.invariant_registry import invariant


@invariant("maisaka.emotion")
def check_emotion_range(fail) -> None:
    """检查所有活跃 agent 的 emotion 值在 [0, 100] 区间。"""
    from src.core.emotion_port_registry import get_emotion_port

    port = get_emotion_port()
    if port is None:
        return
    for agent_id, emotions in port.get_all_emotion_values().items():
        for emo_type, value in emotions.items():
            if not (0.0 <= value <= 100.0):
                fail(f"agent={agent_id} emotion={emo_type} value={value} 超出 [0,100]")