# MaiBot 核心架构变革 — 编码任务规划

> 迁移策略：7 阶段渐进迁移，每阶段可独立验证，不一次性重写。
> 核心原则：组件兼容核心 — 核心定义接口契约，组件实现契约，核心不依赖组件具体实现。

---

## 阶段 1：基础设施 — 定义 Protocol + 数据模型

> 无破坏性，只新增定义，不修改存量代码。

### TASK-1-01: 创建 src/core/protocols.py — 定义核心 Protocol ✅

- [x] 创建 `src/core/protocols.py`，定义以下 7 个 Protocol（全部使用 `@runtime_checkable`）：
  - `SessionRepository` — 会话查询接口（`get_session`, `get_session_name`）
  - `AgentRoutingService` — 智能体路由接口（`resolve_agent`, `bind_session`, `unbind_session`, `get_primary_agent`, `get_session_all_agents`）
  - `ChatRuntime` — 运行时接口（`session_id`, `session_name`, `enqueue_proactive_task`, `start`, `stop`）
  - `ChatRuntimeRegistry` — 运行时注册表接口（`get_runtime`, `get_or_create_runtime`）
  - `NoticeClassifier` — 通知分类接口（`classify`）
  - `MemoryServicePort` — 记忆服务接口（`search`, `get_person_profile`, `build_profile_injection_text`）
  - `SessionInfoPort` — 会话信息反向查询接口（`get_session_info`）
- **依赖**：TASK-1-02（Protocol 引用的数据类型需先定义，但 Python 允许前向引用，可并行）
- **验收标准**：`from src.core.protocols import SessionRepository, AgentRoutingService, ChatRuntime, ChatRuntimeRegistry, NoticeClassifier, MemoryServicePort, SessionInfoPort` 在容器内导入成功，无报错
- **影响文件**：`src/core/protocols.py`（新增）
- **优先级**：极高

### TASK-1-02: 扩展 src/core/types.py — 新增核心数据模型

- [x] 在 `src/core/types.py` 中新增以下数据模型：
  - `NoticeKind` 枚举 — `AMBIENT` / `INTERACTION` / `INPUT_STATUS` / `UNKNOWN`
  - `CoreMessage` 数据类（`frozen=True, slots=True`）— 平台无关的核心消息，字段：`session_id`, `plain_text`, `is_notify`, `notice_kind`, `sender_id`, `sender_name`, `platform`, `timestamp`, `additional_data`
  - `SessionInfo` 数据类（`frozen=True, slots=True`）— 不可变会话快照，字段：`session_id`, `session_name`, `platform`, `is_group_session`, `group_id`, `group_name`, `user_id`, `user_nickname`, `primary_agent_id`, `cohabitant_agent_ids`
  - `ThinkContext` 数据类（`frozen=True, slots=True`）— 思考上下文，字段：`messages`, `emotion_state_text`, `relationship_text`, `memory_snippets`, `cohabitant_summary`, `trigger_reason`, `metadata`
  - `ThinkAction` 枚举 — `REPLY` / `TOOL_CALL` / `SILENT` / `ERROR`
  - `ThinkResult` 数据类（`slots=True`）— 思考结果，字段：`action`, `text`, `tool_calls`, `emotion_type`, `emotion_intensity`, `error_message`, `thinking_time_ms`
- **依赖**：无
- **验收标准**：`from src.core.types import NoticeKind, CoreMessage, SessionInfo, ThinkContext, ThinkAction, ThinkResult` 在容器内导入成功；`CoreMessage(session_id="test", plain_text="hello", is_notify=False)` 可正常实例化
- **影响文件**：`src/core/types.py`（修改）
- **优先级**：极高

### TASK-1-03: 迁移 CycleDetail 到 src/core/types.py

- [x] 将 `CycleDetail` 数据类从 `src/chat/heart_flow/heartFC_utils.py` 迁移到 `src/core/types.py`
- [x] 在 `src/chat/heart_flow/heartFC_utils.py` 中删除 `CycleDetail` 定义，改为从 `src.core.types` 导入并重导出
- [x] 全局搜索所有 `from src.chat.heart_flow.heartFC_utils import CycleDetail` 的导入，确认无需修改（原路径仍可导入）
- **依赖**：TASK-1-02（需要 `src/core/types.py` 已存在）
- **验收标准**：`from src.core.types import CycleDetail` 和 `from src.chat.heart_flow.heartFC_utils import CycleDetail` 均可导入成功；`rg "class CycleDetail" src/core/types.py` 有匹配；`rg "class CycleDetail" src/chat/heart_flow/heartFC_utils.py` 无匹配
- **影响文件**：`src/core/types.py`（修改）、`src/chat/heart_flow/heartFC_utils.py`（修改）
- **优先级**：高

