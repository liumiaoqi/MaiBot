"""崩溃/关闭导出（ZG-2 BUF-04，对标 kmsg_dump）。

崩溃（signal/excepthook/loop 异常）与正常关闭时，将环形缓冲导出为
logs/dump_<ts>_<pid>.log.jsonl 独立命名空间。best-effort：失败仅记录，不二次抛异常。
"""

import json
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from src.common.log_pipeline.ring_buffer import RingBuffer


class CrashDump:
    """环形缓冲导出器。"""

    def __init__(self, ring_buffer: RingBuffer, log_dir: Path, enabled: bool) -> None:
        self._ring_buffer = ring_buffer
        self._log_dir = log_dir
        self._enabled = enabled
        self._exported = False
        self._lock = threading.Lock()
        # ZG-7（T17）：污染状态查询接口，启动接线时注入（模块级单例无法构造时注入）
        self._taint_mask_port = None

    def set_taint_mask_port(self, port) -> None:
        """注入污染状态查询接口（ZG-7，spec §4.5 规则 1）。

        模块级单例在启动早期创建（logger.py），TaintMaskAdapter 启动后期才实例化，
        故用 setter 注入而非构造参数（CC 审查 P2 修正）。
        """
        self._taint_mask_port = port

    def _taint_line(self) -> str:
        """构造污染状态行（JSON）；port 未注入时返回 None（跳过污染行）。"""
        if self._taint_mask_port is None:
            return None
        try:
            data = {
                "tainted_mask": self._taint_mask_port.get_taint(),
                "tainted_verbose": self._taint_mask_port.print_tainted_verbose(),
            }
            try:
                data["degrade_on_taint_mask"] = self._taint_mask_port.get_degrade_on_taint_mask()
            except Exception:
                data["degrade_on_taint_mask"] = "N/A"
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return None

    def export(self, reason: str) -> None:
        """导出缓冲为 dump_*.log.jsonl。best-effort：失败仅记录，不二次抛异常。"""
        if not self._enabled:
            return
        with self._lock:
            if self._exported:
                return
            self._exported = True
        try:
            entries = self._ring_buffer.drain()
            if not entries:
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pid = _get_pid()
            path = self._log_dir / f"dump_{timestamp}_{pid}.log.jsonl"
            with open(path, "w", encoding="utf-8") as f:
                # ZG-7（T17）：首行追加污染状态（对标 Linux kmsg_dump 含 "Tainted: ..." 行）
                taint_line = self._taint_line()
                if taint_line is not None:
                    f.write(taint_line + "\n")
                for entry in entries:
                    line = {
                        "sequence": entry.sequence,
                        "timestamp": entry.timestamp,
                        "level": entry.level,
                        "logger_name": entry.logger_name,
                        "module": entry.module,
                        "event": entry.event,
                        "rate_limit": entry.rate_limit,
                        "truncated": entry.truncated,
                    }
                    if entry.extra:
                        line["extra"] = entry.extra
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
            _print(f"[logger] 崩溃缓冲已导出: {path}（{len(entries)} 条，原因: {reason}）")
        except Exception as e:  # best-effort：失败仅记录
            _print(f"[logger] 崩溃缓冲导出失败: {e}")

    def register_hooks(self) -> None:
        """注册 signal(SIGTERM/SIGINT) + sys.excepthook + asyncio 异常钩子。"""
        if not self._enabled:
            return
        try:
            signal.signal(signal.SIGTERM, self._make_signal_handler(signal.SIGTERM))
            signal.signal(signal.SIGINT, self._make_signal_handler(signal.SIGINT))
        except Exception:
            pass  # 非主线程等场景注册失败忽略
        sys.excepthook = self._make_excepthook(sys.excepthook)

    def _make_signal_handler(self, signum: int):
        """包装信号处理：导出后走原默认行为（SIGTERM 默认终止）。"""

        def handler(sig, frame):
            self.export(f"signal-{sig}")
            if signum == signal.SIGTERM:
                sys.exit(143)
            elif signum == signal.SIGINT:
                sys.exit(130)

        return handler

    def _make_excepthook(self, original):
        """包装未捕获异常钩子：导出后走原钩子。"""

        def hook(exc_type, exc_value, exc_tb):
            self.export(f"uncaught-{exc_type.__name__}")
            original(exc_type, exc_value, exc_tb)

        return hook


def _get_pid() -> int:
    try:
        import os

        return os.getpid()
    except Exception:
        return 0


def _print(message: str) -> None:
    """崩溃场景 logger 可能不可用，用 print 兜底。"""
    try:
        print(message)
    except Exception:
        pass
