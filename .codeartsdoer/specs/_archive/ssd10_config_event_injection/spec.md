# SSD-10: 配置与事件注入化

## 背景

MaiBot 微内核架构要求核心只依赖 Protocol，不依赖组件具体实现。经过 SSD-1~9，核心层已通过 19 个 Protocol 接口完成大部分解耦。但配置访问和事件总线仍存在三类残留：

1. **M5**：`global_config`/`config_manager` 直接导入 100 处（排除 adapters/），其中 `global_config` 78 处无任何 Protocol 替代
2. **H2**：`AutonomyEventBus` 全局单例，6 个文件使用，无 Protocol 替代
3. **M6**：`core/` 层 2 个文件运行时直接导入 `global_config`，违反核心隔离原则

## 审计数据

### M5: config_manager/global_config 直接导入（100 处，排除 adapters/）

| 导入目标 | 行数 | 说明 |
|---------|------|------|
| global_config | 78 | 无 Protocol 替代，最大债务 |
| config_manager | 18 | 部分 TID251 标注过渡期兼容 |
| model_config | 4 | ModelConfigPort 已覆盖，低优先级 |
| **合计** | **100** | |

按目录分布（global_config 78 处）：

| 目录 | 行数 | 文件数 |
|------|------|--------|
| maisaka/ | 30 | 27 |
| webui/ | 9 | 8 |
| chat/ | 7 | 6 |
| common/ | 7 | 6 |
| learners/ | 6 | 6 |
| services/ | 5 | 5 |
| plugin_runtime/ | 4 | 4 |
| core/ | 2 | 2 |
| 其他 | 8 | 8 |

已有 Protocol：`ModelConfigPort`（6 方法）覆盖 model_config，但 **global_config 无任何 Protocol 替代**。

### H2: AutonomyEventBus 全局单例（6 文件，15 处引用）

| 文件 | 用途 |
|------|------|
| `event_bus.py` | 类定义 + 单例 |
| `vitality_manager.py` | emit("agent_state_change") |
| `orchestrator.py` | emit("session_message"/"interjection_mention") + subscribe |
| `agent_interaction/engine.py` | emit("interaction_signal") |
| `autonomy_logger.py` | subscribe 日志 |

**风险有限**：使用范围严格限定在 `maisaka/agent_autonomy/` 内部，未泄漏到核心层。

### M6: core 层直接导入 global_config（2 文件运行时违规）

| 文件 | 访问的配置属性 |
|------|--------------|
| `core/message_utils.py` | bot.nickname, bot.alias_names, chat.reply_timing |
| `core/identity.py` | bot.qq_account, bot.platforms |

## 需求

### N1: 定义 GlobalConfigPort Protocol

为 `global_config` 提供与 `ModelConfigPort` 同级的 Protocol 接口，覆盖核心和组件最常访问的配置属性。

**接口设计原则**：
- 不暴露 `global_config` 对象本身，只暴露具体属性/方法
- 按功能域分组（bot 配置、chat 配置、behavior 配置等）
- 只协议化被实际使用的属性，不盲目暴露全部配置
- 适配器层（`core/adapters/`）负责从 `global_config` 读取并转发

**核心接口方法**（基于 78 处导入的实际使用分析）：

```python
class GlobalConfigPort(Protocol):
    # bot 域
    def get_bot_nickname(self) -> str: ...
    def get_bot_alias_names(self) -> list[str]: ...
    def get_bot_qq_account(self) -> str: ...
    def get_bot_platforms(self) -> list[dict]: ...
    
    # chat 域
    def get_reply_timing_config(self) -> ReplyTimingConfig: ...
    def get_max_context_messages(self) -> int: ...
    
    # behavior 域
    def get_heartbeat_interval(self) -> float: ...
    def get_interjection_config(self) -> InterjectionConfig: ...
```

> **注意**：具体方法列表需在设计阶段根据实际 `global_config` 属性访问统计确定。上面是初步框架。

### N2: 消除 core 层 global_config 直接导入（M6）

将 `core/message_utils.py` 和 `core/identity.py` 的 `global_config` 导入替换为 `GlobalConfigPort` 注入。

- `core/identity.py`：`get_bot_qq_account()` / `get_bot_platforms()` → 通过 GlobalConfigPort
- `core/message_utils.py`：`bot.nickname` / `bot.alias_names` / `chat.reply_timing` → 通过 GlobalConfigPort

### N3: 消除 core 层 config_manager 直接导入

搜索 `core/` 目录中所有 `config_manager` 直接导入，替换为 `ModelConfigPort` 或 `GlobalConfigPort`。

### N4: AutonomyEventBus 协议化（H2）

为 `AutonomyEventBus` 定义 Protocol 接口，消除 `get_instance()` 全局单例。

**接口设计**：
```python
class AutonomyEventBusPort(Protocol):
    def subscribe(self, event_type: str, handler: AutonomyEventHandler) -> None: ...
    def unsubscribe(self, event_type: str, handler: AutonomyEventHandler) -> None: ...
    async def emit(self, event_type: str, data: dict) -> None: ...
    def emit_sync(self, event_type: str, data: dict) -> None: ...
```

**注入方式**：通过构造函数注入到 `VitalityManager`、`Orchestrator`、`InteractionEngine`、`AutonomyLogger`，替代 `AutonomyEventBus.get_instance()`。

### N5: ruff TID251 守卫

在 `pyproject.toml` 的 `banned-api` 中添加对 `global_config` 和 `AutonomyEventBus.get_instance` 的守卫（排除 adapters/ 和合法豁免文件）。

## 不在范围内

- `model_config` 4 处直接导入（ModelConfigPort 已覆盖，低优先级）
- `webui/` 目录的 `global_config` 导入（WebUI 是展示层，不违反核心隔离，后续单独处理）
- `learners/` 目录的 `global_config` 导入（学习者模块独立性低，后续单独处理）
- `config_manager` 在 `main.py` 中的使用（启动入口，合法）

## 验收标准

1. `src/core/` 目录（排除 adapters/）零 `global_config` / `config_manager` 运行时导入
2. `GlobalConfigPort` Protocol 定义完成 + 适配器实现 + 注册点
3. `AutonomyEventBusPort` Protocol 定义完成 + 构造注入替代 `get_instance()`
4. `pyproject.toml` banned-api 守卫覆盖 `global_config` 和 `AutonomyEventBus.get_instance`
5. `ruff check` 通过
6. AGENTS.md 核心禁止项更新状态

## 风险

1. **GlobalConfigPort 方法爆炸**：global_config 属性极多（bot/chat/behavior/emoji/memory...），如果全部协议化会导致接口臃肿。需要按功能域拆分子 Protocol 或只暴露实际使用的属性。
2. **maisaka/ 30 处 global_config 导入**：maisaka 是最大消费方，逐文件改造工作量大。可分批处理，优先 core 层。
3. **AutonomyEventBus 改构造注入**：4 个消费者需要修改构造函数签名，需确保不破坏初始化顺序。