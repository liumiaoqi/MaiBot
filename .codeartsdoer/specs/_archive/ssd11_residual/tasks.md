# SSD-11 编码任务：SSD-10 遗留协议化

## 批次 0：基础设施（快照类型 + Protocol 方法签名）

> 依赖：无（后续所有批次依赖本批次）

- [ ] **T0.1** 在 `src/core/types.py` 新增 5 个快照类型
  - `TalkValueRuleSnapshot`（frozen dataclass：platform/item_id/rule_type/time/value，全部有默认值）
  - `ReplyTimingSnapshot`（frozen dataclass，9 属性：reply_trigger_mode/planner_interrupt_max_consecutive_count/max_consecutive_wait_count/talk_value/private_talk_value/enable_talk_value_rules/talk_value_rules/mentioned_bot_reply/inevitable_at_reply，全部有默认值，属性注释标注 `# DEPRECATED: 将由 vitality 系统替代`）
  - `AgentInteractionSnapshot`（frozen dataclass，12 属性：enabled/evaluation_interval_seconds/cooldown_minutes/max_interactions_per_hour/max_interactions_per_day/echo_enabled/echo_max_depth/echo_decay_ratio/monologue_enabled/monologue_min_interval_minutes/monologue_idle_threshold_minutes/monologue_emotion_intensity_threshold，全部有默认值）
  - `KeywordRuleSnapshot`（frozen dataclass：keywords/regex/reaction，全部有默认值）
  - `KeywordReactionSnapshot`（frozen dataclass：keyword_rules/regex_rules，全部有默认值）
  - 更新 `__all__` 导出列表
  - 验证：`ruff check src/core/types.py` 通过
  - CC/Codex 建议：CC（快照设计需理解 frozen dataclass 兼容性 + DEPRECATED 语义，首次设计必须正确）

- [ ] **T0.2** 在 `src/core/types.py` 扩展 `AMemorixIntegrationSnapshot` 新增 15 个字段
  - 新增字段（按设计文档 D14 清单）：enable_memory_query_tool/enable_person_profile_query_tool/memory_query_default_limit/enable_person_profile_injection/person_profile_injection_max_profiles/heuristic_memory_recall_enabled/heuristic_memory_recall_window_size/heuristic_memory_recall_cache_ttl_seconds/heuristic_memory_recall_min_interval_seconds/heuristic_memory_recall_min_new_messages/heuristic_memory_recall_limit/heuristic_memory_recall_max_chars/heuristic_memory_cross_chat_enabled/heuristic_memory_group_to_private_enabled/heuristic_memory_private_to_group_enabled
  - 所有新增字段必须有默认值（frozen dataclass 兼容性）
  - 验证：`ruff check src/core/types.py` 通过
  - CC/Codex 建议：CC（需确认字段默认值与 config 定义一致）

- [ ] **T0.3** 在 `src/core/protocols.py` 扩展 `ChatConfigPort` 新增 5 个方法签名
  - `get_personality(self) -> str`
  - `get_reply_style_text(self) -> str`
  - `get_multiple_reply_style(self) -> list[str]`
  - `get_reply_timing_config(self) -> ReplyTimingSnapshot`
  - `get_keyword_reaction(self) -> KeywordReactionSnapshot`
  - 更新 docstring：移除"不含 reply_timing 待废弃属性"说明
  - 验证：`ruff check src/core/protocols.py` 通过
  - CC/Codex 建议：CC

- [ ] **T0.4** 在 `src/core/protocols.py` 扩展 `AppConfigPort` 新增 20 个方法签名
  - mcp 域（2）：`get_mcp_enable() -> bool`、`get_mcp_sampling_task_name() -> str`
  - response_splitter 域（6）：`get_response_splitter_enable/max_length/max_sentence_num/max_split_num/enable_kaomoji_protection/enable_overflow_return_all`
  - chinese_typo 域（5）：`get_chinese_typo_enable/error_rate/min_freq/tone_error_rate/word_replace_rate`
  - response_post_process 域（2）：`get_response_post_process_enable/typing_speed`
  - log 域（2）：`get_log_maisaka_prompt_preview_limit/reply_effect_limit`
  - webui 域（2）：`get_webui_host/port`
  - agent 域（2）：`get_default_agent_id/get_agents_dir`
  - agent_interaction 域（1）：`get_agent_interaction_config() -> AgentInteractionSnapshot`
  - emoji 扩展（1）：`get_emoji_send_num() -> int`
  - debug 遗漏（4）：`get_debug_enable_reply_effect_tracking/record_tool_structured_content/keep_prompt_preview_json_base64/enable_llm_cache_stats`
  - 更新 docstring：覆盖域列表
  - 验证：`ruff check src/core/protocols.py` 通过
  - CC/Codex 建议：CC

