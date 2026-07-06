"""DeepSeek 前缀缓存优化管理器。

设计稳定前缀层以最大化 DeepSeek 前缀缓存命中率：
[system消息] → [智能体人设] → [情绪基线] → [内部关系网] → [可变上下文] → [对话历史]

稳定层（不随对话轮次变化）命中缓存；可变层每轮更新。
"""

from __future__ import annotations

import time
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("maisaka_deepseek_prefix_cache")


class PrefixCacheStats:
    """前缀缓存命中率统计。"""

    def __init__(self) -> None:
        self._hits: dict[str, int] = {}
        self._misses: dict[str, int] = {}

    def record_hit(self, agent_id: str, tokens: int) -> None:
        self._hits[agent_id] = self._hits.get(agent_id, 0) + tokens

    def record_miss(self, agent_id: str, tokens: int) -> None:
        self._misses[agent_id] = self._misses.get(agent_id, 0) + tokens

    def get_hit_rate(self, agent_id: str) -> float:
        """获取指定智能体的前缀缓存命中率。"""
        hits = self._hits.get(agent_id, 0)
        misses = self._misses.get(agent_id, 0)
        total = hits + misses
        if total == 0:
            return 0.0
        return hits / total

    def get_stats(self, agent_id: str) -> dict[str, int | float]:
        """获取指定智能体的缓存统计。"""
        return {
            "hit_tokens": self._hits.get(agent_id, 0),
            "miss_tokens": self._misses.get(agent_id, 0),
            "hit_rate": self.get_hit_rate(agent_id),
        }


class PrefixLayer:
    """前缀层，包含内容和层级信息。"""

    def __init__(self, name: str, content: str, is_stable: bool = True) -> None:
        self.name = name
        self.content = content
        self.is_stable = is_stable
        self._hash: Optional[str] = None

    @property
    def content_hash(self) -> str:
        """计算内容哈希，用于检测变化。"""
        if self._hash is None:
            import hashlib

            self._hash = hashlib.md5(self.content.encode()).hexdigest()[:16]
        return self._hash


class PrefixCacheManager:
    """DeepSeek 前缀缓存管理器。"""

    STABLE_LAYERS = ["system", "identity", "emotion_baseline", "internal_relationships"]
    VARIABLE_LAYERS = ["anti_mechanization", "profile", "mid_term", "heuristic", "cross_chat", "history"]

    def __init__(self) -> None:
        self._stats = PrefixCacheStats()
        self._last_stable_hash: dict[str, str] = {}
        self._last_update_time: dict[str, float] = {}

    def build_prefix_layers(
        self,
        agent_id: str,
        system_content: str,
        identity_content: str,
        emotion_baseline_content: str,
        internal_relationships_content: str,
    ) -> list[PrefixLayer]:
        """构建稳定前缀层。"""
        layers = [
            PrefixLayer("system", system_content, is_stable=True),
            PrefixLayer("identity", identity_content, is_stable=True),
            PrefixLayer("emotion_baseline", emotion_baseline_content, is_stable=True),
            PrefixLayer("internal_relationships", internal_relationships_content, is_stable=True),
        ]

        stable_hash = "|".join(layer.content_hash for layer in layers)
        previous_hash = self._last_stable_hash.get(agent_id)

        if previous_hash is not None:
            if stable_hash == previous_hash:
                total_tokens = sum(len(layer.content) for layer in layers) // 4
                self._stats.record_hit(agent_id, total_tokens)
            else:
                total_tokens = sum(len(layer.content) for layer in layers) // 4
                self._stats.record_miss(agent_id, total_tokens)

        self._last_stable_hash[agent_id] = stable_hash
        self._last_update_time[agent_id] = time.time()

        return layers

    def get_cache_stats(self, agent_id: str) -> dict[str, int | float]:
        """获取指定智能体的前缀缓存统计。"""
        return self._stats.get_stats(agent_id)

    def check_threshold_alert(self, agent_id: str, threshold: float = 0.3) -> bool:
        """检查缓存命中率是否低于阈值。"""
        hit_rate = self._stats.get_hit_rate(agent_id)
        if hit_rate > 0 and hit_rate < threshold:
            logger.warning(f"智能体 {agent_id} 前缀缓存命中率 {hit_rate:.2%} 低于阈值 {threshold:.0%}")
            return True
        return False

    def is_prefix_cache_enabled(self, agent_id: str) -> bool:
        """检查智能体是否启用前缀缓存。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry.get_instance()
            if registry.has_agent(agent_id):
                return registry.get_agent(agent_id).deepseek.prefix_cache_enabled
        except Exception:
            pass
        return True