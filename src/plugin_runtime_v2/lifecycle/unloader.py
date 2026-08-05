"""插件卸载编排 — 对标 Linux delete_module syscall。

流程（对标内核 `kernel/module/main.c:804-882`）：
mark_going（设 GOING，对标 try_stop_module）
→ wait_drained（等待在途清零，对标 async_synchronize_full + module_wq）
→ cancel_all_tasks（取消自启任务）
→ on_unload（对标 mod->exit()）
→ 注销 + mark_unformed（对标 free_module 的 state 转换）

三条卸载路径统一走本编排：
SIGTERM（entrypoint._graceful_shutdown）/ ShutdownRequest（endpoint._handle_shutdown）/ reload 排空
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.plugin_runtime_v2.lifecycle.refcount import PluginRefcount, PluginState

if TYPE_CHECKING:
    from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
    from src.plugin_runtime_v2.sdk.context import PluginContext

logger = get_logger("plugin_runtime_v2.lifecycle.unloader")


@dataclass
class UnloadResult:
    """卸载结果 — reason 枚举 {NOT_FOUND, ALREADY_GOING, DRAIN_TIMEOUT}。"""

    success: bool
    reason: str = ""


class PluginUnloader:
    """卸载流程编排器（Runner 进程内，由 RunnerEndpoint 持有）。"""

    def __init__(
        self,
        refcount: PluginRefcount,
        loader: "PluginLoader",
        ctx: "PluginContext | None" = None,
    ) -> None:
        self._refcount = refcount
        self._loader = loader
        self._ctx = ctx

    async def unload_plugin(self, *, timeout_s: float = 30.0) -> UnloadResult:
        """执行完整卸载流程。

        幂等：GOING 状态下调用（如 _handle_shutdown 预置后）继续执行剩余步骤，
        不提前返回 ALREADY_GOING（CX 审查 P0-1：预置 GOING 后必须真正卸载）。

        Returns:
            UnloadResult(success=True) 或 NOT_FOUND / ALREADY_GOING（已 UNFORMED）
        """
        plugin = self._loader.instance
        if plugin is None:
            return UnloadResult(success=False, reason="NOT_FOUND")

        # 1. 设 GOING（对标 try_stop_module；已 GOING 则幂等继续）
        if self._refcount.state == PluginState.UNFORMED:
            return UnloadResult(success=False, reason="ALREADY_GOING")
        if self._refcount.state == PluginState.GOING:
            has_inflight = self._refcount.refcount > 0
        else:
            has_inflight = not self._refcount.mark_going()

        # 2. 等待在途引用清零（对标 async_synchronize_full + module_wq）
        # 超时不中断（CX 审查 P1）：best-effort 继续 cancel/on_unload/mark_unformed，
        # 避免状态永久卡在 GOING 无恢复路径
        if has_inflight:
            await self._refcount.wait_drained(timeout_s=timeout_s)

        # 3. 取消自启任务（硬契约：on_unload 前清理后台 task）
        if self._ctx is not None:
            cancel = getattr(self._ctx, "cancel_all_tasks", None)
            if cancel is not None:
                await cancel()

        # 4. on_unload（对标 mod->exit()，异常不阻断卸载——loader.unload 已包裹异常）
        await self._loader.unload(plugin)

        # 5. 释放（对标 free_module 的 state 转换）
        self._refcount.mark_unformed()
        logger.info("插件 %s 卸载完成", plugin.plugin_id)
        return UnloadResult(success=True)