- [ ] **T0.5** 提交批次 0
  - commit message: `feat(core): SSD-11 批次0 — 快照类型(ReplyTiming/AgentInteraction/KeywordReaction)+Protocol方法签名扩展 [CC]`
  - 验证：`ruff check src/core/` 通过

## 批次 1：适配器实现

> 依赖：批次 0

- [ ] **T1.1** 在 `src/core/adapters/chat_config_port.py` 新增 5 个方法实现
  - `get_personality()` → `global_config.personality.personality`
  - `get_reply_style_text()` → `global_config.personality.reply_style`
  - `get_multiple_reply_style()` → `global_config.personality.multiple_reply_style`
  - `get_reply_timing_config()` → 构造 `ReplyTimingSnapshot`（含 DeprecationWarning 首次调用逻辑：模块级 `_reply_timing_warned = False` flag）
  - `get_keyword_reaction()` → 构造 `KeywordReactionSnapshot`（将 keyword_rules/regex_rules 列表转为 tuple[KeywordRuleSnapshot, ...]）
  - 更新类 docstring
  - 验证：`ruff check src/core/adapters/chat_config_port.py` 通过
  - CC/Codex 建议：Codex（纯参照 design.md 字段映射表机械编写）

- [ ] **T1.2** 在 `src/core/adapters/app_config_port.py` 新增 20 个方法实现
  - mcp 域：`_get_cfg().mcp.enable` / `_get_cfg().mcp.client.sampling.task_name`
  - response_splitter 域：`_get_cfg().response_splitter.*`（6 个属性）
  - chinese_typo 域：`_get_cfg().chinese_typo.*`（5 个属性）
  - response_post_process 域：`_get_cfg().response_post_process.*`（2 个属性）
  - log 域：`_get_cfg().log.maisaka_prompt_preview_limit` / `_get_cfg().log.maisaka_reply_effect_limit`
  - webui 域：`_get_cfg().webui.host` / `_get_cfg().webui.port`
  - agent 域：`_get_cfg().agent.default_agent_id` / `_get_cfg().agent.agents_dir`
  - agent_interaction 域：构造 `AgentInteractionSnapshot`（12 属性映射）
  - emoji 扩展：`_get_cfg().emoji.emoji_send_num`
  - debug 遗漏：`_get_cfg().debug.enable_reply_effect_tracking` / `_get_cfg().debug.record_tool_structured_content` / `_get_cfg().debug.keep_prompt_preview_json_base64` / `_get_cfg().debug.enable_llm_cache_stats`
  - 更新类 docstring
  - 验证：`ruff check src/core/adapters/app_config_port.py` 通过
  - CC/Codex 建议：Codex（按 design.md D4-D14 字段映射表机械编写）

- [ ] **T1.3** 扩展 `get_a_memorix_integration_config()` 适配器方法
  - 在 `src/core/adapters/app_config_port.py` 的 `get_a_memorix_integration_config()` 中新增 15 个字段映射
  - 验证：`ruff check src/core/adapters/app_config_port.py` 通过
  - CC/Codex 建议：Codex（需确认 AMemorixIntegrationConfig 实际属性名，按 design.md D14 清单）

- [ ] **T1.4** 提交批次 1
  - commit message: `feat(core): SSD-11 批次1 — ChatConfigPort/AppConfigPort适配器新增25方法实现 [CX]`
  - 验证：`ruff check src/core/adapters/` 通过

## 批次 2：personality 域迁移

> 依赖：批次 1

- [ ] **T2.1** 迁移 `src/maisaka/chat_loop_service.py` 的 personality 访问
  - 替换 `global_config.personality.personality.strip()` → `get_chat_config_port().get_personality().strip()`
  - 移除 `from src.config.config import global_config` 的 noqa 注释（如该文件仅访问 personality 域）
  - 验证：`ruff check src/maisaka/chat_loop_service.py` 通过
  - CC/Codex 建议：Codex（3 处替换，模式与 SSD-7 generator_base 迁移一致）

