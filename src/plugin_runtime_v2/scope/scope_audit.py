"""运行时 Tier 1 审计模块（ZG16-5 模块 B）。

异步 JSON Lines 写入 + 参数脱敏 + 日志轮转 + 双路上报。
审计 best-effort：崩溃不阻断 Tier 1 操作（spec 5.3.1 规则 11）。
"""

import asyncio
import json
import re
import time
from logging.handlers import RotatingFileHandler  # noqa: TID251  受控用法：日志轮转需 RotatingFileHandler
from pathlib import Path

from src.common.logger import get_logger

logger = get_logger("scope_audit")

# 文件路径检测正则（design 2.4.2）
_FILE_PATH_RE = re.compile(r"^[/\\]|[a-zA-Z]:[/\\]|.+\.\w{1,8}$")


def _looks_like_file_path(s: str) -> bool:
    """判断字符串是否像文件路径（design 2.4.2）。"""
    return bool(_FILE_PATH_RE.search(s))


class ScopeAuditRecorder:
    """Tier 1 敏感操作审计记录器——异步 JSON Lines + 参数脱敏 + 日志轮转。"""

    def __init__(
        self,
        log_path: str = "data/plugin_runtime_v2/scope_audit.log",
        max_size_mb: int = 10,
        backup_count: int = 5,
        sensitive_param_names: list[str] | None = None,
    ) -> None:
        """初始化内存队列 + RotatingFileHandler。

        初始化失败（路径不可创建等）→ 降级为仅 error_escalation 上报 + warning（spec 5.3.3 场景 3）。
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._sensitive_names = sensitive_param_names or [
            "token", "password", "secret", "api_key", "apikey", "credential",
        ]
        self._consumer_task: asyncio.Task | None = None
        self._closed = False

        # 确保目录存在
        try:
            log_file = Path(log_path)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            self._handler = RotatingFileHandler(
                log_path,
                maxBytes=max_size_mb * 1024 * 1024,
                backupCount=backup_count,
                encoding="utf-8",
            )
            self._handler_disabled = False
        except Exception as e:
            logger.warning("审计日志文件初始化失败，降级为仅 error_escalation 上报: %s", e)
            self._handler = None
            self._handler_disabled = True

    def _desensitize_params(
        self,
        params: dict,
        sensitive_names: list[str],
    ) -> dict:
        """参数脱敏：敏感字段→***，文件路径→<file>，复杂类型仅标类型。

        禁止记录完整参数（spec 4.3.1, 5.3.1 规则 10）。
        """
        try:
            result: dict = {}
            lower_sensitive = [n.lower() for n in sensitive_names]
            for key, value in params.items():
                if isinstance(key, str) and key.lower() in lower_sensitive:
                    result[key] = "***"
                elif isinstance(value, str) and _looks_like_file_path(value):
                    result[key] = "<file>"
                elif isinstance(value, (dict, list)):
                    result[key] = f"<{type(value).__name__}>"
                else:
                    result[key] = value
            return result
        except Exception:
            return {"<desensitize_failed>": True}

    async def record(
        self,
        plugin_id: str,
        scope: str,
        params: dict,
    ) -> None:
        """记录 Tier 1 审计条目（异步，不阻塞）。参数脱敏后入队。"""
        try:
            param_summary = self._desensitize_params(params, self._sensitive_names)
            entry = {
                "plugin_id": plugin_id,
                "timestamp": round(time.time(), 3),
                "scope": scope,
                "param_summary": param_summary,
                "level": "INFO",
            }
            # 队列满时丢弃最老条目 + warning（design 2.6.2，避免 OOM）
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                logger.warning("审计队列已满，丢弃最老条目")
            self._queue.put_nowait(entry)
        except Exception as e:
            # best-effort：record 异常不阻断执行（spec 5.3.1 规则 11）
            logger.warning("审计入队失败: %s", e)

    def _write_with_rotation(self, line: str) -> None:
        """写入日志行，手动触发 RotatingFileHandler 轮转。

        RotatingFileHandler.emit() 内部调 shouldRollover/doRollover，
        直接写 stream 绕过轮转——这里手动检查文件大小并触发轮转。
        """
        handler = self._handler
        if handler is None:
            return
        line_bytes = line.encode("utf-8")
        if handler.stream is None:
            handler.stream = handler._open()
        # 检查是否需要轮转（对标 RotatingFileHandler.shouldRollover）
        if handler.maxBytes > 0 and handler.stream.tell() + len(line_bytes) > handler.maxBytes:
            handler.doRollover()
        handler.stream.write(line)
        handler.stream.flush()

    async def _consumer_loop(self) -> None:
        """异步消费者：出队 → json.dumps → 写 RotatingFileHandler → 上报 error_escalation。"""
        while True:
            try:
                entry = await self._queue.get()
                line = json.dumps(entry, ensure_ascii=False)

                # 写入 RotatingFileHandler（手动触发轮转）
                if self._handler is not None and not self._handler_disabled:
                    write_ok = False
                    for attempt in range(3):
                        try:
                            self._write_with_rotation(line + "\n")
                            write_ok = True
                            break
                        except Exception:
                            await asyncio.sleep(0.001 * (attempt + 1))
                    if not write_ok:
                        # 重试 3 次仍失败 → 放弃该条目 + 上报 ERROR（spec 5.3.3 场景 1）
                        self._report_escalation(
                            "ERROR",
                            f"审计写入失败（重试 3 次）: scope={entry.get('scope')}",
                            entry.get("plugin_id", "unknown"),
                        )

                # 双路上报 error_escalation_port（best-effort，spec 5.3.1 规则 6）
                self._report_escalation(
                    "INFO",
                    f"Tier 1 审计: scope={entry.get('scope')}",
                    entry.get("plugin_id", "unknown"),
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("审计消费者循环异常: %s", e)

    def _report_escalation(self, level: str, message: str, component_id: str) -> None:
        """best-effort 上报 error_escalation_port。"""
        try:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                error_level = ErrorLevel.ERROR if level == "ERROR" else ErrorLevel.WARN
                port.report(error_level, message, component_id=component_id)
        except Exception:
            # 上报失败 → 跳过上报（best-effort，spec 5.3.3 场景 2）
            pass

    async def close(self) -> None:
        """关闭：取消消费者 + flush 队列 + 关闭日志文件。"""
        if self._closed:
            return
        self._closed = True

        # 取消消费者任务
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # flush 剩余队列：同步写入文件
        if self._handler is not None and not self._handler_disabled:
            while True:
                try:
                    entry = self._queue.get_nowait()
                    line = json.dumps(entry, ensure_ascii=False)
                    self._write_with_rotation(line + "\n")
                except asyncio.QueueEmpty:
                    break
                except Exception:
                    break
            self._handler.close()


# ── 全局单例 ──
_scope_audit_recorder: ScopeAuditRecorder | None = None


def get_scope_audit_recorder() -> ScopeAuditRecorder | None:
    """获取全局审计记录器（未初始化返回 None，调用方跳过审计）。"""
    return _scope_audit_recorder


def init_scope_audit_recorder(
    log_path: str,
    max_size_mb: int,
    backup_count: int,
    sensitive_param_names: list[str],
) -> ScopeAuditRecorder:
    """初始化全局审计记录器（main.py 启动时调用）。"""
    global _scope_audit_recorder
    recorder = ScopeAuditRecorder(
        log_path=log_path,
        max_size_mb=max_size_mb,
        backup_count=backup_count,
        sensitive_param_names=sensitive_param_names,
    )
    # 启动异步消费者任务（必须在事件循环内调用——main.py 已确保）
    try:
        recorder._consumer_task = asyncio.create_task(recorder._consumer_loop())
    except RuntimeError:
        # 无运行中事件循环 → 消费者不启动，record 入队但不落盘
        # P0 修复后 main.py 在 async main() 内调用，此分支不应触发
        logger.warning("init_scope_audit_recorder 未在事件循环内调用，消费者未启动")
    _scope_audit_recorder = recorder
    return recorder


async def close_scope_audit_recorder() -> None:
    """关闭全局审计记录器（main.py 关闭时调用）。"""
    global _scope_audit_recorder
    if _scope_audit_recorder is not None:
        await _scope_audit_recorder.close()
        _scope_audit_recorder = None