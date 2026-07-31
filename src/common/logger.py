# 使用基于时间戳的文件处理器，简单的轮转份数限制

import logging
from datetime import date, datetime, timedelta, timezone

from pathlib import Path
from typing import Callable, Optional

import asyncio
import json
import threading
import time

import structlog

from src.common.log_pipeline.ring_buffer import BufferEntry, RingBuffer
from src.common.log_pipeline.ratelimit import RateLimiter
from src.common.log_pipeline.suppressor import Suppressor
from src.common.log_pipeline.crash_dump import CrashDump
import tomlkit

from .logger_color_and_mapping import MODULE_ALIASES, RESET_COLOR, CONVERTED_MODULE_COLORS as MODULE_COLORS

logger = logging.getLogger("auto.logger")

# 创建logs目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logger_file = Path(__file__).resolve()
PROJECT_ROOT = logger_file.parent.parent.parent.resolve()
# 全局handler实例，避免重复创建
_file_handler = None
_console_handler = None
_ws_handler = None
# 全局标志，防止重复初始化
_logging_initialized = False
_cleanup_task_started = False

DEFAULT_LIBRARY_LOG_LEVELS: dict[str, str] = {
    "aiohttp": "WARNING",
    "PIL": "WARNING",
}


def get_file_handler():
    """获取文件handler单例"""
    global _file_handler
    if _file_handler is None:
        # 确保日志目录存在
        LOG_DIR.mkdir(exist_ok=True)

        # 检查现有handler，避免重复创建
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, TimestampedFileHandler):
                _file_handler = handler
                return _file_handler

        # 使用基于时间戳的handler，简单的轮转份数限制
        _file_handler = TimestampedFileHandler(
            log_dir=LOG_DIR,
            max_bytes=max(1024, int(LOG_CONFIG.get("log_file_max_bytes", 5 * 1024 * 1024) or 5 * 1024 * 1024)),
            backup_count=max(1, int(LOG_CONFIG.get("max_log_files", 30) or 30)),
            encoding="utf-8",
        )
        # 设置文件handler的日志级别
        file_level = LOG_CONFIG.get("file_log_level", LOG_CONFIG.get("log_level", "INFO"))
        _file_handler.setLevel(getattr(logging, file_level.upper(), logging.INFO))
    return _file_handler


def get_console_handler():
    """获取控制台handler单例"""
    global _console_handler
    if _console_handler is None:
        _console_handler = logging.StreamHandler()
        # 设置控制台handler的日志级别
        console_level = LOG_CONFIG.get("console_log_level", LOG_CONFIG.get("log_level", "INFO"))
        _console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    return _console_handler


def get_ws_handler():
    """获取 WebSocket handler 单例"""
    global _ws_handler
    if _ws_handler is None:
        _ws_handler = WebSocketLogHandler()
        # WebSocket handler 推送所有级别的日志
        _ws_handler.setLevel(logging.DEBUG)
    return _ws_handler


def initialize_ws_handler(loop):
    """初始化 WebSocket handler 的事件循环

    Args:
        loop: asyncio 事件循环
    """
    handler = get_ws_handler()
    handler.set_loop(loop)

    # 为 WebSocket handler 设置 JSON 格式化器（与文件格式相同）
    handler.setFormatter(file_formatter)

    # 添加到根日志记录器
    root_logger = logging.getLogger()
    if handler not in root_logger.handlers:
        root_logger.addHandler(handler)
        print("[日志系统] ✅ WebSocket 日志推送已启用")