- [ ] **T2.2** 迁移 `src/maisaka/replyer/generator_base.py` 的 personality + keyword_reaction 访问
  - 替换 `global_config.personality.personality.strip()` → `get_chat_config_port().get_personality().strip()`
  - 替换 `global_config.personality.reply_style` → `get_chat_config_port().get_reply_style_text()`
  - 替换 `global_config.personality` 整体引用 → 逐属性调用
  - 替换 `global_config.keyword_reaction` → `get_chat_config_port().get_keyword_reaction()`
  - 移除 `from src.config.config import global_config` 的 noqa 注释
  - 验证：`ruff check src/maisaka/replyer/generator_base.py` 通过
  - CC/Codex 建议：Codex（generator_base 是核心回复生成器，但替换模式明确，CC 审查即可）

- [ ] **T2.3** 提交批次 2
  - commit message: `refactor(maisaka): SSD-11 批次2 — personality/keyword_reaction域迁移到ChatConfigPort [CX]`

## 批次 3：reply_timing 域迁移

> 依赖：批次 1

- [ ] **T3.1** 迁移 `src/core/message_utils.py` 的 reply_timing 访问
  - 替换 `global_config.chat.reply_timing` → `get_chat_config_port().get_reply_timing_config()`
  - 将 `reply_timing_config.talk_value` / `reply_timing_config.private_talk_value` / `reply_timing_config.enable_talk_value_rules` / `reply_timing_config.talk_value_rules` 等属性访问改为快照属性访问
  - 移除 `from src.config.config import global_config` 的 noqa 注释
  - 验证：`ruff check src/core/message_utils.py` 通过
  - CC/Codex 建议：Codex（core 层文件，2-3 处替换，模式明确）

- [ ] **T3.2** 迁移 `src/maisaka/mode_policy.py` 的 reply_timing 访问
  - 替换 `global_config.chat.reply_timing.reply_trigger_mode` → `get_chat_config_port().get_reply_timing_config().reply_trigger_mode`
  - 移除 `from src.config.config import global_config` 的 noqa 注释
  - 验证：`ruff check src/maisaka/mode_policy.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T3.3** 迁移 `src/common/utils/utils_config.py` 的 reply_timing 访问
  - 替换 `global_config.chat.reply_timing.talk_value` / `.private_talk_value` / `.enable_talk_value_rules` / `.talk_value_rules` → `get_chat_config_port().get_reply_timing_config()` 快照属性访问
  - 注意：该文件还访问了 expression/experimental/jargon/chat.reply_style/a_memorix 域，本期仅迁移 reply_timing 部分，其余域保留 noqa
  - 验证：`ruff check src/common/utils/utils_config.py` 通过
  - CC/Codex 建议：Codex（该文件访问多域，需精确替换仅 reply_timing 部分）

- [ ] **T3.4** 迁移 `src/maisaka/runtime.py` 的 reply_timing 访问
  - 注意：runtime.py 同时访问 reply_timing/mcp/debug/expression 域，本期仅迁移 reply_timing 部分
  - 替换 `global_config.chat.reply_timing.*` 相关访问 → `get_chat_config_port().get_reply_timing_config()` 快照属性
  - 保留 mcp/debug/expression 的 global_config 访问（后续批次处理）
  - 验证：`ruff check src/maisaka/runtime.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T3.5** 提交批次 3
  - commit message: `refactor: SSD-11 批次3 — reply_timing域迁移到ChatConfigPort(Deprecated) [CC]`

## 批次 4：mcp/debug 域迁移

> 依赖：批次 1

- [ ] **T4.1** 迁移 `src/maisaka/runtime.py` 的 mcp + debug 访问
  - 替换 `global_config.mcp.enable` → `get_app_config_port().get_mcp_enable()`
  - 替换 `global_config.mcp.client.sampling.task_name` → `get_app_config_port().get_mcp_sampling_task_name()`
  - 替换 `global_config.mcp` 整体引用 → 逐属性调用
  - 替换 `global_config.debug.enable_reply_effect_tracking` → `get_app_config_port().get_debug_enable_reply_effect_tracking()`
  - 注意：expression 域访问保留（已通过 SSD-10 协议化，检查是否已迁移）
  - 更新 noqa 注释
  - 验证：`ruff check src/maisaka/runtime.py` 通过
  - CC/Codex 建议：CC（runtime.py 面积最大，多域混合，需确保不引入副作用）

