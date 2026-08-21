"""db.memorix 健康检查 — A_memorix metadata.db 可达性（SELECT 1）。

超时 3s。文件不存在时返回 UNKNOWN（A_memorix 可能未启用）。
"""

import asyncio
import sqlite3
from pathlib import Path

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus


class MemorixDbHealthCheck(BaseHealthCheck):
    """A_memorix metadata.db 健康检查。"""

    timeout = 3.0

    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__(name="db.memorix")
        if db_path is None:
            from src.A_memorix.paths import default_data_dir

            db_path = default_data_dir() / "metadata" / "metadata.db"
        self._db_path = db_path

    async def _do_check(self) -> HealthResult:
        if not self._db_path.exists():
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "metadata.db 不存在（A_memorix 可能未启用）", "path": str(self._db_path)},
            )

        def _select_one() -> bool:
            conn = sqlite3.connect(str(self._db_path), timeout=1.0)
            try:
                cursor = conn.execute("SELECT 1")
                return cursor.fetchone() == (1,)
            finally:
                conn.close()

        ok = await asyncio.to_thread(_select_one)
        if ok:
            return HealthResult(HealthStatus.UP, {"db": str(self._db_path)})
        return HealthResult(HealthStatus.DOWN, {"reason": "SELECT 1 返回异常"})