class TimestampedFileHandler(logging.Handler):
    """基于时间戳的文件处理器，简单的轮转份数限制"""

    def __init__(self, log_dir, max_bytes=5 * 1024 * 1024, backup_count=30, encoding="utf-8"):
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.encoding = encoding
        self._lock = threading.Lock()

        # 当前活跃的日志文件
        self.current_file = None
        self.current_stream = None
        self._init_current_file()

    def _init_current_file(self):
        """初始化当前日志文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_file = self.log_dir / f"app_{timestamp}.log.jsonl"
        self.current_stream = open(self.current_file, "a", encoding=self.encoding)

    def _should_rollover(self):
        """检查是否需要轮转"""
        if self.current_file and self.current_file.exists():
            return self.current_file.stat().st_size >= self.max_bytes
        return False

    def _do_rollover(self):
        """执行轮转：关闭当前文件，创建新文件"""
        if self.current_stream:
            self.current_stream.close()

        # 清理旧文件
        self._cleanup_old_files()

        # 创建新文件
        self._init_current_file()

    def _cleanup_old_files(self):
        """清理旧的日志文件，保留指定数量"""
        try:
            # 获取所有日志文件
            log_files = list(self.log_dir.glob("app_*.log.jsonl"))

            # 按修改时间排序
            log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

            # 删除超出数量限制的文件
            for old_file in log_files[self.backup_count :]:
                try:
                    old_file.unlink()
                    print(f"[日志清理] 删除旧文件: {old_file.name}")
                except Exception as e:
                    print(f"[日志清理] 删除失败 {old_file}: {e}")

        except Exception as e:
            print(f"[日志清理] 清理过程出错: {e}")

    def emit(self, record):
        """发出日志记录"""
        try:
            with self._lock:
                # 检查是否需要轮转
                if self._should_rollover():
                    self._do_rollover()

                # 写入日志
                if self.current_stream:
                    msg = self.format(record)
                    self.current_stream.write(msg + "\n")
                    self.current_stream.flush()

        except Exception as exc:
            logger.warning("操作异常 in logger.py", exc_info=True)
            self.handleError(record)

    def close(self):
        """关闭处理器"""
        with self._lock:
            if self.current_stream:
                self.current_stream.close()
                self.current_stream = None
        super().close()


class WebSocketLogHandler(logging.Handler):
    """WebSocket 日志处理器 - 将日志实时推送到前端"""

    _log_counter = 0  # 类级别计数器,确保 ID 唯一性

    def __init__(self, loop=None):
        super().__init__()
        self.loop = loop
        self._initialized = False

    def set_loop(self, loop):
        """设置事件循环"""
        self.loop = loop
        self._initialized = True

    @staticmethod
    def _consume_broadcast_result(task: asyncio.Task) -> None:
        """消费日志广播任务异常，避免后台任务异常泄漏到事件循环。"""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("操作异常 in logger.py", exc_info=True)

    def _schedule_broadcast(self, log_data: dict, target_loop: asyncio.AbstractEventLoop) -> None:
        """在目标事件循环内创建日志广播任务。"""
        if self.loop is not target_loop or target_loop.is_closed():
            return

        try:
            from src.webui.logs_ws import broadcast_log

            broadcast_coro = broadcast_log(log_data)
            try:
                task = target_loop.create_task(broadcast_coro)
            except Exception as exc:
                logger.warning("操作异常 in logger.py", exc_info=True)
                broadcast_coro.close()
                raise
            task.add_done_callback(self._consume_broadcast_result)
        except RuntimeError:
            pass
        except Exception as exc:
            logger.warning("操作异常 in logger.py", exc_info=True)

    def emit(self, record):
        """发送日志到 WebSocket 客户端"""
        target_loop = self.loop
        if not self._initialized or target_loop is None:
            return
        if target_loop.is_closed() or not target_loop.is_running():
            return

        try:
            # 获取格式化后的消息
            # 对于 structlog,formatted message 包含完整的日志信息
            formatted_msg = self.format(record) if self.formatter else record.getMessage()

            # 如果是 JSON 格式(文件格式化器),解析它
            message = formatted_msg
            module_name = record.name
            level_name = record.levelname
            try:
                log_dict = json.loads(formatted_msg)
                message = log_dict.get("event", formatted_msg)
                module_name = log_dict.get("logger_name") or log_dict.get("module") or record.name
                level_name = str(log_dict.get("level") or record.levelname).upper()
            except (json.JSONDecodeError, ValueError):
                # 不是 JSON,直接使用消息
                message = formatted_msg

            # 生成唯一 ID: 时间戳毫秒 + 自增计数器
            WebSocketLogHandler._log_counter += 1
            log_id = f"{int(record.created * 1000)}_{WebSocketLogHandler._log_counter}"

            # 格式化日志数据
            log_data = {
                "id": log_id,
                "timestamp": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "level": level_name,
                "module": module_name,
                "message": message,
            }

            # 异步广播日志(不阻塞日志记录)
            try:
                target_loop.call_soon_threadsafe(self._schedule_broadcast, log_data, target_loop)
            except Exception as exc:
                logger.warning("操作异常 in logger.py", exc_info=True)
                # WebSocket 推送失败不影响日志记录
                pass

        except Exception as exc:
            logger.warning("操作异常 in logger.py", exc_info=True)
            # 不要让 WebSocket 错误影响日志系统
            self.handleError(record)

    def close(self):
        """关闭 WebSocket 日志推送。"""
        self._initialized = False
        self.loop = None
        super().close()


# 旧的轮转文件处理器已移除，现在使用基于时间戳的处理器


def close_handlers():
    """安全关闭所有handler"""
    global _file_handler, _console_handler, _ws_handler

    if _file_handler:
        _file_handler.close()
        _file_handler = None

    if _console_handler:
        _console_handler.close()
        _console_handler = None

    if _ws_handler:
        _ws_handler.close()
        _ws_handler = None


def remove_duplicate_handlers():  # sourcery skip: for-append-to-extend, list-comprehension
    """移除重复的handler，特别是文件handler"""
    root_logger = logging.getLogger()

    # 收集所有时间戳文件handler
    file_handlers = []
    for handler in root_logger.handlers[:]:
        if isinstance(handler, TimestampedFileHandler):
            file_handlers.append(handler)

    # 如果有多个文件handler，保留第一个，关闭其他的
    if len(file_handlers) > 1:
        print(f"[日志系统] 检测到 {len(file_handlers)} 个重复的文件handler，正在清理...")
        for i, handler in enumerate(file_handlers[1:], 1):
            print(f"[日志系统] 关闭重复的文件handler {i}")
            root_logger.removeHandler(handler)
            handler.close()

        # 更新全局引用
        global _file_handler
        _file_handler = file_handlers[0]


# 读取日志配置
def load_log_config():  # sourcery skip: use-contextlib-suppress
    """从配置文件加载日志设置"""
    config_path = Path("config/bot_config.toml")
    default_config = {
        "date_style": "m-d H:i:s",
        "log_level_style": "lite",
        "color_text": "full",
        "log_level": "INFO",  # 全局日志级别（向下兼容）
        "console_log_level": "INFO",  # 控制台日志级别
        "file_log_level": "DEBUG",  # 文件日志级别
        "log_file_max_bytes": 5 * 1024 * 1024,  # 单个日志文件最大大小
        "max_log_files": 30,  # 最多保留的日志文件数量
        "log_cleanup_days": 30,  # 日志保留天数
        "suppress_libraries": [
            "faiss",
            "httpx",
            "urllib3",
            "asyncio",
            "websockets",
            "httpcore",
            "requests",
            "sqlalchemy",
            "openai",
            "uvicorn",
            "jieba",
        ],
        "library_log_levels": DEFAULT_LIBRARY_LOG_LEVELS.copy(),
        # ── ZG-2 环形缓冲 ──
        "buffer_capacity": 2000,          # 最近 N 条（spec 6.1）
        "buffer_max_bytes": 2097152,      # 内存上限 ≤2MB（NFR-PER-02）
        "buffer_entry_max_bytes": 32768,  # 单条超长截断（BUF-02）
        # ── ZG-2 ratelimit ──
        "ratelimit_window_s": 1.0,        # 窗口（秒）
        "ratelimit_max_events": 10,       # 窗口内阈值
        "ratelimit_summary_interval_s": 1.0,  # 摘要输出间隔
        "ratelimit_whitelist": [],        # logger_name 前缀 / 事件签名
        "ratelimit_apply_levels": ["DEBUG", "INFO", "WARNING"],  # ERROR/CRITICAL 默认豁免
        # ── ZG-2 降级抑制 ──
        "health_suppression_map": {"healthy": "none", "degraded": "INFO", "fault": "WARNING", "recovering": "INFO"},
        "suppress_exempt_components": ["service_manager", "watchdog"],
        "suppression_debounce_s": 5.0,
        # ── ZG-2 崩溃导出 ──
        "crash_dump_enabled": True,
    }

    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = tomlkit.load(f)
                loaded = config.get("log", default_config)
                # 默认值兜底：旧配置缺新键时用默认（ZG-2 新增 12 键不破坏旧配置）
                merged = default_config.copy()
                if isinstance(loaded, dict):
                    merged.update(dict(loaded))
                return merged
    except Exception as e:
        print(f"[日志系统] 加载日志配置失败: {e}")
    return default_config


LOG_CONFIG = load_log_config()

# ============================================================
# ZG-2 日志管线：环形缓冲 / ratelimit / 降级抑制（裁决层）
# ============================================================

_ring_buffer: RingBuffer | None = None
_rate_limiter: RateLimiter | None = None
_suppressor: Suppressor | None = None
_suppression_filter: "SuppressionFilter | None" = None
_ring_buffer_handler: "RingBufferHandler | None" = None
_crash_dump: CrashDump | None = None
_last_summary_flush = 0.0


def _is_rate_limit_record(record: logging.LogRecord) -> bool:
    """判断摘要日志：rate_limit 可能在 record 属性或 structlog 事件 dict 中。"""
    if getattr(record, "rate_limit", False):
        return True
    if isinstance(record.msg, dict) and record.msg.get("rate_limit"):
        return True
    return False


class SuppressionFilter(logging.Filter):
    """root logger 级 Filter：SUP（降级抑制）+ RTL（ratelimit）统一裁决。

    返回 False 则整条日志对所有 handler 不可见。全程 try/except：
    异常时返回 True 放行，绝不阻断原链路（NFR-REL-01）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # 周期性摘要输出（窗口过期且有抑制时）
            if not _is_rate_limit_record(record):
                _maybe_flush_summaries()
            # 同一 record 经多个 handler filter 时只判定一次（避免重复计数）
            cached = getattr(record, "_zg2_filter_result", None)
            if cached is not None:
                return cached
            # 摘要日志直接放行（防嵌套，不计数）
            if _is_rate_limit_record(record):
                result = True
            elif _suppressor is not None and _suppressor.should_suppress(
                record.levelno, record.name
            ):
                # SUP 判定（先于 RTL：FAULT 时低级别不进限频计数）
                result = False
            elif _rate_limiter is not None and not _rate_limiter.check(record):
                # RTL 判定
                result = False
            else:
                result = True
            record._zg2_filter_result = result
            return result
        except Exception:
            return True  # 异常放行 + 降级（不阻断落盘/WS）