---

## 阶段 2：适配器层 — 新增适配器文件

> 无破坏性，只新增适配器文件，不修改存量代码。适配器是唯一允许导入组件具体类的地方。

### TASK-2-01: 创建 src/core/adapters/ 包及 ChatManagerSessionRepository

- [x] 创建 `src/core/adapters/__init__.py`（空包或导出适配器类）
- [x] 创建 `src/core/adapters/session_repository.py`，实现 `ChatManagerSessionRepository`：
  - 实现 `SessionRepository` Protocol 的 `get_session(session_id)` 和 `get_session_name(session_id)` 方法
  - 内部延迟导入 `chat_manager`，将 `BotChatSession` 转换为不可变 `SessionInfo` 快照
  - 构造函数接收 `AgentRoutingService` 实例，用于查询 `primary_agent_id` 和 `cohabitant_agent_ids`
- **依赖**：TASK-1-01（SessionRepository Protocol）、TASK-1-02（SessionInfo 数据类）
- **验收标准**：`from src.core.adapters.session_repository import ChatManagerSessionRepository` 导入成功；`isinstance(ChatManagerSessionRepository(routing_service), SessionRepository)` 返回 True
- **影响文件**：`src/core/adapters/__init__.py`（新增）、`src/core/adapters/session_repository.py`（新增）
- **优先级**：极高

### TASK-2-02: 创建 ChatManagerRoutingAdapter

- [x] 创建 `src/core/adapters/routing_adapter.py`，实现 `ChatManagerRoutingAdapter`：
  - 实现 `AgentRoutingService` Protocol 的全部方法：`resolve_agent`, `bind_session`, `unbind_session`, `get_primary_agent`, `get_session_all_agents`
  - 内部延迟导入 `chat_manager`，通过 `_ensure_router()` 获取 `chat_manager._agent_router`
  - `get_session_all_agents` 返回 `frozenset[str]`（不可变集合）
  - `bind_session` 捕获 `ValueError` 返回 `False`
- **依赖**：TASK-1-01（AgentRoutingService Protocol）、TASK-1-02（AgentConfig 类型）
- **验收标准**：`from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter` 导入成功；`isinstance(ChatManagerRoutingAdapter(), AgentRoutingService)` 返回 True
- **影响文件**：`src/core/adapters/routing_adapter.py`（新增）
- **优先级**：极高

### TASK-2-03: 创建 HeartflowRuntimeRegistry

- [x] 创建 `src/core/adapters/runtime_registry.py`，实现 `HeartflowRuntimeRegistry`：
  - 实现 `ChatRuntimeRegistry` Protocol 的 `get_runtime(session_id)` 和 `get_or_create_runtime(session_id)` 方法
  - 内部延迟导入 `heartflow_manager`，查询 `heartflow_manager.heartflow_chat_list`
  - 返回类型注解为 `ChatRuntime`（实际返回 `MaisakaHeartFlowChatting` 实例，Python Protocol 结构化子类型）
- **依赖**：TASK-1-01（ChatRuntimeRegistry Protocol、ChatRuntime Protocol）
- **验收标准**：`from src.core.adapters.runtime_registry import HeartflowRuntimeRegistry` 导入成功；`isinstance(HeartflowRuntimeRegistry(), ChatRuntimeRegistry)` 返回 True
- **影响文件**：`src/core/adapters/runtime_registry.py`（新增）
- **优先级**：高

### TASK-2-04: 创建 NapCatNoticeClassifier

- [x] 创建 `src/core/adapters/notice_classifier.py`，实现 `NapCatNoticeClassifier`：
  - 实现 `NoticeClassifier` Protocol 的 `classify(message)` 方法
  - 定义 `_NAPCAT_AMBIENT_SUBTYPES`、`_NAPCAT_INTERACTION_SUBTYPES`、`_NAPCAT_INPUT_STATUS_SUBTYPES` 三个 `frozenset`
  - `_extract_napcat_sub_type(message)` 方法从消息中提取 `napcat_notice_sub_type`
  - 分类逻辑：INPUT_STATUS → AMBIENT → INTERACTION → UNKNOWN
