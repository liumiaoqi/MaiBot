"""补回合判定 — 纯函数。

以「标点为主、词表为辅」判定最后一条可见消息是否留下了一个未接住的问题或引导。
判定顺序即优先级（R1→R4），命中即返回；无 IO、无时间、无随机。
"""

from enum import Enum


__all__ = ["ClosureSignal", "detect_closure_signal"]


class ClosureSignal(str, Enum):
    """补回合的触发信号。"""

    QUESTION_MARK = "question_mark"
    TAG_PARTICLE = "tag_particle"
    ELLIPSIS_PROMPT = "ellipsis_prompt"
    NONE = "none"


_TAG_PARTICLES = ("吗", "呢", "吧", "嘛")
_ELLIPSIS_ENDINGS = ("…", "...", "~")
_PROMPT_WORDS = ("谁", "什么", "怎么", "为什么", "哪", "如何", "要不要", "好不好")


def detect_closure_signal(text: str) -> ClosureSignal:
    """判定文本结尾是否留下疑问/引导（spec 5.5.1(1) 的可断言化）。"""
    stripped = text.strip()
    if not stripped:
        return ClosureSignal.NONE

    if stripped.endswith(("?", "？")):
        return ClosureSignal.QUESTION_MARK

    if stripped.endswith(_TAG_PARTICLES):
        return ClosureSignal.TAG_PARTICLE

    if stripped.endswith(_ELLIPSIS_ENDINGS) and any(word in stripped for word in _PROMPT_WORDS):
        return ClosureSignal.ELLIPSIS_PROMPT

    return ClosureSignal.NONE