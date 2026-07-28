# SSD-10 设计文档

## 前置决策：先清理再协议化

在协议化 global_config 之前，必须先清理宏内核遗留的死配置和与新架构冲突的配置。否则会为无意义的配置创建 Protocol，浪费接口维护成本。

### D0: 配置清理（前置批次）

#### 立即删除的死配置（15 项，零运行时引用）

| 配置路径 | 理由 |
|---------|------|
| `chat.reply_timing.no_action_backoff_base_seconds` | 退避逻辑从未实现 |
| `chat.reply_timing.no_action_backoff_cap_seconds` | 同上 |
| `chat.reply_timing.no_action_backoff_start_count` | 同上 |
| `chat.reply_timing.no_action_backoff_bypass_pending_count` | 同上 |
| `chat.mid_term_memory_lenth` | 拼写错误且零引用 |
| `database.save_binary_data` | 功能从未实现 |
| `webui.enable_paragraph_content` | 零引用（含前端） |
| `subagent.dream_enabled` | 零引用 |
| `subagent.dream_interval_days` | 零引用 |
| `subagent.compaction_enabled` | 零引用 |
| `subagent.compaction_threshold_level_1` | 零引用 |
| `subagent.compaction_threshold_level_2` | 零引用 |
| `subagent.compaction_threshold_level_3` | 零引用 |
| `subagent.checkpoint_writer_enabled` | 零引用 |
| `subagent.checkpoint_writer_fork_enabled` | 零引用 |

**操作**：从 Config 类定义中删除这些字段 + 从升级钩子中删除对应迁移逻辑 + 从 TOML 模板中删除。

#### 待评估的架构冲突配置（13 项，本期不删除但标记 DEPRECATED）

| 配置路径 | 冲突原因 | 替代机制 |
|---------|---------|---------|
| `chat.reply_timing.reply_trigger_mode` | 智能体应自主决定何时思考 | vitality + 规则引擎 |
| `chat.reply_timing.planner_interrupt_max_consecutive_count` | 旧 Planner 循环中断 | ThinkingOrgan MAX_CYCLES |
| `chat.reply_timing.max_consecutive_wait_count` | 旧 wait 工具限制 | ThinkingOrgan MAX_CYCLES |
| `chat.reply_timing.talk_value` / `private_talk_value` | 旧发言频率概念 | vitality 系统 |
| `chat.reply_timing.enable_talk_value_rules` / `talk_value_rules` | 动态频率规则 | vitality 系统 |
| `chat.reply_timing.mentioned_bot_reply` / `inevitable_at_reply` | 旧提及必回复 | 管家规则过滤 |
| `experimental.enable_behavior_learning` / `behavior_learning_list` / `behavior_groups` | 旧行为学习 | ThinkingOrgan 思考-行动分离 |
| `experimental.enable_rich_reply` | 旧回复丰富度开关 | reply 工具统一 |
| `a_memorix.connectionist.phase` | 迁移阶段已完成 | 已是最终阶段 |
| `a_memorix.integration.heuristic_memory_*`（4项） | 与直觉引擎重叠 | IntuitionEngine |

**本期策略**：不删除，但在 Config 类定义中添加 `# DEPRECATED: 将由 xxx 替代` 注释。这些配置**不纳入 Protocol 接口**，Protocol 只暴露活跃配置。

#### 清理后的实际协议化范围

清理 15 项死配置后，实际需要协议化的配置访问从 259 次降至约 240 次（减去死配置的 0 次访问——本来就是 0），但更重要的是**Protocol 接口不需要为死配置和待废弃配置预留方法**，接口更精简。

## 设计决策

### D1: GlobalConfigPort 按功能域拆分子 Protocol

**问题**：global_config 有 25 个一级属性、129 条唯一访问路径。单一 Protocol 暴露全部属性会导致接口臃肿（违反大道至简）。

**决策**：按功能域拆分为 3 个子 Protocol，按访问频率分层：

