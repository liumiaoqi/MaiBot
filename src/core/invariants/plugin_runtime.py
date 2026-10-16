"""plugin_runtime 不变量 — 生产插件运行时（v2 宿主端点）已启动。

被检对象是 `PluginRuntimeV2Port`（v2 宿主端点的活体存活状态），**不是** v1 的
`IpcBridgePort`。

⚠️ 为什么换被检对象（2026-10-17 判定 = (b) 假报，非真缺陷）：
- ZG-32 把 v1 运行时收敛掉了（`main.py` 的 v1 启动项是注释态）⇒ v1
  `PluginRuntimeManager._started` 永远为 False ⇒ `IpcBridgePort.is_running` 恒假；
- 本不变量按 `plugin_runtime_v2.enabled` 决定是否跳过 ⇒ v2 启用时去查那个恒假的
  v1 标志，条件恒成立 ⇒ **恒红**。实测：v2 端点「04:18:06 已启动」（且 Runner 已
  握手、收包），本不变量 04:18:09 与 04:23:44 巡检仍报"插件运行时未启动"。
- 恒假与恒真同罪：恒红的告警只会教会人忽略不变量（见 invariant_registry 头部）。

原 v3 的"插件状态机合法"子检查一并移除：它遍历的
`IpcBridgePortAdapter.list_plugin_states()` 是恒空 stub（`ipc_bridge_port.py`
明确写"简化实现……返回空列表"），且它断言的 v1 词表（loaded/initialized/running/
stopped/error）在 v2 里没有对应物（v2 是 live/coming/going/unformed/error）——
留着只是"对着 stub 说自己在检查"。v2 侧的插件状态面属另案。
"""

from src.common.logger import get_logger
from src.core.app_config_port_registry import get_app_config_port
from src.core.invariant_registry import invariant
from src.core.plugin_runtime_v2_port_registry import get_plugin_runtime_v2_port
from src.core.system_state_port_registry import get_system_lifecycle_adapter

logger = get_logger("invariant.plugin_runtime")


@invariant("plugin_runtime")
def check_plugin_runtime(fail) -> None:
    """检查生产插件运行时（v2 宿主端点）真的在监听。"""
    # 配置感知：plugin_runtime_v2 有意禁用时不报违反
    try:
        app_port = get_app_config_port()
        if app_port is not None and not app_port.get_plugin_runtime_v2_enabled():
            logger.debug("plugin_runtime_v2 已禁用，跳过不变量校验")
            return
    except Exception as e:
        logger.warning(f"配置读取异常，降级跳过 plugin_runtime 不变量: {e}")
        return

    # 关停阶段不判定：关闭链本来就要停掉端点，"没在跑"是预期而不是违反。
    # 只读内存状态；查询失败按"没在关停"继续判定（不静默放过）。
    try:
        adapter = get_system_lifecycle_adapter()
        if adapter is not None and adapter.is_shutting_down():
            logger.debug("系统关停中，跳过 plugin_runtime 不变量校验")
            return
    except Exception as e:
        logger.warning(f"生命周期状态读取异常，继续判定 plugin_runtime 不变量: {e}")

    port = get_plugin_runtime_v2_port()
    if port is None:
        fail("插件运行时未接线：v2 宿主端点未注册（启动失败或未启用）")
        return
    if not port.is_running:
        fail("插件运行时未启动")
