"""PluginRuntimeV2Port 注册点 — 生产插件运行时（v2）的存活判定接口。

ZG-32 后 v1 插件运行时已停用（`main.py` 的 v1 启动项为注释态），生产运行时是
v2（gRPC HostEndpoint + Runner 子进程）。核心不感知 `HostEndpoint` 具体类：

- 注册：`main.py` 的 `plugin_runtime_v2` 启动项用 `PluginRuntimeV2Adapter`
  包装**已启动**的 HostEndpoint 后注入；
- 查询：invariants / health_checks 读"活体"存活状态，不读启动结果——
  启动项把异常记进日志后正常返回，启动结果会是"成功"。

⚠️ "未注册"与"注册了但没在跑"是两件事，调用方须分开判：
前者 = 运行时未接线（未启用或启动失败），后者 = 接线了但真的没跑。
未注册时返回 None（调用方自决默认值）。
"""


from typing import Optional

from src.core.protocols import PluginRuntimeV2Port

_port: Optional[PluginRuntimeV2Port] = None


def get_plugin_runtime_v2_port() -> Optional[PluginRuntimeV2Port]:
    """获取已注册的 PluginRuntimeV2Port；未注册返回 None（调用方自决默认值）。"""
    return _port


def set_plugin_runtime_v2_port(port: PluginRuntimeV2Port) -> None:
    """注册 PluginRuntimeV2Port（后注册覆盖）。"""
    global _port
    _port = port


def reset_plugin_runtime_v2_port() -> None:
    """清空注册（测试用）。"""
    global _port
    _port = None
