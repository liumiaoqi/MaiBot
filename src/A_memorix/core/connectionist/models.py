from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from .enums import TimeOfDay, Valence, VoiceStyle

_BEIJING_TZ = timezone(timedelta(hours=8))

SKELETON = 0.1


def _time_of_day_from_timestamp(ts: float) -> TimeOfDay:
    dt = datetime.fromtimestamp(ts, tz=_BEIJING_TZ)
    h = dt.hour
    if 0 <= h < 6:
        return TimeOfDay.DAWN
    if 6 <= h < 11:
        return TimeOfDay.MORNING
    if 11 <= h < 13:
        return TimeOfDay.NOON
    if 13 <= h < 18:
        return TimeOfDay.AFTERNOON
    if 18 <= h < 21:
        return TimeOfDay.EVENING
    return TimeOfDay.NIGHT


def _relative_time_from_timestamp(ts: float, now: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=_BEIJING_TZ)
    now_dt = datetime.fromtimestamp(now, tz=_BEIJING_TZ)
    diff_hours = (now - ts) / 3600
    if diff_hours < 0.1:
        return "刚刚"
    if dt.date() == now_dt.date():
        return "今天"
    if (now_dt.date() - dt.date()).days == 1:
        return "昨天"
    if diff_hours < 96:
        return "这几天"
    if diff_hours < 168:
        return "上周"
    return "很久以前"


def compute_emotional_floor(valence: Valence, emotional_sensitivity: float) -> float:
    if valence == Valence.NEUTRAL:
        return 0.02
    return min(0.30, 0.10 * abs(valence.value_int) * emotional_sensitivity)


@dataclass
class Trace:
    """两个概念之间的连接痕迹，记忆的最小单位"""

    source: str
    target: str
    weight: float = 0.5
    valence: Valence = Valence.NEUTRAL
    agent_id: str = ""
    timestamp: float = 0.0
    detail_level: float = 1.0
    time_of_day: TimeOfDay = TimeOfDay.UNKNOWN
    observation_id: str = ""
    voice_name: str = ""

    @property
    def emotional_floor(self) -> float:
        return compute_emotional_floor(self.valence, 1.0)

    def emotional_floor_for(self, sensitivity: float) -> float:
        return compute_emotional_floor(self.valence, sensitivity)

    def __post_init__(self):
        if self.weight < 0 or self.weight > 1.0:
            raise ValueError(f"weight 必须在 [0, 1.0] 范围内，当前值: {self.weight}")
        if self.detail_level < SKELETON or self.detail_level > 1.0:
            raise ValueError(f"detail_level 必须在 [{SKELETON}, 1.0] 范围内，当前值: {self.detail_level}")
        if not self.source:
            raise ValueError("source 不能为空")
        if not self.target:
            raise ValueError("target 不能为空")

    @property
    def unique_key(self) -> tuple[str, str, str, str]:
        return (self.source, self.target, self.agent_id, self.voice_name)


@dataclass
class MemoryPersonalityV2:
    """智能体记忆性格声明"""

    decay_rate: float = 1.0
    emotional_sensitivity: float = 1.0
    association_depth: int = 2
    reinforcement_boost: float = 0.3
    attention_tags: frozenset[str] = frozenset()
    positive_affinity: float = 1.0
    negative_affinity: float = 1.0
    curiosity: float = 1.0

    def __post_init__(self):
        if not (0.1 <= self.decay_rate <= 5.0):
            raise ValueError(f"decay_rate 有效范围 [0.1, 5.0]，当前值: {self.decay_rate}")
        if not (0.1 <= self.emotional_sensitivity <= 3.0):
            raise ValueError(f"emotional_sensitivity 有效范围 [0.1, 3.0]，当前值: {self.emotional_sensitivity}")
        if not (1 <= self.association_depth <= 4):
            raise ValueError(f"association_depth 有效范围 [1, 4]，当前值: {self.association_depth}")
        if not (0.1 <= self.reinforcement_boost <= 0.5):
            raise ValueError(f"reinforcement_boost 有效范围 [0.1, 0.5]，当前值: {self.reinforcement_boost}")
        if not (0.0 <= self.positive_affinity <= 3.0):
            raise ValueError(f"positive_affinity 有效范围 [0.0, 3.0]，当前值: {self.positive_affinity}")
        if not (0.0 <= self.negative_affinity <= 3.0):
            raise ValueError(f"negative_affinity 有效范围 [0.0, 3.0]，当前值: {self.negative_affinity}")
        if not (0.5 <= self.curiosity <= 2.0):
            raise ValueError(f"curiosity 有效范围 [0.5, 2.0]，当前值: {self.curiosity}")