class RingBufferHandler(logging.Handler):
    """root logger 旁路 handler：emit 时写环形缓冲，不拦截其他 handler。"""

    def __init__(self, ring_buffer: RingBuffer) -> None:
        super().__init__()
        self._ring_buffer = ring_buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # structlog 的 record.msg 是事件 dict，event 字段从 dict 提取
            msg = record.getMessage()
            if isinstance(record.msg, dict):
                event = record.msg.get("event", msg)
            else:
                event = msg
            entry = BufferEntry(
                sequence=0,  # 由 RingBuffer 分配单调序号
                timestamp=datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                level=record.levelname,
                logger_name=record.name,
                module=getattr(record, "module", "") or "",
                event=event,
                rate_limit=_is_rate_limit_record(record),
                extra=dict(getattr(record, "extra", {}) or {}),
            )
            self._ring_buffer.append(entry)
        except Exception:
            pass  # 异常隔离：写入失败不影响落盘/WS


def _maybe_flush_summaries() -> None:
    """周期性摘要输出（挂 filter 调用频率，窗口过期且有抑制时输出）。"""
    global _last_summary_flush
    if _rate_limiter is None:
        return
    now = time.monotonic()
    interval = getattr(_rate_limiter, "_summary_interval_s", 1.0)
    if now - _last_summary_flush < interval:
        return
    _last_summary_flush = now
    _emit_ratelimit_summaries()


