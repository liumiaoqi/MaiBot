from src.core.tooling import ToolSpec
from src.llm_models.payload_content.message import RoleType
from src.maisaka.chat_loop_service import MaisakaChatLoopService
from src.maisaka.runtime import MaisakaHeartFlowChatting


def _build_runtime_stub() -> MaisakaHeartFlowChatting:
    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime._current_action_tool_names = set()
    runtime.deferred_tool_specs_by_name = {}
    runtime.discovered_tool_names = set()
    return runtime


def test_deferred_tools_reminder_only_lists_undiscovered_tools() -> None:
    runtime = _build_runtime_stub()
    runtime.update_deferred_tool_specs(
        [
            ToolSpec(name="plugin_alpha", brief_description="alpha"),
            ToolSpec(name="plugin_beta", brief_description="beta"),
        ]
    )
    runtime.discover_deferred_tools(["plugin_alpha"])

    reminder = runtime.build_deferred_tools_reminder()

    assert "plugin_alpha" not in reminder
    assert "1. plugin_beta" in reminder
    assert "<system-reminder>" in reminder
    assert "tool_search" in reminder


def test_search_and_discover_deferred_tools() -> None:
    runtime = _build_runtime_stub()
    runtime.update_deferred_tool_specs(
        [
            ToolSpec(name="mcp__slack__send_message", brief_description="向 Slack 发送消息"),
            ToolSpec(name="mcp__github__create_issue", brief_description="在 GitHub 创建 Issue"),
        ]
    )

    matched_tool_specs = runtime.search_deferred_tool_specs("slack send", limit=5)
    newly_discovered_tool_names = runtime.discover_deferred_tools([tool_spec.name for tool_spec in matched_tool_specs])

    assert [tool_spec.name for tool_spec in matched_tool_specs] == ["mcp__slack__send_message"]
    assert newly_discovered_tool_names == ["mcp__slack__send_message"]
    assert [tool_spec.name for tool_spec in runtime.get_discovered_deferred_tool_specs()] == [
        "mcp__slack__send_message"
    ]


def test_build_request_messages_appends_injected_user_message() -> None:
    chat_loop_service = MaisakaChatLoopService(chat_system_prompt="system prompt")

    messages = chat_loop_service._build_request_messages(
        [],
        injected_user_messages=["<system-reminder>\n1. plugin_beta\n</system-reminder>"],
    )

    assert len(messages) == 2
    assert messages[0].role == RoleType.System
    assert messages[1].role == RoleType.User
    assert messages[1].content == "<system-reminder>\n1. plugin_beta\n</system-reminder>"
