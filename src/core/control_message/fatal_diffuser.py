"""ZG-8 控制消息优先级 — 致命扩散引擎。

对标 Linux `zap_other_threads`：
- 会话收到致命控制消息（4/5/6/9，FATAL_MASK 判定）时，向关联异步任务扩散取消信号
- 避免孤儿任务继续向已死会话写入
- 异步下发不阻塞控制消息处理（spec §5.9.1 规则 4，ADR-09）
"""

import asyncio
import time
from collections import deque
from typing import Any, Optional

from src.common.logger import get_logger
from src.core.control_message.types import (
    FATAL_MASK,
    ControlMessageKind,
    FatalDiffuseRecord,
)

logger = get_logger("fatal_diffuser")

# 扩散历史环形缓冲上限（spec §6.7 内省）
_DIFFUSE_HISTORY_LIMIT = 100
# 默认扩散超时（秒，spec §9.2 配置项）
_DEFAULT_DIFFUSE_TIMEOUT_SEC = 5.0


class FatalDiffuser:
    """致命扩散引擎 — 识别致命消息 + 异步扩散取消 + 结果记录。"""

    def __init__(
        self,
        session_lifecycle_port: object = None,
        event_bus: object = None,
        app_config_port: object = None,
    ) -> None:
        """初始化致命扩散引擎。

        Args:
            session_lifecycle_port: SessionLifecyclePort（list_session_async_tasks 查询）
            event_bus: AutonomyEventBusPort（发布 control.zap_completed 事件）
            app_config_port: AppConfigPort（diffuse_timeout_sec 配置，可选）
        """
        self._session_lifecycle_port = session_lifecycle_port
        self._event_bus = event_bus
        timeout = _DEFAULT_DIFFUSE_TIMEOUT_SEC
        if app_config_port is not None:
            try:
                timeout = app_config_port.get_control_message_diffuse_timeout_sec()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, f'扩散超时配置读取失败，使用默认 {_DEFAULT_DIFFUSE_TIMEOUT_SEC}', exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("扩散超时配置读取失败，使用默认 %s", _DEFAULT_DIFFUSE_TIMEOUT_SEC, exc_info=True)
        self._diffuse_timeout = max(0.1, float(timeout))
        self._diffuse_history: deque[FatalDiffuseRecord] = deque(
            maxlen=_DIFFUSE_HISTORY_LIMIT
        )

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                await self._event_bus.emit(event_type, data)
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, f'control 事件发布失败: {event_type}', exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("control 事件发布失败: %s", event_type, exc_info=True)

    async def diffuse(
        self, session_id: str, kind: ControlMessageKind
    ) -> Optional[FatalDiffuseRecord]:
        """致命控制消息扩散 — 异步下发取消信号，不阻塞控制消息处理。

        Args:
            session_id: 目标会话 ID
            kind: 控制消息类别

        Returns:
            非致命返回 None；致命且无关联任务时返回空记录；
            致命且有关联任务时返回 None（结果由后台 worker 记录）
        """
        # 1. 致命控制消息识别（FATAL_MASK 位运算，spec §5.9.1 规则 1）
        if not ((1 << (kind - 1)) & FATAL_MASK):
            return None

        # 2. 查询会话关联的异步任务（spec §5.9.1 规则 2）
        if self._session_lifecycle_port is None:
            return None
        try:
            tasks = await self._session_lifecycle_port.list_session_async_tasks(session_id)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, f'CONTROL_ZAP_QUERY_FAILED: 关联任务查询失败 session={session_id}', exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.warning("CONTROL_ZAP_QUERY_FAILED: 关联任务查询失败 session=%s", session_id, exc_info=True)
            return None  # 查询失败跳过扩散（spec §5.9.2 异常场景 1）

        total = len(tasks)
        if total == 0:
            record = FatalDiffuseRecord(
                session_id=session_id,
                kind=kind,
                total_tasks=0,
                cancelled_tasks=0,
                failed_tasks=0,
                diffuse_time=time.monotonic(),
            )
            self._diffuse_history.append(record)
            return record

        # 3. 异步扩散取消信号（不阻塞，spec §5.9.1 规则 4 / ADR-09）
        asyncio.create_task(self._diffuse_worker(session_id, kind, tasks))
        return None

    async def _diffuse_worker(
        self, session_id: str, kind: ControlMessageKind, tasks: list
    ) -> None:
        """扩散 worker — 后台取消关联任务，统计 cancelled/failed。"""
        cancelled = 0
        failed = 0
        for task in tasks:
            try:
                task.cancel()
                await asyncio.wait_for(task, timeout=self._diffuse_timeout)
                cancelled += 1
            except asyncio.CancelledError:
                cancelled += 1
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, f'CONTROL_ZAP_TASK_CANCEL_FAILED: 任务取消失败 session={session_id}', exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                failed += 1  # 部分失败继续扩散（spec §5.9.2 异常场景 2）
                logger.warning("CONTROL_ZAP_TASK_CANCEL_FAILED: 任务取消失败 session=%s", session_id, exc_info=True)

        # 4. 记录扩散结果（spec §5.9.1 规则 5）
        record = FatalDiffuseRecord(
            session_id=session_id,
            kind=kind,
            total_tasks=len(tasks),
            cancelled_tasks=cancelled,
            failed_tasks=failed,
            diffuse_time=time.monotonic(),
        )
        self._diffuse_history.append(record)
        await self._emit(
            "control.zap_completed",
            {
                "session_id": session_id,
                "total": len(tasks),
                "cancelled": cancelled,
                "failed": failed,
            },
        )

    def get_diffuse_history(self, limit: int = 100) -> list[FatalDiffuseRecord]:
        """查询致命扩散历史（环形缓冲，最近 limit 条）。"""
        return list(self._diffuse_history)[-limit:]
