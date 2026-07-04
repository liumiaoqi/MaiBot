"""主动对话内容生成器。

基于智能体人设和当前情绪生成主动对话内容。
内容体现智能体个性和当前情绪。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProactiveContent:
    """主动对话内容。"""

    message: str
    emotion_tone: str = ""
    personality_reflected: bool = True


_EMOTION_TONE_MAP: dict[str, str] = {
    "happy": "开心、分享",
    "excited": "兴奋、热情",
    "lonely": "想念、寻求陪伴",
    "sad": "低落、需要安慰",
    "anxious": "不安、需要确认",
    "angry": "不满、直接表达",
    "calm": "平静、温和",
}

_EMOTION_TEMPLATES: dict[str, list[str]] = {
    "happy": [
        "嘿！突然想跟你说……",
        "好开心啊！想分享一下……",
    ],
    "excited": [
        "哇！我有个超棒的想法！",
        "太激动了！你知道吗……",
    ],
    "lonely": [
        "好久没聊天了……",
        "在吗？突然有点想你……",
    ],
    "calm": [
        "嗯……突然想到一件事。",
        "对了，有个事想说……",
    ],
}


class ProactiveContentGenerator:
    """主动对话内容生成器。"""

    def generate(
        self,
        display_name: str,
        personality: str,
        emotion_state: dict[str, int] | None = None,
        time_period_label: str = "",
        trigger_type: str = "greeting",
        message_template: str = "",
    ) -> ProactiveContent:
        """生成主动对话内容。

        Args:
            display_name: 智能体显示名。
            personality: 人格设定。
            emotion_state: 当前情绪状态。
            time_period_label: 时段标签。
            trigger_type: 触发类型。
            message_template: 消息模板（来自时间触发规则）。

        Returns:
            ProactiveContent: 生成的内容。
        """
        if message_template:
            return ProactiveContent(
                message=message_template,
                emotion_tone="定时触发",
                personality_reflected=True,
            )

        dominant_emotion = self._get_dominant_emotion(emotion_state)
        emotion_tone = _EMOTION_TONE_MAP.get(dominant_emotion, "平静")

        templates = _EMOTION_TEMPLATES.get(dominant_emotion, _EMOTION_TEMPLATES["calm"])

        import random

        message = random.choice(templates)

        if time_period_label:
            time_greetings = {
                "早晨": "早上好！",
                "上午": "上午好！",
                "中午": "中午好！",
                "下午": "下午好！",
                "傍晚": "傍晚了，",
                "晚上": "晚上好！",
                "深夜": "这么晚了……",
            }
            greeting = time_greetings.get(time_period_label, "")
            if greeting:
                message = greeting + message

        return ProactiveContent(
            message=message,
            emotion_tone=emotion_tone,
            personality_reflected=True,
        )

    def _get_dominant_emotion(self, emotion_state: dict[str, int] | None) -> str:
        """获取主导情绪类型。"""
        if not emotion_state:
            return "calm"

        proactive_emotions = {"lonely": 1.5, "happy": 1.2, "excited": 1.3, "calm": 0.8}
        best_emotion = "calm"
        best_score = 0.0

        for emotion, intensity in emotion_state.items():
            weight = proactive_emotions.get(emotion, 0.5)
            score = intensity * weight
            if score > best_score:
                best_score = score
                best_emotion = emotion

        return best_emotion