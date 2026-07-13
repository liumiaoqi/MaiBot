from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from src.common.logger import get_logger

from ..models import Episode, Fragment, Saga, WeaveResult
from ..trace_store import TraceStore
from .episode_store import EpisodeStore
from .fragment_view import build_fragments_from_traces

logger = get_logger("NarrativeWeaver")

_EPISODE_PROMPT_ZH = """\
你是一个叙事编织器。将以下记忆碎片编织为一段连贯的叙事。

碎片信息：
{fragments_text}

共享概念：{shared_concepts}
情感基调：{emotional_axis}

要求：
1. 生成一个标题（≤50字）
2. 生成一段连贯叙事（100-250字），将碎片中的概念自然串联
3. 叙事应该有情感温度，不是冷冰冰的事实罗列
4. 判断这段叙事的情感主轴：bond/vigilance/confidence/humility/warmth/melancholy/grounded/none

输出严格 JSON 格式：
{{
  "title": "标题",
  "content": "叙事文本",
  "emotional_axis": "warmth"
}}

只输出 JSON，不要其他内容。"""

_SAGA_PROMPT_ZH = """\
你是一个叙事编织器。将以下叙事段落编织为一段跨时间的传奇叙事。

段落信息：
{episodes_text}

共享概念桥接：{concept_bridge}
整体情感主轴：{emotional_axis}

要求：
1. 生成一个标题（≤15字）
2. 生成一段叙事摘要（150-300字），描述跨越时间的主题线索
3. 传奇描述的是长期主题（如"一段友谊的深化""一个项目的起伏"），不是单个事件
4. 判断这段传奇的情感主轴：bond/vigilance/confidence/humility/warmth/melancholy/grounded/none

输出严格 JSON 格式：
{{
  "title": "标题",
  "description": "叙事摘要",
  "emotional_axis": "warmth"
}}

只输出 JSON，不要其他内容。"""


