"""ZG-14 测试共享辅助 — 引擎构造 + Port mock + 异步排空。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.escalator import ErrorEscalator


def make_escalator(
    config: ErrorEscalationConfig | None = None,
    *,
    with_ports: bool = True,
    time_func=None,
) -> tuple[ErrorEscalator, dict[str, MagicMock]]:
    """构造引擎 + 各 Port mock（默认全部注入）。

    Port 的异步方法（create_task 派发目标）必须用 AsyncMock——普通
    MagicMock 调用返回 mock 而非 coroutine，create_task 会抛 TypeError。
    """
    esc = ErrorEscalator(config or ErrorEscalationConfig(), time_func=time_func)
    ports: dict[str, MagicMock] = {
        "taint": MagicMock(),
        "state_machine": MagicMock(),
        "service_manager": MagicMock(),
        "event_bus": MagicMock(),
        "crash_dump": MagicMock(),
        "rate_limiter": MagicMock(),
    }
    # 异步动作目标方法 → AsyncMock
    ports["state_machine"].trigger_health_level_change = AsyncMock()
    ports["state_machine"].trigger_shutdown = AsyncMock()
    ports["service_manager"].report_external_fault = AsyncMock()
    ports["service_manager"].restart = AsyncMock()
    ports["crash_dump"].export_snapshot = AsyncMock()
    if with_ports:
        esc.set_taint_mask_port(ports["taint"])
        esc.set_state_machine_port(ports["state_machine"])
        esc.set_service_manager_port(ports["service_manager"])
        esc.set_event_bus_port(ports["event_bus"])
        esc.set_crash_dump_port(ports["crash_dump"])
        esc.set_rate_limiter_port(ports["rate_limiter"])
    return esc, ports


async def drain(esc: ErrorEscalator) -> None:
    """等待异步动作 task 完成（create_task 派发后事件循环跑一轮）。"""
    await asyncio.sleep(0)
    await asyncio.sleep(0)
