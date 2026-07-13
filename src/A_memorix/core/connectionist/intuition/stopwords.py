from __future__ import annotations

from src.common.logger import get_logger

from ..cognitive.cognitive_store import CognitiveStore

logger = get_logger("StopwordManager")

# 内置中文停用词（高频虚词/代词/连词）
_BUILTIN_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
    "什么", "吗", "吧", "啊", "呢", "嗯", "哦", "哈", "呀", "嘛",
})


class StopwordManager:
    """停用词管理——从 CognitiveStore 加载 + 内置停用词"""

    def __init__(self, cognitive_store: CognitiveStore | None = None) -> None:
        self._store = cognitive_store
        self._dynamic_stopwords: set[str] = set()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded or self._store is None:
            return
        self._dynamic_stopwords = set(self._store.query_stopwords(min_frequency=5))
        self._loaded = True

    def is_stopword(self, word: str) -> bool:
        self._ensure_loaded()
        return word in _BUILTIN_STOPWORDS or word in self._dynamic_stopwords

    def update_stopwords(self, concepts: list[str]) -> None:
        """更新高频概念到停用词表"""
        if self._store is None:
            return
        concept_counts: dict[str, int] = {}
        for c in concepts:
            concept_counts[c] = concept_counts.get(c, 0) + 1
        self._store.update_frequencies(concept_counts)
        self._loaded = False

    def filter_stopwords(self, words: list[str]) -> list[str]:
        return [w for w in words if not self.is_stopword(w)]