- **依赖**：TASK-1-01（NoticeClassifier Protocol）、TASK-1-02（NoticeKind 枚举）
- **验收标准**：`from src.core.adapters.notice_classifier import NapCatNoticeClassifier` 导入成功；`isinstance(NapCatNoticeClassifier(), NoticeClassifier)` 返回 True；`NapCatNoticeClassifier().classify(mock_ambient_message)` 返回 `NoticeKind.AMBIENT`
- **影响文件**：`src/core/adapters/notice_classifier.py`（新增）
- **优先级**：高

---

## 阶段 3：核心模块迁移 — 逐步替换导入

> 逐步将核心模块对组件具体类的直接导入替换为 Protocol 接口。每替换一个模块，验证导入链路。

### TASK-3-01: Orchestrator — chat_manager → AgentRoutingService + NoticeClassifier

- [x] 修改 `src/maisaka/agent_autonomy/orchestrator.py`：
  - 构造函数新增 `routing_service: AgentRoutingService | None = None` 和 `notice_classifier: NoticeClassifier | None = None` 参数
  - 默认值从全局适配器获取（`_get_default_routing_service()` / `_get_default_notice_classifier()`）
  - 替换 `activate_agent()` 中 `from src.chat.message_receive.chat_manager import chat_manager` → `self._routing_service.bind_session()`
  - 替换 `deactivate_agent()` 中 `chat_manager.agent_router.unbind_session()` → `self._routing_service.unbind_session()`
  - 替换 `_classify_notice()` 中 `getattr` 链式访问 `napcat_notice_sub_type` → `self._notice_classifier.classify()`
  - 删除 `AMBIENT_NOTICE_SUBTYPES` 常量定义（如果存在于此文件中）
- **依赖**：TASK-1-01、TASK-2-02、TASK-2-04
- **验收标准**：`rg "from src.chat.message_receive.chat_manager import" src/maisaka/agent_autonomy/orchestrator.py` 为 0 匹配；`rg "napcat_" src/maisaka/agent_autonomy/orchestrator.py` 为 0 匹配；容器内 `from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator` 导入成功
- **影响文件**：`src/maisaka/agent_autonomy/orchestrator.py`（修改）
- **优先级**：极高

### TASK-3-02: VitalityManager — chat_manager → AgentRoutingService

- [x] 修改 `src/maisaka/agent_autonomy/vitality_manager.py`：
  - 构造函数新增 `routing_service: AgentRoutingService | None = None` 参数
  - 替换 `sync_standby_agents()` 中 `from src.chat.message_receive.chat_manager import chat_manager` → `self._routing_service`
  - 替换 `get_cohabitation_params()` 中 `chat_manager.agent_router` → `self._routing_service`
- **依赖**：TASK-1-01、TASK-2-02
- **验收标准**：`rg "from src.chat.message_receive.chat_manager import" src/maisaka/agent_autonomy/vitality_manager.py` 为 0 匹配；容器内 `from src.maisaka.agent_autonomy.vitality_manager import VitalityManager` 导入成功
- **影响文件**：`src/maisaka/agent_autonomy/vitality_manager.py`（修改）
- **优先级**：高

### TASK-3-03: ChatLoopServiceAdapter — MaisakaHeartFlowChatting → ChatRuntime

- [x] 修改 `src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py`：
  - 替换 `from src.maisaka.runtime import MaisakaHeartFlowChatting` → 依赖 `ChatRuntime` Protocol
  - 类型注解从 `MaisakaHeartFlowChatting` 改为 `ChatRuntime`
  - `switch_agent_context()` 不再直接修改 `self._chat_loop_service._agent_id`，改为通过 ChatRuntime 接口操作
  - `enqueue_proactive_task()` 通过 ChatRuntime 接口调用
- **依赖**：TASK-1-01（ChatRuntime Protocol）、TASK-2-03（HeartflowRuntimeRegistry）
- **验收标准**：`rg "MaisakaHeartFlowChatting" src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py` 为 0 匹配；容器内 `from src.maisaka.agent_autonomy.bridge.chat_loop_adapter import ChatLoopServiceAdapter` 导入成功
- **影响文件**：`src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py`（修改）
- **优先级**：高

### TASK-3-04: HeartflowManager — MaisakaHeartFlowChatting → ChatRuntime + ChatRuntimeRegistry

