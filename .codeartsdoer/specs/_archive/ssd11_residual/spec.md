# SSD-11: SSD-10 遗留协议化

## 背景

SSD-10 完成了 `global_config` 主要访问域的协议化，建立了 `BotConfigPort`(5方法)、`ChatConfigPort`(5方法)、`AppConfigPort`(21方法)、`AutonomyEventBusPort`(4方法) 四个 Protocol 接口，消除了 `src/core/` 层的 `global_config` 直接导入。

但 SSD-10 设计文档（D1）明确将低频域（<15 次访问）排除在协议化范围外，这些域仍通过 `global_config` 直接访问（带 `noqa: TID251` 注释）。当前代码中仍有 **41 处** `noqa: TID251` 标注，分布在约 40 个文件中。

## 遗留域清单与现状

### 已完成协议化（SSD-10）

| Protocol | 域 | 方法数 |
|----------|-----|--------|
| BotConfigPort | bot | 5 |
| ChatConfigPort | chat（不含 reply_timing 待废弃项） | 5 |
| AppConfigPort | expression/emoji/experimental/visual/debug/agent_autonomy/a_memorix.integration | 21 |
| AutonomyEventBusPort | event_bus | 4 |

### 待协议化域（14 个域，按访问频率排序）

| # | 域 | 访问路径 | 访问文件 | 策略 |
|---|-----|---------|---------|------|
| 1 | personality | `global_config.personality.*` | chat_loop_service.py, generator_base.py | 扩展 ChatConfigPort |
| 2 | reply_timing | `global_config.chat.reply_timing.*` | runtime.py, message_utils.py, mode_policy.py | DEPRECATED 过渡策略 |
| 3 | mcp | `global_config.mcp.*` | runtime.py | 扩展 AppConfigPort |
| 4 | response_splitter | `global_config.response_splitter.*` | post_processor.py | 扩展 AppConfigPort |
| 5 | chinese_typo | `global_config.chinese_typo.*` | post_processor.py | 扩展 AppConfigPort |
| 6 | response_post_process | `global_config.response_post_process.*` | post_processor.py | 扩展 AppConfigPort |
| 7 | log | `global_config.log.*` | prompt_preview_logger.py, storage.py | 扩展 AppConfigPort |
| 8 | webui | `global_config.webui.*` | prompt_cli_renderer.py | 扩展 AppConfigPort |
| 9 | a_memorix | `global_config.a_memorix.integration.*`（扩展属性） | heuristic_injector.py, person_profile.py, builtin_tool/__init__.py, query_memory.py | 扩展 AMemorixIntegrationSnapshot |
| 10 | agent | `global_config.agent.*` | router.py, registry.py | 扩展 AppConfigPort |
| 11 | agent_interaction | `global_config.agent_interaction.*` | bootstrap.py | 扩展 AppConfigPort |
| 12 | keyword_reaction | `global_config.keyword_reaction` | generator_base.py | 扩展 ChatConfigPort |
| 13 | emoji | `global_config.emoji.emoji_send_num` | send_emoji.py | 扩展 AppConfigPort |
| 14 | debug（遗漏） | `global_config.debug.*`（3项） | runtime.py, tool_record_payload.py, prompt_cli_renderer.py | 扩展 AppConfigPort |

## 功能需求

### FR-1: personality 域协议化

**Ubiquitous**: 当核心或组件层访问人格设定配置时，系统应通过 `ChatConfigPort` 接口获取，而非直接导入 `global_config`。

- `ChatConfigPort` 新增方法：
  - `get_personality() -> str` — 人格设定文本
  - `get_reply_style_text() -> str` — 表达风格文本
  - `get_multiple_reply_style() -> list[str]` — 备用表达风格列表

- 影响文件：`chat_loop_service.py`, `generator_base.py`
- 适配器：`GlobalConfigChatConfigPort` 新增 3 个方法实现

### FR-2: reply_timing 域过渡策略

**StateDriven**: 当 reply_timing 配置项被访问时，系统应通过 `ChatConfigPort` 提供只读访问，同时发出 `DeprecationWarning` 提示将由 vitality 系统替代。

- `ChatConfigPort` 新增方法：
  - `get_reply_timing_config() -> ReplyTimingSnapshot` — 返回不可变快照（含 DEPRECATED 标注）
  - 快照属性：`reply_trigger_mode`, `planner_interrupt_max_consecutive_count`, `max_consecutive_wait_count`, `talk_value`, `private_talk_value`, `enable_talk_value_rules`, `talk_value_rules`, `mentioned_bot_reply`, `inevitable_at_reply`

- 影响文件：`runtime.py`, `message_utils.py`, `mode_policy.py`
- `ReplyTimingSnapshot` 为 `frozen dataclass`，适配器方法首次调用时 emit `DeprecationWarning`
- **约束**：不删除配置项，不修改配置值，仅提供 Protocol 访问层

### FR-3: mcp 域协议化

