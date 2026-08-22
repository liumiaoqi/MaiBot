"""EmotionPort 注册点。

核心模块（invariants）通过此 registry 获取 EmotionPort，
不直接导入 maisaka 组件（核心禁止项：核心不导入 maisaka 组件）。
main.py 启动时通过 set_emotion_port() 注入；
未注入时 get 返回 None（调用方走兜底）。

port_registry 仅依赖 Protocol 接口做类型标注，具体实现由
main.py 启动时注入（核心禁止项 13）。
"""


from typing import Optional

from src.core.protocols import EmotionPort

_provider: Optional[EmotionPort] = None


def get_emotion_port() -> Optional[EmotionPort]:
    """获取已注册的 EmotionPort 实例。

    Returns:
        EmotionPort 实例；未注册时返回 None（调用方走兜底）
    """
    return _provider


def set_emotion_port(port: EmotionPort) -> None:
    """注册 EmotionPort 实例。

    Args:
        port: EmotionPort 实例（后注册覆盖）
    """
    global _provider
    _provider = port


def reset_emotion_port() -> None:
    """清空注册（测试用）。"""
    global _provider
    _provider = None