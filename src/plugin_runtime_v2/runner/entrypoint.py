"""Runner 独立进程入口 — 由 Host 的 RunnerSpawner 调用。"""


import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger, initialize_logging

if TYPE_CHECKING:
    from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
    from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader

logger = get_logger("plugin_runtime_v2.runner.entrypoint")


def main() -> None:
    initialize_logging()
    parser = argparse.ArgumentParser(description="MaiBot Plugin Runner")
    parser.add_argument("--host-address", required=True, help="Host gRPC 地址")
    parser.add_argument("--plugin-dir", required=True, help="插件目录路径")
    parser.add_argument("--runner-id", required=True, help="Runner ID")
    args = parser.parse_args()
    # session_token 从环境变量读取，避免 ps/proc 可见（A23a P1-2 安全）
    args.session_token = os.environ.get("_SESSION_TOKEN", "")
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
    from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
    from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig

    plugin_dir = Path(args.plugin_dir)
    plugin_cls, manifest = _discover_plugin(plugin_dir)
    if plugin_cls is None:
        logger.error("未在 %s 发现有效插件，Runner 以无插件模式启动", plugin_dir)
        config = RunnerEndpointConfig(
            host_address=args.host_address,
            runner_id=args.runner_id,
            session_token="",
            scopes=[],
            plugin_id=args.runner_id,
        )
        endpoint = RunnerEndpoint(config)
        await endpoint.start()
        return

    plugin_id = manifest.get("id", args.runner_id)
    plugin_version = manifest.get("version", "1.0.0")
    scopes = manifest.get("scopes", [])

    loader = PluginLoader(plugin_cls)
    config = RunnerEndpointConfig(
        host_address=args.host_address,
        runner_id=args.runner_id,
        session_token=args.session_token,
        scopes=scopes,
        plugin_id=plugin_id,
        plugin_version=plugin_version,
    )
    endpoint = RunnerEndpoint(config, plugin_loader=loader)

    loop = asyncio.get_running_loop()

    def _signal_handler(signum: int, _frame: Any) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("收到 %s，开始优雅关闭", sig_name)
        loop.call_soon_threadsafe(loop.create_task, _graceful_shutdown(endpoint, loader))

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    await endpoint.start()

    # 保持事件循环存活，直到信号触发关闭
    _shutdown_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGTERM, lambda: _shutdown_event.set())
    loop.add_signal_handler(signal.SIGINT, lambda: _shutdown_event.set())
    await _shutdown_event.wait()
    await _graceful_shutdown(endpoint, loader)


async def _graceful_shutdown(
    endpoint: RunnerEndpoint,
    loader: PluginLoader,
) -> None:
    # CX 审查 P0-2：不在此处直接 loader.unload()——endpoint.stop() 内的
    # PluginUnloader 是唯一卸载入口（否则 SIGTERM 路径双重执行 on_unload，
    # 且第一次执行发生在排空/取消任务之前）
    await endpoint.stop()


def _discover_plugin(
    plugin_dir: Path,
) -> tuple[type | None, dict[str, Any]]:
    if not plugin_dir.is_dir():
        logger.error("插件目录不存在: %s", plugin_dir)
        return None, {}

    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = plugin_dir / "_manifest.json"
    if not manifest_path.is_file():
        logger.error("未找到 manifest.json 或 _manifest.json: %s", plugin_dir)
        return None, {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("读取 manifest.json 失败: %s", exc)
        return None, {}

    plugin_py = plugin_dir / "plugin.py"
    if not plugin_py.is_file():
        logger.error("未找到 plugin.py: %s", plugin_py)
        return None, {}

    try:
        plugin_id_safe = manifest.get("id", "unknown").replace("-", "_").replace(".", "_")
        parent_dir = str(plugin_dir.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        package_name = plugin_id_safe
        if package_name not in sys.modules:
            import types
            pkg = types.ModuleType(package_name)
            pkg.__path__ = [str(plugin_dir)]
            pkg.__package__ = package_name
            pkg.__file__ = str(plugin_dir / "__init__.py")
            sys.modules[package_name] = pkg

        mod = importlib.import_module(f"{package_name}.plugin")
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, "动态导入 plugin.py 失败", exception=exc)
        logger.error("动态导入 plugin.py 失败: %s", exc)
        return None, {}

    create_plugin = getattr(mod, "create_plugin", None)
    if create_plugin is not None and callable(create_plugin):
        try:
            plugin_cls = create_plugin()
            if isinstance(plugin_cls, type):
                return plugin_cls, manifest
            logger.error("create_plugin() 未返回类型: %s", type(plugin_cls))
            return None, {}
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "调用 create_plugin() 失败", exception=exc)
            logger.error("create_plugin() 调用失败: %s", exc)
            return None, {}

    from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

    plugin_classes = [
        obj
        for obj in vars(mod).values()
        if isinstance(obj, type) and issubclass(obj, MaiBotPlugin) and obj is not MaiBotPlugin
    ]
    if not plugin_classes:
        logger.error("plugin.py 中未找到 MaiBotPlugin 子类")
        return None, {}
    if len(plugin_classes) > 1:
        logger.warning("plugin.py 中有多个 MaiBotPlugin 子类，使用第一个: %s", plugin_classes[0].__name__)

    return plugin_classes[0], manifest


if __name__ == "__main__":
    main()
