"""错误升级梯 — 错误码/异常 → ErrorLevel 映射（ZG-14 Phase 5）。

错误码分类权威源：ZG-12 定稿的 src/llm_models/error_classifier.py
（PERMANENT_ERROR_CODES / TRANSIENT_ERROR_CODES——错误码定稿，本模块
直接复用避免双表漂移）。本模块在其上叠加 ErrorLevel 语义（survey
0805 §5.3：「永久性错误->report(ERROR)，暂时性->report(WARN)」）：

- classify_http_status(status_code)：HTTP 状态码 → ErrorLevel 纯函数映射
- classify_exception(exc)：异常类型粗分（survey :764「ZG-16 可先用
  异常类型粗分」——HTTPError/TimeoutError/ConnectionError 等）

未收录的错误码/异常按 WARN 兜底（spec §5.6.3 异常场景 1 同款：不低估也
不过度升级——由升级梯计数阈值决定是否继续升级）。
"""

from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.llm_models.error_classifier import PERMANENT_ERROR_CODES, TRANSIENT_ERROR_CODES
from src.llm_models.exceptions import (
    EmptyResponseException,
    LLMTaskTimeoutError,
    ModelAttemptFailed,
    NetworkConnectionError,
    ReqAbortException,
    RespParseException,
)

logger = get_logger("error_escalation.code_mapper")


def classify_http_status(status_code: int) -> ErrorLevel:
    """HTTP 状态码 → ErrorLevel（纯函数，不依赖运行时状态）。

    规则（survey 0805 §5.3 + ZG-12 定稿 error_classifier.py 错误码表）：
    - 永久性错误（配置/认证/参数——重试无意义）→ ERROR：
      400/401/402/403/404/405/410/413/422
    - 暂时性故障（限流/服务端——可重试）→ WARN：
      408/429/499/500/502/503/504/521/522/523/524/529
    - 未收录状态码 → WARN 兜底（不低估也不过度升级，由计数阈值继续升级）

    Args:
        status_code: HTTP 状态码（如 RespNotOkException.status_code）。

    Returns:
        ErrorLevel.ERROR（永久性）/ ErrorLevel.WARN（暂时性或未收录）。
    """
    if status_code in PERMANENT_ERROR_CODES:
        return ErrorLevel.ERROR
    if status_code in TRANSIENT_ERROR_CODES:
        return ErrorLevel.WARN
    logger.warning("ERROR_CODE_UNKNOWN: 未收录 HTTP 状态码 %s，按 WARN 兜底", status_code)
    return ErrorLevel.WARN


def classify_exception(exc: Exception) -> ErrorLevel:
    """异常类型粗分 → ErrorLevel（survey :764「ZG-16 可先用异常类型粗分」）。

    规则：
    - 携带 status_code 属性的异常（RespNotOkException / openai.APIStatusError
      等）→ 委托 classify_http_status
    - 超时类（内建 TimeoutError，3.11+ 与 asyncio.TimeoutError 同型 /
      LLMTaskTimeoutError）→ WARN
    - 连接类（内建 ConnectionError 族 / NetworkConnectionError）→ WARN
    - 空响应 / 解析失败 / 请求中断（调用方按可重试处理）→ WARN
    - ModelAttemptFailed → 递归分类原始异常（根因）
    - 未知异常类型 → WARN 兜底

    Args:
        exc: 待分类异常（LLM 调用错误路径上的异常）。

    Returns:
        ErrorLevel.ERROR（携带永久性错误码）/ ErrorLevel.WARN（其余）。
    """
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return classify_http_status(status_code)

    if isinstance(exc, (TimeoutError, LLMTaskTimeoutError)):
        return ErrorLevel.WARN

    if isinstance(exc, (ConnectionError, NetworkConnectionError)):
        return ErrorLevel.WARN

    if isinstance(exc, (EmptyResponseException, RespParseException, ReqAbortException)):
        return ErrorLevel.WARN

    if isinstance(exc, ModelAttemptFailed):
        original = exc.original_exception
        if isinstance(original, Exception):
            return classify_exception(original)
        return ErrorLevel.WARN

    logger.warning("ERROR_EXC_UNKNOWN: 未收录异常类型 %s，按 WARN 兜底", type(exc).__name__)
    return ErrorLevel.WARN


__all__ = ["classify_exception", "classify_http_status"]