- [ ] **T4.2** 迁移 `src/maisaka/utils/tool_record_payload.py` 的 debug 访问
  - 替换 `global_config.debug.record_tool_structured_content` → `get_app_config_port().get_debug_record_tool_structured_content()`
  - 移除 `from src.config.config import global_config` 的 noqa 注释
  - 验证：`ruff check src/maisaka/utils/tool_record_payload.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T4.3** 迁移 `src/maisaka/display/prompt_cli_renderer.py` 的 debug 访问
  - 替换 `global_config.debug.keep_prompt_preview_json_base64` → `get_app_config_port().get_debug_keep_prompt_preview_json_base64()`
  - 注意：该文件还访问 webui 域（批次 6 处理），本期仅迁移 debug 部分
  - 验证：`ruff check src/maisaka/display/prompt_cli_renderer.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T4.4** 迁移 `src/services/llm_cache_stats.py` 的 debug 访问
  - 替换 `global_config.debug.enable_llm_cache_stats` → `get_app_config_port().get_debug_enable_llm_cache_stats()`
  - 需在 T0.4 中同步新增 `get_debug_enable_llm_cache_stats() -> bool` 方法签名
  - 需在 T1.2 中同步新增适配器实现
  - 验证：`ruff check src/services/llm_cache_stats.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T4.5** 提交批次 4
  - commit message: `refactor: SSD-11 批次4 — mcp/debug域迁移到AppConfigPort [CC]`

## 批次 5：response_splitter/chinese_typo/response_post_process 域迁移

> 依赖：批次 1

- [ ] **T5.1** 迁移 `src/maisaka/context/post_processor.py` 的 3 域访问
  - 替换 `global_config.response_splitter.*`（6 处）→ `get_app_config_port().get_response_splitter_*()` 逐属性调用
  - 替换 `global_config.chinese_typo.*`（5 处）→ `get_app_config_port().get_chinese_typo_*()` 逐属性调用
  - 替换 `global_config.response_post_process.*`（2 处）→ `get_app_config_port().get_response_post_process_*()` 逐属性调用
  - 移除 `from src.config.config import global_config` 的 noqa 注释
  - 验证：`ruff check src/maisaka/context/post_processor.py` 通过
  - CC/Codex 建议：Codex（post_processor 是回复后处理核心，14 处替换需逐一确认）

- [ ] **T5.2** 迁移 `src/chat/utils/utils.py` 的 response_post_process 访问
  - 替换 `global_config.response_post_process.typing_speed` → `get_app_config_port().get_response_post_process_typing_speed()`
  - 移除 `from src.config.config import global_config` 的 noqa 注释
  - 验证：`ruff check src/chat/utils/utils.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T5.3** 提交批次 5
  - commit message: `refactor: SSD-11 批次5 — response_splitter/chinese_typo/response_post_process域迁移到AppConfigPort [CC]`

## 批次 6：log/webui/agent/agent_interaction/emoji 域迁移

> 依赖：批次 1

