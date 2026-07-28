# SSD-10 编码任务

## 批次 0：配置清理（前置）

- [ ] **T0.1** 删除 `src/config/config.py` 中 15 项死配置字段
  - `ReplyTimingConfig`: 删除 `no_action_backoff_base_seconds`/`no_action_backoff_cap_seconds`/`no_action_backoff_start_count`/`no_action_backoff_bypass_pending_count`
  - `ChatConfig`: 删除 `mid_term_memory_lenth`（拼写错误且零引用）
  - `DatabaseConfig`: 删除 `save_binary_data`
  - `WebUIConfig`: 删除 `enable_paragraph_content`
  - `SubAgentSectionConfig`: 整个类删除（8 项全部死配置：`dream_enabled`/`dream_interval_days`/`compaction_enabled`/`compaction_threshold_level_1`/`compaction_threshold_level_2`/`compaction_threshold_level_3`/`checkpoint_writer_enabled`/`checkpoint_writer_fork_enabled`）
  - `Config`: 删除 `subagent` 字段
  - 验证：`ruff check src/config/` 通过
  - CC/Codex 建议：CC（配置定义修改需理解架构语义）

- [ ] **T0.2** 删除升级钩子中对应的迁移逻辑
  - 搜索 `src/config/` 中所有 `no_action_backoff`/`mid_term_memory_lenth`/`save_binary_data`/`enable_paragraph_content`/`subagent`/`dream_enabled`/`compaction_enabled`/`checkpoint_writer` 的引用
  - 删除对应的 `ConfigUpgradeHook` 迁移逻辑
  - 验证：`ruff check src/config/` 通过
  - CC/Codex 建议：CC（升级钩子逻辑需谨慎处理）

- [ ] **T0.3** 删除 TOML 模板中对应的配置项
  - 从 `bot_config.toml` 模板中删除 15 项死配置
  - 验证：模板文件语法正确
  - CC/Codex 建议：Codex（纯删除操作）

- [ ] **T0.4** 标记 13 项架构冲突配置为 DEPRECATED
  - 在 `src/config/config.py` 的字段定义处添加 `# DEPRECATED: 将由 xxx 替代` 注释
  - 标记列表：
    - `ReplyTimingConfig`: `reply_trigger_mode`/`planner_interrupt_max_consecutive_count`/`max_consecutive_wait_count`/`talk_value`/`private_talk_value`/`enable_talk_value_rules`/`talk_value_rules`/`mentioned_bot_reply`/`inevitable_at_reply`
    - `ExperimentalConfig`: `enable_behavior_learning`/`behavior_learning_list`/`behavior_groups`/`enable_rich_reply`
    - `AMemorixConnectionistConfig`: `phase`
    - `AMemorixIntegrationConfig`: `heuristic_memory_recall_enabled`/`heuristic_memory_cross_chat_enabled`/`heuristic_memory_group_to_private_enabled`/`heuristic_memory_private_to_group_enabled`
  - CC/Codex 建议：CC（需理解架构冲突原因）

- [ ] **T0.5** 提交批次 0
  - commit message: `refactor(config): SSD-10 批次0 — 删除15项死配置+标记13项DEPRECATED [CC]`
  - 验证：`ruff check` 通过 + 容器启动正常

## 批次 1：Protocol 定义 + 适配器 + 注册点 + ruff 守卫

- [ ] **T1.1** 在 `src/core/protocols.py` 追加 4 个 Protocol 定义
  - `BotConfigPort`（5 方法：get_bot_nickname/get_bot_alias_names/get_bot_qq_account/get_bot_platforms/get_bot_owner_user_ids）
  - `ChatConfigPort`（5 方法：get_reply_style/get_max_context_size/get_max_private_context_size/get_self_message_special_mark/get_mid_term_memory_config）
  - `AppConfigPort`（~20 方法，覆盖 expression/emoji/experimental/visual/debug/agent_autonomy/a_memorix 域）
  - `AutonomyEventBusPort`（4 方法：subscribe/unsubscribe/emit/emit_sync）
  - 验证：`ruff check src/core/protocols.py` 通过
  - CC/Codex 建议：CC（Protocol 设计需架构理解）

