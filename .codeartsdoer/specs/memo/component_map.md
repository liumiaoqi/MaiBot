# MaiBot 组件地图

> 2026-07-27，CA 通过 explore agent 自动采集
> 用途：查找组件真实类名和位置，避免"想改不知道叫什么"

## 一、启动序列（`src/main.py` → `MainSystem._init_components`）

### 入口与启动编排

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `MainSystem` | `src/main.py:32` | 系统主类，编排初始化和调度任务 |
| `StartupOrchestrator` | `src/core/startup/orchestrator.py:34` | 按6阶段执行启动初始化的编排器 |
| `StartupComponent` | `src/core/startup/types.py:32` | 启动组件描述（名称、阶段、顺序、是否关键） |
| `StartupPhase` | `src/core/startup/types.py:10` | 启动阶段枚举（CONFIG_LOAD/INFRASTRUCTURE/CORE_SERVICES/SUBSYSTEMS/SESSION_RESTORE/READY） |
| `StartupValidator` | `src/core/startup/validator.py:18` | 启动配置校验器 |

### 阶段 0：配置加载

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `ConfigManager` | `src/config/config.py:226` | 配置管理器，管理全局配置和模型配置，模块级单例 `config_manager` |
| `FileWatcher` | `src/config/file_watcher.py:50` | 配置文件热重载监视器 |

### 阶段 1：基础设施

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `run_startup_tool_record_vacuum_if_needed` | `src/services/tool_record_cleanup_service.py:138` | 启动时清理过期工具调用记录 |

### 阶段 2：核心服务（Port 与适配器层）

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `AgentConfigRegistry` | `src/maisaka/agent/registry.py:13` | 智能体配置注册表，加载和管理所有智能体配置 |
| `AgentConfigProviderAdapter` | `src/core/adapters/agent_config_port.py:39` | AgentConfigProvider Protocol 的适配器 |
| `AgentRouter` | `src/maisaka/agent/router.py:15` | 智能体路由器，根据会话绑定决定消息由哪个智能体处理 |
| `SessionStore` | `src/chat/message_receive/session_store.py:18` | 会话存储，管理 BotChatSession 的内存存储 |
| `MessageRegistry` | `src/chat/message_receive/message_registry.py:15` | 消息注册表，记录和查询历史消息 |
| `SessionNameCache` | `src/chat/message_receive/session_name_cache.py:7` | 会话名称缓存 |
| `SessionResolver` | `src/chat/message_receive/session_resolver.py:17` | 会话解析器，将平台消息映射到内部会话 |
| `BindingRestorer` | `src/chat/message_receive/binding_restorer.py:12` | 绑定恢复器，启动时从数据库恢复智能体-会话绑定关系 |
| `SessionLifecycle` | `src/chat/message_receive/session_lifecycle.py:23` | 会话生命周期管理 |
| `ChatManagerAdapter` | `src/core/adapters/chat_manager_adapter.py:26` | SessionRepository/SessionInfoPort/SessionLifecyclePort/SessionQueryPort 适配器 |
| `ChatManagerRoutingAdapter` | `src/core/adapters/routing_adapter.py:14` | AgentRoutingService Protocol 适配器 |
| `ReplyerManager` | `src/chat/replyer/replyer_manager.py:14` | 回复管理器，协调回复生成和发送 |
| `ReplyerServiceAdapter` | `src/core/adapters/replyer_service_adapter.py:7` | ReplyerServicePort Protocol 适配器 |
| `ImageManager` | `src/chat/image_system/image_manager.py:48` | 图像管理器 |
| `ImageDescriptionAdapter` | `src/core/adapters/image_description_adapter.py:7` | ImageDescriptionPort Protocol 适配器 |
| `HeartflowRuntimeRegistry` | `src/core/adapters/runtime_registry.py:13` | ChatRuntimeRegistry Protocol 适配器 |
| `MaisakaRuntimeFactory` | `src/maisaka/runtime.py:2306` | ChatRuntimeFactory Protocol 实现 |
| `ConfigManagerModelConfigPort` | `src/core/adapters/model_config_port.py:18` | ModelConfigPort Protocol 适配器 |
| `LLMServiceAdapter` | `src/core/adapters/llm_service_port.py:46` | LLMService Protocol 适配器 |
| `ChatBot` | `src/chat/message_receive/bot.py:164` | 消息接收处理核心，模块级单例 `chat_bot` |
| `ChatBotMessageIngestionPort` | `src/core/adapters/message_ingestion_port.py:36` | MessageIngestionPort Protocol 适配器 |
| `PersonInfoPortAdapter` | `src/core/adapters/person_info_port.py:15` | PersonInfoPort Protocol 适配器 |
| `GlobalConfigBotConfigPort` | `src/core/adapters/bot_config_port.py:6` | BotConfigPort Protocol 适配器 |
| `GlobalConfigChatConfigPort` | `src/core/adapters/chat_config_port.py:12` | ChatConfigPort Protocol 适配器 |
| `GlobalConfigAppConfigPort` | `src/core/adapters/app_config_port.py:14` | AppConfigPort Protocol 适配器 |
| `AutonomyEventBus` | `src/maisaka/agent_autonomy/event_bus.py:78` | 自主性事件总线 |
| `PromptManager` | `src/prompt/prompt_manager.py:108` | Prompt 模板管理器 |

