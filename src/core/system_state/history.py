"""迁移历史 — 内存环形缓冲 + 崩溃导出。

最近 N 条，崩溃/关闭时尽力导出为 lifecycle_<timestamp>.log.jsonl
（独立命名空间，不污染主日志）。
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from src.common.logger import get_logger
from src.core.system_state.types import TransitionRecord

logger = get_logger(__name__)


class TransitionHistory:
    """迁移历史环形缓冲。"""

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = max(1, capacity)
        self._records: list[TransitionRecord] = []
        self._lock = threading.Lock()

    def append(self, record: TransitionRecord) -> None:
        """追加记录，超容量淘汰最早。"""
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._capacity:
                self._records = self._records[-self._capacity:]

    def get_all(self) -> list[TransitionRecord]:
        """按时间正序返回全部（当前容量内）。"""
        with self._lock:
            return list(self._records)

    def export_to_jsonl(self, path: Path) -> None:
        """导出到 JSONL。best-effort：失败仅记录，不二次抛异常。"""
        try:
            records = self.get_all()
            if not records:
                return
            with open(path, "w", encoding="utf-8") as f:
                for record in records:
                    line = {
                        "timestamp": record.timestamp,
                        "old_state": record.old_state.snake_case,
                        "new_state": record.new_state.snake_case,
                        "reason": record.reason.value,
                        "duration_ms": record.duration_ms,
                    }
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
            logger.info("迁移历史已导出: %s（%d 条）", path, len(records))
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("迁移历史导出失败: %s", path)

    @staticmethod
    def default_export_path(log_dir: Path = Path("logs")) -> Path:
        """默认导出路径：logs/lifecycle_<timestamp>.log.jsonl。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return log_dir / f"lifecycle_{timestamp}.log.jsonl"
