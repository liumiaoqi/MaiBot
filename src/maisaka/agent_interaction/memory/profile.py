"""智能体画像服务。

由交互记忆聚合生成智能体画像，结构兼容 PersonProfileResult，
增加 observer_agent_id / refresh_status 等扩展字段。
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any

from src.maisaka.agent_interaction.event_store import InteractionEventStore
from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter

logger = logging.getLogger(__name__)

# 画像缓存TTL（秒）
_PROFILE_CACHE_TTL = 300  # 5分钟
# 最少交互次数（低于此值返回空画像）
_MIN_INTERACTION_COUNT = 3


@dataclass
class AgentProfileResult:
    """智能体画像结果。"""

    observer_agent_id: str = ""
    target_agent_id: str = ""
    summary: str = ""
    traits: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    interaction_count: int = 0
    last_interaction_at: float = 0.0
    emotion_tendency: str = ""
    refresh_status: str = "pending"

    def to_prompt_text(self) -> str:
        """生成用于提示词注入的画像文本。"""
        if not self.summary and not self.traits:
            return ""
        parts = []
        if self.summary:
            parts.append(self.summary)
        if self.traits:
            parts.append(f"特征：{'、'.join(self.traits[:5])}")
        if self.emotion_tendency:
            parts.append(f"情感倾向：{self.emotion_tendency}")
        return "；".join(parts)


class AgentProfileService:
    """智能体画像服务。

    画像由交互记忆聚合生成，缓存5分钟。
    交互记忆更新后画像标记为 stale，下次检索时重新聚合。
    """

    def __init__(
        self,
        memory_adapter: AgentMemoryAdapter,
        event_store: InteractionEventStore,
    ) -> None:
        self._memory_adapter = memory_adapter
        self._event_store = event_store
        self._cache: dict[str, AgentProfileResult] = {}

    def _cache_key(self, observer_id: str, target_id: str) -> str:
        return f"{observer_id}:{target_id}"

    async def get_profile(
        self, observer_agent_id: str, target_agent_id: str
    ) -> AgentProfileResult:
        """获取智能体画像，缓存未过期时直接返回。"""
        key = self._cache_key(observer_agent_id, target_agent_id)
        cached = self._cache.get(key)

        if cached is not None:
            if cached.refresh_status == "fresh":
                return cached
            if cached.refresh_status == "stale":
                return await self.refresh_profile(observer_agent_id, target_agent_id)

        return await self.refresh_profile(observer_agent_id, target_agent_id)

    async def refresh_profile(
        self, observer_agent_id: str, target_agent_id: str
    ) -> AgentProfileResult:
        """重新聚合生成画像。"""
        # 获取交互事件
        events = await self._event_store.query_events(
            agent_id=observer_agent_id,
            target_agent_id=target_agent_id,
            limit=20,
        )

        if len(events) < _MIN_INTERACTION_COUNT:
            return AgentProfileResult(
                observer_agent_id=observer_agent_id,
                target_agent_id=target_agent_id,
                interaction_count=len(events),
                refresh_status="pending",
            )

        # 聚合画像
        summary_parts = []
        emotion_counts: dict[str, int] = {}
        evidence_list: list[dict[str, Any]] = []

        for event in events[:5]:
            summary_parts.append(event.trigger_reason[:100])

            # 从metadata中提取情绪标签
            try:
                metadata = eval(event.event_metadata) if event.event_metadata else {}
                emotion_tag = metadata.get("emotion_tag", "")
                if emotion_tag:
                    emotion_counts[emotion_tag] = emotion_counts.get(emotion_tag, 0) + 1
            except Exception:
                pass

            evidence_list.append({
                "event_id": event.event_id,
                "type": event.interaction_type,
                "reason": event.trigger_reason[:80],
                "time": str(event.created_at) if event.created_at else "",
            })

        # 从交互记忆中提取特征
        traits = await self._extract_traits(observer_agent_id, target_agent_id)

        # 情感倾向
        emotion_tendency = ""
        if emotion_counts:
            emotion_tendency = max(emotion_counts, key=emotion_counts.get)

        # 最近交互时间
        last_interaction_at = 0.0
        if events and events[0].created_at:
            last_interaction_at = events[0].created_at.timestamp()

        summary = "；".join(summary_parts[:3]) if summary_parts else ""
        if len(summary) > 500:
            summary = summary[:497] + "..."

        profile = AgentProfileResult(
            observer_agent_id=observer_agent_id,
            target_agent_id=target_agent_id,
            summary=summary,
            traits=traits[:10],
            evidence=evidence_list[:5],
            interaction_count=len(events),
            last_interaction_at=last_interaction_at,
            emotion_tendency=emotion_tendency,
            refresh_status="fresh",
        )

        # 更新缓存
        key = self._cache_key(observer_agent_id, target_agent_id)
        self._cache[key] = profile

        return profile

    async def mark_stale(self, observer_agent_id: str, target_agent_id: str) -> None:
        """标记画像为 stale，下次检索时重新聚合。"""
        key = self._cache_key(observer_agent_id, target_agent_id)
        cached = self._cache.get(key)
        if cached is not None:
            cached.refresh_status = "stale"

    async def _extract_traits(
        self, observer_agent_id: str, target_agent_id: str
    ) -> list[str]:
        """从交互记忆中提取高频特征。"""
        try:
            result = await self._memory_adapter.search_interaction_memory(
                observer_agent_id, target_agent_id, limit=10
            )
            if not result.success or not result.hits:
                return []

            # 简单提取：从记忆内容中提取关键词
            traits_set: set[str] = set()
            for hit in result.hits[:5]:
                content = hit.content.strip()
                if len(content) > 20:
                    traits_set.add(content[:20])
            return list(traits_set)
        except Exception:
            return []