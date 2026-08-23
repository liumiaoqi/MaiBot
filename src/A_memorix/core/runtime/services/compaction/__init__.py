"""ZG-N5 记忆压缩升级（Replay-aware）——compaction 包。

对标 dsh compaction-basic + compaction/tool-pairing。
革命替换现有删除式压缩为 surface 替换式 Replay-aware 压缩。

组件：
- ReplayAwareCompactor：核心压缩服务（编排 start → summarize → surface 替换 → end 事务）
- DurableLockManager：持久锁管理器（以 compaction/start 标记为锁）
- ToolPairingBalancer：边界平衡检查器（增量 balance state）
- IdleTaskCoordinator：idle-task 排他协调器
- CompactionEventLogger：事件日志记录器
- SurfaceReplacer：surface 替换器
- Summarizer：摘要生成器
- resolve_compaction_config：配置解析
"""

from .config import CompactionPolicyConfig, ResolvedConfig, resolve_compaction_config
from .durable_lock import DurableLockManager
from .engine import ReplayAwareCompactor
from .event_logger import CompactionEventLogger
from .idle_task import IdleTaskCoordinator
from .summarizer import Summarizer
from .surface import SurfaceReplacer
from .tool_pairing import ToolPairingBalancer

__all__ = [
    "CompactionPolicyConfig",
    "ResolvedConfig",
    "resolve_compaction_config",
    "DurableLockManager",
    "ReplayAwareCompactor",
    "CompactionEventLogger",
    "IdleTaskCoordinator",
    "Summarizer",
    "SurfaceReplacer",
    "ToolPairingBalancer",
]