| Protocol | 覆盖域 | 访问次数 | 优先级 |
|----------|--------|---------|--------|
| `BotConfigPort` | bot（nickname/alias_names/qq_account/platforms） | 63 | P0 — core 层直接依赖 |
| `ChatConfigPort` | chat（reply_timing/reply_style/max_context_size/self_message_special_mark） | 31 | P0 — core 层直接依赖 |
| `AppConfigPort` | 其余高频域（expression/emoji/experimental/visual/debug/agent_autonomy/a_memorix） | 165 | P1 — 组件层依赖 |

**不协议化的域**（低频/展示层专用）：webui(13)、response_splitter(7)、jargon(6)、maim_message(5)、mcp(5)、chinese_typo(5)、personality(4)、response_post_process(3)、log(3)、agent_interaction(3)、voice(2)、telemetry(2)、message_receive(2)、agent(2)、plugin_runtime(2)、keyword_reaction(1)

**理由**：
- 低频域（<15 次）的 Protocol 化收益不足以抵消接口维护成本
- webui 专用配置不应通过核心 Protocol 暴露
- 这些低频域可继续直接导入 global_config，后续按需协议化

### D2: BotConfigPort — 精简接口

```python
class BotConfigPort(Protocol):
    def get_bot_nickname(self) -> str: ...
    def get_bot_alias_names(self) -> list[str]: ...
    def get_bot_qq_account(self) -> str: ...
    def get_bot_platforms(self) -> list[dict]: ...
    def get_bot_owner_user_ids(self) -> list[str]: ...
```

**覆盖**：63 次访问中的 56 次（nickname 47 + alias_names 4 + qq_account 2 + platforms 2 + owner_user_ids 1）。其余 7 次是 `global_config.bot` 整体引用（3次在 identity.py，1次在 person_profile.py 等），改为调用具体方法。

### D3: ChatConfigPort — 含子配置快照

**排除死配置**：`no_action_backoff_*`(4项) 已删除，不纳入快照。
**排除待废弃配置**：`reply_trigger_mode`、`planner_interrupt_max_consecutive_count`、`max_consecutive_wait_count`、`talk_value`/`private_talk_value`、`enable_talk_value_rules`/`talk_value_rules`、`mentioned_bot_reply`/`inevitable_at_reply` 不纳入 Protocol，继续通过 global_config 直接访问（标记 DEPRECATED）。

```python
@dataclass(frozen=True)
class ReplyStyleSnapshot:
    chat_prompts: str
    private_chat_prompts: str
    group_chat_prompt: str
    enable_reply_quote: bool

class ChatConfigPort(Protocol):
    def get_reply_style(self) -> ReplyStyleSnapshot: ...
    def get_max_context_size(self) -> int: ...
    def get_max_private_context_size(self) -> int: ...
    def get_self_message_special_mark(self) -> str: ...
    def get_mid_term_memory_config(self) -> dict: ...
```

**覆盖**：31 次访问中，排除待废弃的 reply_timing 子属性（~16次），剩余 ~15 次活跃访问。reply_timing 的待废弃属性本期不协议化，留待 vitality 系统完全接管后统一清理。

### D4: AppConfigPort — 组件层配置聚合

