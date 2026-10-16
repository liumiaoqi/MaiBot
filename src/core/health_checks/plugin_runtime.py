"""plugin.runtime 健康检查 — 插件运行时状态机。

**被查对象是 v2（生产运行时）**：`PluginRuntimeV2Port`（`HostEndpoint` 的活体投影）。
2026-10-17 由 v1 的 `IpcBridgePort` 换过来 —— v1 运行时已被 ZG-32 收敛掉
（`main.py` 的 v1 启动项是注释态），其 `list_plugin_states()` 是恒空 stub，
连着查它等于"对着 stub 说自己在检查"。

判定（顺序即优先级）：
- port 未注册 → UNKNOWN（"未接线"，具名 reason）
- v2 端点未监听 → DOWN（`is_running` 为假：启动失败或已停）
- 状态列表为 0 条 → UNKNOWN（**非静默绿**：一个插件状态都取不到 ≠ 一切正常）
- 有 `error` 状态插件 → DOWN（带 errored 条数 + 具名 plugin_id）
- 有 `skipped` 状态插件 → DEGRADED（带 skipped 条数 + 具名 plugin_id）
- 否则 → UP
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus
from src.core.plugin_runtime_v2_port_registry import get_plugin_runtime_v2_port


class PluginRuntimeHealthCheck(BaseHealthCheck):
    """插件运行时状态健康检查（v2 宿主端点）。"""

    timeout = 1.0

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="plugin.runtime", timeout=timeout or 1.0)

    async def _do_check(self) -> HealthResult:
        port = get_plugin_runtime_v2_port()
        if port is None:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "v2 plugin_runtime port 未注册（端点未启动或未接线）"},
            )

        # v3：插件状态面检查——数据源是 v2 宿主端点投影（激活/跳过 + Runner 连接）
        states = port.list_plugin_states()
        if not states:
            # ⚠️ 0 条 ⇒ 具名 UNKNOWN，**不许静默绿**：取不到状态就没有"正常"可报。
            return HealthResult(
                HealthStatus.UNKNOWN,
                {
                    "reason": "v2 宿主端点未登记任何插件状态（0 条）——"
                              "无插件目录 / 激活编排未跑 / 投影链路断了，需人工确认",
                    "plugin_count": 0,
                },
            )

        errored = [s.plugin_id for s in states if s.state == "error"]
        skipped = [s.plugin_id for s in states if s.state == "skipped"]
        if errored:
            return HealthResult(
                HealthStatus.DOWN,
                {"errored": len(errored), "plugin_ids": errored[:10]},
            )
        if not port.is_running:
            return HealthResult(
                HealthStatus.DEGRADED,
                {"is_running": False, "reason": "插件运行时未启动"},
            )
        if skipped:
            # 跳过的插件（含 spawn 失败）不是"一切正常"——降级但出声
            return HealthResult(
                HealthStatus.DEGRADED,
                {"skipped": len(skipped), "plugin_ids": skipped[:10],
                 "plugins": len(states)},
            )
        return HealthResult(HealthStatus.UP, {"plugins": len(states)})
