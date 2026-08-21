"""db.main 健康检查 — MaiBot.db 可达性（SELECT 1）。

超时 3s，用 asyncio.to_thread 包装同步 sqlite3 调用。
"""

import asyncio
import sqlite3
from pathlib import Path

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus


class MainDbHealthCheck(BaseHealthCheck):
    """MaiBot.db 主数据库健康检查。"""

    timeout = 3.0

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(name="db.main")
        if db_path is None:
            from src.common.database.database import _DB_FILE

            db_path = _DB_FILE
        self._db_path = db_path

    async def _do_check(self) -> HealthResult:
        def _select_one() -> bool:
            conn = sqlite3.connect(str(self._db_path), timeout=1.0)
            try:
                cursor = conn.execute("SELECT 1")
                result = cursor.fetchone()
                return result == (1,)
            finally:
                conn.close()

        ok = await asyncio.to_thread(_select_one)
        if ok:
            return HealthResult(HealthStatus.UP, {"db": str(self._db_path)})
        return HealthResult(HealthStatus.DOWN, {"reason": "SELECT 1 返回异常"})