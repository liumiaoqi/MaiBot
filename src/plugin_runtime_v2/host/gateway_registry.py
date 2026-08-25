"""网关声明注册表 — 存储 plugin_id → MessageGatewayDeclaration 映射。

RegisterComponents 时存入声明，gateway_ready 时查询声明用于驱动注册，
Runner 断开时移除声明。
"""


import threading

from src.common.logger import get_logger
from src.plugin_runtime_v2.sdk.decorators import MessageGatewayDeclaration

logger = get_logger("plugin_runtime_v2.host.gateway_registry")


class GatewayRegistry:
    """网关声明注册表（线程安全）。

    存储每个插件声明的 @MessageGateway 列表，供 V2GatewayRegistrar 查询。
    """

    def __init__(self) -> None:
        self._declarations: dict[str, list[MessageGatewayDeclaration]] = {}
        self._lock = threading.Lock()

    def register_declarations(
        self,
        plugin_id: str,
        gateways: list[MessageGatewayDeclaration],
    ) -> None:
        """存储插件声明的网关列表（RegisterComponents 时调用）。

        同 plugin 内 gateway name 重复时抛 ValueError。
        重连时覆盖旧声明。
        """
        names = [gw.name for gw in gateways]
        duplicates = [n for n in names if names.count(n) > 1]
        if duplicates:
            raise ValueError(
                f"插件 {plugin_id} 网关声明名称重复: {set(duplicates)}"
            )

        with self._lock:
            self._declarations[plugin_id] = list(gateways)

        logger.info(
            "GatewayRegistry: 插件 %s 注册 %d 个网关声明: %s",
            plugin_id, len(gateways), names,
        )

    def get_declaration(
        self,
        plugin_id: str,
        gateway_name: str,
    ) -> MessageGatewayDeclaration | None:
        """查询单个网关声明。"""
        with self._lock:
            decls = self._declarations.get(plugin_id, [])
            for gw in decls:
                if gw.name == gateway_name:
                    return gw
        return None

    def get_all_declarations(self, plugin_id: str) -> list[MessageGatewayDeclaration]:
        """查询插件的所有网关声明。"""
        with self._lock:
            return list(self._declarations.get(plugin_id, []))

    def remove(self, plugin_id: str) -> None:
        """移除插件的所有声明（Runner 断开时调用）。"""
        with self._lock:
            removed = self._declarations.pop(plugin_id, None)
        if removed is not None:
            logger.info(
                "GatewayRegistry: 移除插件 %s 的 %d 个网关声明",
                plugin_id, len(removed),
            )