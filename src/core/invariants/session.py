"""chat.session 不变量 — session info port 已注册。

v2 简化：检查 port 非 None。v3 增强：sessions dict len vs DB count 一致。
"""

from src.core.invariant_registry import invariant
from src.core.session_port_registry import get_session_info_port


@invariant("chat.session")
def check_session(fail) -> None:
    """检查 session info port 已注册。"""
    port = get_session_info_port()
    if port is None:
        fail("session info port 未注册")