"""模型调用错误分类器（ZG-12 错误码驱动验证）。

错误码驱动验证的核心区分（用户设计，2026-08-05）：
- 永久性错误（配置写错）：404 模型不存在 / 400-422 参数错 / 401-403 认证 / 402 余额——
  **不重试**，立即关闭组件（FAULT + ZG-10 传播）
- 暂时性故障（负载）：429 限流 / 499-529 服务端——退避重试 + fallback

分类依据 OpenClaw FailoverReason 映射（capability_table_0805.md B7）。
"""

PERMANENT_ERROR_CODES = frozenset({400, 401, 402, 403, 404, 405, 410, 413, 422})
"""永久性错误码：配置写错/认证/余额/参数——重试无意义，走组件关闭"""

TRANSIENT_ERROR_CODES = frozenset({408, 429, 499, 500, 502, 503, 504, 521, 522, 523, 524, 529})
"""暂时性故障：限流/过载/服务端——退避重试 + fallback"""

PERMANENT = "permanent"
TRANSIENT = "transient"
UNKNOWN = "unknown"


def classify_error(status_code: int) -> str:
    """错误码分类：permanent（配置写错）/ transient（暂时故障）/ unknown。

    Args:
        status_code: HTTP 状态码（来自 RespNotOkException.status_code）。

    Returns:
        PERMANENT / TRANSIENT / UNKNOWN
    """
    if status_code in PERMANENT_ERROR_CODES:
        return PERMANENT
    if status_code in TRANSIENT_ERROR_CODES:
        return TRANSIENT
    return UNKNOWN


def is_permanent(status_code: int) -> bool:
    """是否为永久性错误（配置写错——不重试，关闭组件）。"""
    return status_code in PERMANENT_ERROR_CODES


def is_transient(status_code: int) -> bool:
    """是否为暂时性故障（退避重试 + fallback）。"""
    return status_code in TRANSIENT_ERROR_CODES
