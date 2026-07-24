"""GlobalConfigAppConfigPort — 从 global_config 各域读取应用配置。"""

from __future__ import annotations

from typing import Any

from src.core.types import AgentAutonomySnapshot, AgentInteractionSnapshot, AMemorixIntegrationSnapshot


class GlobalConfigAppConfigPort:
    """聚合 expression/emoji/experimental/visual/debug/agent_autonomy/a_memorix/mcp/response_splitter/chinese_typo/response_post_process/log/webui/agent/agent_interaction 域配置。"""

    def _get_cfg(self):
        from src.config.config import global_config
        return global_config

    def get_expression_learning_list(self) -> list[str]:
        return list(self._get_cfg().expression.expression_learning_list)

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

    def get_emoji_send_num(self) -> int:
        return self._get_cfg().emoji.emoji_send_num

    def get_experimental_behavior_learning_list(self) -> list[str]:
        return list(self._get_cfg().experimental.behavior_learning_list)

    def get_experimental_enable_rich_reply(self) -> bool:
        return self._get_cfg().experimental.enable_rich_reply


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


    def get_debug_enable_reply_effect_tracking(self) -> bool:
        return self._get_cfg().debug.enable_reply_effect_tracking

    def get_debug_record_tool_structured_content(self) -> bool:
        return self._get_cfg().debug.record_tool_structured_content

    def get_debug_keep_prompt_preview_json_base64(self) -> bool:
        return self._get_cfg().debug.keep_prompt_preview_json_base64

    def get_debug_enable_llm_cache_stats(self) -> bool:
        return self._get_cfg().debug.enable_llm_cache_stats


    def get_mcp_enable(self) -> bool:
        return self._get_cfg().mcp.enable

    def get_mcp_sampling_task_name(self) -> str:
        return self._get_cfg().mcp.client.sampling.task_name

    def get_response_splitter_enable(self) -> bool:
        return self._get_cfg().response_splitter.enable

    def get_response_splitter_max_length(self) -> int:
        return self._get_cfg().response_splitter.max_length

    def get_response_splitter_max_sentence_num(self) -> int:
        return self._get_cfg().response_splitter.max_sentence_num

    def get_response_splitter_max_split_num(self) -> int:
        return self._get_cfg().response_splitter.max_split_num

    def get_response_splitter_enable_kaomoji_protection(self) -> bool:
        return self._get_cfg().response_splitter.enable_kaomoji_protection

    def get_response_splitter_enable_overflow_return_all(self) -> bool:
        return self._get_cfg().response_splitter.enable_overflow_return_all

    def get_chinese_typo_enable(self) -> bool:
        return self._get_cfg().chinese_typo.enable

    def get_chinese_typo_error_rate(self) -> float:
        return self._get_cfg().chinese_typo.error_rate

    def get_chinese_typo_min_freq(self) -> int:
        return self._get_cfg().chinese_typo.min_freq

    def get_chinese_typo_tone_error_rate(self) -> float:
        return self._get_cfg().chinese_typo.tone_error_rate

    def get_chinese_typo_word_replace_rate(self) -> float:
        return self._get_cfg().chinese_typo.word_replace_rate

    def get_response_post_process_enable(self) -> bool:
        return self._get_cfg().response_post_process.enable_response_post_process

    def get_response_post_process_typing_speed(self) -> float:
        return self._get_cfg().response_post_process.typing_speed

    def get_log_maisaka_prompt_preview_limit(self) -> int:
        return self._get_cfg().log.maisaka_prompt_preview_limit

    def get_log_maisaka_reply_effect_limit(self) -> int:
        return self._get_cfg().log.maisaka_reply_effect_limit

    def get_webui_host(self) -> str:
        return self._get_cfg().webui.host

    def get_webui_port(self) -> int:
        return self._get_cfg().webui.port

    def get_default_agent_id(self) -> str:
        return self._get_cfg().agent.default_agent_id

    def get_agents_dir(self) -> str:
        return self._get_cfg().agent.agents_dir

    def get_agent_autonomy_config(self) -> AgentAutonomySnapshot:
        aa = self._get_cfg().agent_autonomy
        return AgentAutonomySnapshot(
            enabled=aa.enabled,
            max_active_agents=aa.max_active_agents,
            auto_exit_timeout_minutes=aa.auto_exit_timeout_minutes,
            interjection_enabled=aa.interjection_enabled,
            interjection_intent_threshold=aa.interjection_intent_threshold,
            interjection_cooldown_minutes=aa.interjection_cooldown_minutes,
            max_interjections_per_hour=aa.max_interjections_per_hour,
            max_interjections_per_session_per_hour=aa.max_interjections_per_session_per_hour,
            interaction_signal_intent_bonus=aa.interaction_signal_intent_bonus,
            embodied_planner_enabled=aa.embodied_planner_enabled,
            speaker_tag_format=aa.speaker_tag_format,
            orchestrator_strategy=aa.orchestrator_strategy,
            intent_expiry_seconds=aa.intent_expiry_seconds,
            vitality_base_value=aa.vitality_base_value,
            vitality_activation_threshold=aa.vitality_activation_threshold,
            vitality_decay_per_minute=aa.vitality_decay_per_minute,
            vitality_stimulus_message=aa.vitality_stimulus_message,
            vitality_stimulus_mention=aa.vitality_stimulus_mention,
            vitality_stimulus_topic=aa.vitality_stimulus_topic,
            vitality_tick_interval_seconds=aa.vitality_tick_interval_seconds,
            fallback_exit_timeout_minutes=aa.fallback_exit_timeout_minutes,
            cohabitation_threshold_reduction=aa.cohabitation_threshold_reduction,
            cohabitation_cooldown_reduction_minutes=aa.cohabitation_cooldown_reduction_minutes,
            interjection_threshold_minimum=aa.interjection_threshold_minimum,
            interjection_cooldown_minimum_minutes=aa.interjection_cooldown_minimum_minutes,
            active_visible_to_active=aa.active_visible_to_active,
            standby_visible_to_active=aa.standby_visible_to_active,
            standby_emotion_visible_to_active=aa.standby_emotion_visible_to_active,
            dormant_visible_to_any=aa.dormant_visible_to_any,
            state_awareness_enabled=aa.state_awareness_enabled,

        )

    def get_a_memorix_integration_config(self) -> AMemorixIntegrationSnapshot:
        ami = self._get_cfg().a_memorix.integration
        return AMemorixIntegrationSnapshot(
            person_fact_writeback_enabled=ami.person_fact_writeback_enabled,
            chat_summary_writeback_enabled=ami.chat_summary_writeback_enabled,
            chat_summary_writeback_message_threshold=ami.chat_summary_writeback_message_threshold,
            chat_summary_writeback_context_length=ami.chat_summary_writeback_context_length,
            enable_memory_query_tool=ami.enable_memory_query_tool,
            enable_person_profile_query_tool=ami.enable_person_profile_query_tool,
            memory_query_default_limit=ami.memory_query_default_limit,
            enable_person_profile_injection=ami.enable_person_profile_injection,
            person_profile_injection_max_profiles=ami.person_profile_injection_max_profiles,
            heuristic_memory_recall_enabled=ami.heuristic_memory_recall_enabled,
            heuristic_memory_recall_window_size=ami.heuristic_memory_recall_window_size,
            heuristic_memory_recall_cache_ttl_seconds=ami.heuristic_memory_recall_cache_ttl_seconds,
            heuristic_memory_recall_min_interval_seconds=ami.heuristic_memory_recall_min_interval_seconds,
            heuristic_memory_recall_min_new_messages=ami.heuristic_memory_recall_min_new_messages,
            heuristic_memory_recall_limit=ami.heuristic_memory_recall_limit,
            heuristic_memory_recall_max_chars=ami.heuristic_memory_recall_max_chars,
            heuristic_memory_cross_chat_enabled=ami.heuristic_memory_cross_chat_enabled,
            heuristic_memory_group_to_private_enabled=ami.heuristic_memory_group_to_private_enabled,
            heuristic_memory_private_to_group_enabled=ami.heuristic_memory_private_to_group_enabled,
        )

    def get_agent_interaction_config(self) -> AgentInteractionSnapshot:
        ai = self._get_cfg().agent_interaction
        return AgentInteractionSnapshot(
            enabled=ai.enabled,
            evaluation_interval_seconds=ai.evaluation_interval_seconds,
            cooldown_minutes=ai.cooldown_minutes,
            max_interactions_per_hour=ai.max_interactions_per_hour,
            max_interactions_per_day=ai.max_interactions_per_day,
            echo_enabled=ai.echo_enabled,
            echo_max_depth=ai.echo_max_depth,
            echo_decay_ratio=ai.echo_decay_ratio,
            monologue_enabled=ai.monologue_enabled,
            monologue_min_interval_minutes=ai.monologue_min_interval_minutes,
            monologue_idle_threshold_minutes=ai.monologue_idle_threshold_minutes,
            monologue_emotion_intensity_threshold=ai.monologue_emotion_intensity_threshold,
        )

    def get_log_llm_request_snapshot_limit(self) -> int:
        return int(self._get_cfg().log.llm_request_snapshot_limit or 0)

    def get_voice_enable_asr(self) -> bool:
        return bool(self._get_cfg().voice.enable_asr)

    def get_maim_message_enable_api_server(self) -> bool:
        return bool(self._get_cfg().maim_message.enable_api_server)

    def get_plugin_runtime_hook_blocking_timeout_sec(self) -> float:
        return float(self._get_cfg().plugin_runtime.hook_blocking_timeout_sec or 60.0)

    def get_telemetry_enable(self) -> bool:
        return bool(self._get_cfg().telemetry.enable)

    def get_message_receive_ban_words(self) -> list[str]:
        return list(self._get_cfg().message_receive.ban_words or [])

    def get_message_receive_ban_msgs_regex(self) -> list[str]:
        return list(self._get_cfg().message_receive.ban_msgs_regex or [])

    def get_a_memorix_shared_memory_groups(self) -> list[str]:
        return list(getattr(self._get_cfg().a_memorix, "shared_memory_groups", []) or [])

    def get_visual_handle_oversized_images(self) -> bool:
        return bool(self._get_cfg().visual.handle_oversized_images)

    def get_visual_max_image_size_mb(self) -> float:
        return float(self._get_cfg().visual.max_image_size_mb or 0.0)

    def get_visual_oversized_image_handle_method(self) -> str:
        return str(self._get_cfg().visual.oversized_image_handle_method or "compress")

    def get_visual_planner_mode(self) -> str:
        return str(self._get_cfg().visual.planner_mode or "text")

    def get_visual_image_cache_cleanup_enabled(self) -> bool:
        try:
            return bool(self._get_cfg().visual.image_cache_cleanup.enabled)
        except Exception:
            return False

    def get_emoji_cache_cleanup_enabled(self) -> bool:
        try:
            return bool(self._get_cfg().emoji.cache_cleanup.enabled)
        except Exception:
            return False

    def get_experimental_focus_mode(self) -> bool:
        return bool(self._get_cfg().experimental.focus_mode)

    def get_experimental_focus_on_private(self) -> bool:
        return bool(self._get_cfg().experimental.focus_on_private)

    def get_experimental_focus_chat_whitelist(self) -> list[str]:
        return list(self._get_cfg().experimental.focus_chat_whitelist or [])

    def get_experimental_focus_cool_time(self) -> float:
        return max(1.0, float(self._get_cfg().experimental.focus_cool_time or 60.0))

    def get_experimental_focus_groups(self) -> list[str]:
        return list(self._get_cfg().experimental.focus_groups or [])

    def get_chat_mid_term_memory(self) -> bool:
        return bool(self._get_cfg().chat.mid_term_memory)

    def get_expression_max_expression_learner(self) -> int:
        return int(self._get_cfg().expression.max_expression_learner or 0)

    def get_expression_self_reflect(self) -> bool:
        return bool(self._get_cfg().expression.expression_self_reflect)

    def get_expression_selection_mode(self) -> str:
        return str(self._get_cfg().expression.expression_selection_mode or "random")

    def get_expression_vector_index_path(self) -> str:
        return str(self._get_cfg().expression.expression_vector_index_path or "")

    def get_expression_groups(self) -> list[Any]:
        return list(self._get_cfg().expression.expression_groups or [])

    def get_webui_enforce_public_outbound_url(self) -> bool:
        return bool(self._get_cfg().webui.enforce_public_outbound_url)

    def get_webui_anti_crawler_mode(self) -> str:
        return str(self._get_cfg().webui.anti_crawler_mode or "off")

    def get_webui_allowed_ips(self) -> str:
        return str(self._get_cfg().webui.allowed_ips or "")

    def get_webui_trusted_proxies(self) -> str:
        return str(self._get_cfg().webui.trusted_proxies or "")

    def get_webui_trust_xff(self) -> bool:
        return bool(self._get_cfg().webui.trust_xff)

    def get_webui_secure_cookie(self) -> bool:
        return bool(self._get_cfg().webui.secure_cookie)

    def get_webui_mode(self) -> str:
        return str(self._get_cfg().webui.mode or "development")

