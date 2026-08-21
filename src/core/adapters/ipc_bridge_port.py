"""IpcBridgePortAdapter — 委托 PluginRuntimeManager 实现 IPC 桥接。

适配器层，唯一允许导入 PluginRuntimeManager 具体类的地方。
核心通过 IpcBridgePort Protocol 接口交互，不直接导入本模块。
"""


from typing import Any, Dict, List, Optional, Tuple

from src.core.protocols import IpcBridgePort, PluginStateSnapshot
from src.plugin_runtime.integration import PluginRuntimeManager


class IpcBridgePortAdapter(IpcBridgePort):
    """IPC 桥接端口适配器 — 委托 PluginRuntimeManager 实现桥接。

    适配器层唯一允许导入 PluginRuntimeManager 具体类的地方（TID251 豁免区）。
    """

    def __init__(self, prm: PluginRuntimeManager) -> None:
        """构造适配器。

        Args:
            prm: PluginRuntimeManager 实例引用，构造时注入，不可变
        """
        self._prm = prm

    @property
    def is_running(self) -> bool:
        """委托 self._prm.is_running"""
        return self._prm.is_running

    async def bridge_event(
        self,
        event_type_value: str,
        message_dict: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """委托 self._prm.bridge_event()，参数和返回值透传。

        不传递 extra_args（EventBus 不使用此参数）。
        """
        return await self._prm.bridge_event(
            event_type_value=event_type_value,
            message_dict=message_dict,
        )

    def list_plugin_states(self) -> List[PluginStateSnapshot]:
        """查询全部插件状态快照（v3 新增）。

        简化实现：PluginRuntimeManager 未暴露插件状态枚举接口，返回空列表。
        后续可接 prm 真实插件状态查询。
        """
        return []
