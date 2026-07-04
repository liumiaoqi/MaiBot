"""上下文摘要生成器。

为每个聊天流生成上下文摘要（关键话题、参与者、情绪氛围）。
摘要生成失败时使用上一次成功的摘要。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContextSummary:
    """上下文摘要。"""

    session_id: str
    agent_id: str
    topics: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    emotion_atmosphere: str = ""
    is_private: bool = False
    message_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_text(self) -> str:
        """生成摘要文本。"""
        parts = []
        if self.topics:
            parts.append(f"话题：{'、'.join(self.topics[:5])}")
        if self.participants:
            parts.append(f"参与者：{'、'.join(self.participants[:5])}")
        if self.emotion_atmosphere:
            parts.append(f"氛围：{self.emotion_atmosphere}")
        return "；".join(parts) if parts else "暂无摘要"


class ContextSummarizer:
    """上下文摘要生成器。"""

    MIN_MESSAGES_FOR_SUMMARY = 20
    _last_summaries: dict[str, ContextSummary] = {}

    def generate_summary(
        self,
        session_id: str,
        agent_id: str,
        messages: list[dict[str, Any]],
        is_private: bool = False,
    ) -> ContextSummary | None:
        """生成上下文摘要。

        Args:
            session_id: 会话ID。
            agent_id: 智能体ID。
            messages: 消息列表。
            is_private: 是否为私聊。

        Returns:
            ContextSummary 或 None。
        """
        if len(messages) < self.MIN_MESSAGES_FOR_SUMMARY:
            logger.debug(
                "消息数不足(%d<%d)，跳过摘要: session=%s",
                len(messages),
                self.MIN_MESSAGES_FOR_SUMMARY,
                session_id,
            )
            return None

        try:
            topics = self._extract_topics(messages)
            participants = self._extract_participants(messages)
            emotion_atmosphere = self._infer_emotion_atmosphere(messages)

            now = time.time()
            summary = ContextSummary(
                session_id=session_id,
                agent_id=agent_id,
                topics=topics,
                participants=participants,
                emotion_atmosphere=emotion_atmosphere,
                is_private=is_private,
                message_count=len(messages),
                created_at=now,
                updated_at=now,
            )

            self._last_summaries[session_id] = summary
            return summary

        except Exception as e:
            logger.warning("摘要生成失败，使用上次摘要: session=%s error=%s", session_id, e)
            return self._last_summaries.get(session_id)

    def _extract_topics(self, messages: list[dict[str, Any]]) -> list[str]:
        """从消息中提取关键话题。"""
        topics: list[str] = []
        seen: set[str] = set()

        for msg in messages[-50:]:
            text = msg.get("text", "") or msg.get("content", "")
            if not text or not isinstance(text, str):
                continue
            for keyword in self._extract_keywords(text):
                if keyword not in seen and len(topics) < 5:
                    topics.append(keyword)
                    seen.add(keyword)

        return topics

    def _extract_keywords(self, text: str) -> list[str]:
        """简单关键词提取。"""
        import re

        words = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
        freq: dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1

        sorted_words = sorted(freq.items(), key=lambda x: -x[1])
        return [w for w, _ in sorted_words[:5]]

    def _extract_participants(self, messages: list[dict[str, Any]]) -> list[str]:
        """从消息中提取参与者。"""
        participants: list[str] = []
        seen: set[str] = set()

        for msg in messages[-50:]:
            sender = msg.get("sender_name", "") or msg.get("sender_id", "")
            if sender and sender not in seen:
                participants.append(str(sender))
                seen.add(sender)
                if len(participants) >= 5:
                    break

        return participants

    def _infer_emotion_atmosphere(self, messages: list[dict[str, Any]]) -> str:
        """推断情绪氛围。"""
        positive_keywords = {"开心", "哈哈", "好的", "谢谢", "喜欢", "棒", "厉害", "有趣"}
        negative_keywords = {"难过", "生气", "烦", "讨厌", "无聊", "累", "焦虑"}

        pos_count = 0
        neg_count = 0

        for msg in messages[-30:]:
            text = str(msg.get("text", "") or msg.get("content", ""))
            for kw in positive_keywords:
                if kw in text:
                    pos_count += 1
            for kw in negative_keywords:
                if kw in text:
                    neg_count += 1

        if pos_count > neg_count * 2:
            return "轻松愉快"
        if neg_count > pos_count * 2:
            return "低沉压抑"
        return "平和正常"