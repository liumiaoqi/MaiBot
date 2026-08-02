"""ZG-7 污染标记 — 污染动作枚举。

对标 Linux `panic_on_taint` boot 参数（panic.c:1249-1274），但降级而非 panic：
MaiBot 是长驻服务，污染不杀进程（N2 裁决，spec §2.3.1 规则 6 禁止 PANIC/FATAL）。
"""

from enum import Enum


class TaintAction(Enum):
    """污染动作枚举（spec §2.3.1 规则 1）。"""

    RECORD = "record"  # 仅记录（默认）
    WARN = "warn"  # 记录 + WARNING 日志
    TRIGGER_DEGRADE = "trigger_degrade"  # 记录 + 驱动 ZG-6 降级