- [x] 修改 `src/chat/heart_flow/heartflow_manager.py`：
  - 替换 `from src.maisaka.runtime import MaisakaHeartFlowChatting` → 依赖 `ChatRuntime` Protocol
  - 替换 `from src.chat.message_receive.chat_manager import chat_manager` → 通过 `ChatRuntimeRegistry` 或 `SessionRepository` 接口
  - `heartflow_chat_list` 类型从 `OrderedDict[str, MaisakaHeartFlowChatting]` 改为 `OrderedDict[str, ChatRuntime]`
  - `get_or_create_heartflow_chat` 返回类型从 `MaisakaHeartFlowChatting` 改为 `ChatRuntime`
- **依赖**：TASK-1-01（ChatRuntime Protocol、ChatRuntimeRegistry Protocol）、TASK-2-03
- **验收标准**：`rg "MaisakaHeartFlowChatting" src/chat/heart_flow/heartflow_manager.py` 为 0 匹配；`rg "from src.chat.message_receive.chat_manager import" src/chat/heart_flow/heartflow_manager.py` 为 0 匹配；容器内 `from src.chat.heart_flow.heartflow_manager import heartflow_manager` 导入成功
- **影响文件**：`src/chat/heart_flow/heartflow_manager.py`（修改）
- **优先级**：高

### TASK-3-05: 阶段 3 静态验证

- [x] 执行以下静态检查，确认阶段 3 迁移完成：
  - `rg "from src.chat.message_receive.chat_manager import" src/maisaka/agent_autonomy/` — 应为 0 匹配
  - `rg "napcat_" src/maisaka/agent_autonomy/` — 应为 0 匹配
  - `rg "MaisakaHeartFlowChatting" src/maisaka/agent_autonomy/ src/chat/heart_flow/` — 应为 0 匹配
  - 容器内重启后，核心模块导入链路正常
- **依赖**：TASK-3-01、TASK-3-02、TASK-3-03、TASK-3-04
- **验收标准**：上述所有 rg 检查均为 0 匹配；容器重启后 bot 正常启动
- **影响文件**：无（验证任务）
- **优先级**：高

---

## 阶段 4：通知分类统一 — 消除 napcat_* 泄漏

> 统一通知分类逻辑，消除 DRY 违反和平台字段泄漏。

### TASK-4-01: runtime.py — _is_ambient_notice → NoticeClassifier

- [x] 修改 `src/maisaka/runtime.py`：
  - 替换 `_is_ambient_notice()` 方法为 `NoticeClassifier` 接口调用
  - 删除 `_AMBIENT_NOTICE_SUBTYPES` 常量定义
  - 通过构造函数注入或默认适配器获取 `NoticeClassifier` 实例
  - 通知分类逻辑改为读取 `CoreMessage.notice_kind` 枚举值（新路径），兼容旧消息格式（回退读取 `additional_config.napcat_notice_sub_type`）
- **依赖**：TASK-1-01、TASK-2-04、TASK-3-01
- **验收标准**：`rg "_AMBIENT_NOTICE_SUBTYPES" src/maisaka/runtime.py` 为 0 匹配；`rg "_is_ambient_notice" src/maisaka/runtime.py` 为 0 匹配；容器内 `from src.maisaka.runtime import MaisakaHeartFlowChatting` 导入成功
- **影响文件**：`src/maisaka/runtime.py`（修改）
- **优先级**：高

### TASK-4-02: 删除 orchestrator.py 中的重复通知分类定义

- [x] 确认 `orchestrator.py` 中的 `AMBIENT_NOTICE_SUBTYPES` 和 `_classify_notice` 已在 TASK-3-01 中删除
- [x] 如果仍有残留，清理之
- [x] 全局搜索确认 `AMBIENT_NOTICE_SUBTYPES` 只在 `src/core/adapters/notice_classifier.py` 中定义一次
- **依赖**：TASK-3-01、TASK-4-01
- **验收标准**：`rg "AMBIENT_NOTICE_SUBTYPES" src/maisaka/` 为 0 匹配；`rg "napcat_notice_sub_type" src/maisaka/ src/core/` 为 0 匹配（适配器内部除外）
- **影响文件**：`src/maisaka/agent_autonomy/orchestrator.py`（确认清理）
- **优先级**：高

### TASK-4-03: 阶段 4 静态验证

- [x] 执行以下静态检查：
  - `rg "AMBIENT_NOTICE_SUBTYPES" src/maisaka/` — 应为 0 匹配
  - `rg "napcat_notice_sub_type" src/maisaka/ src/core/` — 应仅在适配器中出现
  - 容器内重启后，通知消息处理正常
