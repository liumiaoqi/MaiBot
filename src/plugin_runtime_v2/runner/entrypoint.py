"""Runner 独立进程入口 — 由 Host 的 RunnerSpawner 调用。"""

from __future__ import annotations

import argparse
import asyncio



def main() -> None:
    parser = argparse.ArgumentParser(description="MaiBot Plugin Runner")
    parser.add_argument("--host-address", required=True, help="Host gRPC 地址")
    parser.add_argument("--plugin-dir", required=True, help="插件目录路径")
    parser.add_argument("--runner-id", required=True, help="Runner ID")
    args = parser.parse_args()
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
    from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig

    config = RunnerEndpointConfig(
        host_address=args.host_address,
        runner_id=args.runner_id,
        session_token="",
        scopes=[],
        plugin_id=args.runner_id,
    )
    endpoint = RunnerEndpoint(config)
    await endpoint.start()


if __name__ == "__main__":
    main()