- [ ] **T1.2** 在 `src/core/types.py` 追加快照类型
  - `ReplyStyleSnapshot`（frozen dataclass：chat_prompts/private_chat_prompts/group_chat_prompt/enable_reply_quote）
  - `AgentAutonomySnapshot`（frozen dataclass，从 `AgentAutonomySectionConfig` 映射）
  - `AMemorixIntegrationSnapshot`（frozen dataclass，从 `AMemorixIntegrationConfig` 映射）
  - 更新 `__all__`
  - 验证：`ruff check src/core/types.py` 通过
  - CC/Codex 建议：CC

- [ ] **T1.3** 创建 4 个注册点文件
  - `src/core/bot_config_port_registry.py`（register/get/reset 三函数模式）
  - `src/core/chat_config_port_registry.py`
  - `src/core/app_config_port_registry.py`
  - `src/core/event_bus_port_registry.py`
  - 验证：`ruff check src/core/` 通过
  - CC/Codex 建议：Codex（模板化操作，参照已有注册点如 `person_info_port_registry.py`）

- [ ] **T1.4** 创建 3 个适配器文件
  - `src/core/adapters/bot_config_port.py` — `GlobalConfigBotConfigPort`（从 global_config.bot 读取）
  - `src/core/adapters/chat_config_port.py` — `GlobalConfigChatConfigPort`（从 global_config.chat 读取）
  - `src/core/adapters/app_config_port.py` — `GlobalConfigAppConfigPort`（从 global_config 各域读取）
  - 更新 `src/core/adapters/__init__.py` 的 `__all__`
  - 验证：`ruff check src/core/adapters/` 通过
  - CC/Codex 建议：CC（适配器需理解配置结构）

- [ ] **T1.5** 在 `src/main.py` 添加启动注册
  - `register_bot_config_port(GlobalConfigBotConfigPort())` — order 在已有注册点之后
  - `register_chat_config_port(GlobalConfigChatConfigPort())`
  - `register_app_config_port(GlobalConfigAppConfigPort())`
  - 验证：`ruff check src/main.py` 通过
  - CC/Codex 建议：CC

- [ ] **T1.6** 添加 ruff TID251 守卫
  - `pyproject.toml` banned-api 添加：
    - `"src.config.config.global_config".msg = "Use BotConfigPort/ChatConfigPort/AppConfigPort via registry instead"`
    - `"AutonomyEventBus.get_instance".msg = "Use AutonomyEventBusPort injection instead"`
  - per-file-ignores 豁免：
    - `src/core/adapters/*.py`
    - `src/main.py`
    - `src/config/*.py`
    - `src/webui/**`
    - `src/learners/**`
  - 验证：`ruff check` 通过（当前违规文件应被 per-file-ignores 豁免）
  - CC/Codex 建议：CC

- [ ] **T1.7** 提交批次 1
  - commit message: `feat(core): SSD-10 批次1 — BotConfigPort/ChatConfigPort/AppConfigPort/AutonomyEventBusPort Protocol+适配器+注册点+ruff守卫 [CC]`

## 批次 2：core 层 M6 修复

- [ ] **T2.1** 修复 `src/core/identity.py`
  - 替换 `from src.config.config import global_config` → `from src.core.bot_config_port_registry import get_bot_config_port`
  - 替换 `global_config.bot.qq_account` → `get_bot_config_port().get_bot_qq_account()`
  - 替换 `global_config.bot.platforms` → `get_bot_config_port().get_bot_platforms()`
  - 替换 `getattr(global_config.bot, ...)` → 直接调用 Port 方法
  - 验证：`ruff check src/core/identity.py` 通过
  - CC/Codex 建议：CC

- [ ] **T2.2** 修复 `src/core/message_utils.py`
  - 替换 `from src.config.config import global_config` → `from src.core.bot_config_port_registry import get_bot_config_port` + `from src.core.chat_config_port_registry import get_chat_config_port`
  - 替换 `global_config.bot.nickname` → `get_bot_config_port().get_bot_nickname()`
  - 替换 `global_config.bot.alias_names` → `get_bot_config_port().get_bot_alias_names()`
  - 替换 `global_config.chat.reply_timing` → 继续直接访问（待废弃配置本期不协议化，保留 global_config 导入但添加 noqa 注释）
  - 验证：`ruff check src/core/message_utils.py` 通过
  - CC/Codex 建议：CC