- [ ] **T6.1** 迁移 `src/maisaka/display/prompt_preview_logger.py` 的 log 访问
  - 替换 `global_config.log.maisaka_prompt_preview_limit` → `get_app_config_port().get_log_maisaka_prompt_preview_limit()`
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/display/prompt_preview_logger.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.2** 迁移 `src/maisaka/reply_effect/storage.py` 的 log 访问
  - 替换 `global_config.log.maisaka_reply_effect_limit` → `get_app_config_port().get_log_maisaka_reply_effect_limit()`
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/reply_effect/storage.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.3** 迁移 `src/maisaka/display/prompt_cli_renderer.py` 的 webui 访问
  - 替换 `global_config.webui.host` → `get_app_config_port().get_webui_host()`
  - 替换 `global_config.webui.port` → `get_app_config_port().get_webui_port()`
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/display/prompt_cli_renderer.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.4** 迁移 `src/maisaka/agent/router.py` 的 agent 访问
  - 替换 `global_config.agent.default_agent_id` → `get_app_config_port().get_default_agent_id()`
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/agent/router.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.5** 迁移 `src/maisaka/agent/registry.py` 的 agent 访问
  - 替换 `global_config.agent.agents_dir` → `get_app_config_port().get_agents_dir()`
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/agent/registry.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.6** 迁移 `src/maisaka/agent_interaction/bootstrap.py` 的 agent_interaction 访问
  - 替换 `cfg = global_config.agent_interaction` → `cfg = get_app_config_port().get_agent_interaction_config()`（2 处）
  - 将后续属性访问改为快照属性访问
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/agent_interaction/bootstrap.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.7** 迁移 `src/maisaka/builtin_tool/send_emoji.py` 的 emoji 访问
  - 替换 `getattr(global_config.emoji, "emoji_send_num", 25)` → `get_app_config_port().get_emoji_send_num()`
  - 注意：该文件还导入 `config_manager`，需确认是否可一并移除
  - 验证：`ruff check src/maisaka/builtin_tool/send_emoji.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T6.8** 提交批次 6
  - commit message: `refactor: SSD-11 批次6 — log/webui/agent/agent_interaction/emoji域迁移到AppConfigPort [CC]`

## 批次 7：a_memorix 域扩展迁移

> 依赖：批次 0（AMemorixIntegrationSnapshot 扩展）+ 批次 1（适配器实现）

- [ ] **T7.1** 迁移 `src/maisaka/memory/heuristic_injector.py` 的 a_memorix.integration 访问
  - 替换 `global_config.a_memorix.integration` → `get_app_config_port().get_a_memorix_integration_config()`（3 处：行 101/220/371）
  - 将 `config.heuristic_memory_recall_enabled` / `config.heuristic_memory_recall_window_size` 等属性访问改为快照属性访问
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/memory/heuristic_injector.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T7.2** 迁移 `src/maisaka/memory/person_profile.py` 的 a_memorix.integration 访问
  - 替换 `global_config.a_memorix.integration` → `get_app_config_port().get_a_memorix_integration_config()`
  - 替换 `integration_config.enable_person_profile_injection` / `integration_config.person_profile_injection_max_profiles` → 快照属性
  - 注意：该文件还访问 `global_config.bot.qq_account`（已通过 BotConfigPort 协议化），需一并迁移
  - 验证：`ruff check src/maisaka/memory/person_profile.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T7.3** 迁移 `src/maisaka/builtin_tool/__init__.py` 的 a_memorix.integration 访问
  - 替换 `global_config.a_memorix.integration.enable_memory_query_tool` → `get_app_config_port().get_a_memorix_integration_config().enable_memory_query_tool`
  - 替换 `global_config.a_memorix.integration.enable_person_profile_query_tool` → 快照属性
  - 注意：该文件可能还访问 experimental 域，需确认
  - 验证：`ruff check src/maisaka/builtin_tool/__init__.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T7.4** 迁移 `src/maisaka/builtin_tool/query_memory.py` 的 a_memorix.integration 访问
  - 替换 `global_config.a_memorix.integration.memory_query_default_limit` → `get_app_config_port().get_a_memorix_integration_config().memory_query_default_limit`
  - 移除 noqa 注释
  - 验证：`ruff check src/maisaka/builtin_tool/query_memory.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T7.5** 提交批次 7
  - commit message: `refactor(maisaka): SSD-11 批次7 — a_memorix.integration扩展域迁移到AppConfigPort [CC]`

## 批次 8：其余 noqa TID251 文件迁移

> 依赖：批次 2-7（所有域协议化完成后）

- [ ] **T8.1** 迁移 `src/maisaka/replyer/expression_selector.py`
  - 替换 `global_config` / `model_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.2** 迁移 `src/maisaka/replyer/generator.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.3** 迁移 `src/maisaka/replyer/expression_vector_index.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.4** 迁移 `src/maisaka/display/runtime_mixin.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.5** 迁移 `src/maisaka/focus/manager.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点（experimental.focus_* 域）
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.6** 迁移 `src/maisaka/focus/runtime_mixin.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.7** 迁移 `src/maisaka/builtin_tool/context.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.8** 迁移 `src/maisaka/builtin_tool/reply.py`
  - 替换 `from src.config import config as config_module` → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.9** 迁移 `src/maisaka/visual/mode_utils.py`
  - 替换 `config_manager` / `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.10** 迁移 `src/maisaka/memory/mid_term.py`
  - 替换 `global_config` 导入 → 对应 Port 注册点（chat.mid_term_memory/visual/debug 域）
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.11** 迁移 `src/chat/` 模块（6 文件）
  - `bot.py` / `uni_message_sender.py` / `image_receive_compressor.py` / `replyer_manager.py` / `image_system/image_cache_cleanup.py`
  - 逐文件替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check src/chat/` 通过
  - CC/Codex 建议：Codex（可拆分给 Codex 做 CC 审查）

- [ ] **T8.12** 迁移 `src/services/` 模块（4 文件）
  - `send_service.py` / `memory_flow_service.py` / `message_service.py` / `service_task_resolver.py`
  - 逐文件替换 `global_config` / `config_manager` 导入 → 对应 Port 注册点
  - 验证：`ruff check src/services/` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.13** 迁移 `src/common/` 模块（7 文件）
  - `utils/utils_message.py` / `message_server/universal_message_sender.py` / `utils/utils_voice.py` / `data_models/session_message_data_model.py` / `message_server/api.py` / `remote.py`
  - 注意：`utils_config.py` 已在批次 3 部分迁移，需确认剩余 global_config 访问
  - 验证：`ruff check src/common/` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.14** 迁移 `src/plugin_runtime/` 模块（4 文件）
  - `capabilities/data.py` / `host/supervisor.py` / `capabilities/core.py` / `host/hook_dispatcher.py`
  - 逐文件替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check src/plugin_runtime/` 通过
  - CC/Codex 建议：Codex

