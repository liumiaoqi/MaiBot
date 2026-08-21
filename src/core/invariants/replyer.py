"""maisaka.replyer 不变量 — replyer port 已注册且可达。

v2 简化：检查 port 非 None。v3 增强：last_generation 非空 → response_text 非空。
"""

from src.core.invariant_registry import invariant
from src.core.replyer_port_registry import get_replyer_service_port


@invariant("maisaka.replyer")
def check_replyer(fail) -> None:
    """检查 replyer port 已注册。"""
    port = get_replyer_service_port()
    if port is None:
        fail("replyer service port 未注册")