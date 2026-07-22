"""记忆系统纯数据类型 — core 和 A_memorix 共享，不依赖任何一方。

这些类型不包含业务逻辑，都是纯数据容器。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MemoryHit:
    """记忆检索命中项。"""

    content: str
    score: float = 0.0
    hit_type: str = ""
    source: str = ""
    hash_value: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    episode_id: str = ""
    title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "score": self.score,
            "type": self.hit_type,
            "source": self.source,
            "hash": self.hash_value,
            "metadata": self.metadata,
            "episode_id": self.episode_id,
            "title": self.title,
        }


@dataclass
class MemorySearchResult:
    """记忆检索结果。"""

    summary: str = ""
    hits: List[MemoryHit] = field(default_factory=list)
    filtered: bool = False
    success: bool = True
    error: str = ""

    def to_text(self, limit: int = 5, *, truncate_content: bool = True, max_content_chars: int = 160) -> str:
        if not self.hits:
            return ""
        lines = []
        for index, item in enumerate(self.hits[: max(1, int(limit))], start=1):
            content = item.content.strip().replace("\n", " ")
            if truncate_content and len(content) > max_content_chars:
                content = content[:max_content_chars] + "..."
            lines.append(f"{index}. {content}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "summary": self.summary,
            "hits": [item.to_dict() for item in self.hits],
            "filtered": self.filtered,
        }


@dataclass
class MemoryWriteResult:
    """记忆写入结果。"""

    success: bool = False
    stored_ids: List[str] = field(default_factory=list)
    skipped_ids: List[str] = field(default_factory=list)
    detail: str = ""
    pending: bool = False
    trace_id: str = ""
    observation_id: str = ""
    concept_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stored_ids": self.stored_ids,
            "skipped_ids": self.skipped_ids,
            "detail": self.detail,
            "pending": self.pending,
            "trace_id": self.trace_id,
            "observation_id": self.observation_id,
            "concept_names": self.concept_names,
        }


@dataclass
class RecallItem:
    """概念激活扩散召回项。"""

    concept: str
    activation: float = 0.0
    valence: str = "neutral"
    detail_level: float = 0.0
    relative_time: str = ""


@dataclass(frozen=True, slots=True)
class IntuitionContext:
    """直觉触发结果 — 纯规则快速预判。"""

    triggered_entries: tuple[dict, ...] = ()
    triggered_episodes: tuple[dict, ...] = ()
    triggered_sagas: tuple[dict, ...] = ()
    cached_entities: tuple[dict, ...] = ()
    token_estimate: int = 0


@dataclass
class RecallResult:
    """概念召回 + 直觉组合结果。"""

    recall_items: List[RecallItem] = field(default_factory=list)
    intuition: IntuitionContext | None = None


@dataclass
class ProfileView:
    """画像实时视图 — 连接主义原生画像。"""

    subject: str = ""
    observer: str = ""
    associations: tuple[dict, ...] = ()
    voices: dict = field(default_factory=dict)
    contradictions: tuple[dict, ...] = ()
    timeline: tuple[dict, ...] = ()
    depth: str = ""
    episodes: tuple[dict, ...] = ()
    sagas: tuple[dict, ...] = ()


@dataclass
class ReflectResult:
    """反思结果 — 多声音视角 + 矛盾检测。"""

    subject: str = ""
    agent_id: str = ""
    voices: dict = field(default_factory=dict)
    contradictions: tuple[dict, ...] = ()


__all__ = [
    "MemoryHit",
    "MemorySearchResult",
    "MemoryWriteResult",
    "RecallItem",
    "IntuitionContext",
    "RecallResult",
    "ProfileView",
    "ReflectResult",
]
