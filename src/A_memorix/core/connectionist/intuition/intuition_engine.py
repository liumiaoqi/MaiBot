from __future__ import annotations

import re
import time

from src.common.logger import get_logger

from ..cognitive.cognitive_stratifier import CognitiveStratifier
from ..narrative.episode_store import EpisodeStore
from .stopwords import StopwordManager

logger = get_logger("IntuitionEngine")

# Token 预算
_MAX_TOKENS = 800
_CURRENT_STATE_TOKEN_BUDGET = 300
_TRAIT_HYPOTHESIS_TOKEN_BUDGET = 300
_NARRATIVE_TOKEN_BUDGET = 200

# 实体缓存
_ENTITY_CACHE_TTL = 1800  # 30分钟
_ENTITY_CACHE_MAX = 3

# 触发阈值
_KEYWORD_MIN_LENGTH = 2


class IntuitionEngine:
    """直觉引擎——关键词+bigram 双层触发，纯规则计算，≤5ms"""

    def __init__(
        self,
        cognitive_stratifier: CognitiveStratifier,
        episode_store: EpisodeStore,
        stopword_manager: StopwordManager,
    ) -> None:
        self._cs = cognitive_stratifier
        self._es = episode_store
        self._stopwords = stopword_manager
        self._entity_cache: dict[str, tuple[list[dict], float]] = {}

    def intuition_trigger(
        self,
        context_text: str,
        agent_id: str,
        max_tokens: int = _MAX_TOKENS,
    ) -> dict:
        """核心触发逻辑：关键词+bigram 双层匹配，返回 IntuitionResult 字典"""
        start = time.monotonic()
        now = time.time()
        context_lower = context_text.lower()

        # 始终注入 current_state（≤8条）
        current_states = self._cs.query_active_current_state(agent_id, limit=8)
        triggered_entries: list[dict] = []
        token_used = 0

        for entry in current_states:
            entry_dict = self._entry_to_dict(entry)
            tokens = self._estimate_tokens(entry.content)
            if token_used + tokens > _CURRENT_STATE_TOKEN_BUDGET:
                break
            triggered_entries.append(entry_dict)
            token_used += tokens

        # Layer 1：关键词匹配（tags vs context_text，过滤停用词）
        traits_and_hypotheses = self._cs.query_by_type(
            agent_id, ["stable_trait", "active_hypothesis"]
        )
        keyword_hits: list[dict] = []
        for entry in traits_and_hypotheses:
            if self._keyword_match(entry, context_lower):
                keyword_hits.append(self._entry_to_dict(entry))

        # Layer 2：bigram 兜底（未命中条目的 content vs context_text）
        keyword_concepts = {e.concept for e in traits_and_hypotheses if self._keyword_match(e, context_lower)}
        bigram_hits: list[dict] = []
        for entry in traits_and_hypotheses:
            if entry.concept in keyword_concepts:
                continue
            if self._bigram_match(entry.content, context_lower):
                bigram_hits.append(self._entry_to_dict(entry))

        # 合并 trait/hypothesis 结果，受 token 预算控制
        remaining_budget = _TRAIT_HYPOTHESIS_TOKEN_BUDGET
        for entry_dict in keyword_hits + bigram_hits:
            tokens = self._estimate_tokens(entry_dict.get("content", ""))
            if tokens > remaining_budget:
                continue
            triggered_entries.append(entry_dict)
            remaining_budget -= tokens

        # Episode/Saga 触发
        triggered_episodes = self._trigger_episodes(context_lower, agent_id)
        triggered_sagas = self._trigger_sagas(context_lower, agent_id)

        # 实体缓存
        cached_entities = self._get_cached_entities(agent_id, now)
        self._update_entity_cache(agent_id, triggered_entries, now)

        # Token 预算裁剪
        total_tokens = token_used + sum(
            self._estimate_tokens(e.get("content", "")) for e in triggered_episodes
        ) + sum(
            self._estimate_tokens(s.get("description", "")) for s in triggered_sagas
        )

        elapsed = (time.monotonic() - start) * 1000
        return {
            "triggered_entries": triggered_entries,
            "triggered_episodes": triggered_episodes,
            "triggered_sagas": triggered_sagas,
            "cached_entities": cached_entities,
            "token_estimate": total_tokens,
            "trigger_stats": {
                "keyword_hits": len(keyword_hits),
                "bigram_hits": len(bigram_hits),
                "current_states": len(current_states),
                "episodes": len(triggered_episodes),
                "sagas": len(triggered_sagas),
                "elapsed_ms": elapsed,
            },
        }

    # ── 匹配方法 ──────────────────────────────────────

    def _keyword_match(self, entry, context_lower: str) -> bool:
        """Layer 1：关键词匹配（tags vs context_text，过滤停用词）"""
        tags = entry.tags if hasattr(entry, "tags") else []
        filtered = self._stopwords.filter_stopwords(tags)
        for tag in filtered:
            if len(tag) >= _KEYWORD_MIN_LENGTH and tag.lower() in context_lower:
                return True
        # concept 本身也作为关键词
        concept = entry.concept
        if not self._stopwords.is_stopword(concept) and len(concept) >= _KEYWORD_MIN_LENGTH:
            if concept.lower() in context_lower:
                return True
        return False

    def _bigram_match(self, content: str, context_lower: str) -> bool:
        """Layer 2：bigram 兜底"""
        if not content or len(content) < 2:
            return False
        content_bigrams = self._extract_bigrams(content.lower())
        context_bigrams = self._extract_bigrams(context_lower)
        return bool(content_bigrams & context_bigrams)

    @staticmethod
    def _extract_bigrams(text: str) -> set[str]:
        """提取中文字符 bigram"""
        # 仅提取中文字符的 bigram
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        if len(chinese_chars) < 2:
            return set()
        return {chinese_chars[i] + chinese_chars[i + 1] for i in range(len(chinese_chars) - 1)}

    # ── Episode/Saga 触发 ─────────────────────────────

    def _trigger_episodes(self, context_lower: str, agent_id: str) -> list[dict]:
        episodes = self._es.query_episodes_by_agent(agent_id, status="active")
        hits: list[dict] = []
        for ep in episodes:
            # 关键词匹配：all_concepts vs context
            all_concepts = ep.all_concepts if hasattr(ep, "all_concepts") else []
            filtered = self._stopwords.filter_stopwords(all_concepts)
            matched = any(c.lower() in context_lower for c in filtered if len(c) >= _KEYWORD_MIN_LENGTH)
            if not matched:
                # bigram 兜底
                matched = self._bigram_match(ep.content, context_lower)
            if matched:
                hits.append({
                    "id": ep.id,
                    "title": ep.title,
                    "content": ep.content,
                    "emotional_axis": ep.emotional_axis,
                })
        return hits

    def _trigger_sagas(self, context_lower: str, agent_id: str) -> list[dict]:
        sagas = self._es.query_sagas_by_agent(agent_id, status="active")
        hits: list[dict] = []
        for saga in sagas:
            # 关键词匹配：title + description
            matched = saga.title.lower() in context_lower if len(saga.title) >= 2 else False
            if not matched:
                matched = self._bigram_match(saga.description, context_lower)
            if matched:
                hits.append({
                    "id": saga.id,
                    "title": saga.title,
                    "description": saga.description,
                    "emotional_axis": saga.emotional_axis,
                })
        return hits

    # ── 实体缓存 ──────────────────────────────────────

    def _get_cached_entities(self, agent_id: str, now: float) -> list[dict]:
        cached = self._entity_cache.get(agent_id)
        if cached is None:
            return []
        entities, ts = cached
        if now - ts > _ENTITY_CACHE_TTL:
            del self._entity_cache[agent_id]
            return []
        return entities[:_ENTITY_CACHE_MAX]

    def _update_entity_cache(self, agent_id: str, entries: list[dict], now: float) -> None:
        entities = [
            {"concept": e.get("concept", ""), "type": e.get("type", "")}
            for e in entries
            if e.get("concept")
        ][:_ENTITY_CACHE_MAX]
        if entities:
            self._entity_cache[agent_id] = (entities, now)

    # ── 工具方法 ──────────────────────────────────────

    @staticmethod
    def _entry_to_dict(entry) -> dict:
        return {
            "id": entry.id,
            "concept": entry.concept,
            "type": entry.type,
            "content": entry.content,
            "confidence": entry.confidence,
            "tags": entry.tags if hasattr(entry, "tags") else [],
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略 token 估算：中文≈1字/token，英文≈0.75词/token"""
        if not text:
            return 0
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        other_chars = len(text) - chinese_chars
        return chinese_chars + other_chars // 4