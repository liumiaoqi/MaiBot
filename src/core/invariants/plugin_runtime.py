"""plugin_runtime 不变量 — 插件运行时已启动。

通过 IpcBridgePort.is_running 查询。v2 简化：检查 is_running。
v3 增强：插件状态机合法（loaded→initialized→running）。
"""

from src.common.logger import get_logger
from src.core.app_config_port_registry import get_app_config_port
from src.core.invariant_registry import invariant
from src.core.ipc_bridge_port_registry import get_ipc_bridge_port

logger = get_logger("invariant.plugin_runtime")


@invariant("plugin_runtime")
def check_plugin_runtime(fail) -> None:
    """检查插件运行时已启动 + 状态机合法。"""
    # 配置感知：plugin_runtime_v2 有意禁用时不报违反
    try:
        app_port = get_app_config_port()
        if app_port is not None and not app_port.get_plugin_runtime_v2_enabled():
            logger.debug("plugin_runtime_v2 已禁用，跳过不变量校验")
            return
    except Exception as e:
        logger.warning(f"配置读取异常，降级跳过 plugin_runtime 不变量: {e}")
        return

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