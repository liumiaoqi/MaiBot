from src.maisaka.builtin_tool import get_action_tool_specs, get_timing_tool_specs


def test_wait_tool_available_in_timing_stage() -> None:
    tool_names = {tool_spec.name for tool_spec in get_timing_tool_specs()}

    assert "wait" in tool_names


def test_wait_tool_not_available_in_action_stage() -> None:
    tool_names = {tool_spec.name for tool_spec in get_action_tool_specs()}

    assert "wait" not in tool_names
    assert "finish" in tool_names
    assert "tool_search" in tool_names


def test_tool_search_not_available_in_timing_stage() -> None:
    tool_names = {tool_spec.name for tool_spec in get_timing_tool_specs()}

    assert "tool_search" not in tool_names
