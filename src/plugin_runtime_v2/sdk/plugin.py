"""SDK v4 插件基类 — 所有插件的入口点。

插件开发者继承此类，使用 @Tool/@Event/@Command/@HomeCard 装饰器声明组件，
在 scopes 类属性中声明所需权限。
"""


from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.plugin_runtime_v2.sdk.context import PluginContext


class MaiBotPlugin:
    """SDK v4 插件基类 — 所有插件的入口点。

    插件开发者继承此类，使用 @Tool/@Event/@Command/@HomeCard 装饰器声明组件，
    在 scopes 类属性中声明所需权限。

    用法::

        class MyPlugin(MaiBotPlugin):
            plugin_id = "org.example.my_plugin"
            scopes = ["message:send:text", "database:read:self"]

            @Tool(name="my_tool", description="示例工具")
            async def my_tool(self, args: dict[str, Any]) -> dict[str, Any]:
                return {"result": "ok"}
    """

    plugin_id: str = ""
    plugin_version: str = "1.0.0"
    scopes: list[str] = []

    ctx: PluginContext

    async def on_load(self) -> None:
        """插件加载时调用。子类可覆盖以执行初始化逻辑。"""

    async def on_unload(self) -> None:
        """插件卸载时调用。子类可覆盖以执行清理逻辑。

        ZG-15 硬契约：on_load 中启动的后台任务（asyncio.create_task）必须
        经 `self.ctx.register_task(task)` 登记——卸载前框架统一
        `cancel_all_tasks()` 取消；未登记的任务不被自动取消，可能在卸载后
        继续运行导致竞态（访问已释放资源）。
        """

    async def on_config_update(
        self,
        new_config: dict[str, Any],
        prev_config: dict[str, Any],
    ) -> None:
        """配置更新时调用。子类可覆盖以响应配置变更。

        签名扩展：既有单参数 config 扩展为 (new_config, prev_config)。
        设计参考 dsh SettingsScope.watch(callback: (next, prev)) `index.ts:103-129`。
        prev_config 对比是热更核心价值——插件需知道什么变了。
        """
