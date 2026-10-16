"""PluginRuntimeV2Adapter — 委托 v2 HostEndpoint 提供运行时存活判定。

适配器层，唯一允许导入 HostEndpoint 具体类的地方。核心通过
PluginRuntimeV2Port 接口交互，不直接导入本模块。
"""


from typing import TYPE_CHECKING

from src.core.protocols import PluginRuntimeV2Port

if TYPE_CHECKING:
    from src.plugin_runtime_v2.host.endpoint import HostEndpoint


class PluginRuntimeV2Adapter(PluginRuntimeV2Port):
    """v2 插件运行时存活端口适配器 — 只读 HostEndpoint 的活体状态。"""

    def __init__(self, endpoint: "HostEndpoint") -> None:
        """构造适配器。

        Args:
            endpoint: 已启动的 v2 HostEndpoint 实例引用，构造时注入，不可变
        """
        self._endpoint = endpoint

    @property
    def is_running(self) -> bool:
        """委托 self._endpoint.is_running（活体标志，非启动结果）"""
        return self._endpoint.is_running
