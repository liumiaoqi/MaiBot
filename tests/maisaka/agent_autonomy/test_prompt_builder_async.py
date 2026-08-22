"""prompt_builder 异步重构测试（T3.1/T3.6）。

验证 _build_agent_interaction_memory 在事件循环运行时返回真实交互记忆，
不再因 loop.is_running() 直接返回空字符串（P0-A12b-1 修复）。
"""


from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder


class TestBuildAgentInteractionMemoryAsync:
    """_build_agent_interaction_memory 异步行为测试。"""

    async def test_returns_nonempty_when_event_loop_running(self):
        """事件循环运行时，返回非空交互记忆（P0 修复核心验证）。"""
        rel = MagicMock()
        rel.target_agent_id = "agent_b"
        agent_config = MagicMock()
        agent_config.internal_relationships = [rel]

        profile = MagicMock()
        profile.to_prompt_text.return_value = "最近一起讨论了项目方案"

        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(return_value=profile)

        with patch(
            "src.maisaka.agent_interaction.memory.profile.AgentProfileService",
            return_value=mock_service,
        ), patch(
            "src.maisaka.agent_interaction.memory.adapter.AgentMemoryAdapter",
        ), patch(
            "src.maisaka.agent_interaction.event_store.InteractionEventStore",
        ), patch(
            "src.core.adapters.get_memory_service_port",
            return_value=MagicMock(),
        ):
            result = await EmbodiedPlannerPromptBuilder._build_agent_interaction_memory(
                "agent_a", agent_config
            )

        assert result != ""
        assert "最近的交互动态" in result
        assert "agent_b" in result

    async def test_returns_empty_when_no_relationships(self):
        """无内部关系时返回空字符串。"""
        agent_config = MagicMock()
        agent_config.internal_relationships = []

        result = await EmbodiedPlannerPromptBuilder._build_agent_interaction_memory(
            "agent_a", agent_config
        )

        assert result == ""

    async def test_returns_empty_when_all_profiles_empty(self):
        """所有 profile.to_prompt_text() 返回空时，最终返回空字符串。"""
        rel = MagicMock()
        rel.target_agent_id = "agent_b"
        agent_config = MagicMock()
        agent_config.internal_relationships = [rel]

        profile = MagicMock()
        profile.to_prompt_text.return_value = ""

        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(return_value=profile)

        with patch(
            "src.maisaka.agent_interaction.memory.profile.AgentProfileService",
            return_value=mock_service,
        ), patch(
            "src.maisaka.agent_interaction.memory.adapter.AgentMemoryAdapter",
        ), patch(
            "src.maisaka.agent_interaction.event_store.InteractionEventStore",
        ), patch(
            "src.core.adapters.get_memory_service_port",
            return_value=MagicMock(),
        ):
            result = await EmbodiedPlannerPromptBuilder._build_agent_interaction_memory(
                "agent_a", agent_config
            )

        assert result == ""

    async def test_multiple_relationships_aggregated(self):
        """多个内部关系时，聚合所有非空 profile 文本。"""
        rel1 = MagicMock()
        rel1.target_agent_id = "agent_b"
        rel2 = MagicMock()
        rel2.target_agent_id = "agent_c"
        agent_config = MagicMock()
        agent_config.internal_relationships = [rel1, rel2]

        profile1 = MagicMock()
        profile1.to_prompt_text.return_value = "关系良好"
        profile2 = MagicMock()
        profile2.to_prompt_text.return_value = "最近有分歧"

        mock_service = MagicMock()
        mock_service.get_profile = AsyncMock(side_effect=[profile1, profile2])

        with patch(
            "src.maisaka.agent_interaction.memory.profile.AgentProfileService",
            return_value=mock_service,
        ), patch(
            "src.maisaka.agent_interaction.memory.adapter.AgentMemoryAdapter",
        ), patch(
            "src.maisaka.agent_interaction.event_store.InteractionEventStore",
        ), patch(
            "src.core.adapters.get_memory_service_port",
            return_value=MagicMock(),
        ):
            result = await EmbodiedPlannerPromptBuilder._build_agent_interaction_memory(
                "agent_a", agent_config
            )

        assert "agent_b" in result
        assert "agent_c" in result
        assert "关系良好" in result
        assert "最近有分歧" in result


class TestBuildSystemPromptAsync:
    """build_system_prompt 异步行为测试。"""

    async def test_build_system_prompt_is_coroutine(self):
        """build_system_prompt 是 async 方法（返回协程而非字符串）。"""
        import inspect

        assert inspect.iscoroutinefunction(EmbodiedPlannerPromptBuilder.build_system_prompt)

    async def test_build_embodied_context_is_coroutine(self):
        """_build_embodied_context 是 async 方法。"""
        import inspect

        assert inspect.iscoroutinefunction(EmbodiedPlannerPromptBuilder._build_embodied_context)

    async def test_build_agent_interaction_memory_is_coroutine(self):
        """_build_agent_interaction_memory 是 async 方法。"""
        import inspect

        assert inspect.iscoroutinefunction(EmbodiedPlannerPromptBuilder._build_agent_interaction_memory)
