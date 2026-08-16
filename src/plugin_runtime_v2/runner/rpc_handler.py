"""ZG16-6a: Runner 侧 UpdatePluginConfig RPC 处理。

接收配置 → 更新 ConfigContext 缓存 → 调用 plugin.on_config_update(new, prev)
→ 风扇出 watch callbacks；未实现时降级 reload。
"""

import json

from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.core.error_escalation_port_registry import get_error_escalation_port
from src.plugin_runtime_v2.proto import plugin_config_pb2
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

logger = get_logger("plugin_runtime_v2.runner.rpc_handler")


async def handle_update_plugin_config(
    request: plugin_config_pb2.UpdatePluginConfigRequest,
    plugin_registry,
    runner_supervisor,
) -> plugin_config_pb2.UpdatePluginConfigResponse:
    """Runner 侧 UpdatePluginConfig RPC 处理。

    接收配置 → 更新 ConfigContext 缓存 → 调用 plugin.on_config_update(new, prev)
    → 风扇出 watch callbacks；未实现时降级 reload。
    """
    plugin = plugin_registry.get(request.plugin_id)
    if plugin is None:
        return plugin_config_pb2.UpdatePluginConfigResponse(
            success=False, error=f"插件 {request.plugin_id} 未加载"
        )

    new_config = json.loads(request.config_json)
    prev_config = plugin.ctx.config.get()
    plugin.ctx.config._apply_update(new_config, request.revision)

    # 判断插件是否实现 on_config_update（非基类空实现）
    if _plugin_implements_on_config_update(plugin):
        try:
            await plugin.on_config_update(new_config, prev_config)
        except Exception as e:
            logger.error(f"on_config_update 回调异常: {e}")
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, f"on_config_update 回调异常: {e}", component_id=request.plugin_id)
            # 不回滚配置，插件继续用新配置（spec 5.3.3 场景 3）
    else:
        # 降级 reload（spec 5.3.3 场景 4）——复用 runner_supervisor.reload_one()
        logger.info(f"插件 {request.plugin_id} 未实现 on_config_update，降级 reload")
        await runner_supervisor.reload_one(request.plugin_id)

    return plugin_config_pb2.UpdatePluginConfigResponse(
        success=True, new_revision=request.revision
    )


def _plugin_implements_on_config_update(plugin) -> bool:
    """判断插件是否 override 了 on_config_update（非基类空实现）。"""
    base_method = MaiBotPlugin.on_config_update
    plugin_method = type(plugin).on_config_update
    return plugin_method is not base_method