def _emit_ratelimit_summaries() -> None:
    """摘要批量输出（由事件循环调度调用）。"""
    if _rate_limiter is None:
        return

    def _output(summary: dict) -> None:
        try:
            _log_summary(summary)
        except Exception:
            pass

    try:
        _rate_limiter.emit_summaries(_output)
    except Exception:
        pass


def _log_summary(summary: dict) -> None:
    """输出摘要日志（带 rate_limit 标记，经 get_logger 走统一链路）。"""
    summary_logger = get_logger(summary.get("source") or "log_pipeline")
    summary_logger.warning(
        summary.get("event") or "日志频率抑制摘要",
        rate_limit=True,
        actual_count=summary.get("actual_count", 0),
        suppressed_count=summary.get("suppressed_count", 0),
        first_ts=summary.get("first_ts", 0.0),
        last_ts=summary.get("last_ts", 0.0),
    )


def _schedule_summary_output() -> None:
    """摘要输出调度：事件循环可用时 call_soon_threadsafe，否则回退同步（低频单条）。"""
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(_emit_ratelimit_summaries)
    except RuntimeError:
        _emit_ratelimit_summaries()


def init_log_pipeline() -> None:
    """初始化 ZG-2 管线组件并挂载到 root logger（_immediate_setup 内调用）。"""
    global _ring_buffer, _rate_limiter, _suppressor, _suppression_filter, _ring_buffer_handler

    cfg = LOG_CONFIG
    _ring_buffer = RingBuffer(
        capacity=int(cfg.get("buffer_capacity", 2000)),
        max_bytes=int(cfg.get("buffer_max_bytes", 2 * 1024 * 1024)),
        entry_max_bytes=int(cfg.get("buffer_entry_max_bytes", 32768)),
    )
    _rate_limiter = RateLimiter(
        window_s=float(cfg.get("ratelimit_window_s", 1.0)),
        max_events=int(cfg.get("ratelimit_max_events", 10)),
        apply_levels={
            logging.getLevelNamesMapping().get(lv, logging.WARNING)
            for lv in cfg.get("ratelimit_apply_levels", ["DEBUG", "INFO", "WARNING"])
        },
        whitelist=tuple(cfg.get("ratelimit_whitelist", []) or []),
        summary_interval_s=float(cfg.get("ratelimit_summary_interval_s", 1.0)),
    )
    _suppressor = Suppressor(
        health_map=cfg.get(
            "health_suppression_map",
            {"healthy": "none", "degraded": "INFO", "fault": "WARNING", "recovering": "INFO"},
        ),
        exempt_components=tuple(cfg.get("suppress_exempt_components", ["service_manager", "watchdog"]) or []),
        debounce_s=float(cfg.get("suppression_debounce_s", 5.0)),
    )

    root_logger = logging.getLogger()
    _suppression_filter = SuppressionFilter()
    # logger 级 filter 只作用于该 logger 自身的 handle；
    # 子 logger 传播时走 handler 级 filter —— 须给每个 handler 挂载（抑制即全 handler 不可见）
    root_logger.addFilter(_suppression_filter)
    for handler in root_logger.handlers[:]:
        handler.addFilter(_suppression_filter)
    _ring_buffer_handler = RingBufferHandler(_ring_buffer)
    _ring_buffer_handler.addFilter(_suppression_filter)
    root_logger.addHandler(_ring_buffer_handler)

    # 崩溃/关闭导出（kmsg_dump）
    global _crash_dump
    if bool(cfg.get("crash_dump_enabled", True)):
        from pathlib import Path

        _crash_dump = CrashDump(_ring_buffer, LOG_DIR, enabled=True)
        _crash_dump.register_hooks()