### 阶段 3：子系统

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `PluginRuntimeManager` | `src/plugin_runtime/integration.py:68` | v1 插件运行时管理器 |
| `HostEndpoint` | `src/plugin_runtime_v2/host/endpoint.py:40` | v2 插件运行时 Host 端点 |
| `init_v2_host_endpoint` | `src/plugin_runtime_v2/bootstrap.py:23` | v2 插件运行时初始化函数 |
| `AMemorixHostService` | `src/A_memorix/host_service.py:73` | A_Memorix 记忆系统宿主服务 |
| `EmojiManager` | `src/emoji_system/emoji_manager.py:263` | Emoji 管理器 |

### 阶段 4：会话恢复

| 类/函数名　　　　　　　　 | 文件路径　　　　　　　　　　　　　　　　　| 职责　　　　　 |
| ---------------------------| -------------------------------------------| ----------------|
| `MemoryAutomationService` | `src/services/memory_flow_service.py:661` | 记忆自动化服务 |

### 阶段 5：就绪

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `EventBus` | `src/core/event_bus.py:23` | 核心事件总线 |
| `ThreadedWebUIServer` | `src/webui/webui_server.py:217` | WebUI 服务器 |
| `InteractionScheduler` | `src/maisaka/agent_interaction/scheduler.py:21` | 智能体交互调度器 |
| `AgentRelationshipManager` | `src/maisaka/agent_interaction/relationship_manager.py:27` | 智能体关系管理器 |

## 二、核心架构组件（不在启动序列中直接注册）

### 智能体自主性层（`src/maisaka/agent_autonomy/`）

