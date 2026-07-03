"""关系信号提取器，从LLM推理内容中提取关系相关信号。"""

from __future__ import annotations

from src.common.logger import get_logger

logger = get_logger("maisaka_relationship_signal")

_POSITIVE_PATTERNS = (
    "喜欢",
    "开心",
    "高兴",
    "感谢",
    "谢谢",
    "好感",
    "亲近",
    "关心",
    "温暖",
    "珍惜",
    "想念",
    "信任",
    "依赖",
    "在乎",
    "重要",
    "like",
    "love",
    "care",
    "thank",
    "happy",
    "glad",
    "trust",
    "miss",
)

_NEGATIVE_PATTERNS = (
    "讨厌",
    "烦",
    "生气",
    "愤怒",
    "失望",
    "不满",
    "厌恶",
    "冷漠",
    "不耐烦",
    "反感",
    "排斥",
    "疏远",
    "hate",
    "dislike",
    "angry",
    "annoyed",
    "disappointed",
    "cold",
)


class RelationshipSignal:
    """从推理内容中提取的关系信号。"""

    def __init__(self, positive_count: int = 0, negative_count: int = 0) -> None:
        self.positive_count = positive_count
        self.negative_count = negative_count

    @property
    def is_positive(self) -> bool:
        """判断整体信号是否偏正面。"""
        return self.positive_count >= self.negative_count

    @property
    def sentiment_strength(self) -> float:
        """计算情感强度，范围 [-1, 1]。"""
        total = self.positive_count + self.negative_count
        if total == 0:
            return 0.0
        return (self.positive_count - self.negative_count) / total


def extract_relationship_signal(reasoning_content: str) -> RelationshipSignal:
    """从推理内容中提取关系信号。

    Args:
        reasoning_content: LLM的推理/思考内容。

    Returns:
        RelationshipSignal: 提取的关系信号。
    """
    if not reasoning_content:
        return RelationshipSignal()

    text_lower = reasoning_content.lower()

    positive_count = sum(1 for p in _POSITIVE_PATTERNS if p in text_lower)
    negative_count = sum(1 for p in _NEGATIVE_PATTERNS if p in text_lower)

    return RelationshipSignal(positive_count=positive_count, negative_count=negative_count)