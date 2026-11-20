"""butler_closure 数据契约与补回合判定的纯函数单测。"""

import dataclasses

import pytest

from src.maisaka.agent_autonomy.butler_closure import (
    BudgetDecision,
    ButlerClosureConfig,
    OpeningDraft,
    PresentAgent,
    SceneSnapshot,
    SummonRequest,
)
from src.maisaka.agent_autonomy.closure_signal import ClosureSignal, detect_closure_signal


class TestDetectClosureSignal:
    """detect_closure_signal 的 R1-R4 判定。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("今天要不要一起吃饭？", ClosureSignal.QUESTION_MARK),
            ("what?", ClosureSignal.QUESTION_MARK),
            ("那我们去看看呢", ClosureSignal.TAG_PARTICLE),
            ("就这样吧", ClosureSignal.TAG_PARTICLE),
            ("你觉得我们应该怎么办…", ClosureSignal.ELLIPSIS_PROMPT),
            ("要不要一起~", ClosureSignal.ELLIPSIS_PROMPT),
        ],
    )
    def test_positive_signals(self, text, expected):
        assert detect_closure_signal(text) is expected

    @pytest.mark.parametrize(
        "text",
        [
            "我知道为什么",
            "你怎么看",
            "我先睡了…",
            "今天天气不错。",
            "",
            "   ",
        ],
    )
    def test_negative_signals(self, text):
        assert detect_closure_signal(text) is ClosureSignal.NONE

    def test_is_deterministic(self):
        text = "你觉得我们应该怎么办…"
        results = {detect_closure_signal(text) for _ in range(3)}
        assert results == {ClosureSignal.ELLIPSIS_PROMPT}


class TestOpeningDraftJudge:
    """OpeningDraft.judge_prompt 的唯一入口校验。"""

    present = (PresentAgent(agent_id="a1", display_name="银狼"),)

    @pytest.mark.parametrize("raw", ["", "   ", "NONE", " none "])
    def test_empty_or_none_rejected(self, raw):
        draft = OpeningDraft.judge_prompt(
            raw,
            present=self.present,
            user_text="今天好累",
            max_chars=120,
        )
        assert draft.ok is False
        assert draft.reject_reason == "empty"

    def test_truncates_at_sentence_end(self):
        draft = OpeningDraft.judge_prompt(
            "第一句。第二句。" * 30,
            present=self.present,
            user_text="今天好累",
            max_chars=20,
        )
        assert draft.ok is True
        assert draft.chars <= 20
        assert draft.text.endswith("。")
        assert draft.chars == len(draft.text)

    def test_rejects_untruncatable_text(self):
        draft = OpeningDraft.judge_prompt(
            "啊" * 60,
            present=self.present,
            user_text="今天好累",
            max_chars=20,
        )
        assert draft.ok is False
        assert draft.reject_reason == "no_sentence_end"

    def test_rejects_named_target(self):
        draft = OpeningDraft.judge_prompt(
            "银狼你来说说看",
            present=self.present,
            user_text="今天好累",
            max_chars=120,
        )
        assert draft.ok is False
        assert draft.reject_reason == "named_target"

    def test_rejects_user_echo(self):
        draft = OpeningDraft.judge_prompt(
            "今天好累",
            present=self.present,
            user_text="今天好累",
            max_chars=120,
        )
        assert draft.ok is False
        assert draft.reject_reason == "echo_user"

    def test_accepts_scene_description(self):
        draft = OpeningDraft.judge_prompt(
            "傍晚的客厅安静着。",
            present=self.present,
            user_text="今天好累",
            max_chars=120,
        )
        assert draft.ok is True
        assert draft.reject_reason == ""


class TestDataContracts:
    """不可变契约的形状与默认值。"""

    def test_summon_request_has_no_content_field(self):
        names = {field.name for field in dataclasses.fields(SummonRequest)}
        assert names == {"target_agent_id", "reason"}

    def test_butler_closure_config_defaults(self):
        config = ButlerClosureConfig()
        assert config.opening_enabled is True
        assert config.silence_threshold_minutes == 30
        assert config.budget_limit == 2
        assert config.opening_max_chars == 120
        assert config.opening_timeout_seconds == 4.0
        assert config.closure_enabled is True

    def test_scene_snapshot_keeps_none_emotion_hint(self):
        snapshot = SceneSnapshot(now_text="周五 20:00", present=(), emotion_hint=None, missing=())
        assert snapshot.emotion_hint is None

    def test_budget_decision_is_frozen(self):
        decision = BudgetDecision(granted=True, used=1, limit=2, exhausted=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            decision.used = 2