| 类/函数名　　　　　　　　　　 | 文件路径　　　　　　　　　　　　　　　　　　　　　　　　　| 职责　　　　　　　　　　　　　　　　　　　 |
| -------------------------------| -----------------------------------------------------------| --------------------------------------------|
| `AgentOrchestrator`　　　　　 | `src/maisaka/agent_autonomy/orchestrator.py:38`　　　　　 | 智能体编排器，协调"谁在思考"　　　　　　　 |
| `ThinkingOrgan`　　　　　　　 | `src/maisaka/agent_autonomy/thinking_organ.py:42`　　　　 | 思维器官，执行工具循环　　　　　　　　　　 |
| `ThinkingOrganFactory`　　　　| `src/maisaka/agent_autonomy/thinking_organ_factory.py:19` | 思维器官工厂　　　　　　　　　　　　　　　 |
| `AutonomousAgent`　　　　　　 | `src/maisaka/agent_autonomy/agent.py:27`　　　　　　　　　| 自主智能体，封装内心世界+思维器官+表达器官 |
| `InnerWorld`　　　　　　　　　| `src/maisaka/agent_autonomy/inner_world.py:23`　　　　　　| 内心世界，维护情绪+欲望+记忆　　　　　　　 |
| `EmotionManager`　　　　　　　| `src/maisaka/agent/emotion.py:70`　　　　　　　　　　　　 | 情绪管理器，7种情绪　　　　　　　　　　　　|
| `InnerNeedEngine`　　　　　　 | `src/maisaka/agent_autonomy/inner_need.py:177`　　　　　　| 内需引擎（欲望系统）　　　　　　　　　　　 |
| `VitalityManager`　　　　　　 | `src/maisaka/agent_autonomy/vitality_manager.py:33`　　　 | 活力管理器，主动发言决策　　　　　　　　　 |
| `ExpressionOrgan`　　　　　　 | `src/maisaka/agent_autonomy/expression_organ.py:7`　　　　| 表达器官　　　　　　　　　　　　　　　　　 |
| `InnerVoiceGenerator`　　　　 | `src/maisaka/agent_autonomy/inner_voice.py:40`　　　　　　| 内心独白生成器　　　　　　　　　　　　　　 |
| `ExperienceWriter`　　　　　　| `src/maisaka/agent_autonomy/experience_writer.py:22`　　　| 体验写入器　　　　　　　　　　　　　　　　 |
| `BehaviorIntentEngine`　　　　| `src/maisaka/agent_autonomy/behavior_intent.py:239`　　　 | 行为意图引擎　　　　　　　　　　　　　　　 |
| `Butler`　　　　　　　　　　　| `src/maisaka/agent_autonomy/butler.py:53`　　　　　　　　 | 管家，三层过滤　　　　　　　　　　　　　　 |
| `ParallelThinkScheduler`　　　| `src/maisaka/agent_autonomy/parallel_think.py:17`　　　　 | 并行思考调度器　　　　　　　　　　　　　　 |
| `AgentLifecycleManager`　　　 | `src/maisaka/agent_autonomy/lifecycle.py:49`　　　　　　　| 智能体生命周期管理　　　　　　　　　　　　 |
| `VitalityTickScheduler`　　　 | `src/maisaka/agent_autonomy/vitality_tick.py:17`　　　　　| 活力心跳调度器　　　　　　　　　　　　　　 |
| `ReminderManager`　　　　　　 | `src/maisaka/agent_autonomy/reminder.py:272`　　　　　　　| 提醒管理器　　　　　　　　　　　　　　　　 |
| `InterjectionScheduler`　　　 | `src/maisaka/agent_autonomy/interjection_scheduler.py:25` | 插话调度器　　　　　　　　　　　　　　　　 |
| `InterjectionCooldownManager` | `src/maisaka/agent_autonomy/interjection_cooldown.py:13`　| 插话冷却管理器　　　　　　　　　　　　　　 |
| `AmbientAwarenessProcessor`　 | `src/maisaka/agent_autonomy/ambient_awareness.py:19`　　　| 环境感知处理器　　　　　　　　　　　　　　 |
| `SessionRecoveryService`　　　| `src/maisaka/agent_autonomy/session_recovery.py:15`　　　 | 会话恢复服务　　　　　　　　　　　　　　　 |

### 智能体交互层（`src/maisaka/agent_interaction/`）

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `InteractionEngine` | `src/maisaka/agent_interaction/engine.py:37` | 交互引擎 |
| `MonologueEngine` | `src/maisaka/agent_interaction/monologue_engine.py:68` | 独白引擎 |
| `MemoryDrivenTrigger` | `src/maisaka/agent_interaction/triggers/memory_driven.py:29` | 记忆驱动触发器 |
| `EchoDetector` | `src/maisaka/agent_interaction/echo_detector.py:23` | 回声检测器 |

## 三、聊天管理层

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `ChatManager` | `src/chat/message_receive/chat_manager.py:26` | 聊天管理器 |
| `HeartflowManager` | `src/chat/heart_flow/heartflow_manager.py:17` | 心流管理器（模块级单例 `heartflow_manager`） |
| `SendServiceMessagePortV2` | `src/services/send_service.py:1359` | MessagePortV2 Protocol 实现 |

## 四、核心数据类型（`src/core/types.py`）

| 类/函数名 | 职责 |
|-----------|------|
| `CoreMessage` | 平台无关的入站消息 |
| `SessionInfo` | 不可变会话快照 |
| `NoticeKind` | 通知类型枚举（AMBIENT/INTERACTION/INPUT_STATUS/UNKNOWN） |
| `ThinkResult` | 思考结果（action/text/reply_sent/silence_reason/thought_summary） |
| `ThinkCycleLog` | 思考循环日志 |
| `SilenceReason` | 沉默原因枚举（7种） |

## 五、核心 Protocol 接口（`src/core/protocols.py`）

