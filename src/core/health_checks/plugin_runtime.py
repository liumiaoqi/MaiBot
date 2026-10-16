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
- 有 `rejected` 状态插件 → DEGRADED（解析阶段被拒：manifest 读不出/不过 schema）
- 否则 → UP

⚠️ **报告纪律（2026-10-17 裁定，一句话）**：**报最具体的成因，同时把泛化态作为
上下文留下**——**别让更具体的那条顶掉更基础的那条**。落到本检查器就是：`errored`
（具体：带 plugin_id、可行动）**保持在** `is_running=False`（泛化态）之前，**但
detail 里必须同时有两者**——"未监听"这件事不许因为报了 DEGRADED/DOWN 就消失。
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

        # v3：插件状态面检查——数据源是 v2 宿主端点投影（激活/跳过/拒绝 + Runner 连接）
        states = port.list_plugin_states()
        if not states:
            # ⚠️ 0 条 ⇒ 具名 UNKNOWN，**不许静默绿**：取不到状态就没有"正常"可报。
            # ⚠️ 别与"值域缺口"混：这里是**空源**（抽到 0 条）；值域缺口是**空间
            # 本身没覆盖全部结果**（有插件、但它落不进任何一栏 ⇒ 投影面看不见）。
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
        rejected = [s.plugin_id for s in states if s.state == "rejected"]
        # 泛化态：端点到底在不在监听（活体状态，不是"对象已构造"）。它要进**每一条**
        # verdict 的 detail——它是上下文，不是"更弱的信号"，不许被更具体的那条顶掉。
        is_running = bool(getattr(port, "is_running", False))

        if errored:
            # ⚠️ 顺序裁定（2026-10-17）：`errored` **保持在** `is_running` 之前——
            # 更具体的信号优先（`errored` 带 plugin_id、可行动；`is_running=False`
            # 是泛化态）。但**两态都要在 detail 里**：未监听这件事不能因为报了
            # 更具体的成因就消失（`is_running` 字段 + `reason` 都不落）。
            reason = "有插件连接已断（error）"
            if not is_running:
                reason += "；且插件运行时未监听（is_running=False，泛化态）"
            return HealthResult(
                HealthStatus.DOWN,
                {
                    "errored": len(errored),
                    "plugin_ids": errored[:10],
                    "is_running": is_running,
                    "reason": reason,
                },
            )

        if not is_running:
            detail: dict = {
                "is_running": False,
                "reason": "插件运行时未启动（未监听）",
                "plugins": len(states),
            }
            # 泛化态出声时，**具体态一并留下**——只报一句"未启动"会把可行动的信息丢掉
            if skipped:
                detail["skipped"] = len(skipped)
                detail["skipped_plugin_ids"] = skipped[:10]
            if rejected:
                detail["rejected"] = len(rejected)
                detail["rejected_plugin_ids"] = rejected[:10]
            return HealthResult(HealthStatus.DEGRADED, detail)

        if skipped:
            # 跳过的插件（含 spawn 失败）不是"一切正常"——降级但出声
            return HealthResult(
                HealthStatus.DEGRADED,
                {"skipped": len(skipped), "plugin_ids": skipped[:10],
                 "plugins": len(states), "is_running": is_running},
            )

        if rejected:
            # 解析阶段被拒（**值域第三栏**）：manifest 读不出/不过 schema/id 重复/
            # 自依赖。它们**从未进依赖图**，但必须可见——藏起来就是把"坏插件"
            # 说成"没有插件"（"值域缺口"的补丁，2026-10-17）。
            return HealthResult(
                HealthStatus.DEGRADED,
                {"rejected": len(rejected), "plugin_ids": rejected[:10],
                 "plugins": len(states), "is_running": is_running},
            )

        return HealthResult(
            HealthStatus.UP, {"plugins": len(states), "is_running": is_running},
        )
