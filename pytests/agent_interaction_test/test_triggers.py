"""ZG P1/P2 修复批 6 T6.3：6 个交互触发器单元测试。

覆盖 src/maisaka/agent_interaction/triggers/ 下全部触发器：
- EmotionDrivenTrigger：情绪驱动触发
- TimeAwarenessTrigger：时间感知触发
- MentionPropagationTrigger：提及传播触发
- InnerNeedTrigger：内在需求触发
- EventRippleTrigger：事件涟漪触发
- MemoryDrivenTrigger：记忆驱动触发（含配置透传）

同时覆盖 TriggerRegistry 注册/查询基础功能。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.memory_types import MemoryHit, MemorySearchResult
from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import (
    BaseTrigger,
    TriggerRegistry,
)
from src.maisaka.agent_interaction.triggers import (
    EmotionDrivenTrigger,
    EventRippleTrigger,
    InnerNeedTrigger,
    MentionPropagationTrigger,
    MemoryDrivenTrigger,
    TimeAwarenessTrigger,
)


# ── 辅助函数 ─────────────────────────────────────────────


def _make_emotion_state(
    dominant: str = "calm", intensity: float = 10.0, **overrides
) -> EmotionState:
    """构造 EmotionState。

    Args:
        dominant: 主导情绪类型
        intensity: 主导情绪强度
        **overrides: 覆盖其他情绪维度
    """
    emotions = {
        e: 0.0
        for e in ("happy", "sad", "anxious", "angry", "calm", "excited", "lonely")
    }
    emotions[dominant] = intensity
    emotions.update(overrides)
    return EmotionState(emotions=emotions, dominant_emotion=dominant)


def _make_relationship(
    target_id: str = "agent_b",
    score: float = 100.0,
    rel_type: str = "friend",
    agent_id: str = "agent_a",
    last_interaction_at: datetime | None = None,
    coactivation: float = 0.0,
) -> AgentInteractionRelationshipRead:
    """构造 AgentInteractionRelationshipRead。"""
    return AgentInteractionRelationshipRead(
        id=1,
        agent_id=agent_id,
        target_agent_id=target_id,
        score=score,
        relationship_type=rel_type,
        attitude="",
        interaction_count=5,
        last_interaction_at=last_interaction_at,
        coactivation_strength=coactivation,
    )


# ── EmotionDrivenTrigger 测试 ────────────────────────────


class EmotionDrivenTriggerTest:
    """EmotionDrivenTrigger 情绪驱动触发器测试。"""

    @pytest.fixture
    def trigger(self):
        return EmotionDrivenTrigger()

    async def test_intensity_below_threshold_no_trigger(self, trigger):
        """情绪强度 < 60 不触发。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=30)
        rels = [_make_relationship(target_id="b", score=300, rel_type="friend")]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False
        assert result.interaction_type == "emotion_driven"
        assert result.initiator_agent_id == "a"

    async def test_high_intensity_lonely_triggers(self, trigger):
        """lonely 高强度 + friend 关系 → 触发。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=80)
        rels = [
            _make_relationship(
                target_id="b", score=300, rel_type="friend", coactivation=1.0
            )
        ]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is True
        assert result.target_agent_id == "b"
        assert result.interaction_type == "emotion_driven"
        assert result.trigger_probability > 0

    async def test_low_probability_no_trigger(self, trigger):
        """触发概率 < 0.3 不触发。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=60)
        rels = [
            _make_relationship(
                target_id="b", score=10, rel_type="rival", coactivation=0.0
            )
        ]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False

    async def test_empty_relationships_no_trigger(self, trigger):
        """空关系列表不触发。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=80)
        result = await trigger.evaluate("a", emotion, [])
        assert result.should_trigger is False

    async def test_selects_best_target(self, trigger):
        """多关系选择触发概率最高的目标。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=90)
        rels = [
            _make_relationship(
                target_id="friend_b",
                score=100,
                rel_type="friend",
                coactivation=0.5,
            ),
            _make_relationship(
                target_id="family_c",
                score=300,
                rel_type="family",
                coactivation=1.0,
            ),
        ]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is True
        # family 系数 1.5 > friend 系数 1.0，且 score 更高 → family_c 概率更高
        assert result.target_agent_id == "family_c"

    async def test_emerged_relationship_type_resolved(self, trigger):
        """emerged_ 类型关系被映射到基础类型后参与概率计算。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=90)
        rels = [
            _make_relationship(
                target_id="b", score=300, rel_type="emerged_friend", coactivation=1.0
            )
        ]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is True
        # metadata 记录原始关系类型
        assert result.metadata["relationship_type"] == "emerged_friend"

    async def test_metadata_contains_emotion_info(self, trigger):
        """触发结果 metadata 包含情绪信息。"""
        emotion = _make_emotion_state(dominant="happy", intensity=90)
        rels = [
            _make_relationship(
                target_id="b", score=300, rel_type="friend", coactivation=1.0
            )
        ]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is True
        assert result.metadata["dominant_emotion"] == "happy"
        assert result.metadata["intensity"] == 90

    async def test_trigger_reason_contains_description(self, trigger):
        """触发原因包含情绪交互描述。"""
        emotion = _make_emotion_state(dominant="lonely", intensity=90)
        rels = [
            _make_relationship(
                target_id="b", score=300, rel_type="friend", coactivation=1.0
            )
        ]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is True
        assert "寻求陪伴" in result.trigger_reason


# ── TimeAwarenessTrigger 测试 ────────────────────────────


class TimeAwarenessTriggerTest:
    """TimeAwarenessTrigger 时间感知触发器测试。"""

    @pytest.fixture
    def trigger(self):
        return TimeAwarenessTrigger()

    async def test_no_time_context_no_trigger(self, trigger):
        """time_context=None 不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(score=300, rel_type="friend")]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False
        assert result.interaction_type == "time_awareness"

    async def test_low_active_coefficient_no_trigger(self, trigger):
        """活跃系数 < 0.8 不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(score=300, rel_type="friend")]
        result = await trigger.evaluate(
            "a", emotion, rels, time_context={"active_coefficient": 0.5}
        )
        assert result.should_trigger is False

    async def test_high_active_coefficient_triggers(self, trigger):
        """高活跃系数 + friend 关系 → 触发（非深夜时段）。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300, rel_type="friend")]
        with patch(
            "src.maisaka.agent_interaction.triggers.time_awareness.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 14
            mock_dt.now.return_value = mock_now
            result = await trigger.evaluate(
                "a", emotion, rels, time_context={"active_coefficient": 0.9}
            )
        assert result.should_trigger is True
        assert result.target_agent_id == "b"

    async def test_late_night_skips_non_intimate(self, trigger):
        """深夜时段跳过非亲密关系（friend）。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="friend_b", score=300, rel_type="friend")]
        with patch(
            "src.maisaka.agent_interaction.triggers.time_awareness.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 23
            mock_dt.now.return_value = mock_now
            result = await trigger.evaluate(
                "a", emotion, rels, time_context={"active_coefficient": 0.9}
            )
        assert result.should_trigger is False

    async def test_late_night_intimate_triggers(self, trigger):
        """深夜时段对 family 关系触发。"""
        emotion = _make_emotion_state()
        rels = [
            _make_relationship(target_id="family_b", score=300, rel_type="family")
        ]
        with patch(
            "src.maisaka.agent_interaction.triggers.time_awareness.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 23
            mock_dt.now.return_value = mock_now
            result = await trigger.evaluate(
                "a", emotion, rels, time_context={"active_coefficient": 0.9}
            )
        assert result.should_trigger is True
        assert result.target_agent_id == "family_b"

    async def test_empty_relationships_no_trigger(self, trigger):
        """空关系列表不触发。"""
        emotion = _make_emotion_state()
        result = await trigger.evaluate(
            "a", emotion, [], time_context={"active_coefficient": 0.9}
        )
        assert result.should_trigger is False

    async def test_default_active_coefficient_below_threshold(self, trigger):
        """time_context 无 active_coefficient 时默认 0.5 < 0.8 不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(score=300, rel_type="friend")]
        result = await trigger.evaluate("a", emotion, rels, time_context={})
        assert result.should_trigger is False

    async def test_metadata_contains_time_info(self, trigger):
        """触发结果 metadata 包含时间信息。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300, rel_type="friend")]
        with patch(
            "src.maisaka.agent_interaction.triggers.time_awareness.datetime"
        ) as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 14
            mock_dt.now.return_value = mock_now
            result = await trigger.evaluate(
                "a",
                emotion,
                rels,
                time_context={"active_coefficient": 0.9, "time_period": "afternoon"},
            )
        assert result.should_trigger is True
        assert result.metadata["time_period"] == "afternoon"
        assert result.metadata["active_coefficient"] == 0.9
        assert result.metadata["is_late_night"] is False


# ── MentionPropagationTrigger 测试 ───────────────────────


class MentionPropagationTriggerTest:
    """MentionPropagationTrigger 提及传播触发器测试。"""

    @pytest.fixture
    def trigger(self):
        return MentionPropagationTrigger()

    async def test_memory_context_with_mentioner_triggers(self, trigger):
        """memory_context 提供提及方且 mention_tendency >= 0.3 → 触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=100)]
        memory_ctx = {"mentioner_id": "b", "mention_tendency": 0.5}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.target_agent_id == "b"
        # 概率 = 0.5 * 0.6 = 0.3
        assert result.trigger_probability == pytest.approx(0.3)

    async def test_low_mention_tendency_no_trigger(self, trigger):
        """mention_tendency < 0.3 不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=100)]
        memory_ctx = {"mentioner_id": "b", "mention_tendency": 0.1}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is False

    async def test_no_mentioner_no_trigger(self, trigger):
        """无提及方且关系 mention_tendency 不足时不触发。"""
        emotion = _make_emotion_state()
        # score=10 → mention=0.033 < 0.3
        rels = [_make_relationship(target_id="b", score=10)]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False

    async def test_falls_back_to_relationships(self, trigger):
        """无 memory_context 时从关系查找 mention_tendency >= 0.3 触发。"""
        emotion = _make_emotion_state()
        # score=300 → mention=1.0 >= 0.3
        rels = [_make_relationship(target_id="b", score=300)]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is True
        assert result.target_agent_id == "b"

    async def test_empty_relationships_no_trigger(self, trigger):
        """空关系列表且无 memory_context 不触发。"""
        emotion = _make_emotion_state()
        result = await trigger.evaluate("a", emotion, [])
        assert result.should_trigger is False

    async def test_metadata_contains_mentioner_info(self, trigger):
        """触发结果 metadata 包含提及方信息。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=100)]
        memory_ctx = {"mentioner_id": "b", "mention_tendency": 0.8}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.metadata["mentioner_id"] == "b"
        assert result.metadata["mention_tendency"] == 0.8

    async def test_probability_calculation(self, trigger):
        """触发概率 = mention_tendency × 0.6。"""
        emotion = _make_emotion_state()
        memory_ctx = {"mentioner_id": "c", "mention_tendency": 0.5}
        result = await trigger.evaluate("a", emotion, [], memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.trigger_probability == pytest.approx(0.3)

    async def test_skips_self_relationship(self, trigger):
        """无 memory_context 时跳过 target_agent_id == agent_id 的自关系。"""
        emotion = _make_emotion_state()
        # 关系列表只有自己对自己的关系，应被 continue 跳过
        rels = [_make_relationship(target_id="a", score=300, agent_id="a")]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False


# ── InnerNeedTrigger 测试 ────────────────────────────────


class InnerNeedTriggerTest:
    """InnerNeedTrigger 内在需求触发器测试。"""

    @pytest.fixture
    def trigger(self):
        return InnerNeedTrigger()

    async def test_non_calm_emotion_no_trigger(self, trigger):
        """主导情绪非 calm 不触发。"""
        emotion = _make_emotion_state(dominant="happy", intensity=10)
        rels = [_make_relationship(score=300)]
        memory_ctx = {"idle_hours": 3.0}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is False
        assert result.interaction_type == "inner_need"

    async def test_high_calm_intensity_no_trigger(self, trigger):
        """calm 强度 >= 20 不触发。"""
        emotion = _make_emotion_state(dominant="calm", intensity=25)
        rels = [_make_relationship(score=300)]
        memory_ctx = {"idle_hours": 3.0}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is False

    async def test_low_idle_hours_no_trigger(self, trigger):
        """idle_hours < 2 不触发。"""
        emotion = _make_emotion_state(dominant="calm", intensity=10)
        rels = [_make_relationship(score=300)]
        memory_ctx = {"idle_hours": 1.0}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is False

    async def test_calm_low_intensity_triggers(self, trigger):
        """calm 低强度 + 长空闲 → 触发。"""
        emotion = _make_emotion_state(dominant="calm", intensity=5)
        rels = [_make_relationship(target_id="b", score=300)]
        memory_ctx = {"idle_hours": 3.0}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.target_agent_id == "b"

    async def test_empty_relationships_no_trigger(self, trigger):
        """空关系列表不触发。"""
        emotion = _make_emotion_state(dominant="calm", intensity=5)
        memory_ctx = {"idle_hours": 3.0}
        result = await trigger.evaluate("a", emotion, [], memory_context=memory_ctx)
        assert result.should_trigger is False

    async def test_metadata_contains_need_info(self, trigger):
        """触发结果 metadata 包含需求信息。"""
        emotion = _make_emotion_state(dominant="calm", intensity=5)
        rels = [_make_relationship(target_id="b", score=300, rel_type="friend")]
        memory_ctx = {"idle_hours": 3.0}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.metadata["calm_intensity"] == 5
        assert result.metadata["idle_hours"] == 3.0
        assert result.metadata["relationship_type"] == "friend"

    async def test_no_memory_context_no_trigger(self, trigger):
        """无 memory_context 时 idle_hours=0 < 2 不触发。"""
        emotion = _make_emotion_state(dominant="calm", intensity=5)
        rels = [_make_relationship(score=300)]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False


# ── EventRippleTrigger 测试 ──────────────────────────────


class EventRippleTriggerTest:
    """EventRippleTrigger 事件涟漪触发器测试。"""

    @pytest.fixture
    def trigger(self):
        return EventRippleTrigger()

    async def test_no_event_impact_no_trigger(self, trigger):
        """event_impact <= 0 不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(score=300, rel_type="family")]
        memory_ctx = {"event_impact": 0.0, "event_desc": "测试"}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is False
        assert result.interaction_type == "event_ripple"

    async def test_event_impact_triggers_for_family(self, trigger):
        """family 关系 + event_impact > 0 → 触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300, rel_type="family")]
        memory_ctx = {"event_impact": 0.8, "event_desc": "关系升级"}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.target_agent_id == "b"

    async def test_no_intimate_relationship_no_trigger(self, trigger):
        """无 family/romantic 关系不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(score=300, rel_type="friend")]
        memory_ctx = {"event_impact": 0.8, "event_desc": "测试"}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is False

    async def test_default_event_desc(self, trigger):
        """未提供 event_desc 时使用默认值"重要交互"。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300, rel_type="romantic")]
        memory_ctx = {"event_impact": 0.8}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert "重要交互" in result.trigger_reason

    async def test_metadata_contains_event_info(self, trigger):
        """触发结果 metadata 包含事件信息。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300, rel_type="family")]
        memory_ctx = {"event_impact": 0.8, "event_desc": "情绪剧变"}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        assert result.metadata["event_impact"] == 0.8
        assert result.metadata["event_desc"] == "情绪剧变"
        assert result.metadata["relationship_type"] == "family"

    async def test_probability_calculation(self, trigger):
        """触发概率 = event_impact × mention × 0.5。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300, rel_type="family")]
        memory_ctx = {"event_impact": 0.8}
        result = await trigger.evaluate("a", emotion, rels, memory_context=memory_ctx)
        assert result.should_trigger is True
        # mention = 1.0, prob = 0.8 * 1.0 * 0.5 = 0.4
        assert result.trigger_probability == pytest.approx(0.4)

    async def test_no_memory_context_no_trigger(self, trigger):
        """无 memory_context 时 event_impact=0 不触发。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(score=300, rel_type="family")]
        result = await trigger.evaluate("a", emotion, rels)
        assert result.should_trigger is False


# ── MemoryDrivenTrigger 测试 ─────────────────────────────


class MemoryDrivenTriggerTest:
    """MemoryDrivenTrigger 记忆驱动触发器测试。"""

    @pytest.fixture
    def mock_adapter(self):
        """mock AgentMemoryAdapter，默认返回空检索结果。"""
        adapter = MagicMock()
        empty_result = MemorySearchResult(success=True, hits=[])
        adapter.search_interaction_memory = AsyncMock(return_value=empty_result)
        return adapter

    @pytest.fixture
    def trigger(self, mock_adapter):
        return MemoryDrivenTrigger(mock_adapter)

    def test_config_passthrough(self, mock_adapter):
        """构造函数配置透传正确。"""
        t = MemoryDrivenTrigger(
            mock_adapter,
            positive_bonus=0.25,
            negative_penalty=0.35,
            reconcile_bonus=0.18,
            reunion_probability=0.2,
            reunion_threshold_hours=48,
            recall_rate_limit_rpm=20,
        )
        assert t._positive_bonus == 0.25
        assert t._negative_penalty == 0.35
        assert t._reconcile_bonus == 0.18
        assert t._reunion_probability == 0.2
        assert t._reunion_threshold_hours == 48
        assert t._recall_rate_limit_rpm == 20

    def test_default_config_values(self, mock_adapter):
        """默认配置值正确。"""
        t = MemoryDrivenTrigger(mock_adapter)
        assert t._positive_bonus == 0.2
        assert t._negative_penalty == 0.3
        assert t._reconcile_bonus == 0.15
        assert t._reunion_probability == 0.15
        assert t._reunion_threshold_hours == 24
        assert t._recall_rate_limit_rpm == 10

    def test_recall_rate_limit_floored_to_1(self, mock_adapter):
        """recall_rate_limit_rpm < 1 时被 max(1, ...) 限制为 1。"""
        t = MemoryDrivenTrigger(mock_adapter, recall_rate_limit_rpm=0)
        assert t._recall_rate_limit_rpm == 1

    def test_memory_adapter_stored(self, mock_adapter):
        """构造函数存储 memory_adapter 引用。"""
        t = MemoryDrivenTrigger(mock_adapter)
        assert t._memory_adapter is mock_adapter

    async def test_positive_memory_bonus(self, mock_adapter):
        """正面记忆加成触发。"""
        hit = MemoryHit(content="愉快的对话", metadata={"tags": ["positive"]})
        result = MemorySearchResult(success=True, hits=[hit])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # base=0.5 + positive_bonus=0.2 = 0.7 ≥ 0.3 触发
        assert evaluation.should_trigger is True
        assert evaluation.target_agent_id == "b"

    async def test_negative_memory_penalty(self, mock_adapter):
        """负面记忆惩罚导致概率不足不触发。"""
        hits = [
            MemoryHit(content="吵架了", metadata={"tags": ["negative"]}),
            MemoryHit(content="冷战", metadata={"tags": ["negative"]}),
        ]
        result = MemorySearchResult(success=True, hits=hits)
        mock_adapter.search_interaction_memory = AsyncMock(return_value=result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # base=0.5 - 2*0.3 = -0.1 → max(0,-0.1)=0 < 0.3 不触发
        assert evaluation.should_trigger is False

    async def test_reconcile_bonus(self, mock_adapter):
        """和好记忆加成触发。"""
        hit = MemoryHit(content="想和好", metadata={"tags": []})
        result = MemorySearchResult(success=True, hits=[hit])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # base=0.5 + reconcile=0.15 = 0.65 ≥ 0.3 触发
        assert evaluation.should_trigger is True
        assert evaluation.target_agent_id == "b"

    async def test_continuation_bonus(self, mock_adapter):
        """续聊约定加成触发。"""
        hit = MemoryHit(content="下次再聊", metadata={"tags": []})
        result = MemorySearchResult(success=True, hits=[hit])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # base=0.5 + continuation=0.1 = 0.6 ≥ 0.3 触发
        assert evaluation.should_trigger is True

    async def test_reunion_when_no_memory(self, mock_adapter):
        """无交互记忆且 last_interaction_at=None 时重逢检查触发。"""
        empty_result = MemorySearchResult(success=True, hits=[])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=empty_result)
        trigger = MemoryDrivenTrigger(
            mock_adapter,
            reunion_probability=0.5,  # 调高以触发
        )
        emotion = _make_emotion_state()
        rels = [
            _make_relationship(target_id="b", score=300, last_interaction_at=None)
        ]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # mention=1.0, reunion=0.5*1.0=0.5 ≥ 0.3 触发
        assert evaluation.should_trigger is True
        assert evaluation.target_agent_id == "b"

    async def test_low_probability_no_trigger(self, mock_adapter):
        """默认重逢概率 0.15 不足 0.3 不触发。"""
        empty_result = MemorySearchResult(success=True, hits=[])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=empty_result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [
            _make_relationship(target_id="b", score=300, last_interaction_at=None)
        ]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # mention=1.0, reunion=0.15*1.0=0.15 < 0.3 不触发
        assert evaluation.should_trigger is False

    async def test_empty_relationships_no_trigger(self, mock_adapter):
        """空关系列表不触发。"""
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        evaluation = await trigger.evaluate("a", emotion, [])
        assert evaluation.should_trigger is False

    async def test_memory_search_failure_fallback(self, mock_adapter):
        """记忆检索异常时走兜底低概率（mention × 0.3）。"""
        mock_adapter.search_interaction_memory = AsyncMock(
            side_effect=RuntimeError("检索失败")
        )
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # 兜底 prob = mention * 0.3 = 1.0 * 0.3 = 0.3 ≥ 0.3 触发
        assert evaluation.should_trigger is True

    async def test_recall_rate_limit_skips_search(self, mock_adapter):
        """检索频率限流：超限时整轮跳过记忆检索。"""
        hit = MemoryHit(content="愉快", metadata={"tags": ["positive"]})
        result = MemorySearchResult(success=True, hits=[hit])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=result)
        trigger = MemoryDrivenTrigger(mock_adapter, recall_rate_limit_rpm=1)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        # 第一次调用：允许检索，prob = 0.5 + 0.2 = 0.7 触发
        eval1 = await trigger.evaluate("a", emotion, rels)
        assert eval1.should_trigger is True
        # 第二次调用：限流跳过检索，prob = mention * 0.3 = 0.3 ≥ 0.3 触发
        eval2 = await trigger.evaluate("a", emotion, rels)
        assert eval2.should_trigger is True
        # 验证第二次确实被限流（search 仅被第一次调用 1 次）
        assert mock_adapter.search_interaction_memory.call_count == 1

    async def test_interaction_type_is_memory_driven(self, trigger):
        """触发结果 interaction_type 为 memory_driven。"""
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        assert evaluation.interaction_type == "memory_driven"

    async def test_tags_as_string_parsed(self, mock_adapter):
        """tags 为字符串时被正确解析为列表。"""
        hit = MemoryHit(content="愉快对话", metadata={"tags": "positive"})
        result = MemorySearchResult(success=True, hits=[hit])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        rels = [_make_relationship(target_id="b", score=300)]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # base=0.5 + positive=0.2 = 0.7 ≥ 0.3 触发
        assert evaluation.should_trigger is True

    async def test_reunion_with_old_timestamp_triggers(self, mock_adapter):
        """last_interaction_at 远古时间戳（超阈值）时重逢触发。"""
        from datetime import timedelta

        empty_result = MemorySearchResult(success=True, hits=[])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=empty_result)
        trigger = MemoryDrivenTrigger(
            mock_adapter,
            reunion_probability=0.5,
            reunion_threshold_hours=24,
        )
        emotion = _make_emotion_state()
        # 2 天前交互，超过 24 小时阈值
        old_time = datetime.now() - timedelta(days=2)
        rels = [
            _make_relationship(target_id="b", score=300, last_interaction_at=old_time)
        ]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # mention=1.0, reunion=0.5*1.0=0.5 ≥ 0.3 触发
        assert evaluation.should_trigger is True
        assert evaluation.target_agent_id == "b"

    async def test_reunion_with_recent_timestamp_no_trigger(self, mock_adapter):
        """last_interaction_at 最近（未超阈值）时不触发重逢。"""
        from datetime import timedelta

        empty_result = MemorySearchResult(success=True, hits=[])
        mock_adapter.search_interaction_memory = AsyncMock(return_value=empty_result)
        trigger = MemoryDrivenTrigger(mock_adapter)
        emotion = _make_emotion_state()
        # 1 小时前交互，未超 24 小时阈值
        recent_time = datetime.now() - timedelta(hours=1)
        rels = [
            _make_relationship(target_id="b", score=300, last_interaction_at=recent_time)
        ]
        evaluation = await trigger.evaluate("a", emotion, rels)
        # check_reunion 返回 0.0 < 0.3 不触发
        assert evaluation.should_trigger is False

    async def test_error_escalation_port_called_on_failure(self, mock_adapter):
        """记忆检索异常且 error_escalation_port 已注册时调用 port.report。"""
        from src.core.error_escalation_port_registry import (
            reset_error_escalation_port,
            set_error_escalation_port,
        )

        mock_port = MagicMock()
        set_error_escalation_port(mock_port)
        try:
            mock_adapter.search_interaction_memory = AsyncMock(
                side_effect=RuntimeError("检索失败")
            )
            trigger = MemoryDrivenTrigger(mock_adapter)
            emotion = _make_emotion_state()
            rels = [_make_relationship(target_id="b", score=300)]
            await trigger.evaluate("a", emotion, rels)
            # 验证 port.report 被调用
            assert mock_port.report.called
        finally:
            reset_error_escalation_port()

    def test_allow_recall_evicts_expired_timestamps(self, mock_adapter):
        """_allow_recall 清除过期时间戳（popleft 路径）。"""
        import time as time_module

        trigger = MemoryDrivenTrigger(mock_adapter, recall_rate_limit_rpm=2)
        # 手动注入一个过期时间戳（2 分钟前）
        trigger._recall_timestamps.append(time_module.time() - 120.0)
        # 调用 _allow_recall，过期时间戳应被清除，返回 True
        assert trigger._allow_recall() is True
        # 过期时间戳已被 popleft 清除，只剩刚添加的 1 个
        assert len(trigger._recall_timestamps) == 1


# ── TriggerRegistry 测试 ─────────────────────────────────


class TriggerRegistryTest:
    """TriggerRegistry 触发器注册表测试。"""

    def test_register_and_get(self):
        """注册后可按类型获取同一实例。"""
        registry = TriggerRegistry()
        trigger = EmotionDrivenTrigger()
        registry.register("emotion_driven", trigger)
        assert registry.get("emotion_driven") is trigger

    def test_get_nonexistent_returns_none(self):
        """获取未注册的类型返回 None。"""
        registry = TriggerRegistry()
        assert registry.get("nonexistent") is None

    def test_list_types_empty(self):
        """空注册表 list_types 返回空列表。"""
        registry = TriggerRegistry()
        assert registry.list_types() == []

    def test_list_types(self):
        """list_types 返回所有已注册类型。"""
        registry = TriggerRegistry()
        registry.register("emotion_driven", EmotionDrivenTrigger())
        registry.register("time_awareness", TimeAwarenessTrigger())
        assert set(registry.list_types()) == {"emotion_driven", "time_awareness"}

    def test_all_triggers(self):
        """all_triggers 返回所有 (类型, 触发器) 元组。"""
        registry = TriggerRegistry()
        t1 = EmotionDrivenTrigger()
        t2 = TimeAwarenessTrigger()
        registry.register("emotion_driven", t1)
        registry.register("time_awareness", t2)
        pairs = registry.all_triggers()
        assert len(pairs) == 2
        assert ("emotion_driven", t1) in pairs
        assert ("time_awareness", t2) in pairs

    def test_register_overwrite(self):
        """重复注册同类型覆盖旧实例。"""
        registry = TriggerRegistry()
        t1 = EmotionDrivenTrigger()
        t2 = EmotionDrivenTrigger()
        registry.register("emotion_driven", t1)
        registry.register("emotion_driven", t2)
        assert registry.get("emotion_driven") is t2

    def test_registry_with_six_triggers(self):
        """注册全部 6 个触发器（模拟 bootstrap.py 生产装配路径）。"""
        registry = TriggerRegistry()
        registry.register("emotion_driven", EmotionDrivenTrigger())
        registry.register("time_awareness", TimeAwarenessTrigger())
        registry.register("mention_propagation", MentionPropagationTrigger())
        registry.register("event_ripple", EventRippleTrigger())
        registry.register("inner_need", InnerNeedTrigger())
        # MemoryDrivenTrigger 需要 memory_adapter 参数
        mock_adapter = MagicMock()
        registry.register("memory_driven", MemoryDrivenTrigger(mock_adapter))
        assert set(registry.list_types()) == {
            "emotion_driven",
            "time_awareness",
            "mention_propagation",
            "event_ripple",
            "inner_need",
            "memory_driven",
        }
        for trigger_type in registry.list_types():
            trigger = registry.get(trigger_type)
            assert isinstance(trigger, BaseTrigger)