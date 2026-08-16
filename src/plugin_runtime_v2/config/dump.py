"""ZG16-6a: dump_plugin_config 端点——CLI + 调试端点 + render。

设计参考：dsh --dump-config `apps/cli/src/dump-config.ts:30-52` + renderConfigDump `app-boot/src/index.ts:379-442`。
"""

import argparse
import json
import sys

from src.plugin_runtime_v2.config.merger import ProvenanceEntry


def _flatten_config(config: dict, prefix: str = "") -> list[tuple[str, object]]:
    """扁平化配置为 (key_path, value) 列表。"""
    items = []
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.extend(_flatten_config(value, full_key))
        else:
            items.append((full_key, value))
    return items


def _format_toml_value(value) -> str:
    """格式化 TOML 值。"""
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_toml_value(v) for v in value) + "]"
    return str(value)


def render_config_dump_human(
    config: dict,
    provenance: dict[str, ProvenanceEntry],
    revision: int,
) -> str:
    """人可读 TOML + # 来源注释。

    设计参考 dsh renderConfigDump `app-boot/src/index.ts:379-442`。
    """
    lines = [f"# revision: {revision}"]
    for key, value in _flatten_config(config):
        entry = provenance.get(key)
        if entry:
            lines.append(f"# 来源: {entry.layer}, {entry.file}:{entry.line or '?'}")
        lines.append(f"{key} = {_format_toml_value(value)}")
    return "\n".join(lines)


def render_config_dump_json(
    config: dict,
    provenance: dict[str, ProvenanceEntry],
    revision: int,
) -> str:
    """机器可读 JSON。"""
    return json.dumps({
        "config": config,
        "provenance": {
            k: {"layer": v.layer, "file": v.file, "line": v.line}
            for k, v in provenance.items()
        },
        "revision": revision,
    }, ensure_ascii=False, indent=2)


async def dump_plugin_config_main(
    plugin_id: str,
    manager,  # PluginConfigManager 实例
    stream_id: str | None = None,
    fmt: str = "human",
) -> int:
    """dump_plugin_config CLI 主逻辑。返回退出码 0=成功, 2=错误。"""
    try:
        result = await manager.dump_config(plugin_id, stream_id, fmt)
        print(result)
        return 0
    except KeyError:
        print(f"插件 {plugin_id} 未加载", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"dump 失败: {e}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：python -m src.plugin_runtime_v2.config.dump <plugin_id> [--stream <id>] [--json|--human]"""
    parser = argparse.ArgumentParser(description="dump 插件配置快照 + provenance")
    parser.add_argument("plugin_id", help="插件 ID")
    parser.add_argument("--stream", default=None, help="聊天流 ID（group:{gid} 或 user:{uid}）")
    fmt_group = parser.add_mutually_exclusive_group()
    fmt_group.add_argument("--json", action="store_const", const="json", dest="fmt")
    fmt_group.add_argument("--human", action="store_const", const="human", dest="fmt", default="human")
    args = parser.parse_args(argv)
    # 获取 PluginConfigManager 实例（通过生产接线点）
    import asyncio

    from src.plugin_runtime_v2.config.host_config_manager import get_plugin_config_manager
    manager = get_plugin_config_manager()
    return asyncio.run(dump_plugin_config_main(args.plugin_id, manager, args.stream, args.fmt))


if __name__ == "__main__":
    sys.exit(main())


# 调试端点处理函数（Host 启动时注册路由）
async def handle_dump_endpoint(plugin_id: str, stream_id: str | None, fmt: str, manager) -> dict | str:
    """HTTP GET /debug/plugin_config/{plugin_id} 处理函数。"""
    return await manager.dump_config(plugin_id, stream_id, fmt)