def get_pipeline_status() -> dict:
    """管线内省（MNT-02）：缓冲水位 / 抑制计数 / 当前抑制线。"""
    status: dict = {
        "buffer": {"size": 0, "capacity": 2000, "total_bytes": 0, "max_bytes": 0},
        "ratelimit": {"active_sources": 0, "total_suppressed": 0},
        "suppression": {"health_level": "healthy", "current_line": "none"},
    }
    if _ring_buffer is not None:
        status["buffer"] = {
            "size": _ring_buffer.size,
            "capacity": _ring_buffer._capacity,
            "total_bytes": _ring_buffer.total_bytes,
            "max_bytes": _ring_buffer._max_bytes,
        }
    if _rate_limiter is not None:
        status["ratelimit"] = _rate_limiter.stats()
    if _suppressor is not None:
        from src.common.log_pipeline.suppressor import _get_current_health_level

        status["suppression"] = {
            "health_level": _get_current_health_level(),
            "current_line": _suppressor.current_line(),
        }
    return status


def get_ring_buffer_snapshot(limit: int | None = None) -> list[dict]:
    """缓冲快照（供 WebUI /search?source=buffer 查询）。"""
    if _ring_buffer is None:
        return []
    return [
        {
            "sequence": e.sequence,
            "timestamp": e.timestamp,
            "level": e.level,
            "logger_name": e.logger_name,
            "module": e.module,
            "event": e.event,
            "rate_limit": e.rate_limit,
        }
        for e in _ring_buffer.snapshot(limit)
    ]



def get_library_log_levels() -> dict[str, str]:
    """获取第三方库日志级别，并补齐内置噪声库的默认限制。"""
    library_log_levels = DEFAULT_LIBRARY_LOG_LEVELS.copy()
    configured_levels = LOG_CONFIG.get("library_log_levels", {})
    if hasattr(configured_levels, "items"):
        library_log_levels.update(dict(configured_levels.items()))
    return library_log_levels


def get_timestamp_format():
    """将配置中的日期格式转换为Python格式"""
    date_style = LOG_CONFIG.get("date_style", "Y-m-d H:i:s")
    # 转换PHP风格的日期格式到Python格式
    format_map = {
        "Y": "%Y",  # 4位年份
        "m": "%m",  # 月份（01-12）
        "d": "%d",  # 日期（01-31）
        "H": "%H",  # 小时（00-23）
        "i": "%M",  # 分钟（00-59）
        "s": "%S",  # 秒数（00-59）
    }

    python_format = date_style
    for php_char, python_char in format_map.items():
        python_format = python_format.replace(php_char, python_char)

    return python_format


def configure_third_party_loggers():
    """配置第三方库的日志级别"""
    # 设置根logger级别为所有handler中最低的级别，确保所有日志都能被捕获
    console_level = LOG_CONFIG.get("console_log_level", LOG_CONFIG.get("log_level", "INFO"))
    file_level = LOG_CONFIG.get("file_log_level", LOG_CONFIG.get("log_level", "INFO"))

    # 获取最低级别（DEBUG < INFO < WARNING < ERROR < CRITICAL）
    console_level_num = getattr(logging, console_level.upper(), logging.INFO)
    file_level_num = getattr(logging, file_level.upper(), logging.INFO)
    min_level = min(console_level_num, file_level_num)

    root_logger = logging.getLogger()
    root_logger.setLevel(min_level)

    # 完全屏蔽的库
    suppress_libraries = LOG_CONFIG.get("suppress_libraries", [])
    for lib_name in suppress_libraries:
        lib_logger = logging.getLogger(lib_name)
        lib_logger.setLevel(logging.CRITICAL + 1)  # 设置为比CRITICAL更高的级别，基本屏蔽所有日志
        lib_logger.propagate = False  # 阻止向上传播

    # 设置特定级别的库
    library_log_levels = get_library_log_levels()
    for lib_name, level_name in library_log_levels.items():
        lib_logger = logging.getLogger(lib_name)
        level = getattr(logging, level_name.upper(), logging.WARNING)
        lib_logger.setLevel(level)


def reconfigure_existing_loggers():
    """重新配置所有已存在的logger，解决加载顺序问题"""
    # 获取根logger
    root_logger = logging.getLogger()

    # 重新设置根logger的所有handler的格式化器
    for handler in root_logger.handlers:
        if isinstance(handler, TimestampedFileHandler):
            handler.setFormatter(file_formatter)
        elif isinstance(handler, logging.StreamHandler):
            handler.setFormatter(console_formatter)

    # 遍历所有已存在的logger并重新配置
    logger_dict = logging.getLogger().manager.loggerDict
    for name, logger_obj in logger_dict.items():
        if isinstance(logger_obj, logging.Logger):
            # 检查是否是第三方库logger
            suppress_libraries = LOG_CONFIG.get("suppress_libraries", [])
            library_log_levels = get_library_log_levels()

            # 如果在屏蔽列表中
            if any(name.startswith(lib) for lib in suppress_libraries):
                logger_obj.setLevel(logging.CRITICAL + 1)
                logger_obj.propagate = False
                continue

            # 如果在特定级别设置中
            for lib_name, level_name in library_log_levels.items():
                if name.startswith(lib_name):
                    level = getattr(logging, level_name.upper(), logging.WARNING)
                    logger_obj.setLevel(level)
                    break

            # 强制清除并重新设置所有handler
            original_handlers = logger_obj.handlers[:]
            for handler in original_handlers:
                # 安全关闭handler
                if hasattr(handler, "close"):
                    handler.close()
                logger_obj.removeHandler(handler)

            # 如果logger没有handler，让它使用根logger的handler（propagate=True）
            if not logger_obj.handlers:
                logger_obj.propagate = True

            # 不重新添加子logger自己的handler，统一走根logger传播
            # 之前重新添加StreamHandler导致propagate=True时每条日志输出两次


