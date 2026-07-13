from __future__ import annotations

import time

from src.common.logger import get_logger

from ..models import LifecycleResult
from ..narrative.episode_store import EpisodeStore

logger = get_logger("LifecycleManager")

# Fragment 生命周期阈值（天）
_FRAGMENT_COOLING_DAYS = 14
_FRAGMENT_FROZEN_DAYS = 30
_FRAGMENT_TOMBSTONE_DAYS = 90

# Episode 生命周期阈值（天）
_EPISODE_COOLING_DAYS = 30
_EPISODE_FROZEN_DAYS = 60
_EPISODE_TOMBSTONE_DAYS = 180

# Saga 生命周期阈值（天）
_SAGA_ARCHIVE_DAYS = 365


class LifecycleManager:
    """Fragment/Episode/Saga 生命周期管理——与粒度退化正交"""

    def __init__(self, episode_store: EpisodeStore) -> None:
        self._store = episode_store

    def advance_lifecycle(self, agent_id: str = "") -> LifecycleResult:
        """推进所有叙事元素的生命周期（幂等操作）"""
        start = time.monotonic()
        now = time.time()
        fragments_advanced = 0
        episodes_advanced = 0
        sagas_archived = 0
        revived = 0

        # Fragment 生命周期推进
        fragments_advanced += self._advance_fragments(agent_id, now)
        # Episode 生命周期推进
        episodes_advanced += self._advance_episodes(agent_id, now)
        # Saga 生命周期推进
        sagas_archived += self._advance_sagas(agent_id, now)

        elapsed = (time.monotonic() - start) * 1000
        result = LifecycleResult(
            fragments_advanced=fragments_advanced,
            episodes_advanced=episodes_advanced,
            sagas_archived=sagas_archived,
            revived=revived,
            elapsed_ms=elapsed,
        )
        logger.debug(
            "lifecycle advanced: fragments=%d, episodes=%d, sagas=%d, revived=%d, %.1fms",
            fragments_advanced, episodes_advanced, sagas_archived, revived, elapsed,
        )
        return result

    def touch_fragment(self, observation_id: str, agent_id: str) -> None:
        """访问 Fragment——更新 last_accessed_at，cooling 状态复活为 active"""
        now = time.time()
        fragments = self._store.query_fragments_by_status(agent_id, "cooling")
        for f in fragments:
            if f["observation_id"] == observation_id:
                self._store.update_fragment_status(observation_id, agent_id, "active")
                self._store.update_fragment_last_accessed(observation_id, agent_id, now)
                return
        self._store.update_fragment_last_accessed(observation_id, agent_id, now)

    def touch_episode(self, episode_id: int) -> None:
        """访问 Episode——更新 last_accessed_at"""
        self._store.update_episode_last_accessed(episode_id, time.time())

    def touch_saga(self, saga_id: int) -> None:
        """访问 Saga——更新 last_accessed_at"""
        self._store.update_saga_last_accessed(saga_id, time.time())

    # ── 内部方法 ──────────────────────────────────────

    def _advance_fragments(self, agent_id: str, now: float) -> int:
        advanced = 0
        # active → cooling（14天无访问）
        active = self._store.query_fragments_by_status(agent_id, "active")
        for f in active:
            if f["last_accessed_at"] <= 0:
                continue
            days_since = (now - f["last_accessed_at"]) / 86400
            if days_since >= _FRAGMENT_COOLING_DAYS:
                self._store.update_fragment_status(f["observation_id"], agent_id, "cooling")
                advanced += 1

        # cooling → frozen（cooling后30天）
        cooling = self._store.query_fragments_by_status(agent_id, "cooling")
        for f in cooling:
            if f["last_accessed_at"] <= 0:
                continue
            days_since = (now - f["last_accessed_at"]) / 86400
            if days_since >= _FRAGMENT_COOLING_DAYS + _FRAGMENT_FROZEN_DAYS:
                self._store.update_fragment_status(f["observation_id"], agent_id, "frozen")
                advanced += 1

        # frozen → tombstone（frozen后90天）
        frozen = self._store.query_fragments_by_status(agent_id, "frozen")
        for f in frozen:
            if f["last_accessed_at"] <= 0:
                continue
            days_since = (now - f["last_accessed_at"]) / 86400
            if days_since >= _FRAGMENT_COOLING_DAYS + _FRAGMENT_FROZEN_DAYS + _FRAGMENT_TOMBSTONE_DAYS:
                self._store.update_fragment_status(f["observation_id"], agent_id, "tombstone")
                advanced += 1

        return advanced

    def _advance_episodes(self, agent_id: str, now: float) -> int:
        advanced = 0
        # active → cooling（30天无访问）
        active = self._store.query_episodes_by_agent(agent_id, status="active")
        for ep in active:
            if ep.last_accessed_at <= 0:
                continue
            days_since = (now - ep.last_accessed_at) / 86400
            if days_since >= _EPISODE_COOLING_DAYS:
                self._store.update_episode_status(ep.id, "cooling")
                advanced += 1

        # cooling → frozen（cooling后60天）
        cooling = self._store.query_episodes_by_agent(agent_id, status="cooling")
        for ep in cooling:
            if ep.last_accessed_at <= 0:
                continue
            days_since = (now - ep.last_accessed_at) / 86400
            if days_since >= _EPISODE_COOLING_DAYS + _EPISODE_FROZEN_DAYS:
                self._store.update_episode_status(ep.id, "frozen")
                advanced += 1

        # frozen → tombstone（frozen后180天）
        frozen = self._store.query_episodes_by_agent(agent_id, status="frozen")
        for ep in frozen:
            if ep.last_accessed_at <= 0:
                continue
            days_since = (now - ep.last_accessed_at) / 86400
            if days_since >= _EPISODE_COOLING_DAYS + _EPISODE_FROZEN_DAYS + _EPISODE_TOMBSTONE_DAYS:
                self._store.update_episode_status(ep.id, "tombstone")
                advanced += 1

        return advanced

    def _advance_sagas(self, agent_id: str, now: float) -> int:
        archived = 0
        active = self._store.query_sagas_by_agent(agent_id, status="active")
        for saga in active:
            if saga.last_accessed_at <= 0:
                continue
            days_since = (now - saga.last_accessed_at) / 86400
            if days_since >= _SAGA_ARCHIVE_DAYS:
                self._store.update_saga_status(saga.id, "archived")
                archived += 1
        return archived