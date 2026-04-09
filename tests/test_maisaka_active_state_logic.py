from src.maisaka.reasoning_engine import MaisakaReasoningEngine


def test_retry_planner_after_interrupt_only_when_has_new_messages_and_more_rounds() -> None:
    assert MaisakaReasoningEngine._should_retry_planner_after_interrupt(
        round_index=0,
        max_internal_rounds=6,
        has_pending_messages=True,
    )


def test_do_not_retry_planner_after_interrupt_without_pending_messages() -> None:
    assert not MaisakaReasoningEngine._should_retry_planner_after_interrupt(
        round_index=0,
        max_internal_rounds=6,
        has_pending_messages=False,
    )


def test_do_not_retry_planner_after_interrupt_on_last_round() -> None:
    assert not MaisakaReasoningEngine._should_retry_planner_after_interrupt(
        round_index=5,
        max_internal_rounds=6,
        has_pending_messages=True,
    )