- **依赖**：TASK-4-01、TASK-4-02
- **验收标准**：上述检查通过；容器重启后通知消息（戳一戳、输入状态等）分类正确
- **影响文件**：无（验证任务）
- **优先级**：高

---

## 阶段 5：Agent-owns-Thinking 变革 — 核心架构变革

> 这是最核心的变革阶段。每个智能体拥有自己的思维管道（ThinkingOrgan），Orchestrator 只协调"谁在思考"，不关心"怎么思考"。
> 插话和提醒不再走 enqueue_proactive_task 伪装，而是直接触发目标智能体的 ThinkingOrgan。

### TASK-5-01: 在 protocols.py 中新增 ThinkingOrgan Protocol

- [x] 在 `src/core/protocols.py` 中新增 `ThinkingOrgan` Protocol：
  - `agent_id` 属性 — 所属智能体 ID
  - `is_degraded` 属性 — 是否降级
  - `think(context: ThinkContext) -> ThinkResult` — 执行一次思考
  - `think_proactive(reason: str, context: ThinkContext) -> ThinkResult` — 执行一次主动思考
- [x] 在 `src/core/protocols.py` 中新增 `ThinkingOrganFactory` Protocol：
  - `create(agent_id: str, session_id: str) -> ThinkingOrgan` — 为智能体创建思维管道
- **依赖**：TASK-1-01、TASK-1-02（ThinkContext、ThinkResult 数据模型）
- **验收标准**：`from src.core.protocols import ThinkingOrgan, ThinkingOrganFactory` 导入成功；`isinstance` 检查通过
- **影响文件**：`src/core/protocols.py`（修改）
- **优先级**：极高

### TASK-5-02: 让现有 ThinkingOrgan 类满足 Protocol

- [x] 修改 `src/maisaka/agent_autonomy/thinking_organ.py`：
  - 新增 `think(context: ThinkContext) -> ThinkResult` 方法：
    - 接收 `ThinkContext`（消息序列、情绪状态、关系描述、记忆片段等）
    - 构建系统提示词和人格提示词（复用现有 `build_system_prompt` / `build_personality_prompt`）
    - 调用 LLM（通过 Planner 或直接调用 LLM 客户端）
    - 返回 `ThinkResult`（回复文本、工具调用、或静默）
  - 新增 `think_proactive(reason: str, context: ThinkContext) -> ThinkResult` 方法：
    - 与 `think` 类似，但在提示词中注入主动思考原因（欲望/提醒/管家协调）
    - `trigger_reason` 为 `inner_need` / `reminder` / `butler_interjection`
  - 确保现有 `build_system_prompt`、`build_personality_prompt`、`get_prompt_template_name` 方法保持不变（向后兼容）
- **依赖**：TASK-5-01、TASK-1-02
- **验收标准**：`isinstance(ThinkingOrgan(...), ThinkingOrganProtocol)` 返回 True；`think()` 和 `think_proactive()` 方法可调用；现有 `build_system_prompt()` 等方法不受影响
- **影响文件**：`src/maisaka/agent_autonomy/thinking_organ.py`（修改）
- **优先级**：极高

### TASK-5-03: 创建 ThinkingOrganFactory

- [x] 创建 `src/maisaka/agent_autonomy/thinking_organ_factory.py`：
  - 实现 `ThinkingOrganFactory` Protocol 的 `create(agent_id, session_id)` 方法
  - 封装 ThinkingOrgan 的创建细节：`EmbodiedPlannerPromptBuilder` 构建、LLM 客户端注入等
  - 从 `AutonomousAgent.__init__` 中提取创建逻辑
- **依赖**：TASK-5-01、TASK-5-02
- **验收标准**：`from src.maisaka.agent_autonomy.thinking_organ_factory import ThinkingOrganFactory` 导入成功；`factory.create("silver_wolf", "session_123")` 返回 `ThinkingOrgan` 实例
- **影响文件**：`src/maisaka/agent_autonomy/thinking_organ_factory.py`（新增）
- **优先级**：极高

### TASK-5-04: 创建 ParallelThinkScheduler

