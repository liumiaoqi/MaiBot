"""plugin_runtime 不变量 — 插件运行时已启动。

通过 IpcBridgePort.is_running 查询。v2 简化：检查 is_running。
v3 增强：插件状态机合法（loaded→initialized→running）。
"""

from src.core.invariant_registry import invariant
from src.core.ipc_bridge_port_registry import get_ipc_bridge_port


@invariant("plugin_runtime")
def check_plugin_runtime(fail) -> None:
    """检查插件运行时已启动 + 状态机合法。"""
    port = get_ipc_bridge_port()
    if port is None:
        fail("ipc_bridge port 未注册")
        return
    if not port.is_running:
        fail("插件运行时未启动")
    # v3：插件状态机合法
    states = port.list_plugin_states()
    for s in states:
        if s.state not in ("loaded", "initialized", "running", "stopped", "error"):
            fail(f"插件 {s.plugin_id} 状态非法: {s.state}")