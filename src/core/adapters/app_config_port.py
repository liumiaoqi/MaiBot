"""GlobalConfigAppConfigPort — 从 global_config 各域读取应用配置。"""

from __future__ import annotations

from src.core.types import AgentAutonomySnapshot, AMemorixIntegrationSnapshot


class GlobalConfigAppConfigPort:
    """聚合 expression/emoji/experimental/visual/debug/agent_autonomy/a_memorix 域配置。"""

    def _get_cfg(self):
        from src.config.config import global_config
        return global_config

    def get_expression_selection_mode(self) -> str:
        return self._get_cfg().expression.expression_selection_mode

    def get_expression_learning_list(self) -> list[str]:
        return list(self._get_cfg().expression.expression_learning_list)

    def get_expression_self_reflect(self) -> bool:
        return self._get_cfg().expression.self_reflect

    def get_expression_groups(self) -> list[str]:
        return list(self._get_cfg().expression.expression_groups)

    def get_max_expression_learner(self) -> int:
        return self._get_cfg().expression.max_expression_learner

    def get_expression_vector_index_path(self) -> str:
        return self._get_cfg().expression.expression_vector_index_path

    def get_expression_checked_only(self) -> bool:
        return self._get_cfg().expression.expression_checked_only

    def get_expression_vector_candidate_pool_size(self) -> int:
        return self._get_cfg().expression.expression_vector_candidate_pool_size

    def get_emoji_max_reg_num(self) -> int:
        return self._get_cfg().emoji.max_reg_num

    def get_emoji_max_size_mb(self) -> float:
        return self._get_cfg().emoji.max_size_mb

    def get_emoji_do_replace(self) -> bool:
        return self._get_cfg().emoji.do_replace

    def get_experimental_behavior_learning_list(self) -> list[str]:
        return list(self._get_cfg().experimental.behavior_learning_list)

    def get_experimental_enable_rich_reply(self) -> bool:
        return self._get_cfg().experimental.enable_rich_reply

    def get_experimental_focus_mode(self) -> bool:
        return self._get_cfg().experimental.focus_mode

    def get_experimental_enable_behavior_learning(self) -> bool:
        return self._get_cfg().experimental.enable_behavior_learning

    def get_visual_max_image_num(self) -> int:
        return self._get_cfg().visual.max_image_num

    def get_visual_replyer_mode(self) -> str:
        return self._get_cfg().visual.replyer_mode

    def get_debug_show_maisaka_thinking(self) -> bool:
        return self._get_cfg().debug.show_maisaka_thinking

    def get_debug_show_jargon_prompt(self) -> bool:
        return self._get_cfg().debug.show_jargon_prompt

    def get_agent_autonomy_config(self) -> AgentAutonomySnapshot:
        aa = self._get_cfg().agent_autonomy
        return AgentAutonomySnapshot(
            orchestrator_strategy=aa.orchestrator_strategy,
            max_concurrent_interjections=aa.max_concurrent_interjections,
            interjection_cooldown_seconds=aa.interjection_cooldown_seconds,
            vitality_decay_rate=aa.vitality_decay_rate,
            vitality_recovery_rate=aa.vitality_recovery_rate,
            standby_threshold=aa.standby_threshold,
            active_threshold=aa.active_threshold,
        )

    def get_a_memorix_integration_config(self) -> AMemorixIntegrationSnapshot:
        ami = self._get_cfg().a_memorix.integration
        return AMemorixIntegrationSnapshot(
            person_fact_writeback_enabled=ami.person_fact_writeback_enabled,
            chat_summary_writeback_enabled=ami.chat_summary_writeback_enabled,
            chat_summary_writeback_message_threshold=ami.chat_summary_writeback_message_threshold,
            chat_summary_writeback_context_length=ami.chat_summary_writeback_context_length,
        )