class NarrativeWeaver:
    """叙事编织器——Fragment→Episode→Saga 三层叙事自组织"""

    def __init__(
        self,
        trace_store: TraceStore,
        episode_store: EpisodeStore,
        *,
        llm_client: Any = None,
    ) -> None:
        self._trace_store = trace_store
        self._episode_store = episode_store
        self._llm = llm_client
        self._pending_observations: dict[str, set[str]] = defaultdict(set)

    def notify_observation(self, observation_id: str, agent_id: str) -> None:
        """将 observation_id 加入待编织队列"""
        self._pending_observations[agent_id].add(observation_id)
        self._episode_store.upsert_fragment_status(observation_id, agent_id, "active")

    async def weave(self, agent_id: str) -> WeaveResult:
        """执行叙事编织：Fragment→Episode→Saga"""
        start = time.monotonic()
        fragments_processed = 0
        episodes_created = 0
        sagas_created = 0

        # 第一步：Fragment→Episode
        unwoven_ids = self._episode_store.query_unwoven_observation_ids(agent_id)
        # 合并待编织队列
        pending = self._pending_observations.pop(agent_id, set())
        all_obs_ids = list(set(unwoven_ids) | pending)

        if not all_obs_ids:
            return WeaveResult(elapsed_ms=(time.monotonic() - start) * 1000)

        traces_by_obs = self._trace_store.query_by_observation_ids(all_obs_ids)
        fragment_statuses = self._episode_store.get_fragment_statuses_map(agent_id)
        fragments = build_fragments_from_traces(traces_by_obs, fragment_statuses)
        fragments_processed = len(fragments)

        if fragments_processed < 2:
            return WeaveResult(
                fragments_processed=fragments_processed,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

        groups = self._detect_fragment_connections(fragments, min_shared_concepts=2)
        logger.debug(f"[weave] {fragments_processed} 碎片, {len(groups)} 连接组")

        episodes: list[Episode] = []
        for group_indices in groups:
            episode = await self._weave_episode(fragments, group_indices, agent_id)
            if episode is not None:
                episode.id = self._episode_store.insert_episode(episode)
                episodes.append(episode)
                episodes_created += 1

        # 第二步：Episode→Saga
        if len(episodes) >= 2:
            saga_groups = self._detect_episode_connections(episodes)
            for group_indices in saga_groups:
                group_episodes = [episodes[i] for i in group_indices]
                saga = await self._weave_saga(group_episodes, agent_id)
                if saga is not None:
                    saga.id = self._episode_store.insert_saga(saga)
                    sagas_created += 1

        elapsed = (time.monotonic() - start) * 1000
        return WeaveResult(
            fragments_processed=fragments_processed,
            episodes_created=episodes_created,
            sagas_created=sagas_created,
            elapsed_ms=elapsed,
        )

    # ── Fragment 连接检测 ──────────────────────────────

    @staticmethod
    def _detect_fragment_connections(
        fragments: list[Fragment], min_shared_concepts: int = 2
    ) -> list[list[int]]:
        """检测 Fragment 间的概念连接密度，返回连接组"""
        n = len(fragments)
        adj: dict[int, set[int]] = defaultdict(set)

        for i in range(n):
            for j in range(i + 1, n):
                shared = set(fragments[i].concepts) & set(fragments[j].concepts)
                if len(shared) >= min_shared_concepts:
                    adj[i].add(j)
                    adj[j].add(i)

        return NarrativeWeaver._bfs_connected_groups(n, adj, min_group_size=2)

    # ── Episode 连接检测 ──────────────────────────────

    @staticmethod
    def _detect_episode_connections(episodes: list[Episode]) -> list[list[int]]:
        """检测 Episode 间的连接（共享概念桥接/情感主轴/底层概念交集）"""
        n = len(episodes)
        adj: dict[int, set[int]] = defaultdict(set)

        for i in range(n):
            for j in range(i + 1, n):
                # 条件1：共享概念桥接
                shared_bridge = set(episodes[i].concept_bridge) & set(episodes[j].concept_bridge)
                if shared_bridge:
                    adj[i].add(j)
                    adj[j].add(i)
                    continue

                # 条件2：共享情感主轴（非 none）
                if (
                    episodes[i].emotional_axis == episodes[j].emotional_axis
                    and episodes[i].emotional_axis != "none"
                ):
                    adj[i].add(j)
                    adj[j].add(i)
                    continue

                # 条件3：底层 Fragment 概念交集（实体级桥接，1个共享即可）
                fi_all = set(episodes[i].all_concepts)
                fj_all = set(episodes[j].all_concepts)
                if fi_all & fj_all:
                    adj[i].add(j)
                    adj[j].add(i)

        return NarrativeWeaver._bfs_connected_groups(n, adj, min_group_size=2)

    @staticmethod
    def _bfs_connected_groups(
        n: int, adj: dict[int, set[int]], min_group_size: int = 2
    ) -> list[list[int]]:
        visited: set[int] = set()
        groups: list[list[int]] = []
        for start in range(n):
            if start in visited or start not in adj:
                continue
            group: list[int] = []
            queue = [start]
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                group.append(node)
                for neighbor in adj.get(node, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if len(group) >= min_group_size:
                groups.append(sorted(group))
        return groups

    # ── Episode 编织 ──────────────────────────────────

    async def _weave_episode(
        self, fragments: list[Fragment], indices: list[int], agent_id: str
    ) -> Episode | None:
        shared = self._get_shared_concepts(fragments, indices)
        emotional_axis = self._derive_emotional_axis(fragments, indices)

        fragments_text = ""
        all_concepts: set[str] = set()
        for idx in indices:
            f = fragments[idx]
            fragments_text += f"- 碎片{idx}: 概念={f.concepts}, 情感={f.valence.value}, 权重={f.max_weight:.2f}\n"
            all_concepts.update(f.concepts)

        prompt = _EPISODE_PROMPT_ZH.format(
            fragments_text=fragments_text.strip(),
            shared_concepts=", ".join(shared),
            emotional_axis=emotional_axis,
        )

        raw = await self._call_llm(prompt)
        if raw is not None:
            data = self._parse_json(raw)
            if data and "title" in data and "content" in data:
                return Episode(
                    agent_id=agent_id,
                    title=data["title"],
                    content=data["content"],
                    weight=max(fragments[i].max_weight for i in indices),
                    emotional_axis=data.get("emotional_axis", emotional_axis),
                    fragment_ids=[fragments[i].observation_id for i in indices],
                    concept_bridge=shared,
                    all_concepts=sorted(all_concepts),
                    consolidation_type="standard",
                    timestamp=min(fragments[i].timestamp for i in indices),
                )

        # LLM 降级
        return Episode(
            agent_id=agent_id,
            title=f"关于{', '.join(shared[:3])}的碎片",
            content=f"[降级] 概念关联：{', '.join(sorted(all_concepts))}",
            weight=max(fragments[i].max_weight for i in indices) * 0.5,
            emotional_axis=emotional_axis,
            fragment_ids=[fragments[i].observation_id for i in indices],
            concept_bridge=shared,
            all_concepts=sorted(all_concepts),
            consolidation_type="degraded",
            timestamp=min(fragments[i].timestamp for i in indices),
        )

    # ── Saga 编织 ─────────────────────────────────────

    async def _weave_saga(
        self, episodes: list[Episode], agent_id: str
    ) -> Saga | None:
        all_bridges: set[str] = set()
        for ep in episodes:
            all_bridges.update(ep.concept_bridge)

        axis_counts: dict[str, int] = defaultdict(int)
        for ep in episodes:
            axis_counts[ep.emotional_axis] += 1
        dominant_axis = max(axis_counts, key=axis_counts.get) if axis_counts else "none"

        episodes_text = ""
        for ep in episodes:
            episodes_text += f"- 段落「{ep.title}」: {ep.content[:80]}... 情感={ep.emotional_axis}\n"

        prompt = _SAGA_PROMPT_ZH.format(
            episodes_text=episodes_text.strip(),
            concept_bridge=", ".join(sorted(all_bridges)),
            emotional_axis=dominant_axis,
        )

        raw = await self._call_llm(prompt)
        if raw is not None:
            data = self._parse_json(raw)
            if data and "title" in data and "description" in data:
                return Saga(
                    agent_id=agent_id,
                    title=data["title"],
                    description=data["description"],
                    emotional_axis=data.get("emotional_axis", dominant_axis),
                    episode_ids=[ep.id for ep in episodes],
                    timestamp=min(ep.timestamp for ep in episodes),
                )

        # LLM 降级
        return Saga(
            agent_id=agent_id,
            title=f"关于{', '.join(sorted(all_bridges)[:3])}的传奇",
            description=f"[降级] 段落关联：{', '.join(ep.title for ep in episodes)}",
            emotional_axis=dominant_axis,
            episode_ids=[ep.id for ep in episodes],
            timestamp=min(ep.timestamp for ep in episodes),
        )

    # ── 查询委托 ──────────────────────────────────────

    def query_fragments_status(self, agent_id: str = "") -> list[dict]:
        return self._episode_store.query_fragments_status(agent_id)

    def query_episodes_by_agent(self, agent_id: str, status: str = "") -> list[Episode]:
        return self._episode_store.query_episodes_by_agent(agent_id, status)

    def query_sagas_by_agent(self, agent_id: str, status: str = "") -> list[Saga]:
        return self._episode_store.query_sagas_by_agent(agent_id, status)

    def update_fragment_status(self, observation_id: str, agent_id: str, status: str) -> None:
        self._episode_store.upsert_fragment_status(observation_id, agent_id, status)

    def update_episode_status(self, episode_id: int, status: str) -> None:
        self._episode_store.update_episode_status(episode_id, status)

    def update_saga_status(self, saga_id: int, status: str) -> None:
        self._episode_store.update_saga_status(saga_id, status)

    # ── 辅助方法 ──────────────────────────────────────

    @staticmethod
    def _get_shared_concepts(fragments: list[Fragment], indices: list[int]) -> list[str]:
        if not indices:
            return []
        shared = set(fragments[indices[0]].concepts)
        for idx in indices[1:]:
            shared &= set(fragments[idx].concepts)
        return sorted(shared)

    @staticmethod
    def _derive_emotional_axis(fragments: list[Fragment], indices: list[int]) -> str:
        valence_counts: dict[int, int] = defaultdict(int)
        for idx in indices:
            valence_counts[fragments[idx].valence.value_int] += 1
        if valence_counts.get(1, 0) > valence_counts.get(-1, 0):
            return "warmth"
        if valence_counts.get(-1, 0) > valence_counts.get(1, 0):
            return "melancholy"
        return "grounded"

    async def _call_llm(self, prompt: str) -> str | None:
        if self._llm is None:
            return None
        try:
            result = await self._llm.generate_response(prompt)
            return result.response_text if hasattr(result, "response_text") else str(result)
        except Exception as e:
            logger.warning(f"LLM 叙事编织调用失败: {e}")
            return None

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        json_str = raw
        if "```" in json_str:
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            json_str = json_str.strip()
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            return None