def adopt_library_logger(logger_name: str, handler_names: Optional[set[str]] = None):
    """移除第三方库自带 handler，让日志统一走根 logger。"""
    logger_obj = logging.getLogger(logger_name)

    for handler in logger_obj.handlers[:]:
        handler_name = getattr(handler, "name", "")
        if handler_names is not None and handler_name not in handler_names:
            continue

        if hasattr(handler, "close"):
            handler.close()
        logger_obj.removeHandler(handler)

    logger_obj.propagate = True


def normalize_embedded_event_dict(logger, method_name, event_dict):
    """将嵌套在 event 字段中的结构化日志还原为可读文本。"""
    record = event_dict.get("_record")
    if record is not None and isinstance(getattr(record, "msg", None), dict):
        embedded_event = record.msg
    else:
        embedded_event = event_dict.get("event")

    if not isinstance(embedded_event, dict):
        return event_dict

    event_text = embedded_event.get("event")
    if event_text is not None:
        event_dict["event"] = event_text
    else:
        event_dict["event"] = str(embedded_event)

    for field_name in ("logger_name", "module", "lineno", "pathname"):
        if field_name not in event_dict and field_name in embedded_event:
            event_dict[field_name] = embedded_event[field_name]

    for key, value in embedded_event.items():
        if key in {"event", "level", "timestamp", "logger_name", "module", "lineno", "pathname"}:
            continue
        if key not in event_dict:
            event_dict[key] = value

    return event_dict


def convert_pathname_to_module(logger, method_name, event_dict):
    # sourcery skip: extract-method, use-string-remove-affix
    """将 pathname 转换为模块风格的路径"""
    if "logger_name" in event_dict and event_dict["logger_name"] == "maim_message":
        if "pathname" in event_dict:
            del event_dict["pathname"]
            event_dict["module"] = "maim_message"
        return event_dict
    if "pathname" in event_dict:
        pathname = event_dict["pathname"]
        try:
            # 使用绝对路径确保准确性
            pathname_path = Path(pathname).resolve()
            rel_path = pathname_path.relative_to(PROJECT_ROOT)

            # 转换为模块风格：移除 .py 扩展名，将路径分隔符替换为点
            module_path = str(rel_path).replace("\\", ".").replace("/", ".")
            if module_path.endswith(".py"):
                module_path = module_path[:-3]

            # 使用转换后的模块路径替换 module 字段
            event_dict["module"] = module_path
            # 移除原始的 pathname 字段
            del event_dict["pathname"]
        except Exception:
            # 子进程初始化期间 logger 可能为 None，不能用 logger.warning()
            # 直接 fallback：删除 pathname，用文件名作 module 备选
            if "pathname" in event_dict:
                del event_dict["pathname"]
            if "module" not in event_dict:
                event_dict["module"] = Path(pathname).stem

    return event_dict


