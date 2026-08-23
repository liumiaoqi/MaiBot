"""进程级关停状态。"""

from threading import Event

from src.common.logger import get_logger

logger = get_logger("common.shutdown")

_shutdown_requested = Event()


def request_shutdown(reason: str = "") -> None:
    """标记当前进程正在关停。"""

    logger.warning(f"进程关停请求: reason={reason or '(未提供)'}")
    _shutdown_requested.set()


def is_shutdown_requested() -> bool:
    """返回当前进程是否已经进入关停流程。"""

    return _shutdown_requested.is_set()
