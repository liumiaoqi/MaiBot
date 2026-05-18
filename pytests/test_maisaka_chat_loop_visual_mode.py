import pytest

from src.maisaka import chat_loop_service as chat_loop_service_module
from src.maisaka.chat_loop_service import MaisakaChatLoopService


def test_expression_selector_uses_text_context() -> None:
    assert MaisakaChatLoopService._resolve_enable_visual_message("expression_selector") is False


def test_reply_effect_judge_uses_text_context() -> None:
    assert MaisakaChatLoopService._resolve_enable_visual_message("reply_effect_judge") is False


@pytest.mark.parametrize("request_kind", ["planner", "timing_gate"])
def test_planner_requests_follow_planner_visual_mode(
    monkeypatch: pytest.MonkeyPatch,
    request_kind: str,
) -> None:
    monkeypatch.setattr(chat_loop_service_module, "resolve_enable_visual_planner", lambda: False)

    assert MaisakaChatLoopService._resolve_enable_visual_message(request_kind) is False


def test_visual_sub_agent_requests_keep_visual_context() -> None:
    assert MaisakaChatLoopService._resolve_enable_visual_message("emotion") is True
