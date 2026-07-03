"""智能体关系进展系统。"""

from .level import RelationshipLevel, RelationshipSnapshot
from .manager import RelationshipManager
from .signal import RelationshipSignal, extract_relationship_signal
from .tracker import RelationshipEvent, RelationshipTracker

__all__ = [
    "RelationshipEvent",
    "RelationshipLevel",
    "RelationshipManager",
    "RelationshipSignal",
    "RelationshipSnapshot",
    "RelationshipTracker",
    "extract_relationship_signal",
]