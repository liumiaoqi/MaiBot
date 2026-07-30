"""纯内存 embedding 缓存 — 无 TTL、无持久化、无大小限制"""

import hashlib


def _text_to_simulated_embedding(text: str, dim: int = 32) -> list[float]:
    """将文本转为固定维度的模拟 embedding 向量，基于 SHA-256 哈希。

    这是纯 Python 替代方案，不依赖 numpy。同一文本总是产生同一向量。
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec: list[float] = []
    for i in range(dim):
        byte_idx = i % len(h)
        # 将字节映射到 [-1, 1]
        val = (h[byte_idx] / 127.5) - 1.0
        vec.append(val)
    return vec


class EmbeddingCache:
    """纯内存 embedding 缓存，键 (agent_id, layer, text_hash)"""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, int], list[float]] = {}

    def get_or_compute(
        self,
        agent_id: str,
        layer: str,
        text: str,
        compute_fn=None,
    ) -> list[float]:
        """如果缓存命中则返回缓存值，否则调用 compute_fn 计算并缓存。

        若未提供 compute_fn，使用内置哈希模拟 embedding。
        """
        text_hash = hash(text)
        key = (agent_id, layer, text_hash)
        if key in self._cache:
            return self._cache[key]
        if compute_fn is not None:
            vec = compute_fn(text)
        else:
            vec = _text_to_simulated_embedding(text)
        self._cache[key] = vec
        return vec

    def invalidate(self, agent_id: str, layer: str) -> None:
        """使指定 agent+layer 的缓存失效"""
        keys_to_remove = [
            k for k in self._cache if k[0] == agent_id and k[1] == layer
        ]
        for k in keys_to_remove:
            del self._cache[k]

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
