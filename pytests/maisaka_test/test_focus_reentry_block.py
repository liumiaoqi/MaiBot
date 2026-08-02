from types import SimpleNamespace

import pytest

import src.maisaka.focus.manager as focus_manager_module
import src.maisaka.focus.runtime_mixin as focus_runtime_mixin_module
import src.maisaka.runtime as maisaka_runtime_module
from src.maisaka.focus.manager import FocusModeManager
from src.maisaka.runtime import MaisakaHeartFlowChatting


@pytest.fixture
def focus_manager() -> FocusModeManager:
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )

    app_config_port = SimpleNamespace(
        get_experimental_focus_mode=lambda: True,
        get_experimental_focus_on_private=lambda: True,
        get_experimental_focus_chat_whitelist=lambda: [],
        get_experimental_focus_groups=lambda: [],
        get_experimental_focus_cool_time=lambda: 120.0,
    )
    set_app_config_port(app_config_port)
    yield FocusModeManager()
    reset_app_config_port()


@pytest.fixture
def gate_focus_manager(focus_manager, monkeypatch) -> FocusModeManager:
    monkeypatch.setattr(maisaka_runtime_module, "focus_mode_manager", focus_manager)
    monkeypatch.setattr(focus_runtime_mixin_module, "focus_mode_manager", focus_manager)
    return focus_manager


def _build_gate_runtime(session_id: str = "group-a") -> MaisakaHeartFlowChatting:
    runtime = MaisakaHeartFlowChatting.__new__(MaisakaHeartFlowChatting)
    runtime.session_id = session_id
    runtime._session_info = SimpleNamespace(is_group_session=True)
    runtime.log_prefix = "[test]"
    runtime._maybe_schedule_focus_at_wakeup = lambda **kwargs: None
    runtime._maybe_schedule_focus_cooldown_wakeup = lambda **kwargs: None
    return runtime


def test_idle_exit_block_expires_after_focus_cool_time(focus_manager, monkeypatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(focus_manager_module, "time", SimpleNamespace(time=lambda: clock["now"]))

    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is True
    assert focus_manager.release_focus_and_block_next_entry("group-a") is True
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is False

    clock["now"] += 119.0
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is False

    clock["now"] += 1.0
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is True


def test_unblock_focus_entry_allows_blocked_session_reentry(focus_manager) -> None:
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is True
    assert focus_manager.release_focus_and_block_next_entry("group-a") is True
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is False

    assert focus_manager.unblock_focus_entry("group-a") is True
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is True


def test_unblock_focus_entry_ignores_other_sessions(focus_manager) -> None:
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is True
    assert focus_manager.release_focus_and_block_next_entry("group-a") is True

    assert focus_manager.unblock_focus_entry("group-b") is False
    assert focus_manager.try_enter_focus("group-a", is_group_chat=True) is False


def test_focus_gate_drops_plain_message_while_blocked(gate_focus_manager) -> None:
    assert gate_focus_manager.try_enter_focus("group-a", is_group_chat=True) is True
    assert gate_focus_manager.release_focus_and_block_next_entry("group-a") is True

    runtime = _build_gate_runtime()
    plain_message = SimpleNamespace(is_at=False, message_id="msg-1")

    assert MaisakaHeartFlowChatting._should_continue_after_focus_gate(runtime, plain_message) is False
    assert gate_focus_manager.is_in_focus_set("group-a") is False


def test_focus_gate_allows_at_message_from_blocked_session(gate_focus_manager) -> None:
    assert gate_focus_manager.try_enter_focus("group-a", is_group_chat=True) is True
    assert gate_focus_manager.release_focus_and_block_next_entry("group-a") is True

    runtime = _build_gate_runtime()
    at_message = SimpleNamespace(is_at=True, message_id="msg-2")

    assert MaisakaHeartFlowChatting._should_continue_after_focus_gate(runtime, at_message) is True
    assert gate_focus_manager.is_in_focus_set("group-a") is True
