"""核心适配器层 — 唯一允许导入组件具体类的地方。

适配器将组件的具体实现包装为核心 Protocol 接口，
核心模块只依赖 Protocol，不直接导入组件。
"""

from src.core.adapters.memory_service import AMemorixMemoryServicePort
from src.core.adapters.message_port import SendServicePort
from src.core.adapters.notice_classifier import NapCatNoticeClassifier
from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
from src.core.adapters.runtime_registry import HeartflowRuntimeRegistry
from src.core.adapters.session_repository import ChatManagerSessionRepository

__all__ = [
    "AMemorixMemoryServicePort",
    "ChatManagerSessionRepository",
    "HeartflowRuntimeRegistry",
    "NapCatNoticeClassifier",
    "SendServicePort",
]