from pathlib import Path

import json
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


def test_save_debug_planner_request_body_uses_llm_request_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(chat_loop_service_module, "DEBUG_PLANNER_CACHE_DIR", tmp_path)
    monkeypatch.setattr(chat_loop_service_module.global_config.debug, "record_planner_request", True)

    service = MaisakaChatLoopService(session_id="session/1")

    service._save_debug_planner_request_body(
        request_kind="planner",
        model_name="demo-model",
        messages=[],
        tool_definitions=[],
        response_format=None,
        selection_reason="test",
        selected_history_count=0,
        response_body={},
        final_response_body={},
    )

    snapshot_files = list(tmp_path.glob("*.json"))
    assert len(snapshot_files) == 1
    payload = json.loads(snapshot_files[0].read_text(encoding="utf-8"))
    assert payload["request_type"] == "maisaka_planner"