- [ ] **T2.3** 提交批次 2
  - commit message: `fix(core): SSD-10 批次2 — core层M6修复(identity.py+message_utils.py)消除global_config直接导入 [CC]`

## 批次 3：maisaka/agent_autonomy/ 迁移

- [ ] **T3.1** 迁移 `src/maisaka/agent_autonomy/` 中的 global_config 导入
  - 涉及文件（~8 个）：
    - `orchestrator.py` — global_config → BotConfigPort + AppConfigPort
    - `vitality_manager.py` — global_config → AppConfigPort
    - `vitality_tick.py` — global_config → AppConfigPort
    - `prompt_builder.py` — global_config → BotConfigPort
    - `thinking_organ.py` — global_config → BotConfigPort + AppConfigPort
    - `ambient_awareness.py` — global_config → AppConfigPort
    - `behavior_intent.py` — global_config → AppConfigPort
    - `interjection_cooldown.py` — global_config → AppConfigPort
  - 每个文件：替换 `from src.config.config import global_config` → 对应 Port 注册点调用
  - 验证：`ruff check src/maisaka/agent_autonomy/` 通过
  - CC/Codex 建议：CC（需理解 agent_autonomy 配置语义）

- [ ] **T3.2** 迁移 `src/maisaka/agent_autonomy/state_awareness/` 和 `bridge/`
  - `state_awareness/summary_generator.py` — global_config → AppConfigPort
  - `state_awareness/visibility_rule.py` — global_config → AppConfigPort
  - `bridge/chat_loop_adapter.py` — global_config → BotConfigPort
  - `bridge/reply_context_extender.py` — global_config → BotConfigPort
  - 验证：`ruff check` 通过
  - CC/Codex 建议：CC

- [ ] **T3.3** 提交批次 3
  - commit message: `refactor(maisaka): SSD-10 批次3 — agent_autonomy模块global_config迁移到Port [CC]`

## 批次 4：maisaka/ 其余模块迁移

- [ ] **T4.1** 迁移 `src/maisaka/replyer/` 中的 global_config 导入
  - 涉及文件：`generator_base.py`/`generator.py`/`expression_selector.py`/`expression_vector_index.py`
  - 验证：`ruff check` 通过
  - CC/Codex 建议：CC

- [ ] **T4.2** 迁移 `src/maisaka/memory/` 中的 global_config 导入
  - 涉及文件：`heuristic_injector.py`/`mid_term.py`/`person_profile.py`
  - 验证：`ruff check` 通过
  - CC/Codex 建议：CC

- [ ] **T4.3** 迁移 `src/maisaka/` 其余模块
  - `runtime.py`/`chat_loop_service.py`/`agent/router.py`/`agent/registry.py`
  - `context/post_processor.py`/`focus/manager.py`/`focus/runtime_mixin.py`
  - `display/runtime_mixin.py`/`display/prompt_preview_logger.py`/`display/prompt_cli_renderer.py`
  - `reply_effect/storage.py`/`utils/tool_record_payload.py`
  - `builtin_tool/__init__.py`/`builtin_tool/send_emoji.py`/`builtin_tool/query_memory.py`/`builtin_tool/context.py`
  - `visual/mode_utils.py`/`visual/chat_history_refresher.py`
  - `agent_interaction/bootstrap.py`
  - 验证：`ruff check src/maisaka/` 通过
  - CC/Codex 建议：CC（大量文件，可拆分给 Codex 做 CC 审查）

- [ ] **T4.4** 提交批次 4
  - commit message: `refactor(maisaka): SSD-10 批次4 — maisaka其余模块global_config迁移到Port [CC]`

## 批次 5：chat/services/common/plugin_runtime 迁移

- [ ] **T5.1** 迁移 `src/chat/` 中的 global_config 导入
  - 涉及文件：`bot.py`/`uni_message_sender.py`/`utils/utils.py`/`replyer/replyer_manager.py`/`image_receive_compressor.py`/`image_system/image_cache_cleanup.py`
  - 验证：`ruff check src/chat/` 通过
  - CC/Codex 建议：CC