- [ ] **T8.15** 迁移其余零散文件
  - `src/cli/maisaka_cli_sender.py` / `src/emoji_system/emoji_cache_cleanup.py` / `src/llm_models/request_snapshot.py` / `src/person_info/person_info.py`
  - 逐文件替换 `global_config` 导入 → 对应 Port 注册点
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex（零散文件，操作简单）

- [ ] **T8.16** 提交批次 8
  - commit message: `refactor: SSD-11 批次8 — 其余noqa TID251文件迁移到Port [CC]`

## 批次 9：收尾（ruff 守卫收紧 + AGENTS.md 更新 + 验证）

> 依赖：批次 8（所有文件迁移完成后）

- [ ] **T9.1** 收紧 `pyproject.toml` 的 per-file-ignores
  - 移除已完成迁移文件的 TID251 豁免（如 `src/chat/message_receive/bot.py` 已迁移则移除）
  - 保留合法豁免：`src/core/adapters/*`、`src/main.py`、`src/config/config.py`、`src/A_memorix/**`、`src/core/person_info_port_registry.py`、`src/core/message_port_registry.py`、`src/services/llm_service.py`、`src/services/memory_service.py`、`src/maisaka/message_port.py`、`src/plugin_runtime/hook_catalog.py`、`src/services/send_service.py`、`src/chat/heart_flow/heartflow_manager.py`、`src/chat/heart_flow/heartflow_message_processor.py`、`src/services/html_render_service.py`、`src/services/telemetry_stats_service.py`
  - 验证：`ruff check` 全项目通过（global_config 相关 TID251 清零，其余 config_manager/Person/heartflow_manager 违规留待 SSD-12）
  - CC/Codex 建议：CC

- [ ] **T9.2** 更新 `AGENTS.md` Protocol 表格
  - 更新 `ChatConfigPort` 方法数：5 → 10（+personality 3 +reply_timing 1 +keyword_reaction 1）
  - 更新 `AppConfigPort` 方法数：21 → 40（+mcp 2 +response_splitter 6 +chinese_typo 5 +response_post_process 2 +log 2 +webui 2 +agent 2 +agent_interaction 1 +emoji 1 +debug 3）
  - 更新 `AMemorixIntegrationSnapshot` 字段数：4 → 19
  - 新增 `ReplyTimingSnapshot`/`AgentInteractionSnapshot`/`KeywordReactionSnapshot`/`TalkValueRuleSnapshot`/`KeywordRuleSnapshot` 快照类型说明
  - CC/Codex 建议：CC

- [ ] **T9.3** 更新 `AGENTS.md` 核心禁止项状态
  - 更新 `9. 禁止核心直接导入 global_config` 状态（如 core 层零违规则标注 ✅ 已消除，覆盖 reply_timing）
  - CC/Codex 建议：CC

- [ ] **T9.4** 更新 `AGENTS.md` 已完成 SSD 摘要
  - 添加 SSD-11 行：主题="SSD-10 遗留协议化"，关键成果="14 域协议化完成，AppConfigPort 21→40 方法，ChatConfigPort 5→10 方法，global_config TID251 清零"
  - 更新"待后续"清单：移除已完成的域
  - CC/Codex 建议：CC

- [ ] **T9.5** 最终验证
  - `ruff check` 全项目通过
  - 容器启动正常，功能无回归
  - `src/core/`（排除 adapters/）零 `global_config` 运行时导入（含 reply_timing）
  - `global_config` 相关 TID251 清零（其余 config_manager/Person/heartflow_manager 违规留待 SSD-12）
  - CC/Codex 建议：CC

- [ ] **T9.6** 提交收尾
  - commit message: `chore: SSD-11 收尾 — ruff守卫收紧+AGENTS.md更新+Protocol表格同步 [CC]`