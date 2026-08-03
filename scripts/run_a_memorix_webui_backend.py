from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 需先完成 sys.path 引导，故 import 不在文件顶部
from src.A_memorix.host_service import a_memorix_host_service  # noqa: E402
from src.webui.webui_server import get_webui_server  # noqa: E402


async def main() -> None:
    server = get_webui_server()
    await a_memorix_host_service.start()
    try:
        await server.start()
    finally:
        await a_memorix_host_service.stop()


if __name__ == "__main__":
    asyncio.run(main())
