from src.maisaka.reasoning_engine import MaisakaReasoningEngine


def test_continue_action_closes_timing_gate_for_following_rounds() -> None:
    assert MaisakaReasoningEngine._mark_timing_gate_completed("continue") is False


def test_non_continue_actions_require_next_timing_gate() -> None:
    assert MaisakaReasoningEngine._mark_timing_gate_completed("wait") is True
    assert MaisakaReasoningEngine._mark_timing_gate_completed("no_reply") is True