- [x] 创建 `src/maisaka/agent_autonomy/parallel_think.py`：
  - 实现 `ParallelThinkScheduler` 类：
    - 构造函数接收 `max_concurrent: int = 2`，创建 `asyncio.Semaphore`
    - `schedule(agent_id, organ, context) -> asyncio.Task[ThinkResult]` — 调度一次思考
    - `wait_all() -> dict[str, ThinkResult]` — 等待所有待处理思考完成
    - `cancel(agent_id)` — 取消指定智能体的待处理思考
  - 使用 `asyncio.Semaphore` 控制并发数，避免同时发起过多 LLM 请求
- **依赖**：TASK-1-02（ThinkResult）、TASK-5-01（ThinkingOrgan Protocol）
- **验收标准**：`from src.maisaka.agent_autonomy.parallel_think import ParallelThinkScheduler` 导入成功；两个 mock ThinkingOrgan 并行思考时，总耗时接近 `max(A, B)` 而非 `A + B`
- **影响文件**：`src/maisaka/agent_autonomy/parallel_think.py`（新增）
- **优先级**：极高

### TASK-5-05: AutonomousAgent 持有 ThinkingOrgan 实例，通过工厂创建

- [x] 修改 `src/maisaka/agent_autonomy/agent.py`：
  - `AutonomousAgent.__init__` 改为接收 `ThinkingOrganFactory` 实例（可选，默认使用内置工厂）
  - `self._thinking_organ` 通过工厂创建，而非直接 `ThinkingOrgan(agent_id, self._prompt_builder)`
  - 新增 `thinking_organ` 属性，返回 `ThinkingOrgan` 实例
  - 保持 `_init_components()` 和 `_init_engines()` 的现有逻辑不变
- **依赖**：TASK-5-02、TASK-5-03
- **验收标准**：`agent.thinking_organ` 返回 `ThinkingOrgan` 实例；`isinstance(agent.thinking_organ, ThinkingOrganProtocol)` 返回 True；现有 `agent.thinking_organ.build_system_prompt()` 仍可调用
- **影响文件**：`src/maisaka/agent_autonomy/agent.py`（修改）
- **优先级**：极高

### TASK-5-06: Orchestrator 改造 — enqueue_proactive_task → agent.think()

- [x] 修改 `src/maisaka/agent_autonomy/orchestrator.py`：
  - 构造函数新增 `thinking_organ_factory: ThinkingOrganFactory | None = None` 参数
  - 新增 `ParallelThinkScheduler` 实例
  - 改造 `_trigger_interjection_for()`：
    - 当前：通过 `enqueue_proactive_task(plugin_id="maisaka_butler", ...)` 伪装多智能体插话
    - 目标：直接获取目标智能体的 `ThinkingOrgan`，调用 `organ.think(context)`，结果通过 `MessagePort.send()` 发出
  - 改造 `_reminder_tick_loop()`：
    - 当前：通过 `enqueue_proactive_task(plugin_id="maisaka_reminder", ...)` 触发提醒
    - 目标：直接获取主智能体的 `ThinkingOrgan`，调用 `organ.think_proactive(reason, context)`，结果通过 `MessagePort.send()` 发出
  - 删除所有 `enqueue_proactive_task` 用于多智能体插话/提醒的调用
  - 确认 `enqueue_proactive_task` 仅保留用于插件主动对话场景
- **依赖**：TASK-5-01、TASK-5-02、TASK-5-04、TASK-5-05
- **验收标准**：`rg "enqueue_proactive_task" src/maisaka/agent_autonomy/orchestrator.py` 为 0 匹配（或仅保留插件主动对话场景）；`rg "maisaka_butler|maisaka_reminder" src/maisaka/agent_autonomy/orchestrator.py` 为 0 匹配；管家插话 → 目标智能体的 `ThinkingOrgan.think()` 被调用 → 回复通过 `MessagePort.send()` 发出
- **影响文件**：`src/maisaka/agent_autonomy/orchestrator.py`（修改）
- **优先级**：极高

### TASK-5-07: 管家插话改造 — 直接触发目标智能体 ThinkingOrgan

- [x] 修改管家插话流程（`src/maisaka/agent_autonomy/orchestrator.py` 中的管家相关方法）：
  - 管家三层过滤完成后，不再走"插件主动对话"路径
  - 直接通过 `ParallelThinkScheduler.schedule()` 调度目标智能体的 `ThinkingOrgan.think()`
  - 构造 `ThinkContext`，`trigger_reason="butler_interjection"`
  - 思考完成后，`ThinkResult.action == REPLY` 时通过 `MessagePort.send()` 发出插话
  - 主智能体回复和共居智能体插话可并行执行