class ModuleColoredConsoleRenderer:
    """自定义控制台渲染器，为不同模块提供不同颜色"""

    def __init__(self, colors=True):
        # sourcery skip: merge-duplicate-blocks, remove-redundant-if
        self._colors = colors
        self._config = LOG_CONFIG

        # 日志级别颜色
        self._level_colors = {
            "debug": "\033[38;5;208m",  # 橙色
            "info": "\033[38;5;117m",  # 天蓝色
            "success": "\033[32m",  # 绿色
            "warning": "\033[33m",  # 黄色
            "error": "\033[31m",  # 红色
            "critical": "\033[35m",  # 紫色
        }

        # 根据配置决定是否启用颜色
        color_text = self._config.get("color_text", "title")
        if color_text == "none":
            self._colors = False
        elif color_text == "title":
            self._enable_module_colors = True
            self._enable_level_colors = False
            self._enable_full_content_colors = False
        elif color_text == "full":
            self._enable_module_colors = True
            self._enable_level_colors = True
            self._enable_full_content_colors = True
        else:
            self._enable_module_colors = True
            self._enable_level_colors = False
            self._enable_full_content_colors = False

    def __call__(self, logger, method_name, event_dict):
        # sourcery skip: merge-duplicate-blocks
        """渲染日志消息"""
        # 获取基本信息
        timestamp = event_dict.get("timestamp", "")
        level = event_dict.get("level", "info")
        logger_name = event_dict.get("logger_name") or event_dict.get("logger", "")
        event = event_dict.get("event", "")

        # 构建输出
        parts = []

        # 日志级别样式配置
        log_level_style = self._config.get("log_level_style", "lite")
        level_color = self._level_colors.get(level.lower(), "") if self._colors else ""

        # 时间戳（lite模式下按级别着色）
        if timestamp:
            if log_level_style == "lite" and level_color:
                timestamp_part = f"{level_color}{timestamp}{RESET_COLOR}"
            else:
                timestamp_part = timestamp
            parts.append(timestamp_part)

        # 日志级别显示（根据配置样式）
        if log_level_style == "full":
            # 显示完整级别名并着色
            level_text = level.upper()
            if level_color:
                level_part = f"{level_color}[{level_text:>8}]{RESET_COLOR}"
            else:
                level_part = f"[{level_text:>8}]"
            parts.append(level_part)

        elif log_level_style == "compact":
            # 只显示首字母并着色
            level_text = level.upper()[0]
            if level_color:
                level_part = f"{level_color}[{level_text:>8}]{RESET_COLOR}"
            else:
                level_part = f"[{level_text:>8}]"
            parts.append(level_part)

        # lite模式不显示级别，只给时间戳着色

        # 获取模块颜色，用于full模式下的整体着色
        module_color = ""
        if self._colors and self._enable_module_colors and logger_name:
            module_color = MODULE_COLORS.get(logger_name, "")

        # 模块名称（带颜色和别名支持）
        if logger_name:
            # 获取别名，如果没有别名则使用原名称
            display_name = MODULE_ALIASES.get(logger_name, logger_name)

            if self._colors and self._enable_module_colors:
                if module_color:
                    module_part = f"{module_color}[{display_name}]{RESET_COLOR}"
                else:
                    module_part = f"[{display_name}]"
            else:
                module_part = f"[{display_name}]"
            parts.append(module_part)

        # 消息内容（确保转换为字符串）
        event_content = ""
        if isinstance(event, str):
            event_content = event
        elif isinstance(event, dict):
            # 如果是字典，格式化为可读字符串
            try:
                event_content = json.dumps(event, ensure_ascii=False, indent=None)
            except (TypeError, ValueError):
                event_content = str(event)
        else:
            # 其他类型直接转换为字符串
            event_content = str(event)

        # 在full模式下为消息内容着色
        if self._colors and self._enable_full_content_colors and module_color:
            event_content = f"{module_color}{event_content}{RESET_COLOR}"

        parts.append(event_content)

        # 处理其他字段
        extras = []
        for key, value in event_dict.items():
            if key not in (
                "timestamp",
                "level",
                "logger_name",
                "logger",
                "event",
                "module",
                "lineno",
                "pathname",
                "exception",
            ):
                # 确保值也转换为字符串
                if isinstance(value, (dict, list)):
                    try:
                        value_str = json.dumps(value, ensure_ascii=False, indent=None)
                    except (TypeError, ValueError):
                        value_str = str(value)
                else:
                    value_str = str(value)

                # 在full模式下为额外字段着色
                extra_field = f"{key}={value_str}"
                if self._colors and self._enable_full_content_colors and module_color:
                    extra_field = f"{module_color}{extra_field}{RESET_COLOR}"

                extras.append(extra_field)

        if extras:
            parts.append(" ".join(extras))

        rendered_message = " ".join(parts)
        exception_text = event_dict.get("exception")
        if exception_text:
            return f"{rendered_message}\n{exception_text}"

        return rendered_message


# 配置标准logging以支持文件输出和压缩
# 使用单例handler避免重复创建
file_handler = get_file_handler()
console_handler = get_console_handler()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[file_handler, console_handler],
)