**Ubiquitous**: 当组件层访问 MCP 配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_mcp_enable() -> bool`
  - `get_mcp_sampling_task_name() -> str`

- 影响文件：`runtime.py`

### FR-4: response_splitter 域协议化

**Ubiquitous**: 当组件层访问回复拆分配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_response_splitter_enable() -> bool`
  - `get_response_splitter_max_length() -> int`
  - `get_response_splitter_max_sentence_num() -> int`
  - `get_response_splitter_max_split_num() -> int`
  - `get_response_splitter_enable_kaomoji_protection() -> bool`
  - `get_response_splitter_enable_overflow_return_all() -> bool`

- 影响文件：`post_processor.py`

### FR-5: chinese_typo 域协议化

**Ubiquitous**: 当组件层访问错别字配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_chinese_typo_enable() -> bool`
  - `get_chinese_typo_error_rate() -> float`
  - `get_chinese_typo_min_freq() -> int`
  - `get_chinese_typo_tone_error_rate() -> float`
  - `get_chinese_typo_word_replace_rate() -> float`

- 影响文件：`post_processor.py`

### FR-6: response_post_process 域协议化

**Ubiquitous**: 当组件层访问回复后处理配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_response_post_process_enable() -> bool`
  - `get_response_post_process_typing_speed() -> float`

- 影响文件：`post_processor.py`

### FR-7: log 域协议化

**Ubiquitous**: 当组件层访问日志配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_log_maisaka_prompt_preview_limit() -> int`
  - `get_log_maisaka_reply_effect_limit() -> int`

- 影响文件：`prompt_preview_logger.py`, `storage.py`

### FR-8: webui 域协议化

**Ubiquitous**: 当组件层访问 WebUI 配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_webui_host() -> str`
  - `get_webui_port() -> int`

- 影响文件：`prompt_cli_renderer.py`

### FR-9: a_memorix 域扩展协议化

**Ubiquitous**: 当组件层访问 A_memorix 集成配置的扩展属性时，系统应通过 `AMemorixIntegrationSnapshot` 快照获取。

- `AMemorixIntegrationSnapshot` 新增字段：
  - `enable_memory_query_tool: bool`
  - `enable_person_profile_query_tool: bool`
  - `memory_query_default_limit: int`
  - 以及 `heuristic_injector.py`/`person_profile.py`/`builtin_tool/__init__.py`/`query_memory.py` 实际访问的其他属性

- 影响文件：`heuristic_injector.py`, `person_profile.py`, `builtin_tool/__init__.py`, `query_memory.py`
- **约束**：遵守 `A_memorix/MODIFICATION_POLICY.md`，核心只通过 `MemoryServicePort` / `AMemorixIntegrationSnapshot` 访问，不直接导入 A_memorix 内部模块

### FR-10: agent 域协议化

**Ubiquitous**: 当组件层访问智能体配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_default_agent_id() -> str`
  - `get_agents_dir() -> str`

- 影响文件：`router.py`, `registry.py`

### FR-11: agent_interaction 域协议化

**Ubiquitous**: 当组件层访问智能体交互配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_agent_interaction_config() -> AgentInteractionSnapshot` — 整体引用模式

- 影响文件：`bootstrap.py`
- `AgentInteractionSnapshot` 为 `frozen dataclass`

### FR-12: keyword_reaction 域协议化

**Ubiquitous**: 当组件层访问关键词反应配置时，系统应通过 `ChatConfigPort` 接口获取。

- `ChatConfigPort` 新增方法：
  - `get_keyword_reaction() -> KeywordReactionSnapshot` — 整体引用模式

- 影响文件：`generator_base.py`

### FR-13: emoji 域扩展协议化