- [ ] **T5.2** 迁移 `src/services/` 中的 global_config 导入
  - 涉及文件：`send_service.py`/`memory_flow_service.py`/`message_service.py`/`llm_cache_stats.py`
  - 验证：`ruff check src/services/` 通过
  - CC/Codex 建议：CC

- [ ] **T5.3** 迁移 `src/common/` 中的 global_config 导入
  - 涉及文件：`utils/utils_message.py`/`message_server/universal_message_sender.py`/`utils/utils_voice.py`/`data_models/session_message_data_model.py`/`utils/utils_config.py`/`message_server/api.py`/`remote.py`
  - 验证：`ruff check src/common/` 通过
  - CC/Codex 建议：CC

- [ ] **T5.4** 迁移 `src/plugin_runtime/` 中的 global_config 导入
  - 涉及文件：`capabilities/data.py`/`host/supervisor.py`/`capabilities/core.py`/`host/hook_dispatcher.py`
  - 验证：`ruff check src/plugin_runtime/` 通过
  - CC/Codex 建议：CC

- [ ] **T5.5** 迁移其余零散文件
  - `src/emoji_system/emoji_cache_cleanup.py`/`src/llm_models/request_snapshot.py`/`src/person_info/person_info.py`/`src/mcp_module/__init__.py`/`src/cli/maisaka_cli_sender.py`
  - 验证：`ruff check` 通过
  - CC/Codex 建议：Codex（零散文件，操作简单）

- [ ] **T5.6** 提交批次 5
  - commit message: `refactor: SSD-10 批次5 — chat/services/common/plugin_runtime/零散模块global_config迁移到Port [CC]`

## 批次 6：AutonomyEventBusPort 构造注入

- [ ] **T6.1** 修改 `src/maisaka/agent_autonomy/event_bus.py`
  - 移除 `_instance` 类变量和 `get_instance()` 类方法
  - 让 `AutonomyEventBus` 实现 `AutonomyEventBusPort` Protocol（鸭子类型，无需显式继承）
  - 验证：`ruff check` 通过
  - CC/Codex 建议：CC

- [ ] **T6.2** 修改 4 个消费者，构造注入 event_bus
  - `vitality_manager.py` — 添加 `event_bus: AutonomyEventBusPort` 参数，替换 `AutonomyEventBus.get_instance()`
  - `orchestrator.py` — 同上
  - `agent_interaction/engine.py` — 同上
  - `autonomy_logger.py` — 同上
  - 验证：`ruff check` 通过
  - CC/Codex 建议：CC

- [ ] **T6.3** 在 `src/main.py` 创建 AutonomyEventBus 实例并注入
  - 创建 `event_bus = AutonomyEventBus()` 实例
  - 通过注册点 `register_event_bus_port(event_bus)` 注册
  - 或直接构造注入到各消费者（取决于初始化链路）
  - 验证：容器启动正常
  - CC/Codex 建议：CC

- [ ] **T6.4** 提交批次 6
  - commit message: `refactor(maisaka): SSD-10 批次6 — AutonomyEventBusPort构造注入替代get_instance单例 [CC]`

## 收尾

- [ ] **T7.1** 更新 `AGENTS.md` 核心禁止项状态
  - 添加：`9. 禁止核心直接导入 global_config ✅ 已消除`（如果批次 2 完成后 core 层零违规）
  - 更新 Protocol 表格：添加 BotConfigPort/ChatConfigPort/AppConfigPort/AutonomyEventBusPort
  - CC/Codex 建议：CC

- [ ] **T7.2** 更新 mdc 规则文件
  - 同步 Protocol 表格和核心禁止项状态
  - CC/Codex 建议：CC

- [ ] **T7.3** 最终验证
  - `ruff check` 全项目通过
  - 容器启动正常
  - `src/core/`（排除 adapters/）零 global_config/config_manager 运行时导入
  - `AutonomyEventBus.get_instance` 零调用
  - CC/Codex 建议：CC

- [ ] **T7.4** 提交收尾
  - commit message: `chore: SSD-10 收尾 — 更新AGENTS.md+mdc核心禁止项状态+Protocol表格 [CC]`