```python
class AppConfigPort(Protocol):
    # expression 域（24次）
    def get_expression_selection_mode(self) -> str: ...
    def get_expression_learning_list(self) -> list[str]: ...
    def get_expression_self_reflect(self) -> bool: ...
    def get_expression_groups(self) -> list[str]: ...
    def get_max_expression_learner(self) -> int: ...
    def get_expression_vector_index_path(self) -> str: ...
    def get_expression_checked_only(self) -> bool: ...
    def get_expression_vector_candidate_pool_size(self) -> int: ...
    
    # emoji 域（16次）
    def get_emoji_max_reg_num(self) -> int: ...
    def get_emoji_max_size_mb(self) -> float: ...
    def get_emoji_do_replace(self) -> bool: ...
    
    # experimental 域（15次）
    def get_experimental_behavior_learning_list(self) -> list[str]: ...
    def get_experimental_enable_rich_reply(self) -> bool: ...
    def get_experimental_focus_mode(self) -> bool: ...
    def get_experimental_enable_behavior_learning(self) -> bool: ...
    
    # visual 域（10次）
    def get_visual_max_image_num(self) -> int: ...
    def get_visual_replyer_mode(self) -> str: ...
    
    # debug 域（10次）
    def get_debug_show_maisaka_thinking(self) -> bool: ...
    def get_debug_show_jargon_prompt(self) -> bool: ...
    
    # agent_autonomy 域（13次）— 整体引用模式
    def get_agent_autonomy_config(self) -> AgentAutonomySnapshot: ...
    
    # a_memorix 域（12次）— 整体引用模式
    def get_a_memorix_integration_config(self) -> AMemorixIntegrationSnapshot: ...
```

**整体引用处理**：`agent_autonomy`（8次整体引用）和 `a_memorix.integration`（4次整体引用）通过不可变快照返回，与 SessionInfo 快照模式一致。

### D5: AutonomyEventBusPort — 构造注入替代单例

```python
class AutonomyEventBusPort(Protocol):
    def subscribe(self, event_type: str, handler: AutonomyEventHandler) -> None: ...
    def unsubscribe(self, event_type: str, handler: AutonomyEventHandler) -> None: ...
    async def emit(self, event_type: str, data: dict) -> None: ...
    def emit_sync(self, event_type: str, data: dict) -> None: ...
```

**注入方式**：4 个消费者通过构造函数接收 `AutonomyEventBusPort`：
- `VitalityManager.__init__(..., event_bus: AutonomyEventBusPort)`
- `Orchestrator.__init__(..., event_bus: AutonomyEventBusPort)`
- `InteractionEngine.__init__(..., event_bus: AutonomyEventBusPort)`
- `AutonomyLogger.__init__(..., event_bus: AutonomyEventBusPort)`

**适配器**：`AutonomyEventBus` 自身实现 `AutonomyEventBusPort`，移除 `get_instance()` 单例，改为在 `main.py` 中创建实例并注入。

### D6: 注册点模式（与已有模式一致）

```python
# src/core/bot_config_port_registry.py
_bot_config_port: BotConfigPort | None = None

def register_bot_config_port(port: BotConfigPort) -> None: ...
def get_bot_config_port() -> BotConfigPort: ...
def reset_bot_config_port() -> None: ...

# src/core/chat_config_port_registry.py（同模式）
# src/core/app_config_port_registry.py（同模式）
# src/core/event_bus_port_registry.py（同模式）
```

**适配器**：
```python
# src/core/adapters/bot_config_port.py
class GlobalConfigBotConfigPort:
    def __init__(self) -> None:
        from src.config.config import global_config
        self._config = global_config
    
    def get_bot_nickname(self) -> str:
        return str(self._config.bot.nickname)
    # ...
```

**启动注册**（`main.py`）：
```python
register_bot_config_port(GlobalConfigBotConfigPort())
register_chat_config_port(GlobalConfigChatConfigPort())
register_app_config_port(GlobalConfigAppConfigPort())
register_event_bus_port(AutonomyEventBus())  # 同一实例
```