**Ubiquitous**: 当组件层访问 emoji 发送数量配置时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_emoji_send_num() -> int`

- 影响文件：`send_emoji.py`

### FR-14: debug 遗漏协议化

**Ubiquitous**: 当组件层访问调试配置的遗漏项时，系统应通过 `AppConfigPort` 接口获取。

- `AppConfigPort` 新增方法：
  - `get_debug_enable_reply_effect_tracking() -> bool`
  - `get_debug_record_tool_structured_content() -> bool`
  - `get_debug_keep_prompt_preview_json_base64() -> bool`
  - `get_debug_enable_llm_cache_stats() -> bool`

- 影响文件：`runtime.py`, `tool_record_payload.py`, `prompt_cli_renderer.py`

### FR-15: ruff TID251 守卫收紧

**EventDriven**: 当所有遗留域完成协议化后，系统应收紧 `per-file-ignores` 豁免范围，移除已完成迁移文件的 TID251 豁免。

- 移除 `src/webui/**` 的 TID251 豁免（如 webui 域已完成迁移）
- 移除 `src/learners/**` 的 TID251 豁免（如 learners 模块已完成迁移）
- 保留 `src/core/adapters/*.py`、`src/main.py`、`src/config/*.py` 的豁免

### FR-16: 其余 noqa: TID251 文件迁移

**Ubiquitous**: 当组件层文件仍通过 `global_config` 直接访问已协议化的配置域时，应替换为对应 Port 注册点调用。

- 涉及文件（非上述 14 个域的专属文件，但仍有 TID251 标注）：
  - `cli/maisaka_cli_sender.py`
  - `emoji_system/emoji_cache_cleanup.py`
  - `llm_models/request_snapshot.py`
  - `person_info/person_info.py`
  - `plugin_runtime/` (4 文件)
  - `services/` (4 文件)
  - `chat/` (6 文件)
  - `common/` (7 文件)
  - `maisaka/` 其余模块（expression_selector.py, generator.py, expression_vector_index.py, display/runtime_mixin.py, focus/manager.py, focus/runtime_mixin.py, builtin_tool/context.py, builtin_tool/reply.py, visual/mode_utils.py, mid_term.py）

## 非功能需求

### NFR-1: 接口稳定性

- 新增 Protocol 方法必须与已有方法风格一致（`get_xxx()` 命名，返回具体类型或 frozen 快照）
- 快照类型必须为 `frozen dataclass`，与 `ReplyStyleSnapshot`/`AgentAutonomySnapshot` 模式一致

### NFR-2: 大道至简

- 小域（<5 方法）合并到已有 Protocol，不创建独立 Protocol
- 整体引用模式（如 `agent_interaction`、`keyword_reaction`）使用快照返回，不逐属性暴露
- `AppConfigPort` 方法数增长可接受（从 21 → ~40），每个方法对应一个实际使用的配置属性

### NFR-3: 向后兼容

- `AppConfigPort`/`ChatConfigPort` 新增方法不破坏已有实现
- 适配器 `GlobalConfigAppConfigPort`/`GlobalConfigChatConfigPort` 同步新增方法实现
- `AMemorixIntegrationSnapshot` 新增字段必须有默认值（`frozen dataclass` 兼容性）

### NFR-4: DEPRECATED 过渡

- `ReplyTimingSnapshot` 的所有属性标注 `# DEPRECATED: 将由 vitality 系统替代`
- `ChatConfigPort.get_reply_timing_config()` 首次调用时 emit `DeprecationWarning`
- 不删除配置项、不修改配置值、不改变运行时行为

## 约束条件

1. **核心隔离**：`src/core/`（排除 adapters/）不得直接导入 `global_config`，所有配置访问通过 Protocol
2. **已有 Protocol 扩展优先**：不创建新 Protocol，只扩展 `AppConfigPort`/`ChatConfigPort` 和已有快照类型
3. **a_memorix 修改策略**：遵守 `MODIFICATION_POLICY.md`，核心通过 `AMemorixIntegrationSnapshot` 访问扩展属性，不直接导入 A_memorix 内部模块
4. **reply_timing 不删除**：仅提供 Protocol 访问层 + DeprecationWarning，vitality 系统完全接管后再统一清理
5. **不新增 ConfigUpgradeHook**：只改模板+新增版本号
6. **不提交无边界的 ruff/格式化/导入整理**：只迁移与协议化相关的 `noqa: TID251` 文件

## 验收标准

1. `src/core/`（排除 adapters/）零 `global_config` 运行时导入（含 reply_timing）
2. `AppConfigPort` 新增 ~19 方法覆盖 mcp/response_splitter/chinese_typo/response_post_process/log/webui/agent/agent_interaction/emoji/debug 域
3. `ChatConfigPort` 新增 ~4 方法覆盖 personality/reply_timing/keyword_reaction 域
4. `AMemorixIntegrationSnapshot` 新增 a_memorix 扩展属性字段
5. `ReplyTimingSnapshot` frozen dataclass + DeprecationWarning
6. `AgentInteractionSnapshot` / `KeywordReactionSnapshot` frozen dataclass
7. `GlobalConfigAppConfigPort` / `GlobalConfigChatConfigPort` 适配器同步实现所有新增方法
8. `ruff check` 全项目通过，`global_config` 相关 `noqa: TID251` 清零（其余 `config_manager`/`Person`/`heartflow_manager` 违规留待 SSD-12）
9. AGENTS.md Protocol 表格更新 + 核心禁止项状态更新
10. 容器启动正常，功能无回归

## 风险

1. **AppConfigPort 方法膨胀**：从 21 → ~40 方法，接口较长。缓解：每个方法对应实际使用的配置属性，不是猜测性设计；未来可按需拆分子 Protocol。
2. **reply_timing DeprecationWarning 噪声**：高频访问路径可能产生大量警告。缓解：使用 `warnings.warn(..., stacklevel=2)` + 只在首次调用时 emit（通过模块级 flag 控制）。
3. **AMemorixIntegrationSnapshot 字段遗漏**：a_memorix 集成配置属性较多，快照字段可能遗漏。缓解：在设计阶段逐文件确认实际访问的属性。
4. **41 处文件迁移工作量大**：缓解：分批处理，优先处理 14 个域的专属文件，再处理其余文件。注意 TID251 违规中仅 19 处是 `global_config`，其余 `config_manager`(8)/`Person`(4)/`heartflow_manager`(2) 留待 SSD-12。