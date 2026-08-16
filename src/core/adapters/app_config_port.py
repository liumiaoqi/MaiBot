"""GlobalConfigAppConfigPort — 从 global_config 各域读取应用配置。"""


from typing import Any, Optional

from src.core.types import AgentAutonomySnapshot, AgentInteractionSnapshot, AMemorixIntegrationSnapshot
from src.core.types import CacheCleanupConfig, MaimMessageConfigSnapshot, PluginRuntimeRenderSnapshot, PluginRuntimeSnapshot
from src.core.watchdog.config import WatchdogConfig


from src.common.logger import get_logger
logger = get_logger("core.adapters.app_config_port")

class GlobalConfigAppConfigPort:
    """聚合 expression/emoji/experimental/visual/debug/agent_autonomy/a_memorix/mcp/response_splitter/chinese_typo/response_post_process/log/webui/agent/agent_interaction/plugin_runtime 域配置。"""

    def _get_cfg(self):
        from src.config.config import global_config
        return global_config

    def get_expression_learning_list(self) -> list[str]:
        return list(self._get_cfg().expression.learning_list)

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

    def get_emoji_check_interval(self) -> int:
        return int(self._get_cfg().emoji.check_interval)

    def get_emoji_steal_emoji(self) -> bool:
        return bool(self._get_cfg().emoji.steal_emoji)

    def get_emoji_content_filtration(self) -> bool:
        return bool(self._get_cfg().emoji.content_filtration)

    def get_emoji_send_num(self) -> int:
        return self._get_cfg().emoji.emoji_send_num

    def get_experimental_enable_rich_reply(self) -> bool:
        return self._get_cfg().experimental.enable_rich_reply


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
            # ZG-23a: 出站去重 + 发言节流配置
            outbound_dedup_window_seconds=aa.outbound_dedup_window_seconds,
            outbound_dedup_max_entries=aa.outbound_dedup_max_entries,
            mention_chain_decay_base=aa.mention_chain_decay_base,
            mention_chain_max_depth=aa.mention_chain_max_depth,
            cohabitation_decay_factor=aa.cohabitation_decay_factor,
            cohabitation_min_max=aa.cohabitation_min_max,

        )

    def get_a_memorix_full_config(self) -> dict:
        """获取完整 a_memorix 配置字典（含 storage/embedding/retrieval 等全字段）。

        ZG-10 记忆检索回归修复：integration 快照缺 storage 字段导致 kernel
        data_dir 回落默认 ./data——恢复完整配置读取。
        """
        return self._get_cfg().a_memorix.model_dump()

    def get_a_memorix_integration_config(self) -> AMemorixIntegrationSnapshot:
        ami = self._get_cfg().a_memorix.integration
        return AMemorixIntegrationSnapshot(
            person_fact_writeback_enabled=ami.person_fact_writeback_enabled,
            chat_summary_writeback_enabled=ami.chat_summary_writeback_enabled,
            chat_summary_writeback_message_threshold=ami.chat_summary_writeback_message_threshold,
            chat_summary_writeback_context_length=ami.chat_summary_writeback_context_length,
            enable_memory_query_tool=ami.enable_memory_query_tool,
            memory_query_default_limit=ami.memory_query_default_limit,
            enable_person_profile_injection=ami.enable_person_profile_injection,
            person_profile_injection_max_profiles=ami.person_profile_injection_max_profiles,
            heuristic_memory_recall_enabled=ami.heuristic_memory_recall_enabled,
            heuristic_memory_recall_window_size=ami.heuristic_memory_recall_window_size,
            heuristic_memory_recall_cache_ttl_seconds=ami.heuristic_memory_recall_cache_ttl_seconds,
            heuristic_memory_recall_min_interval_seconds=ami.heuristic_memory_recall_min_interval_seconds,
            heuristic_memory_recall_rate_limit_rpm=ami.heuristic_memory_recall_rate_limit_rpm,
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
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "读取 image_cache_cleanup.enabled 异常", exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.debug("读取 image_cache_cleanup.enabled 异常: %s", exc)
            return False

    def get_emoji_cache_cleanup_enabled(self) -> bool:
        try:
            return bool(self._get_cfg().emoji.cache_cleanup.enabled)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "读取 emoji.cache_cleanup.enabled 异常", exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.debug("读取 emoji.cache_cleanup.enabled 异常: %s", exc)
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

    def get_recall_threshold(self) -> float:
        return float(getattr(self._get_cfg().chat, "recall_threshold", 0.65))

    def get_recall_top_k(self) -> int:
        return int(getattr(self._get_cfg().chat, "recall_top_k", 3))

    def get_recall_candidate_limit(self) -> int:
        return int(getattr(self._get_cfg().chat, "recall_candidate_limit", 100))

    def get_recall_original_message_limit(self) -> int:
        return int(getattr(self._get_cfg().chat, "recall_original_message_limit", 20))

    def get_recall_original_token_limit(self) -> int:
        return int(getattr(self._get_cfg().chat, "recall_original_token_limit", 2000))

    def get_recall_timeout_ms(self) -> int:
        return int(getattr(self._get_cfg().chat, "recall_timeout_ms", 1000))

    def get_enable_ascii_image(self) -> bool:
        return bool(getattr(self._get_cfg().chat, "enable_ascii_image", False))

    def get_ascii_column_width(self) -> int:
        return int(getattr(self._get_cfg().chat, "ascii_column_width", 48))

    def get_ascii_main_color_count(self) -> int:
        return int(getattr(self._get_cfg().chat, "ascii_main_color_count", 2))

    def get_ascii_cache_max_size(self) -> int:
        return int(getattr(self._get_cfg().chat, "ascii_cache_max_size", 256))

    def get_ascii_charset(self) -> str:
        return str(getattr(self._get_cfg().chat, "ascii_charset", "@%#*+=-:."))

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

    def get_plugin_runtime_config(self) -> PluginRuntimeSnapshot:
        cfg = self._get_cfg().plugin_runtime
        return PluginRuntimeSnapshot(
            enabled=bool(cfg.enabled),
            ipc_socket_path=str(cfg.ipc_socket_path or ""),
            health_check_interval_sec=float(cfg.health_check_interval_sec),
            max_restart_attempts=int(cfg.max_restart_attempts),
            runner_spawn_timeout_sec=float(cfg.runner_spawn_timeout_sec),
            hook_blocking_timeout_sec=float(cfg.hook_blocking_timeout_sec),
        )

    def get_plugin_runtime_render_config(self) -> PluginRuntimeRenderSnapshot:
        render = self._get_cfg().plugin_runtime.render
        return PluginRuntimeRenderSnapshot(
            enabled=bool(render.enabled),
            browser_ws_endpoint=str(render.browser_ws_endpoint or ""),
            executable_path=str(render.executable_path or ""),
            browser_install_root=str(render.browser_install_root or ""),
            headless=bool(render.headless),
            concurrency_limit=int(render.concurrency_limit),
        )

    def get_watchdog_config(self) -> WatchdogConfig:

        cfg = self._get_cfg().watchdog
        return WatchdogConfig(
            touch_interval_s=float(cfg.touch_interval_s),
            check_interval_s=float(cfg.check_interval_s),
            mild_threshold_s=float(cfg.mild_threshold_s),
            severe_threshold_s=float(cfg.severe_threshold_s),
            consecutive_report_threshold=int(cfg.consecutive_report_threshold),
            cooldown_s=float(cfg.cooldown_s),
            v1_poll_interval_s=float(cfg.v1_poll_interval_s),
            v2_diff_interval_s=float(cfg.v2_diff_interval_s),
        )

    def get_control_message_global_enabled(self) -> bool:
        return bool(self._get_cfg().control_message.global_enabled)

    def get_control_message_unmaskable_whitelist(self) -> set[int]:
        return set(self._get_cfg().control_message.unmaskable_whitelist)

    def get_control_message_private_queue_limit(self) -> int:
        return int(self._get_cfg().control_message.private_queue_limit)

    def get_control_message_shared_queue_limit(self) -> int:
        return int(self._get_cfg().control_message.shared_queue_limit)

    def get_control_message_unkillable_entities(self) -> list[str]:
        return list(self._get_cfg().control_message.unkillable_entities)

    def get_control_message_system_blocked_kinds(self) -> set[int]:
        return set(self._get_cfg().control_message.system_blocked_kinds)

    def get_control_message_system_ignored_kinds(self) -> set[int]:
        return set(self._get_cfg().control_message.system_ignored_kinds)

    def get_control_message_delivery_history_limit(self) -> int:
        return int(self._get_cfg().control_message.delivery_history_limit)

    def get_control_message_diffuse_timeout_sec(self) -> float:
        return float(self._get_cfg().control_message.diffuse_timeout_sec)

    def get_control_message_force_caller_whitelist(self) -> set[str]:
        return set(self._get_cfg().control_message.force_caller_whitelist)

    def get_error_escalation_config(self) -> Optional[dict]:
        """获取错误升级梯配置域（ZG-14；字段缺失按默认，异常回退 None 全默认）。"""
        try:
            section = self._get_cfg().error_escalation
        except AttributeError:
            return None
        return {
            "error_on_warn": section.error_on_warn,
            "warn_error_threshold": section.warn_error_threshold,
            "critical_on_error": section.critical_on_error,
            "error_critical_threshold": section.error_critical_threshold,
            "critical_fatal_threshold": section.critical_fatal_threshold,
            "level_actions": section.level_actions,
            "count_window_sec": section.count_window_sec,
            "crash_dump_min_level": section.crash_dump_min_level,
            "storm_min_threshold": section.storm_min_threshold,
        }

    def get_taint_on_taint(self) -> dict[str, str]:
        """获取污染动作映射（key=标志名，value=动作；缺省仅记录，默认空 dict）。"""
        return dict(self._get_cfg().tainted_mask.on_taint)

    def get_taint_warn_limit(self) -> int:
        """获取 WARN 累计阈值（warn_count 达到后触发降级；0=禁用）。"""
        return int(self._get_cfg().tainted_mask.warn_limit)

    def get_taint_preset_mask(self) -> int:
        """获取预置位掩码（启动即置位，如测试模式预置 128）。"""
        return int(self._get_cfg().tainted_mask.preset_mask)

    def get_degrade_on_taint_mask(self) -> int:
        """获取掩码级降级触发掩码（0=禁用，默认 0）。"""
        return int(self._get_cfg().tainted_mask.degrade_on_taint_mask)

    def register_reload_callback(self, callback: object) -> None:
        from src.config.config import config_manager  # noqa: TID251 — 适配器层允许导入
        config_manager.register_reload_callback(callback)

    def unregister_reload_callback(self, callback: object) -> None:
        from src.config.config import config_manager  # noqa: TID251 — 适配器层允许导入
        config_manager.unregister_reload_callback(callback)

    def get_global_config_json(self) -> str:
        from src.config.config import config_manager  # noqa: TID251 — 适配器层允许导入
        return config_manager.get_global_config().model_dump(mode="json")

    def get_model_config_json(self) -> str:
        from src.config.config import config_manager  # noqa: TID251 — 适配器层允许导入
        return config_manager.get_model_config().model_dump(mode="json")

    def get_mmc_version(self) -> str:
        from src.config.config import MMC_VERSION
        return MMC_VERSION

    def get_emoji_cache_cleanup_config(self) -> CacheCleanupConfig:
        from src.core.types import CacheCleanupConfig
        cfg = self._get_cfg().emoji.cache_cleanup
        return CacheCleanupConfig(
            enabled=self.get_emoji_cache_cleanup_enabled(),
            check_interval_hours=float(cfg.check_interval_hours),
            emoji_file_retention_days=float(cfg.emoji_file_retention_days),
            no_file_record_retention_days=float(cfg.no_file_record_retention_days),
        )

    def get_image_cache_cleanup_config(self) -> CacheCleanupConfig:
        from src.core.types import CacheCleanupConfig
        cfg = self._get_cfg().visual.image_cache_cleanup
        return CacheCleanupConfig(
            enabled=self.get_visual_image_cache_cleanup_enabled(),
            check_interval_hours=float(cfg.check_interval_hours),
            image_file_retention_days=float(cfg.image_file_retention_days),
            no_file_result_retention_days=float(cfg.no_file_result_retention_days),
        )

    def get_maim_message_config(self) -> MaimMessageConfigSnapshot:
        from src.core.types import MaimMessageConfigSnapshot
        cfg = self._get_cfg().maim_message
        return MaimMessageConfigSnapshot(
            enable_api_server=bool(cfg.enable_api_server),
            api_server_host=str(cfg.api_server_host),
            api_server_port=int(cfg.api_server_port),
            api_server_use_wss=bool(cfg.api_server_use_wss),
            api_server_cert_file=str(cfg.api_server_cert_file),
            api_server_key_file=str(cfg.api_server_key_file),
            api_server_allowed_api_keys=tuple(cfg.api_server_allowed_api_keys),
            ws_server_host=str(cfg.ws_server_host),
            ws_server_port=int(cfg.ws_server_port),
            auth_token=tuple(cfg.auth_token),
        )

    async def reload_config(self, changed_scopes: tuple[str, ...] = ()) -> bool:
        """热重载配置，委托 config_manager。"""
        from src.config.config import config_manager  # noqa: TID251 — 适配器层允许导入
        return await config_manager.reload_config(changed_scopes=list(changed_scopes))

    def get_jargon_learning_list(self) -> list[str]:
        return list(self._get_cfg().jargon.learning_list)

    def get_jargon_groups(self) -> list[Any]:
        return list(self._get_cfg().jargon.jargon_groups)

    def get_plugin_runtime_v2_enabled(self) -> bool:
        return bool(getattr(self._get_cfg(), "plugin_runtime_v2", None) and self._get_cfg().plugin_runtime_v2.enabled)

    def get_plugin_runtime_v2_host_listen_address(self) -> str:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return str(cfg.host_listen_address) if cfg else "0.0.0.0:50051"

    def get_plugin_runtime_v2_runner_spawn_count(self) -> int:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return int(cfg.runner_spawn_count) if cfg else 0

    def get_plugin_runtime_v2_runner_spawn_timeout_sec(self) -> float:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return float(cfg.runner_spawn_timeout_sec) if cfg else 30.0

    def get_plugin_runtime_v2_health_check_interval_sec(self) -> float:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return float(cfg.health_check_interval_sec) if cfg else 60.0

    def get_plugin_runtime_v2_max_restart_attempts(self) -> int:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return int(cfg.max_restart_attempts) if cfg else 3

    def get_plugin_runtime_v2_scope_approval_file(self) -> str:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return str(cfg.scope_approval_file) if cfg else "data/scope_approvals.json"

    def get_plugin_runtime_v2_default_rpm(self) -> int:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return int(cfg.default_rpm) if cfg else 60

    # ZG16-5 scopes 强制化审计配置 getter
    def get_enable_scope_audit(self) -> bool:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return bool(cfg.enable_scope_audit) if cfg else True

    def get_audit_log_path(self) -> str:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return str(cfg.audit_log_path) if cfg else "data/plugin_runtime_v2/scope_audit.log"

    def get_audit_log_max_size_mb(self) -> int:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return int(cfg.audit_log_max_size_mb) if cfg else 10

    def get_audit_log_backup_count(self) -> int:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        return int(cfg.audit_log_backup_count) if cfg else 5

    def get_tier1_scopes(self) -> list[str]:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and cfg.tier1_scopes:
            return list(cfg.tier1_scopes)
        return [
            "system:execute:cli",
            "system:read:screenshot",
            "system:read:location",
            "account:execute:operation",
            "finance:read:qr_code",
            "network:fetch:url",
        ]

    def get_sensitive_param_names(self) -> list[str]:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and cfg.sensitive_param_names:
            return list(cfg.sensitive_param_names)
        return ["token", "password", "secret", "api_key", "apikey", "credential"]

    # ZG16-6a 插件配置管理
    def get_plugin_config_debounce_ms(self) -> int:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and getattr(cfg, "plugin_config_debounce_ms", None) is not None:
            return cfg.plugin_config_debounce_ms
        return 300

    def get_plugin_config_revision_path(self) -> str:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and getattr(cfg, "plugin_config_revision_path", None) is not None:
            return cfg.plugin_config_revision_path
        return "data/plugin_runtime_v2/plugin_config_revisions.json"

    def get_enable_plugin_config_watch(self) -> bool:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and getattr(cfg, "enable_plugin_config_watch", None) is not None:
            return cfg.enable_plugin_config_watch
        return True

    def get_enable_dump_plugin_config(self) -> bool:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and getattr(cfg, "enable_dump_plugin_config", None) is not None:
            return cfg.enable_dump_plugin_config
        return True

    def get_enable_schema_drift_detect(self) -> bool:
        cfg = getattr(self._get_cfg(), "plugin_runtime_v2", None)
        if cfg and getattr(cfg, "enable_schema_drift_detect", None) is not None:
            return cfg.enable_schema_drift_detect
        return True

    def get_plugin_override(self, plugin_id: str) -> tuple[dict, dict]:
        """读取 bot_config [plugin_override.{plugin_id}] 节。

        返回 (global_override, per_stream_overrides)。
        无该节时返回 ({}, {})。
        """
        import tomllib
        from pathlib import Path

        bot_config_path = Path("config/bot_config.toml")
        if not bot_config_path.exists():
            return {}, {}
        try:
            with open(bot_config_path, "rb") as f:
                full_config = tomllib.load(f)
        except Exception:
            return {}, {}
        override_section = full_config.get("plugin_override", {})
        plugin_section = override_section.get(plugin_id, {})
        if not plugin_section:
            return {}, {}
        per_stream = plugin_section.pop("per_stream", {})
        return plugin_section, per_stream
