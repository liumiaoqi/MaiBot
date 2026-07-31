"""ZG-2 日志管线增强模块 — 环形缓冲 / ratelimit / 降级抑制 / 崩溃导出。

供 src/common/logger.py 组装；本包不依赖 src/core/ 具体类（CMP-05）。
"""

from .ring_buffer import BufferEntry, RingBuffer

__all__ = ["BufferEntry", "RingBuffer"]
