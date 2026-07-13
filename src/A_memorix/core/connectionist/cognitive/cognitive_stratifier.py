from __future__ import annotations

import time


from src.common.logger import get_logger

from ..enums import Valence
from ..models import CognitiveDecayResult, CognitiveEntry
from .cognitive_store import CognitiveStore

logger = get_logger("CognitiveStratifier")

# 初始分类规则：valence + 概念类型 + 来源质量 → type
_INITIAL_CLASSIFICATION_RULES: dict[tuple, str] = {
    # (has_emotion, concept_type, source_quality) → cognitive_type
    ("emotional", "person", "direct_statement"): "stable_trait",
    ("emotional", "person", "inferred"): "stable_trait",
    ("emotional", "activity", "direct_statement"): "current_state",
    ("emotional", "activity", "inferred"): "current_state",
    ("emotional", "object", "direct_statement"): "stable_trait",
    ("emotional", "object", "inferred"): "active_hypothesis",
    ("neutral", "person", "direct_statement"): "stable_trait",
    ("neutral", "person", "inferred"): "active_hypothesis",
    ("neutral", "activity", "direct_statement"): "current_state",
    ("neutral", "activity", "inferred"): "active_hypothesis",
    ("neutral", "object", "direct_statement"): "active_hypothesis",
    ("neutral", "object", "inferred"): "active_hypothesis",
}

# 证据增量
_SAME_OBS_INCREMENT = 0.02  # 同批次回声
_DIFF_OBS_INCREMENT = 0.05  # 独立来源
_CONTRADICTION_PENALTY = 0.10  # 矛盾惩罚

# 阈值
_HYPOTHESIS_UPGRADE_DIVERSITY = 3
_HYPOTHESIS_UPGRADE_CONFIDENCE = 0.70
_TRAIT_CONTRADICTION_THRESHOLD = 3
_TRAIT_CONTRADICTION_WINDOW_DAYS = 30
_HYPOTHESIS_ABANDON_DAYS = 14
_TRAIT_DORMANT_DAYS = 14
_CURRENT_STATE_HALF_LIFE_DAYS = 7
_CURRENT_STATE_MAX_ACTIVE = 12