def configure_structlog():
    """配置structlog"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.PATHNAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            convert_pathname_to_module,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt=get_timestamp_format(), utc=False),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# 配置structlog
configure_structlog()

# 为文件输出配置JSON格式
file_formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.processors.JSONRenderer(ensure_ascii=False),
    foreign_pre_chain=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        normalize_embedded_event_dict,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            parameters=[structlog.processors.CallsiteParameter.PATHNAME, structlog.processors.CallsiteParameter.LINENO]
        ),
        convert_pathname_to_module,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ],
)

# 为控制台输出配置可读格式
console_formatter = structlog.stdlib.ProcessorFormatter(
    processor=ModuleColoredConsoleRenderer(colors=True),
    foreign_pre_chain=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        normalize_embedded_event_dict,
        convert_pathname_to_module,
        structlog.processors.TimeStamper(fmt=get_timestamp_format(), utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ],
)

# 获取根logger并配置格式化器
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if isinstance(handler, TimestampedFileHandler):
        handler.setFormatter(file_formatter)
    else:
        handler.setFormatter(console_formatter)


# 立即配置日志系统，确保最早期的日志也使用正确格式
def _immediate_setup():
    """立即设置日志系统，在模块导入时就生效"""
    # 重新配置structlog
    configure_structlog()

    # 清除所有已有的handler，重新配置
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 使用单例handler避免重复创建
    file_handler = get_file_handler()
    console_handler = get_console_handler()

    # 重新添加配置好的handler
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 设置格式化器
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)

    # 清理重复的handler
    remove_duplicate_handlers()

    # maim_message 导入时会给同名 stdlib logger 挂默认 handler，这里统一收口。
    adopt_library_logger("maim_message", handler_names={"maim_message_default_handler"})

    # 配置第三方库日志
    configure_third_party_loggers()

    # 重新配置所有已存在的logger
    reconfigure_existing_loggers()

    # ZG-2: 管线挂载（裁决层 Filter + 环形缓冲旁路 Handler）
    init_log_pipeline()


# 立即执行配置
_immediate_setup()

raw_logger: structlog.stdlib.BoundLogger = structlog.get_logger()

binds: dict[str, Callable] = {}


def get_logger(name: Optional[str]) -> structlog.stdlib.BoundLogger:
    """获取logger实例，支持按名称绑定"""
    if name is None:
        return raw_logger
    if name == "maim_message":
        adopt_library_logger(name, handler_names={"maim_message_default_handler"})
    logger = binds.get(name)  # type: ignore
    if logger is None:
        logger: structlog.stdlib.BoundLogger = structlog.get_logger(name).bind(logger_name=name)
        binds[name] = logger
    return logger


def initialize_logging(verbose: bool = True):
    """手动初始化日志系统，确保所有logger都使用正确的配置

    在应用程序的早期调用此函数，确保所有模块都使用统一的日志配置

    Args:
        verbose: 是否输出详细的初始化信息。默认为 True。
                 在 Runner 进程中可以设置为 False 以避免重复的初始化日志。
    """
    global LOG_CONFIG, _logging_initialized

    # 防止重复初始化（在同一进程内）
    if _logging_initialized:
        return

    _logging_initialized = True

    LOG_CONFIG = load_log_config()


def cleanup_old_logs():
    """清理过期的日志文件"""
    try:
        cleanup_days = max(1, int(LOG_CONFIG.get("log_cleanup_days", 30) or 30))
        cutoff_date = datetime.now() - timedelta(days=cleanup_days)
        deleted_count = 0
        deleted_size = 0

        # 遍历日志目录（显式三模式，天然排除 dump_* 独立命名空间）
        for pattern in ("app_*.log.jsonl", "maibot_*.log.jsonl", "think_cycles_*.log.jsonl"):
            for log_file in LOG_DIR.glob(pattern):
                try:
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_size = log_file.stat().st_size
                        log_file.unlink()
                        deleted_count += 1
                        deleted_size += file_size
                except Exception as e:
                    logger = get_logger("logger")
                    logger.warning(f"清理日志文件 {log_file} 时出错: {e}")

        if deleted_count > 0:
            logger = get_logger("logger")
            logger.info(f"清理了 {deleted_count} 个过期日志文件，释放空间 {deleted_size / 1024 / 1024:.2f} MB")

    except Exception as e:
        logger = get_logger("logger")
        logger.error(f"清理旧日志文件时出错: {e}")


def start_log_cleanup_task():
    """启动日志清理任务"""
    global _cleanup_task_started

    # 防止重复启动清理任务
    if _cleanup_task_started:
        return

    _cleanup_task_started = True

    def cleanup_task():
        while True:
            cleanup_old_logs()
            time.sleep(24 * 60 * 60)  # 每24小时执行一次

    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()


def shutdown_logging():
    """优雅关闭日志系统，释放所有文件句柄"""
    # 先输出到控制台，避免日志系统关闭后无法输出
    print("[logger] 正在关闭日志系统...")

    # ZG-2: 正常关闭前导出环形缓冲（关闭 handlers 之前，缓冲仍完整）
    if _crash_dump is not None:
        _crash_dump.export("shutdown")

    # 关闭所有handler
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if hasattr(handler, "close"):
            handler.close()
        root_logger.removeHandler(handler)

    # 关闭全局handler
    close_handlers()

    # 关闭所有其他logger的handler
    logger_dict = logging.getLogger().manager.loggerDict
    for _name, logger_obj in logger_dict.items():
        if isinstance(logger_obj, logging.Logger):
            for handler in logger_obj.handlers[:]:
                if hasattr(handler, "close"):
                    handler.close()
                logger_obj.removeHandler(handler)

    # 使用 print 而不是 logger，因为 logger 已经关闭
    print("[logger] 日志系统已关闭")


def log_think_cycle(entry: dict) -> None:
    """写入 ThinkCycleLog 到 logs/think_cycles_{date}.log.jsonl。

    Args:
        entry: 包含 agent_id/action/cycles/total_tokens/elapsed_ms 等字段的字典。
    """
    from datetime import date
    _log_dir = Path("logs")
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / f"think_cycles_{date.today().isoformat()}.log.jsonl"
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