- **依赖**：TASK-5-06
- **验收标准**：管家插话流程中不再出现 `enqueue_proactive_task`；插话通过 `agent.thinking_organ.think()` 触发；主智能体回复和插话可并行
- **影响文件**：`src/maisaka/agent_autonomy/orchestrator.py`（修改）
- **优先级**：极高

### TASK-5-08: 提醒触发改造 — 直接触发主智能体 ThinkingOrgan

- [x] 修改提醒触发流程（`src/maisaka/agent_autonomy/orchestrator.py` 中的提醒相关方法）：
  - `_reminder_tick_loop()` 中，到期提醒不再走 `enqueue_proactive_task`
  - 直接获取主智能体的 `ThinkingOrgan`，调用 `organ.think_proactive(reason, context)`
  - 构造 `ThinkContext`，`trigger_reason="reminder"`，`metadata` 包含 `reminder_id` 和 `is_direct`
  - 思考完成后，`ThinkResult.action == REPLY` 时通过 `MessagePort.send()` 发出提醒消息
- **依赖**：TASK-5-06
- **验收标准**：提醒触发流程中不再出现 `enqueue_proactive_task`；提醒通过 `agent.thinking_organ.think_proactive()` 触发；提醒消息通过 `MessagePort.send()` 发出
- **影响文件**：`src/maisaka/agent_autonomy/orchestrator.py`（修改）
- **优先级**：极高

### TASK-5-09: 阶段 5 核心验证

- [x] 执行以下验证：
  - **静态检查**：
    - `rg "enqueue_proactive_task" src/maisaka/agent_autonomy/orchestrator.py` — 应为 0 匹配（管家插话和提醒不再走此路径）
    - `rg "maisaka_butler|maisaka_reminder" src/maisaka/agent_autonomy/orchestrator.py` — 应为 0 匹配
    - `rg "ThinkingOrgan" src/core/protocols.py` — 应有匹配
    - `rg "ParallelThinkScheduler" src/maisaka/agent_autonomy/` — 应有匹配
  - **功能验证**：
    - 管家插话 → 目标智能体的 `ThinkingOrgan.think()` 被调用 → 回复通过 `MessagePort.send()` 发出
    - 提醒触发 → 主智能体的 `ThinkingOrgan.think_proactive()` 被调用 → 回复通过 `MessagePort.send()` 发出
    - 主智能体回复和共居智能体插话可并行执行
  - **容器验证**：重启容器后 bot 正常启动，核心功能不受影响
- **依赖**：TASK-5-06、TASK-5-07、TASK-5-08
- **验收标准**：上述所有检查通过；容器重启后核心功能正常
- **影响文件**：无（验证任务）
- **优先级**：极高

---

## 阶段 6：A_memorix 隔离 — 内部函数不泄漏

> 消除核心对 A_memorix 内部模块的直接导入，以及 A_memorix 对 chat_manager 的反向依赖。

### TASK-6-01: person_profile.py — build_profile_injection_text → MemoryServicePort

- [x] 修改 `src/maisaka/memory/person_profile.py`：
  - 删除 `from src.A_memorix.core.utils.profile_text import build_profile_injection_text` 直接导入
  - 改为通过 `MemoryServicePort` Protocol 接口调用 `build_profile_injection_text`
  - 通过构造函数注入或全局适配器获取 `MemoryServicePort` 实例
- **依赖**：TASK-1-01（MemoryServicePort Protocol）
- **验收标准**：`rg "from src.A_memorix.core" src/maisaka/memory/person_profile.py` 为 0 匹配；容器内 `from src.maisaka.memory.person_profile import ...` 导入成功
- **影响文件**：`src/maisaka/memory/person_profile.py`（修改）
- **优先级**：中

### TASK-6-02: SDKMemoryKernel — chat_manager → SessionInfoPort

- [x] 修改 `src/A_memorix/core/runtime/sdk_memory_kernel.py`：
  - 删除 `from src.chat.message_receive.chat_manager import chat_manager` 直接导入
  - 改为通过 `SessionInfoPort` Protocol 接口获取会话信息
  - ⚠️ 此文件属于 A_memorix 模块，修改前需阅读 `src/A_memorix/MODIFICATION_POLICY.md`
