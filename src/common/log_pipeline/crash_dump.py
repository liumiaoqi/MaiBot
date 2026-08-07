"""崩溃/关闭导出（ZG-2 BUF-04，对标 kmsg_dump）。

崩溃（signal/excepthook/loop 异常）与正常关闭时，将环形缓冲导出为
logs/dump_<ts>_<pid>.log.jsonl 独立命名空间。best-effort：失败仅记录，不二次抛异常。

ZG-14 方法分离（spec §5.5.1 规则 1）：
- export_on_crash：一次性导出（signal/excepthook 调用，保留原语义）
- export_snapshot：多次导出（ZG-14 CRASH_DUMP 动作调用，含等级/计数/
  配置上下文，经独立 RateLimiter 1 分钟最多 3 次防快照风暴，规则 4）
- export：兼容入口，委托 export_on_crash（不破坏现有调用点，规则 6）
"""

import json
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from src.common.log_pipeline.ring_buffer import RingBuffer

# export_snapshot 独立限流：默认 1 分钟最多 3 次（spec §5.5.1 规则 4）
_SNAPSHOT_WINDOW_SEC = 60.0
_SNAPSHOT_MAX_EXPORTS = 3


class _SnapshotLimiter:
    """export_snapshot 独立限流器（1 分钟最多 3 次，spec §5.5.1 规则 4）。"""

    def __init__(
        self,
        *,
        window_sec: float = _SNAPSHOT_WINDOW_SEC,
        max_exports: int = _SNAPSHOT_MAX_EXPORTS,
        time_func=time.time,
    ) -> None:
        self._window_sec = window_sec
        self._max_exports = max_exports
        self._time_func = time_func
        self._exports: list[float] = []

    def allow(self) -> bool:
        """窗口内未超限则允许并记录，否则抑制（静默计数不导出）。"""
        now = self._time_func()
        self._exports = [ts for ts in self._exports if now - ts < self._window_sec]
        if len(self._exports) >= self._max_exports:
            return False
        self._exports.append(now)
        return True


class CrashDump:
    """环形缓冲导出器。"""

    def __init__(
        self,
        ring_buffer: RingBuffer,
        log_dir: Path,
        enabled: bool,
        *,
        time_func=time.time,
    ) -> None:
        self._ring_buffer = ring_buffer
        self._log_dir = log_dir
        self._enabled = enabled
        self._exported = False
        self._lock = threading.Lock()
        self._snapshot_limiter = _SnapshotLimiter(time_func=time_func)
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
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "查询掩码降级状态失败", exception=exc)
                # 查询掩码失败：字段降级为 N/A（spec §5.2.3.1）；标记债务
                # （崩溃场景 logger 不可用，用 _print 兜底，不留普通日志）
                from src.core.tainted_mask.mark import mark_exception_swallowed

                mark_exception_swallowed()
                data["degrade_on_taint_mask"] = "N/A"
            return json.dumps(data, ensure_ascii=False)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "构建污染状态行失败", exception=exc)
            return None

    def export(self, reason: str) -> None:
        """兼容入口：委托 export_on_crash（保留原签名，不破坏调用点）。

        现 signal/excepthook 调用点保持 export 不变（spec §4.5 规则 3）。
        """
        self.export_on_crash(reason)

    def export_on_crash(self, reason: str) -> None:
        """一次性导出（signal/excepthook 调用，保留原语义）。

        首次调用导出，后续直接返回（spec §5.5.1 规则 1）。best-effort：
        失败仅记录，不二次抛异常。
        """
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
            self._write_dump(path, None, entries, reason)
            _print(f"[logger] 崩溃缓冲已导出: {path}（{len(entries)} 条，原因: {reason}）")
        except Exception as e:  # best-effort：失败仅记录
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "崩溃缓冲导出失败", exception=e)
            _print(f"[logger] 崩溃缓冲导出失败: {e}")

    def export_snapshot(self, reason: str, context: dict | None = None) -> None:
        """主动快照导出（多次调用，ZG-14 CRASH_DUMP 动作调用）。

        与 export_on_crash 一次性语义分离（spec §5.5.1 规则 1）；经独立
        限流器 1 分钟最多 3 次（规则 4，超出静默计数不导出）；快照含
        触发等级/消息/组件标识/计数/配置上下文（规则 3）+ 最近 N 条日志
        环形缓冲副本（snapshot() 只读不消费，规则 6）；只读导出不修改
        全局状态（规则 6）；失败（如磁盘满）捕获记录不阻塞其他动作
        （规则 5，spec §5.5.3 异常场景 1）。
        """
        if not self._enabled:
            return
        if not self._snapshot_limiter.allow():
            _print(f"[logger] 快照导出被限流跳过: {reason}（1 分钟最多 {_SNAPSHOT_MAX_EXPORTS} 次）")
            return
        try:
            # 只读副本（不消费缓冲——快照不影响后续崩溃导出）
            entries = self._ring_buffer.snapshot()
            # 微秒精度防同秒多快照文件名冲突（export_snapshot 允许多次导出）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            pid = _get_pid()
            path = self._log_dir / f"snapshot_{timestamp}_{pid}.log.jsonl"
            meta = {"type": "snapshot", "reason": reason}
            if context is not None:
                meta["context"] = context
            # 环形缓冲未初始化（空）时导出空快照 + 标记（spec §5.5.3 异常场景 2）
            if not entries:
                meta["buffer_empty"] = True
            self._write_dump(path, meta, entries, reason)
            _print(f"[logger] 主动快照已导出: {path}（{len(entries)} 条，原因: {reason}）")
        except Exception as e:  # IOError 等：跳过本次快照（spec §5.5.3 异常场景 1）
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "主动快照导出失败", exception=e)
            _print(f"[logger] 主动快照导出失败: {e}")

    def _write_dump(self, path: Path, meta: dict | None, entries, reason: str) -> None:
        """公共写文件：meta 首行（可选）+ 环形缓冲条目 + 污染状态行。"""
        with open(path, "w", encoding="utf-8") as f:
            if meta is not None:
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")
            # ZG-7（T17）：污染状态行（对标 Linux kmsg_dump 含 "Tainted: ..." 行）
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

    def register_hooks(self) -> None:
        """注册 signal(SIGTERM/SIGINT) + sys.excepthook + asyncio 异常钩子。"""
        if not self._enabled:
            return
        try:
            signal.signal(signal.SIGTERM, self._make_signal_handler(signal.SIGTERM))
            signal.signal(signal.SIGINT, self._make_signal_handler(signal.SIGINT))
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "注册信号处理失败", exception=exc)
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
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "获取进程 PID 失败", exception=exc)
        return 0


def _print(message: str) -> None:
    """崩溃场景 logger 可能不可用，用 print 兜底。"""
    try:
        print(message)
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "崩溃日志 print 输出失败", exception=exc)
        pass
