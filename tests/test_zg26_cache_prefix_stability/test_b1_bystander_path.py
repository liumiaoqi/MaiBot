"""ZG-26 测试：b1 旁观者路径不受缓存前缀稳定化影响（P1-1 修复后）。

chat_loop_service.build_prompt_template_context 仅在 autonomy 关闭时调用，
此时无 injected 载体——置空会丢失信息。因此 chat_loop_service 不应用 cache_stability，
emotion/relationship/favor 始终保持原值。
"""

from unittest.mock import patch

from src.maisaka.chat_loop_service import MaisakaChatLoopService


def _make_chat_loop_service():
    """构造最小 MaisakaChatLoopService 实例。"""
    service = MaisakaChatLoopService.__new__(MaisakaChatLoopService)
    service._agent_id = ""
    service._emotion_state_text = "开心"
    service._relationship_text = "朋友"
    service._current_user_name = ""
    service._current_user_id = ""
    service._use_embodied_prompt = False
    service._session_id = "test_session"
    service._is_group_chat = False
    return service


def _run_with_patches(service, enabled):
    """在 patch 环境下运行 build_prompt_template_context。"""
    patches = [
        patch("src.maisaka.chat_loop_service.get_bot_config_port"),
        patch.object(MaisakaChatLoopService, "_build_personality_prompt", return_value="测试人设"),
        patch.object(MaisakaChatLoopService, "_build_group_chat_attention_block", return_value=""),
        patch.object(MaisakaChatLoopService, "_build_planner_idle_focus_rule", return_value=""),
        patch.object(MaisakaChatLoopService, "_build_query_memory_rule", return_value=""),
    ]
    acp_patch = patch("src.maisaka.chat_loop_service.get_app_config_port")
    acp_mock = acp_patch.start()
    acp_mock.return_value.is_cache_prefix_stability_enabled.return_value = enabled
    try:
        for p in patches:
            p.start()
        return service.build_prompt_template_context()
    finally:
        for p in patches:
            p.stop()
        acp_patch.stop()


def test_bystander_emotion_always_preserved():
    """旁观者路径 emotion 始终保持原值（无论开关状态）。"""
    service = _make_chat_loop_service()
    result = _run_with_patches(service, enabled=True)
    assert result["agent_emotion_state"] == "开心"


def test_bystander_relationship_always_preserved():
    """旁观者路径 relationship 始终保持原值。"""
    service = _make_chat_loop_service()
    result = _run_with_patches(service, enabled=True)
    assert result["agent_relationship"] == "朋友"


def test_bystander_favor_always_preserved():
    """旁观者路径 favor 始终保持原值（无 agent_id 时为空）。"""
    service = _make_chat_loop_service()
    result = _run_with_patches(service, enabled=True)
    assert result["agent_favor_injection"] == ""