| Protocol 名 | 职责 | 实现者 |
|-------------|------|--------|
| `SessionRepository` | 会话查询 | `ChatManagerAdapter` |
| `AgentRoutingService` | �9智能体路由 | `ChatManagerRoutingAdapter` |
| `ChatRuntime` | 聊天运行时 | `MaisakaHeartFlowChatting` |
| `MessageIngestionPort` | 消息摄入 | `ChatBotMessageIngestionPort` |
| `ChatRuntimeRegistry` | 运行时注册表 | `HeartflowRuntimeRegistry` |
| `ChatRuntimeFactory` | 运行时工厂 | `MaisakaRuntimeFactory` |
| `MemoryServicePort` | 记忆服务（16方法） | `AMemorixMemoryServicePort` |
| `ThinkingOrgan` | 思维管道 | `ThinkingOrgan` |
| `MessagePortV2` | 统一消息发送 | `SendServiceMessagePortV2` |
| `ModelConfigPort` | 模型配置查询 | `ConfigManagerModelConfigPort` |
| `ReplyerServicePort` | 回复服务 | `ReplyerServiceAdapter` |
| `ImageDescriptionPort` | 图像描述 | `ImageDescriptionAdapter` |
| `AgentConfigProvider` | 智能体配置 | `AgentConfigProviderAdapter` |
| `LLMService` | LLM服务 | `LLMServiceAdapter` |
| `PersonInfoPort` | 人物信息 | `PersonInfoPortAdapter` |
| `BotConfigPort` | 机器人配置 | `GlobalConfigBotConfigPort` |
| `ChatConfigPort` | 聊天配置 | `GlobalConfigChatConfigPort` |
| `AppConfigPort` | 应用配置 | `GlobalConfigAppConfigPort` |
| `AutonomyEventBusPort` | 事件总线 | `AutonomyEventBus` |

## 六、记忆系统（`src/A_memorix/`）

| 类/函数名 | 文件路径 | 职责 |
|3-----------|---------|------|
| `AMemorixHostService` | `src/A_memorix/host_service.py:73` | 记忆系统宿主服务 |
| `AMemorixMemoryServicePort` | `src/core/adapters/memory_service.py:35` | MemoryServicePort 适配器（16方法） |
| `SDKMemoryKernel` | `src/A_memorix/core/runtime/sdk_memory_kernel.py:42` | SDK 记忆内核 |
| `NarrativeWeaver` | `src/A_memorix/core/connectionist/narrative/narrative_weaver.py:78` | 叙事编织器 |
| `CognitiveStratifier` | `src/A_memorix/core/connectionist/cognitive/cognitive_stratifier.py:47` | 认知分层器 |
| `LifecycleManager` | `src/A_memorix/core/connectionist/lifecycle/lifecycle_manager.py:26` | 生命周期管理器 |
| `IntuitionEngine` | `src/A_memorix/core/connectionist/intuition/intuition_engine.py:28` | 直觉引擎（≤50ms） |
| `MemoryField` | `src/A_memorix/core/connectionist/memory_field.py:40` | 记忆场 |

## 七、v2 插件运行时（`src/plugin_runtime_v2/`）

### Host 端

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `HostEndpoint` | `src/plugin_runtime_v2/host/endpoint.py:40` | Host 端点 |
| `RunnerSupervisor` | `src/plugin_runtime_v2/host/runner_supervisor.py:65` | Runner 监管器 |
| `RunnerSpawner` | `src/plugin_runtime_v2/host/runner_spawner.py:29` | Runner 生成器 |
| `LogForwarder` | `src/plugin_runtime_v2/host/log_forwarder.py:13` | 日志转发器 |
| `EventDispatcher` | `src/plugin_runtime_v2/mcp/event_dispatcher.py:21` | v2 事件分发器 |
| `MCPHostBridge` | `src/plugin_runtime_v2/mcp/host_bridge.py:22` | MCP Host 桥接层 |

### Runner 端

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `RunnerEndpoint` | `src/plugin_runtime_v2/runner/endpoint.py:46` | Runner 端点 |
| `PluginLoader` | `src/plugin_runtime_v2/runner/plugin_loader>py:16` | v2 插件加载器 |
| `PluginContext` | `src/plugin_runtime_v2/sdk/context.py:113` | 插件上下文 |

## 八、Maisaka 子系统

| 类/函数名 | 文件路径 | 职责 |
|-----------|---------|------|
| `DreamAgent` | `src/maisaka/subagent/agents/dream.py:77` | 梦境智能体 |
| `CompactionAgent` | `src/maisaka/subagent/agents/compaction.py:96` | 压缩智能体 |
| `GoalManager` | `src/maisaka/goal/manager.py:72` | 目标管理器 |
| `TimeAwarenessService` | `src/maisaka/time_awareness/service.py:22` | 时间感知服务 |
| `CrossChatContextService` | `src/maisaka/cross_chat/service.py:19` | 跨聊天上下文服务 |
| `KnowledgeStore` | `src/maisaka/consolidation/knowledge_store.py:81` | 知识存储 |

---

总计约 120 个核心类/函数。启动序列 31 步，核心 Protocol 19 个，智能体自主性层 20+ 组件。