- **依赖**：TASK-1-01（SessionInfoPort Protocol）、TASK-1-02（SessionInfo 数据类）
- **验收标准**：`rg "from src.chat.message_receive.chat_manager import" src/A_memorix/` 为 0 匹配；容器内 A_memorix 功能正常
- **影响文件**：`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改）
- **优先级**：中

### TASK-6-03: 阶段 6 静态验证

- [x] 执行以下静态检查：
  - `rg "from src.A_memorix.core" src/maisaka/` — 应为 0 匹配
  - `rg "from src.chat.message_receive.chat_manager import" src/A_memorix/` — 应为 0 匹配
  - 容器内重启后，记忆检索功能正常
- **依赖**：TASK-6-01、TASK-6-02
- **验收标准**：上述检查通过；容器重启后记忆功能正常
- **影响文件**：无（验证任务）
- **优先级**：中

---

## 阶段 7：MessagePort 全面采用 — 内置工具统一走 MessagePort

> 内置工具和插件运行时发送消息统一通过 MessagePort，不再直接调用 send_service。

### TASK-7-01: 内置工具 — send_service → MessagePort

- [x] 修改 `src/maisaka/builtin_tool/` 下的内置工具文件：
  - `reply.py` — 替换 `send_service` 直接调用为 `MessagePort.send()`
  - `send_image.py` — 替换 `send_service` 直接调用为 `MessagePort` 扩展接口
  - `send_emoji.py` — 替换 `send_service` 直接调用为 `MessagePort` 扩展接口
  - 其他涉及消息发送的内置工具 — 统一替换
  - 通过 `BuiltinToolRuntimeContext` 注入 `MessagePort` 实例
- **依赖**：TASK-1-01（MessagePort Protocol 已存在于 `src/maisaka/message_port.py`）
- **验收标准**：`rg "from src.services.send_service import" src/maisaka/builtin_tool/` 为 0 匹配；容器内内置工具发送消息功能正常
- **影响文件**：`src/maisaka/builtin_tool/reply.py`、`src/maisaka/builtin_tool/send_image.py`、`src/maisaka/builtin_tool/send_emoji.py`、`src/maisaka/builtin_tool/context.py`（修改）
- **优先级**：中

### TASK-7-02: 阶段 7 静态验证

- [x] 执行以下静态检查：
  - `rg "from src.services.send_service import" src/maisaka/builtin_tool/` — 应为 0 匹配
  - 容器内重启后，内置工具（reply、send_image、send_emoji）发送消息功能正常
- **依赖**：TASK-7-01
- **验收标准**：上述检查通过；容器重启后内置工具功能正常
- **影响文件**：无（验证任务）
- **优先级**：中

---

## 最终验证：全局架构债务消除确认

### TASK-FINAL-01: 全局静态检查

- [x] 执行以下全局静态检查，确认所有架构债务已消除：
  - `rg "from src.chat.message_receive.chat_manager import" src/core/ src/maisaka/agent_autonomy/` — 应为 0 匹配
  - `rg "napcat_" src/core/ src/maisaka/agent_autonomy/` — 应为 0 匹配
  - `rg "enqueue_proactive_task" src/maisaka/agent_autonomy/orchestrator.py` — 应为 0 匹配（或仅保留插件主动对话场景）
  - `rg "MaisakaHeartFlowChatting" src/maisaka/agent_autonomy/ src/chat/heart_flow/heartflow_manager.py` — 应为 0 匹配
  - `rg "from src.A_memorix.core" src/maisaka/` — 应为 0 匹配
  - `rg "from src.services.send_service import" src/maisaka/builtin_tool/` — 应为 0 匹配
- **依赖**：所有阶段任务完成
- **验收标准**：上述所有检查通过
- **影响文件**：无（验证任务）
- **优先级**：高

### TASK-FINAL-02: 端到端功能验证

- [x] 在容器内执行端到端功能验证：
  - 用户消息到达 → 智能体回复正常
  - 通知消息（戳一戳、输入状态）→ 分类正确，AMBIENT 不触发 Planner
  - 管家插话 → 共居智能体通过 `ThinkingOrgan.think()` 插话
  - 提醒触发 → 主智能体通过 `ThinkingOrgan.think_proactive()` 主动发言
  - 心跳评估 → 欲望驱动主动发言正常
  - 记忆检索 → A_memorix 通过 `MemoryServicePort` 正常返回记忆
  - 内置工具 → 通过 `MessagePort` 发送消息正常
- **依赖**：TASK-FINAL-01
- **验收标准**：所有端到端场景验证通过
- **影响文件**：无（验证任务）
- **优先级**：高