### D7: ruff TID251 守卫

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"src.config.config.global_config".msg = "Use BotConfigPort/ChatConfigPort/AppConfigPort via registry instead"
"src.config.config.config_manager".msg = "Use ModelConfigPort/GlobalConfigPort via registry instead"
"AutonomyEventBus.get_instance".msg = "Use AutonomyEventBusPort injection instead"
```

**豁免**（per-file-ignores）：
- `src/core/adapters/*.py` — 适配器层允许导入
- `src/main.py` — 启动入口，合法
- `src/config/*.py` — 配置定义自身
- `src/webui/**` — 本期不处理
- `src/learners/**` — 本期不处理

### D8: 分批策略

| 批次 | 范围 | 改动量 |
|------|------|--------|
| 0 | 配置清理：删除 15 项死配置 + 标记 13 项 DEPRECATED | ~5 文件（config.py + 模板 + 升级钩子） |
| 1 | Protocol 定义 + 适配器 + 注册点 + ruff 守卫 | 新增 ~6 文件 |
| 2 | core 层 M6 修复（identity.py + message_utils.py） | 2 文件 |
| 3 | maisaka/agent_autonomy/ 的 BotConfigPort + ChatConfigPort + AppConfigPort 迁移 | ~15 文件 |
| 4 | maisaka/ 其余模块迁移 | ~15 文件 |
| 5 | chat/services/common/plugin_runtime 迁移 | ~15 文件 |
| 6 | AutonomyEventBusPort 构造注入 | 5 文件 |

## 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/core/protocols.py` | 追加 BotConfigPort/ChatConfigPort/AppConfigPort/AutonomyEventBusPort |
| `src/core/types.py` | 追加 ReplyTimingSnapshot/ReplyStyleSnapshot/AgentAutonomySnapshot/AMemorixIntegrationSnapshot |
| `src/core/bot_config_port_registry.py` | BotConfigPort 注册点 |
| `src/core/chat_config_port_registry.py` | ChatConfigPort 注册点 |
| `src/core/app_config_port_registry.py` | AppConfigPort 注册点 |
| `src/core/event_bus_port_registry.py` | AutonomyEventBusPort 注册点 |
| `src/core/adapters/bot_config_port.py` | GlobalConfigBotConfigPort 适配器 |
| `src/core/adapters/chat_config_port.py` | GlobalConfigChatConfigPort 适配器 |
| `src/core/adapters/app_config_port.py` | GlobalConfigAppConfigPort 适配器 |

### 修改文件（批次2 — core 层 M6）

| 文件 | 改动 |
|------|------|
| `src/core/identity.py` | global_config → BotConfigPort |
| `src/core/message_utils.py` | global_config → BotConfigPort + ChatConfigPort |

### 修改文件（批次3-5 — 组件层迁移）

~45 文件，将 `from src.config.config import global_config` 替换为对应 Port 注册点调用。

### 修改文件（批次6 — AutonomyEventBus）

| 文件 | 改动 |
|------|------|
| `src/maisaka/agent_autonomy/event_bus.py` | 移除 `get_instance()` 单例，实现 AutonomyEventBusPort |
| `src/maisaka/agent_autonomy/vitality_manager.py` | 构造注入 event_bus |
| `src/maisaka/agent_autonomy/orchestrator.py` | 构造注入 event_bus |
| `src/maisaka/agent_interaction/engine.py` | 构造注入 event_bus |
| `src/maisaka/agent_autonomy/autonomy_logger.py` | 构造注入 event_bus |
| `src/main.py` | 创建 AutonomyEventBus 实例并注入 |

### 配置修改

| 文件 | 改动 |
|------|------|
| `pyproject.toml` | banned-api 守卫 + per-file-ignores |
| `src/core/adapters/__init__.py` | 新增导出 |
| `AGENTS.md` | 核心禁止项更新状态 |

## 风险与缓解

1. **AppConfigPort 方法过多**（~20 方法）→ 可接受，每个方法对应一个实际使用的配置属性，不是猜测性设计
2. **快照类型与 Pydantic 模型不同步**→ 快照是 frozen dataclass，属性名与 Pydantic 模型一致，适配器负责映射
3. **maisaka/ 30 处迁移工作量大**→ 分批处理，批次3-4 优先处理 agent_autonomy（与 H2 联动）
4. **AutonomyEventBus 改构造注入影响初始化顺序**→ main.py 中先创建 event_bus 实例，再注入到各消费者