class CognitiveStratifier:
    """认知分层器——概念节点的确定性元数据标注"""

    def __init__(self, cognitive_store: CognitiveStore) -> None:
        self._store = cognitive_store

    async def notify_observation(
        self,
        observation_id: str,
        concepts: list[str],
        valence: Valence,
        agent_id: str,
        *,
        concept_types: dict[str, str] | None = None,
        source_quality: str = "inferred",
    ) -> None:
        """新观察通知：新概念创建初始认知条目，已有概念增加证据"""
        concept_types = concept_types or {}
        now = time.time()

        for concept in concepts:
            existing = self._store.query_by_concept(concept, agent_id, status="active")

            if not existing:
                # 新概念 → 初始分类
                cog_type = self._classify_initial(concept, valence, concept_types, source_quality)
                decay_type = self._decay_type_for(cog_type)
                entry = CognitiveEntry(
                    concept=concept,
                    agent_id=agent_id,
                    type=cog_type,
                    content=f"{concept}的{cog_type}",
                    confidence=0.3,
                    decay_type=decay_type,
                    evidence_count=1,
                    last_evidence_at=now,
                    source_diversity=1,
                    source_quality=source_quality,
                    tags=[concept],
                    observation_ids=[observation_id],
                    timestamp=now,
                )
                if cog_type == "current_state":
                    entry.expires_at = now + 90 * 86400  # 最长90天
                self._store.insert_entry(entry)
                self._enforce_current_state_limit(agent_id)
            else:
                # 已有概念 → 证据匹配
                self._process_evidence(existing, observation_id, valence, agent_id, now)

    def process_cognitive_decay(self, agent_id: str = "") -> CognitiveDecayResult:
        """处理认知衰减（心跳时运行）"""
        start = time.monotonic()
        now = time.time()
        entries_processed = 0
        hypotheses_abandoned = 0
        traits_dormant = 0
        states_expired = 0

        # current_state 指数衰减
        current_states = self._store.query_by_type(agent_id, ["current_state"], status="active")
        for entry in current_states:
            entries_processed += 1
            if entry.expires_at and now > entry.expires_at:
                self._store.update_entry(entry.id, status="resolved")
                states_expired += 1
            elif entry.last_evidence_at > 0:
                days_since = (now - entry.last_evidence_at) / 86400
                decay = 0.5 ** (days_since / _CURRENT_STATE_HALF_LIFE_DAYS)
                new_confidence = max(0.02, entry.confidence * decay)
                self._store.update_entry(entry.id, confidence=new_confidence)

        # active_hypothesis 14天无证据 → abandoned
        hypotheses = self._store.query_by_type(agent_id, ["active_hypothesis"], status="active")
        for entry in hypotheses:
            entries_processed += 1
            days_since = (now - entry.last_evidence_at) / 86400 if entry.last_evidence_at > 0 else 999
            if days_since >= _HYPOTHESIS_ABANDON_DAYS:
                self._store.update_entry(entry.id, status="abandoned")
                hypotheses_abandoned += 1

        # stable_trait 14天无证据 → dormant
        traits = self._store.query_by_type(agent_id, ["stable_trait"], status="active")
        for entry in traits:
            entries_processed += 1
            days_since = (now - entry.last_evidence_at) / 86400 if entry.last_evidence_at > 0 else 999
            if days_since >= _TRAIT_DORMANT_DAYS:
                self._store.update_entry(entry.id, status="dormant")
                traits_dormant += 1

        elapsed = (time.monotonic() - start) * 1000
        return CognitiveDecayResult(
            entries_processed=entries_processed,
            hypotheses_abandoned=hypotheses_abandoned,
            traits_dormant=traits_dormant,
            states_expired=states_expired,
            elapsed_ms=elapsed,
        )

    # ── 查询委托 ──────────────────────────────────────

    def query_active_current_state(self, agent_id: str, limit: int = 12) -> list[CognitiveEntry]:
        return self._store.query_active_current_state(agent_id, limit)

    def query_by_type(self, agent_id: str, types: list[str], status: str = "active") -> list[CognitiveEntry]:
        return self._store.query_by_type(agent_id, types, status)

    def get_cognitive_entries(self, agent_id: str, concept: str = "") -> list[CognitiveEntry]:
        if concept:
            return self._store.query_by_concept(concept, agent_id)
        return self._store.query_by_type(agent_id, ["immutable_fact", "stable_trait", "current_state", "active_hypothesis"])

    def add_cognitive_evidence(
        self, entry_id: int, observation_id: str, is_confirm: bool
    ) -> None:
        delta = _DIFF_OBS_INCREMENT if is_confirm else -_CONTRADICTION_PENALTY
        self._store.increment_evidence(entry_id, observation_id, delta)

    # ── 内部方法 ──────────────────────────────────────

    def _classify_initial(
        self, concept: str, valence: Valence, concept_types: dict[str, str], source_quality: str
    ) -> str:
        has_emotion = "emotional" if valence != Valence.NEUTRAL else "neutral"
        ctype = concept_types.get(concept, "object")
        key = (has_emotion, ctype, source_quality)
        return _INITIAL_CLASSIFICATION_RULES.get(key, "active_hypothesis")

    @staticmethod
    def _decay_type_for(cog_type: str) -> str:
        if cog_type == "immutable_fact":
            return "none"
        if cog_type == "current_state":
            return "exponential"
        return "evidence_dependent"

    def _process_evidence(
        self,
        existing: list[CognitiveEntry],
        observation_id: str,
        valence: Valence,
        agent_id: str,
        now: float,
    ) -> None:
        # 找到最相关的条目（同 type 最高的 confidence）
        for entry in existing:
            if entry.type in ("superseded", "abandoned", "resolved"):
                continue

            is_same_obs = observation_id in entry.observation_ids
            increment = _SAME_OBS_INCREMENT if is_same_obs else _DIFF_OBS_INCREMENT

            # 简化证据匹配：同一概念出现即视为一致证据
            # 矛盾检测：valence 方向与条目 decay_type 不一致
            is_contradictory = self._is_contradictory(entry, valence)

            if is_contradictory:
                self._store.increment_evidence(entry.id, observation_id, -_CONTRADICTION_PENALTY)
                self._check_contradiction_threshold(entry, agent_id, now)
            else:
                new_diversity = entry.source_diversity
                if not is_same_obs:
                    new_diversity += 1
                self._store.increment_evidence(entry.id, observation_id, increment)
                self._store.update_entry(entry.id, source_diversity=new_diversity)

                # 假设升级检查
                if (
                    entry.type == "active_hypothesis"
                    and new_diversity >= _HYPOTHESIS_UPGRADE_DIVERSITY
                ):
                    updated = self._store.query_by_concept(entry.concept, agent_id, status="active")
                    for u in updated:
                        if u.id == entry.id and u.confidence >= _HYPOTHESIS_UPGRADE_CONFIDENCE:
                            self._upgrade_hypothesis(u, agent_id, now)

    def _is_contradictory(self, entry: CognitiveEntry, valence: Valence) -> bool:
        # immutable_fact 不接受矛盾
        if entry.type == "immutable_fact":
            return False
        # 简化：如果条目是 positive trait 但新证据是 negative，视为矛盾
        return False  # 原型阶段简化，不做矛盾检测

    def _check_contradiction_threshold(self, entry: CognitiveEntry, agent_id: str, now: float) -> None:
        if entry.type != "stable_trait":
            return
        # 原型简化：标记 needs_review
        updated = self._store.query_by_concept(entry.concept, agent_id, status="active")
        for u in updated:
            if u.id == entry.id and u.evidence_count >= _TRAIT_CONTRADICTION_THRESHOLD:
                self._store.update_entry(u.id, status="needs_review")

    def _upgrade_hypothesis(self, entry: CognitiveEntry, agent_id: str, now: float) -> None:
        """假设升级为 stable_trait"""
        new_entry = CognitiveEntry(
            concept=entry.concept,
            agent_id=agent_id,
            type="stable_trait",
            content=entry.content,
            confidence=entry.confidence,
            decay_type="evidence_dependent",
            evidence_count=entry.evidence_count,
            last_evidence_at=now,
            source_diversity=entry.source_diversity,
            source_quality=entry.source_quality,
            tags=entry.tags,
            observation_ids=entry.observation_ids,
            timestamp=now,
        )
        new_id = self._store.insert_entry(new_entry)
        self._store.update_entry(entry.id, status="superseded", superseded_by=new_id)

    def _enforce_current_state_limit(self, agent_id: str) -> None:
        """current_state 超12条 → resolve 最旧的"""
        count = self._store.count_active_by_type(agent_id, "current_state")
        if count <= _CURRENT_STATE_MAX_ACTIVE:
            return
        states = self._store.query_active_current_state(agent_id, limit=count)
        overflow = count - _CURRENT_STATE_MAX_ACTIVE
        oldest = sorted(states, key=lambda e: e.timestamp)[:overflow]
        for entry in oldest:
            self._store.update_entry(entry.id, status="resolved")