@dataclass
class InnerVoice:
    """内心声音定义"""

    name: str
    style: VoiceStyle = VoiceStyle.PRESERVE
    focus_concepts: frozenset[str] = frozenset()
    weight_multiplier: float = 1.0
    description: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("name 不能为空")
        if not (0.1 <= self.weight_multiplier <= 2.0):
            raise ValueError(f"weight_multiplier 有效范围 [0.1, 2.0]，当前值: {self.weight_multiplier}")

    def transform_valence(self, valence: Valence) -> Valence:
        match self.style:
            case VoiceStyle.AMPLIFY:
                if valence == Valence.NEUTRAL:
                    return Valence.NEUTRAL
                return valence
            case VoiceStyle.NEUTRALIZE:
                return Valence.NEUTRAL
            case VoiceStyle.PRESERVE:
                return valence
            case VoiceStyle.INVERT:
                match valence:
                    case Valence.POSITIVE:
                        return Valence.NEGATIVE
                    case Valence.NEGATIVE:
                        return Valence.POSITIVE
                    case Valence.NEUTRAL:
                        return Valence.NEUTRAL
            case VoiceStyle.CHAOTIC:
                import random

                return random.choice(list(Valence))
        return valence

    def filter_concepts(self, concepts: list[str], existing: frozenset[str] | None = None) -> list[str]:
        if not self.focus_concepts:
            return concepts
        existing = existing or frozenset()
        return [c for c in concepts if c in self.focus_concepts or c in existing]


@dataclass
class ExtractedConcept:
    """LLM 提取的概念"""

    name: str
    concept_type: str = "unknown"
    confidence: float = 1.0


@dataclass
class ExtractedRelation:
    """LLM 提取的概念间关系"""

    source: str
    target: str
    relation: str = ""


@dataclass
class ExtractionResult:
    """LLM 概念提取结果"""

    concepts: list[ExtractedConcept] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    valence: Valence = Valence.NEUTRAL
    summary: str = ""


@dataclass
class AgentMemoryResult:
    """单个智能体的记忆处理结果"""

    agent_id: str = ""
    remembered: bool = False
    reason: str = ""
    traces_created: int = 0
    voices_active: list[str] = field(default_factory=list)


@dataclass
class ObserveResult:
    """observe() 的返回结果"""

    text: str = ""
    extraction: ExtractionResult = field(default_factory=ExtractionResult)
    memory_results: list[AgentMemoryResult] = field(default_factory=list)


@dataclass
class RecallItem:
    """recall() 的单条回忆结果"""

    concept: str = ""
    activation: float = 0.0
    valence: Valence = Valence.NEUTRAL
    detail_level: float = 1.0
    time_of_day: TimeOfDay = TimeOfDay.UNKNOWN
    relative_time: str = ""


@dataclass
class AssociationItem:
    """画像中的关联概念"""

    concept: str = ""
    strength: float = 0.0
    valence: Valence = Valence.NEUTRAL
    voice: str = ""
    time_of_day: TimeOfDay = TimeOfDay.UNKNOWN
    relative_time: str = ""
    detail: float = 1.0


@dataclass
class VoiceView:
    """内心声音视角"""

    concept: str = ""
    valence: Valence = Valence.NEUTRAL
    strength: float = 0.0


@dataclass
class ContradictionItem:
    """矛盾点：同一概念在不同声音下有不同情感"""

    concept: str = ""
    voice_a: str = ""
    valence_a: Valence = Valence.NEUTRAL
    voice_b: str = ""
    valence_b: Valence = Valence.NEUTRAL


@dataclass
class TimelineItem:
    """时间线条目"""

    timestamp: float = 0.0
    concept: str = ""
    valence: Valence = Valence.NEUTRAL
    voice: str = ""
    detail_level: float = 1.0


@dataclass
class ProfileView:
    """画像实时视图"""

    subject: str = ""
    observer: str = ""
    associations: list[AssociationItem] = field(default_factory=list)
    voices: dict[str, list[VoiceView]] = field(default_factory=dict)
    contradictions: list[ContradictionItem] = field(default_factory=list)
    timeline: list[TimelineItem] = field(default_factory=list)
    depth: str = "空白"
    concept_type: str = "unknown"


@dataclass
class ReflectResult:
    """反思结果"""

    subject: str = ""
    agent_id: str = ""
    voices: dict[str, list[VoiceView]] = field(default_factory=dict)
    contradictions: list[ContradictionItem] = field(default_factory=list)


@dataclass
class DecayResult:
    """粒度退化结果"""

    traces_processed: int = 0
    traces_consolidated: int = 0
    elapsed_ms: float = 0.0