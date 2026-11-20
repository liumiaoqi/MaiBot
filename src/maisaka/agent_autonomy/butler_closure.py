"""管家收尾能力 — 纯数据契约。

本模块只承载枚举与不可变数据结构（话题起点、场景快照、预算决策、配置），
并提供开场文本的唯一构造入口。零 IO、零 LLM、零 src 内依赖，
便于脱离数据库与消息管道做纯函数单测。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


__all__ = [
    "ActionKind",
    "BudgetDecision",
    "ButlerClosureConfig",
    "OpeningDraft",
    "OpeningOutcome",
    "PresentAgent",
    "SceneSnapshot",
    "SummonRequest",
    "TopicContext",
    "TopicTrigger",
]


class TopicTrigger(str, Enum):
    """话题起点的判定类型。"""

    SESSION_FIRST = "session_first"
    SILENCE_GAP = "silence_gap"


class OpeningOutcome(str, Enum):
    """单次开场的结果。"""

    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


class ActionKind(str, Enum):
    """可观测的动作类型。"""

    OPENING = "opening"
    SUMMON = "summon"
    SPEAK_FOR = "speak_for"
    CLOSURE = "closure"
    BUDGET_EXHAUSTED = "budget_exhausted"
    OPENING_FAILED = "opening_failed"
    SUMMON_DROPPED = "summon_dropped"


@dataclass(slots=True, frozen=True)
class PresentAgent:
    """开场时在场的角色。"""

    agent_id: str
    display_name: str


@dataclass(slots=True, frozen=True)
class SceneSnapshot:
    """场景层公共事实；只允许携带以下三类，不得新增未提供的事实。"""

    now_text: str
    present: tuple[PresentAgent, ...]
    emotion_hint: str | None
    missing: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class TopicContext:
    """某一话题的只读上下文快照。"""

    topic_id: str
    session_id: str
    trigger: TopicTrigger
    started_at: datetime
    silence_seconds: float
    budget_limit: int
    budget_used: int
    closure_used: bool
    is_new: bool


@dataclass(slots=True, frozen=True)
class OpeningDraft:
    """开场文本的校验结果；唯一构造入口为 judge_prompt。"""

    ok: bool
    text: str
    chars: int
    reject_reason: str

    @classmethod
    def judge_prompt(
        cls,
        raw_text: str,
        *,
        present: tuple[PresentAgent, ...],
        user_text: str,
        max_chars: int,
    ) -> "OpeningDraft":
        """校验并收敛开场文本。

        判定顺序：空/NONE → 超长截断 → 点名 → 复述用户原话。
        截断必须落在句末标点上；找不到则整条放弃，不发半句。
        """
        stripped = raw_text.strip()
        if stripped.lower() in _EMPTY_REPLIES:
            return cls(ok=False, text="", chars=0, reject_reason="empty")

        truncated = _truncate_at_sentence_end(stripped, max_chars)
        if truncated is None:
            return cls(ok=False, text="", chars=0, reject_reason="no_sentence_end")

        names = [agent.display_name for agent in present if agent.display_name]
        if any(name in truncated for name in names) and any(
            verb in truncated for verb in _DIRECTIVE_VERBS
        ):
            return cls(ok=False, text="", chars=0, reject_reason="named_target")

        if user_text.strip() and truncated == user_text.strip():
            return cls(ok=False, text="", chars=0, reject_reason="echo_user")

        return cls(ok=True, text=truncated, chars=len(truncated), reject_reason="")


@dataclass(slots=True, frozen=True)
class SummonRequest:
    """唤起请求；结构上只有「谁」与「为什么」，不存在台词字段。"""

    target_agent_id: str
    reason: str


@dataclass(slots=True, frozen=True)
class BudgetDecision:
    """一次预算扣减的结果。"""

    granted: bool
    used: int
    limit: int
    exhausted: bool


@dataclass(slots=True, frozen=True)
class ButlerClosureConfig:
    """管家收尾能力的构造期配置。"""

    opening_enabled: bool = True
    silence_threshold_minutes: int = 30
    budget_limit: int = 2
    opening_max_chars: int = 120
    opening_timeout_seconds: float = 4.0
    closure_enabled: bool = True


_EMPTY_REPLIES = frozenset({"", "none"})
_SENTENCE_ENDINGS = frozenset("。！？!?…")
_DIRECTIVE_VERBS = ("你来说", "你说说", "你解释", "你回答", "你讲讲")


def _truncate_at_sentence_end(text: str, max_chars: int) -> str | None:
    """截到 max_chars 内最后一个句末标点；找不到则返回 None。"""
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    for index in range(len(window) - 1, -1, -1):
        if window[index] in _SENTENCE_ENDINGS:
            return window[: index + 1]
    return None