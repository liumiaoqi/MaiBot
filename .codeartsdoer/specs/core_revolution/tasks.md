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

---

## 阶段 7：SDKMemoryKernel 革命性重构

> **设计哲学**：面对 9650 行的 God Class，不是用持续打补丁的方式去助长它的混乱，而是用革命的手段去扬弃它。保留精华（记忆检索、人物画像、关系图谱的核心能力），抛弃糟粕（God Class、过度防御、字符串分发、代理层冗余）。
>
> **目标**：SDKMemoryKernel 从 9650 行 → ≤800 行薄协调层；9 个功能域服务拆分到 `services/`；11 个 Admin Handler 拆分到 `admin/`；3 个配置数据类拆分到 `config/`；删除 `_KernelRuntimeFacade`、47 处 `getattr`、466 处 `or ""` 兜底。
>
> **5 阶段迁移**：7A 基础设施 → 7B 功能域提取 → 7C Admin Handler → 7D Kernel 瘦身清理 → 7E 验证
>
> **核心约束**：
> - 外部 API 签名不变（`host_service` / `plugin.py` 的调用方式不变）
> - 子模块不反向持有 `SDKMemoryKernel` 引用
> - 不引入新的循环依赖
> - 数据目录结构和持久化格式不变

---

### 阶段 7A：基础设施 — 配置数据类 + Admin Handler 基类 + 服务包

> 无破坏性，只新增定义和空包，不修改存量代码。

#### TASK-7A-01: 创建 config/ 包及 FeedbackConfig 数据类

- [ ] 创建 `src/A_memorix/core/runtime/config/__init__.py`（空包或导出配置类）
- [ ] 创建 `src/A_memorix/core/runtime/config/feedback_config.py`，实现 `FeedbackConfig`：
  - `@dataclass(frozen=True)` 不可变数据类
  - 字段：`enabled`、`window_hours`、`check_interval_seconds`、`batch_size`、`auto_apply_threshold`、`max_messages`、`prefilter_enabled`、`paragraph_mark_enabled`、`paragraph_hard_filter_enabled`、`profile_refresh_enabled`、`profile_force_refresh_on_read`、`episode_rebuild_enabled`、`episode_query_block_enabled`、`reconcile_interval_seconds`、`reconcile_batch_size`
  - `@classmethod from_global_config(cls) -> FeedbackConfig` — 从 `global_config.a_memorix.integration` 一次性读取所有配置，替代 15+ 处 `getattr` 模式
- **需求ID**：REQ-CLEANUP-007、REQ-CLEANUP-004
- **依赖**：无
- **验收标准**：`from src.A_memorix.core.runtime.config.feedback_config import FeedbackConfig` 导入成功；`FeedbackConfig.from_global_config()` 返回有效配置实例；`FeedbackConfig(enabled=True).enabled` 为 True
- **影响文件**：`src/A_memorix/core/runtime/config/__init__.py`（新增）、`src/A_memorix/core/runtime/config/feedback_config.py`（新增）
- **优先级**：极高
- **复杂度**：中

#### TASK-7A-02: 创建 FuzzyModifyConfig 数据类

- [ ] 创建 `src/A_memorix/core/runtime/config/fuzzy_modify_config.py`，实现 `FuzzyModifyConfig`：
  - `@dataclass(frozen=True)` 不可变数据类
  - 字段：`enabled`、`auto_execute_enabled`、`confirm_threshold`、`candidate_limit`、`max_targets`、`allow_global_scope`
  - `@classmethod from_global_config(cls) -> FuzzyModifyConfig` — 从 `global_config.a_memorix.integration` 一次性读取
- **需求ID**：REQ-CLEANUP-007、REQ-CLEANUP-004
- **依赖**：TASK-7A-01（同包结构已建立）
- **验收标准**：`from src.A_memorix.core.runtime.config.fuzzy_modify_config import FuzzyModifyConfig` 导入成功；`FuzzyModifyConfig.from_global_config()` 返回有效配置实例
- **影响文件**：`src/A_memorix/core/runtime/config/fuzzy_modify_config.py`（新增）
- **优先级**：高
- **复杂度**：低

#### TASK-7A-03: 创建 VectorPoolConfig 数据类

- [ ] 创建 `src/A_memorix/core/runtime/config/vector_pool_config.py`，实现 `VectorPoolConfig`：
  - `@dataclass(frozen=True)` 不可变数据类
  - 字段：`mode`、`config_enabled`、`embedding_fallback_enabled`、`allow_metadata_only_write`、`embedding_probe_interval_seconds`、`paragraph_vector_backfill_enabled`、`paragraph_vector_backfill_interval_seconds`、`paragraph_vector_backfill_batch_size`、`paragraph_vector_backfill_max_retry`
  - `@classmethod from_global_config(cls) -> VectorPoolConfig` — 从 `global_config.a_memorix.integration` 一次性读取
- **需求ID**：REQ-CLEANUP-007、REQ-CLEANUP-004
- **依赖**：TASK-7A-01
- **验收标准**：`from src.A_memorix.core.runtime.config.vector_pool_config import VectorPoolConfig` 导入成功；`VectorPoolConfig.from_global_config()` 返回有效配置实例
- **影响文件**：`src/A_memorix/core/runtime/config/vector_pool_config.py`（新增）
- **优先级**：高
- **复杂度**：低

#### TASK-7A-04: 创建 admin/ 包及 BaseAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/__init__.py`（空包或导出 Handler 类）
- [ ] 创建 `src/A_memorix/core/runtime/admin/base.py`，实现 `BaseAdminHandler`：
  - `async def handle(self, action: str, **kwargs) -> Dict[str, Any]` — 抽象方法，子类重写实现分发逻辑
  - 不支持的 action 返回 `{"success": False, "error": f"不支持的 {domain} action: {act}"}`
  - 提供公共工具方法：`_str_action(action) -> str`（标准化 action 字符串）、`_require_initialized()`（检查依赖是否就绪）
- **需求ID**：REQ-CLEANUP-003
- **依赖**：无
- **验收标准**：`from src.A_memorix.core.runtime.admin.base import BaseAdminHandler` 导入成功；`BaseAdminHandler()` 可实例化
- **影响文件**：`src/A_memorix/core/runtime/admin/__init__.py`（新增）、`src/A_memorix/core/runtime/admin/base.py`（新增）
- **优先级**：高
- **复杂度**：低

#### TASK-7A-05: 创建 services/ 包

- [ ] 创建 `src/A_memorix/core/runtime/services/__init__.py`（空包，后续逐步导出服务类）
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：无
- **验收标准**：`from src.A_memorix.core.runtime.services import ...` 导入路径可用
- **影响文件**：`src/A_memorix/core/runtime/services/__init__.py`（新增）
- **优先级**：高
- **复杂度**：极低

#### TASK-7A-06: 阶段 7A 验证

- [ ] 执行以下验证：
  - `from src.A_memorix.core.runtime.config.feedback_config import FeedbackConfig` — 导入成功
  - `from src.A_memorix.core.runtime.config.fuzzy_modify_config import FuzzyModifyConfig` — 导入成功
  - `from src.A_memorix.core.runtime.config.vector_pool_config import VectorPoolConfig` — 导入成功
  - `from src.A_memorix.core.runtime.admin.base import BaseAdminHandler` — 导入成功
  - `from src.A_memorix.core.runtime.services import ...` — 包路径可用
  - `FeedbackConfig.from_global_config()` — 返回有效配置
  - 容器内重启后 A_memorix 功能正常（未修改存量代码）
- **需求ID**：REQ-CLEANUP-007
- **依赖**：TASK-7A-01、TASK-7A-02、TASK-7A-03、TASK-7A-04、TASK-7A-05
- **验收标准**：上述所有检查通过；容器重启后功能正常
- **影响文件**：无（验证任务）
- **优先级**：高
- **复杂度**：低

---

### 阶段 7B：功能域提取 — 逐个提取独立服务

> 按依赖关系从底层到上层逐个提取。每个服务提取后，Kernel 中原方法先改为委托调用，确认功能正常。
> **提取原则**：一次只提取一个功能域，提取后立即验证。

#### TASK-7B-01: 提取 EmbeddingHealthService（最小依赖，~150 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/embedding_health.py`，实现 `EmbeddingHealthService`：
  - 从 SDKMemoryKernel 提取以下方法：`_is_embedding_degraded`、`_embedding_degraded_snapshot`、`_set_embedding_degraded`、`_refresh_runtime_self_check`
  - 构造函数注入：`embedding_manager`、`vector_pool_config: VectorPoolConfig`
  - 持有 `_embedding_degraded: Dict[str, Any]` 状态
  - 对外暴露 `is_degraded` 属性、`snapshot() -> Dict`、`set_degraded(reason)`、`refresh_self_check()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._embedding_health_service = EmbeddingHealthService(...)` 实例
- [ ] 将 Kernel 中原方法改为委托：`def _is_embedding_degraded(self) -> bool: return self._embedding_health_service.is_degraded`
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7A-03（VectorPoolConfig）、TASK-7A-05（services 包）
- **验收标准**：`from src.A_memorix.core.runtime.services.embedding_health import EmbeddingHealthService` 导入成功；Kernel 中 `_is_embedding_degraded` 委托到服务；容器重启后 Embedding 降级检测功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/embedding_health.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：极高
- **复杂度**：低

#### TASK-7B-02: 提取 VectorPoolManager（依赖 EmbeddingHealthService，~800 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/vector_pool.py`，实现 `VectorPoolManager`：
  - 从 SDKMemoryKernel 提取以下方法：`_dual_vector_pools_enabled`、`_dual_vector_pools_config_enabled`、`_dual_vector_ready_manifest_path`、`_dual_vector_ready`、`_stored_vector_dimension`、`_embedding_fingerprint_status`、`_vector_mismatch_error`、`_vector_rebuild_status`、`_vector_pool_mode`、`_vector_store_snapshot`、`_vector_pools_status`、`_dual_vector_auto_migration_loop`、`_embedding_fallback_enabled`、`_allow_metadata_only_write`、`_paragraph_vector_backfill_enabled`
  - 构造函数注入：`config: Dict[str, Any]`、`data_dir: Path`、`embedding_dimension: int`、`embedding_manager`、`vector_store`、`paragraph_vector_store`、`graph_vector_store`、`embedding_health_service: EmbeddingHealthService`、`vector_pool_config: VectorPoolConfig`
  - 持有双池状态：`_dual_vector_pools_ready`、`_dual_vector_auto_migration_*`、`_vector_rebuild_lock`、`_vector_persist_blocked_until_rebuild`
  - 对外暴露 `dual_pools_enabled`、`dual_pools_ready`、`persist()`、`reload_dual_vector_stores_from_disk()`、`vector_rebuild_status()`、`vector_pools_status()` 等方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._vector_pool_manager = VectorPoolManager(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7B-01（EmbeddingHealthService）、TASK-7A-03（VectorPoolConfig）
- **验收标准**：`from src.A_memorix.core.runtime.services.vector_pool import VectorPoolManager` 导入成功；Kernel 中向量池相关方法委托到服务；容器重启后双池配置和向量持久化功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/vector_pool.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：极高
- **复杂度**：高

#### TASK-7B-03: 提取 ParagraphBackfillService（依赖 VectorPoolManager，~200 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/paragraph_backfill.py`，实现 `ParagraphBackfillService`：
  - 从 SDKMemoryKernel 提取以下方法：`_enqueue_paragraph_vector_backfill`、`_write_paragraph_vector_or_enqueue`、`_run_paragraph_backfill_once`
  - 构造函数注入：`metadata_store`、`vector_pool_manager: VectorPoolManager`、`embedding_health_service: EmbeddingHealthService`、`vector_pool_config: VectorPoolConfig`
  - 持有回填队列状态
  - 对外暴露 `enqueue(paragraph_hash, error)`、`write_or_enqueue(paragraph_hash, content, context)`、`run_once()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._paragraph_backfill_service = ParagraphBackfillService(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7B-01、TASK-7B-02
- **验收标准**：`from src.A_memorix.core.runtime.services.paragraph_backfill import ParagraphBackfillService` 导入成功；Kernel 中段落回填方法委托到服务；容器重启后段落向量回填功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/paragraph_backfill.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：高
- **复杂度**：中

#### TASK-7B-04: 提取 VectorRebuildService（依赖 VectorPoolManager + ParagraphBackfillService，~600 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/vector_rebuild.py`，实现 `VectorRebuildService`：
  - 从 SDKMemoryKernel 提取以下方法：`_rebuild_all_vectors`、`_rebuild_all_vectors_locked`、`_encode_and_add_rebuild_vectors` 及相关辅助方法
  - 构造函数注入：`metadata_store`、`vector_pool_manager: VectorPoolManager`、`embedding_health_service: EmbeddingHealthService`、`paragraph_backfill_service: ParagraphBackfillService`
  - 使用 `vector_pool_manager._vector_rebuild_lock` 保证互斥
  - 对外暴露 `rebuild_all()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._vector_rebuild_service = VectorRebuildService(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7B-02、TASK-7B-03
- **验收标准**：`from src.A_memorix.core.runtime.services.vector_rebuild import VectorRebuildService` 导入成功；Kernel 中向量重建方法委托到服务；容器重启后向量重建功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/vector_rebuild.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：高
- **复杂度**：高

#### TASK-7B-05: 提取 MemoryMaintenanceService（依赖 GraphStore + MetadataStore，~200 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/memory_maintenance.py`，实现 `MemoryMaintenanceService`：
  - 从 SDKMemoryKernel 提取以下方法：`_memory_maintenance_loop`、`_process_freeze_and_prune`、`_orphan_gc_phase`
  - 构造函数注入：`graph_store`、`metadata_store`、`vector_pool_manager: VectorPoolManager`
  - 对外暴露 `run_maintenance_cycle()`、`process_freeze_and_prune()`、`orphan_gc()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._memory_maintenance_service = MemoryMaintenanceService(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7B-02
- **验收标准**：`from src.A_memorix.core.runtime.services.memory_maintenance import MemoryMaintenanceService` 导入成功；Kernel 中记忆维护方法委托到服务；容器重启后记忆衰减/冻结/修剪功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/memory_maintenance.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：高
- **复杂度**：中

#### TASK-7B-06: 提取 GraphOperations（依赖 GraphStore + MetadataStore，~500 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/graph_operations.py`，实现 `GraphOperations`：
  - 从 SDKMemoryKernel 提取以下方法：`_serialize_graph`、`_search_graph`、`_build_graph_node_detail`、`_build_evidence_graph`、`_rename_node`、`_update_edge_weight`
  - 构造函数注入：`graph_store`、`metadata_store`、`relation_write_service`
  - 对外暴露 `serialize_graph()`、`search_graph()`、`build_node_detail()`、`build_evidence_graph()`、`rename_node()`、`update_edge_weight()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._graph_operations = GraphOperations(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：无（仅依赖存储层）
- **验收标准**：`from src.A_memorix.core.runtime.services.graph_operations import GraphOperations` 导入成功；Kernel 中图操作方法委托到服务；容器重启后图序列化/搜索功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/graph_operations.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：高
- **复杂度**：中

#### TASK-7B-07: 提取 BackgroundTaskScheduler（独立，~400 行调度逻辑）

- [ ] 创建 `src/A_memorix/core/runtime/services/background_scheduler.py`，实现 `BackgroundTaskScheduler`：
  - 从 SDKMemoryKernel 提取以下方法：`_start_background_tasks`、`_stop_background_tasks`、`_ensure_background_task` 及 `_background_tasks` / `_background_lock` / `_background_stopping` 状态
  - 构造函数：`__init__()` — 初始化 `_tasks: Dict[str, asyncio.Task]`、`_lock: asyncio.Lock`、`_stopping: bool`
  - 对外暴露 `register(name, factory)`、`ensure_task(name, factory)`、`start_all()`、`stop_all()`、`stopping` 属性
  - Kernel 在 `initialize()` 中调用 `scheduler.register(...)` 注册 9 个后台循环
  - Kernel 在 `shutdown()` 中调用 `scheduler.stop_all()`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._background_scheduler = BackgroundTaskScheduler()` 实例
- [ ] 将 Kernel 中后台任务管理方法改为委托调用
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7A-05
- **验收标准**：`from src.A_memorix.core.runtime.services.background_scheduler import BackgroundTaskScheduler` 导入成功；Kernel 中后台任务启停委托到调度器；容器重启后所有后台循环正常启动
- **影响文件**：`src/A_memorix/core/runtime/services/background_scheduler.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：极高
- **复杂度**：中

#### TASK-7B-08: 提取 FeedbackCorrectionService（最大块，~2000 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/feedback_correction.py`，实现 `FeedbackCorrectionService`：
  - 从 SDKMemoryKernel 提取以下方法（32 个）：`_feedback_correction_loop`、`_feedback_correction_reconcile_loop`、`_process_feedback_task`、`_apply_feedback_decision`、`_rollback_feedback_task`、`_enqueue_feedback_episode_rebuilds`、`_enqueue_feedback_profile_refreshes`、`_process_feedback_profile_refresh_batch`、`_process_feedback_episode_rebuild_batch`、`_feedback_contains_signal`、`_feedback_noise`、`_feedback_signal_tokens`、`_feedback_affected_counts`、`_feedback_apply_result_status`、`_feedback_cfg_window_label`、15+ 个 `_feedback_cfg_*` 静态方法
  - 构造函数注入：`config: FeedbackConfig`、`metadata_store`、`graph_store`、`vector_pool_manager: VectorPoolManager`、`embedding_health_service: EmbeddingHealthService`、`session_info_port`
  - 配置读取从 15+ 个 `_feedback_cfg_*` 静态方法改为 `self.config.xxx` 直接属性访问
  - 持有 `_feedback_classifier: Optional[LLMServiceClient]` 延迟初始化
  - 对外暴露 `process_feedback_task()`、`apply_feedback_correction()`、`rollback_feedback_task()`、`feedback_correction_loop()`、`feedback_correction_reconcile_loop()`、`feedback_contains_signal()`、`feedback_noise()`、`build_feedback_task_summary()`、`build_feedback_task_detail()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._feedback_correction_service = FeedbackCorrectionService(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- [ ] 删除 Kernel 中 15+ 个 `_feedback_cfg_*` 静态方法（已合并为 `FeedbackConfig`）
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002、REQ-CLEANUP-004、REQ-CLEANUP-007
- **依赖**：TASK-7A-01（FeedbackConfig）、TASK-7B-01、TASK-7B-02、TASK-7B-07
- **验收标准**：`from src.A_memorix.core.runtime.services.feedback_correction import FeedbackCorrectionService` 导入成功；Kernel 中反馈纠错方法委托到服务；`_feedback_cfg_*` 静态方法已删除；容器重启后反馈纠错功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/feedback_correction.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式 + 删除 `_feedback_cfg_*`）
- **优先级**：极高
- **复杂度**：极高

#### TASK-7B-09: 提取 FuzzyModifyService（~1000 行）

- [ ] 创建 `src/A_memorix/core/runtime/services/fuzzy_modify.py`，实现 `FuzzyModifyService`：
  - 从 SDKMemoryKernel 提取以下方法：`_preview_fuzzy_modify_action`、`_execute_fuzzy_modify_action`、`_rollback_fuzzy_modify_action`、`_apply_fuzzy_modify_plan`、`_build_fuzzy_modify_paragraph_cascade`、`_execute_fuzzy_modify_paragraph_cascade`、`_mark_fuzzy_modify_target_superseded`、6 个 `_fuzzy_modify_cfg_*` 静态方法
  - 构造函数注入：`config: FuzzyModifyConfig`、`metadata_store`、`graph_store`、`vector_pool_manager: VectorPoolManager`、`embedding_health_service: EmbeddingHealthService`、`llm_client: Optional[LLMServiceClient]`
  - 配置读取从 6 个 `_fuzzy_modify_cfg_*` 静态方法改为 `self.config.xxx` 直接属性访问
  - 持有 `_fuzzy_modify_planner: Optional[LLMServiceClient]` 延迟初始化
  - 对外暴露 `preview_action()`、`execute_action()`、`rollback_action()`、`apply_plan()` 方法
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._fuzzy_modify_service = FuzzyModifyService(...)` 实例
- [ ] 将 Kernel 中原方法改为委托调用
- [ ] 删除 Kernel 中 6 个 `_fuzzy_modify_cfg_*` 静态方法（已合并为 `FuzzyModifyConfig`）
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002、REQ-CLEANUP-004、REQ-CLEANUP-007
- **依赖**：TASK-7A-02（FuzzyModifyConfig）、TASK-7B-01、TASK-7B-02
- **验收标准**：`from src.A_memorix.core.runtime.services.fuzzy_modify import FuzzyModifyService` 导入成功；Kernel 中模糊修改方法委托到服务；`_fuzzy_modify_cfg_*` 静态方法已删除；容器重启后模糊修改功能正常
- **影响文件**：`src/A_memorix/core/runtime/services/fuzzy_modify.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式 + 删除 `_fuzzy_modify_cfg_*`）
- **优先级**：高
- **复杂度**：高

#### TASK-7B-10: 阶段 7B 验证

- [ ] 执行以下验证：
  - **服务导入检查**：所有 9 个服务类均可从 `src/A_memorix/core/runtime/services/` 导入
  - **委托模式检查**：Kernel 中对应方法改为委托调用，行为等价
  - **服务隔离检查**：`rg "from ..sdk_memory_kernel import SDKMemoryKernel" src/A_memorix/core/runtime/services/` — 应为 0 匹配
  - **配置合并检查**：`rg "_feedback_cfg_" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配；`rg "_fuzzy_modify_cfg_" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配
  - **容器验证**：重启容器后所有功能正常（记忆检索、向量重建、反馈纠错、模糊修改、记忆维护）
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002、REQ-CLEANUP-009
- **依赖**：TASK-7B-01 ~ TASK-7B-09
- **验收标准**：上述所有检查通过；容器重启后功能正常
- **影响文件**：无（验证任务）
- **优先级**：极高
- **复杂度**：低

---

### 阶段 7C：Admin Handler 提取 — 逐个提取 Admin 分发

> 每个 Admin Handler 从 Kernel 的 `memory_*_admin` 方法中提取分发逻辑。提取后 Kernel 的 `memory_*_admin` 方法退化为委托 Handler。

#### TASK-7C-01: 提取 GraphAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/graph_admin.py`，实现 `GraphAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_graph_admin`（行 3139-3281，8 个 action）提取分发逻辑
  - 构造函数注入：`graph_ops: GraphOperations`、`metadata_store`、`relation_write_service`、`relation_vectors_enabled: bool`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`get_graph`、`search`、`node_detail`、`evidence_graph`、`rename_node`、`update_edge_weight`、`delete_node`、`add_edge`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._graph_admin_handler = GraphAdminHandler(...)` 实例
- [ ] 将 `memory_graph_admin` 改为：`return await self._graph_admin_handler.handle(action, **kwargs)`
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04（BaseAdminHandler）、TASK-7B-06（GraphOperations）
- **验收标准**：`from src.A_memorix.core.runtime.admin.graph_admin import GraphAdminHandler` 导入成功；`memory_graph_admin` 委托到 Handler；容器重启后图管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/graph_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：高
- **复杂度**：中

#### TASK-7C-02: 提取 SourceAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/source_admin.py`，实现 `SourceAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_source_admin`（行 3283-3322，3 个 action）提取分发逻辑
  - 构造函数注入：`metadata_store`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`list`、`detail`、`delete`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._source_admin_handler = SourceAdminHandler(...)` 实例
- [ ] 将 `memory_source_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.source_admin import SourceAdminHandler` 导入成功；`memory_source_admin` 委托到 Handler；容器重启后来源管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/source_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-03: 提取 EpisodeAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/episode_admin.py`，实现 `EpisodeAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_episode_admin`（行 3324-3385，4+ 个 action）提取分发逻辑
  - 构造函数注入：`metadata_store`、`episode_service`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`list`、`detail`、`rebuild`、`query_block_status`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._episode_admin_handler = EpisodeAdminHandler(...)` 实例
- [ ] 将 `memory_episode_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.episode_admin import EpisodeAdminHandler` 导入成功；`memory_episode_admin` 委托到 Handler；容器重启后 Episode 管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/episode_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-04: 提取 ProfileAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/profile_admin.py`，实现 `ProfileAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_profile_admin`（行 3386-3486，5+ 个 action）提取分发逻辑
  - 构造函数注入：`metadata_store`、`person_profile_service`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`get`、`list`、`refresh`、`delete`、`force_refresh`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._profile_admin_handler = ProfileAdminHandler(...)` 实例
- [ ] 将 `memory_profile_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.profile_admin import ProfileAdminHandler` 导入成功；`memory_profile_admin` 委托到 Handler；容器重启后人物画像管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/profile_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-05: 提取 FeedbackAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/feedback_admin.py`，实现 `FeedbackAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_feedback_admin`（行 3487-3518，3 个 action）提取分发逻辑
  - 构造函数注入：`metadata_store`、`feedback_correction_service: FeedbackCorrectionService`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`list`、`detail`、`rollback`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._feedback_admin_handler = FeedbackAdminHandler(...)` 实例
- [ ] 将 `memory_feedback_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04、TASK-7B-08（FeedbackCorrectionService）
- **验收标准**：`from src.A_memorix.core.runtime.admin.feedback_admin import FeedbackAdminHandler` 导入成功；`memory_feedback_admin` 委托到 Handler；容器重启后反馈纠错管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/feedback_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-06: 提取 RuntimeAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/runtime_admin.py`，实现 `RuntimeAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_runtime_admin`（行 3520-3613，7 个 action）提取分发逻辑
  - 构造函数注入：`vector_pool_manager: VectorPoolManager`、`embedding_health_service: EmbeddingHealthService`、`paragraph_backfill_service: ParagraphBackfillService`、`metadata_store`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`status`、`vector_rebuild`、`embedding_self_check`、`backfill_status`、`backfill_trigger`、`vector_pools_status`、`persist`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._runtime_admin_handler = RuntimeAdminHandler(...)` 实例
- [ ] 将 `memory_runtime_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04、TASK-7B-01、TASK-7B-02、TASK-7B-03
- **验收标准**：`from src.A_memorix.core.runtime.admin.runtime_admin import RuntimeAdminHandler` 导入成功；`memory_runtime_admin` 委托到 Handler；容器重启后运行时管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/runtime_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：中

#### TASK-7C-07: 提取 ImportAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/import_admin.py`，实现 `ImportAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_import_admin`（行 3615-3670，12+ 个 action）提取分发逻辑
  - 构造函数注入：`import_task_manager: ImportTaskManager`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`start`、`status`、`cancel`、`list`、`detail`、`retry`、`delete` 等 12+ 个 action
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._import_admin_handler = ImportAdminHandler(...)` 实例
- [ ] 将 `memory_import_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.import_admin import ImportAdminHandler` 导入成功；`memory_import_admin` 委托到 Handler；容器重启后导入管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/import_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：中

#### TASK-7C-08: 提取 TuningAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/tuning_admin.py`，实现 `TuningAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_tuning_admin`（行 3672-3755，5+ 个 action）提取分发逻辑
  - 构造函数注入：`retrieval_tuning_manager: RetrievalTuningManager`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`get_profile`、`set_profile`、`reset_profile`、`list_profiles`、`validate`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._tuning_admin_handler = TuningAdminHandler(...)` 实例
- [ ] 将 `memory_tuning_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.tuning_admin import TuningAdminHandler` 导入成功；`memory_tuning_admin` 委托到 Handler；容器重启后调优管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/tuning_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-09: 提取 V5AdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/v5_admin.py`，实现 `V5AdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_v5_admin`（行 3756-3806，4+ 个 action）提取分发逻辑
  - 构造函数注入：`metadata_store`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`migrate`、`status`、`rollback`、`verify`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._v5_admin_handler = V5AdminHandler(...)` 实例
- [ ] 将 `memory_v5_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.v5_admin import V5AdminHandler` 导入成功；`memory_v5_admin` 委托到 Handler；容器重启后 V5 管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/v5_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-10: 提取 DeleteAdminHandler

- [ ] 创建 `src/A_memorix/core/runtime/admin/delete_admin.py`，实现 `DeleteAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_delete_admin`（行 3807-3864，4+ 个 action）提取分发逻辑
  - 构造函数注入：`metadata_store`、`graph_store`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`paragraph`、`entity`、`relation`、`source`
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._delete_admin_handler = DeleteAdminHandler(...)` 实例
- [ ] 将 `memory_delete_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04
- **验收标准**：`from src.A_memorix.core.runtime.admin.delete_admin import DeleteAdminHandler` 导入成功；`memory_delete_admin` 委托到 Handler；容器重启后删除管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/delete_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-11: 提取 CorrectionAdminHandler（含 fuzzy_modify 兼容入口）

- [ ] 创建 `src/A_memorix/core/runtime/admin/correction_admin.py`，实现 `CorrectionAdminHandler(BaseAdminHandler)`：
  - 从 `SDKMemoryKernel.memory_correction_admin`（行 3865-3908，5 个 action）+ `memory_fuzzy_modify_admin`（行 3910-3911，1 个委托）提取分发逻辑
  - 构造函数注入：`fuzzy_modify_service: FuzzyModifyService`、`metadata_store`
  - `handle(action, **kwargs)` 内部 if/elif 分发到：`preview`、`execute`、`rollback`、`plan_detail`、`cancel`
  - 兼容 `memory_fuzzy_modify_admin` 的 action（直接委托到本 Handler）
- [ ] 在 `SDKMemoryKernel.__init__` 中创建 `self._correction_admin_handler = CorrectionAdminHandler(...)` 实例
- [ ] 将 `memory_correction_admin` 和 `memory_fuzzy_modify_admin` 改为委托
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7A-04、TASK-7B-09（FuzzyModifyService）
- **验收标准**：`from src.A_memorix.core.runtime.admin.correction_admin import CorrectionAdminHandler` 导入成功；`memory_correction_admin` 和 `memory_fuzzy_modify_admin` 委托到 Handler；容器重启后修正/模糊修改管理 Admin API 功能正常
- **影响文件**：`src/A_memorix/core/runtime/admin/correction_admin.py`（新增）、`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 委托模式）
- **优先级**：中
- **复杂度**：低

#### TASK-7C-12: 阶段 7C 验证

- [ ] 执行以下验证：
  - **Handler 导入检查**：所有 11 个 Handler 类均可从 `src/A_memorix/core/runtime/admin/` 导入
  - **委托模式检查**：所有 `memory_*_admin` 方法退化为委托 Handler
  - **Handler 隔离检查**：`rg "from ..sdk_memory_kernel import SDKMemoryKernel" src/A_memorix/core/runtime/admin/` — 应为 0 匹配
  - **Admin API 功能验证**：通过 WebUI 或直接调用验证所有 Admin API 功能正常
  - **容器验证**：重启容器后所有 Admin API 功能正常
- **需求ID**：REQ-CLEANUP-003
- **依赖**：TASK-7C-01 ~ TASK-7C-11
- **验收标准**：上述所有检查通过；容器重启后 Admin API 功能正常
- **影响文件**：无（验证任务）
- **优先级**：高
- **复杂度**：低

---

### 阶段 7D：Kernel 瘦身 + 清理

> 在功能域服务和 Admin Handler 全部提取完成后，对 Kernel 进行瘦身和清理：删除代理层、消除 getattr、消除过度防御、确认 Kernel 行数 ≤ 800。

#### TASK-7D-01: 删除 _KernelRuntimeFacade（ImportTaskManager / RetrievalTuningManager 改为构造函数注入）

- [ ] 修改 `src/A_memorix/core/utils/web_import_manager.py`（`ImportTaskManager`）：
  - 构造函数从接收 `facade: _KernelRuntimeFacade` 改为接收具体依赖：`metadata_store`、`vector_store`、`embedding_manager`、`sparse_index`、`config: Dict[str, Any]` 等
  - 删除对 `facade.get_config()`、`facade.is_runtime_ready()`、`facade.is_chat_enabled()` 等代理方法的调用
  - 改为直接使用注入的依赖
- [ ] 修改 `src/A_memorix/core/utils/retrieval_tuning_manager.py`（`RetrievalTuningManager`）：
  - 构造函数从接收 `facade` 改为接收具体依赖
  - 删除对 `facade` 代理方法的调用
- [ ] 修改 `src/A_memorix/core/utils/summary_importer.py`（`SummaryImporter`）：
  - 删除对 `plugin_instance.get_config()`、`plugin_instance._dual_vector_pools_enabled()`、`plugin_instance.write_paragraph_vector_or_enqueue()` 的 `getattr` 调用
  - 改为通过构造函数注入所需依赖
- [ ] 修改 `src/A_memorix/core/runtime/search_runtime_initializer.py`：
  - 删除对 `plugin_instance._dual_vector_pools_enabled` 的 `getattr` 调用
  - 改为通过构造函数注入 `vector_pool_manager: VectorPoolManager`
- [ ] 修改 `src/A_memorix/core/utils/search_execution_service.py`：
  - 删除对 `plugin_instance` 的 `getattr` 调用链（`is_chat_enabled`、`reinforce_access`、`execute_request_with_dedup`）
  - 改为通过构造函数注入所需依赖
- [ ] 在 `SDKMemoryKernel` 中：
  - 删除 `_KernelRuntimeFacade` 类定义（行 73-174）
  - 删除 `self._runtime_facade = _KernelRuntimeFacade(self)`
  - 修改 `initialize()` 中创建 `ImportTaskManager` / `RetrievalTuningManager` 的代码，改为注入具体依赖
  - 修改 `_build_runtime_config` 中的 `"plugin_instance": self._runtime_facade` 引用
- **需求ID**：REQ-CLEANUP-006
- **依赖**：TASK-7B-02（VectorPoolManager）、TASK-7B-07（BackgroundTaskScheduler）
- **验收标准**：`rg "_KernelRuntimeFacade" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配；`rg "plugin_instance" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配或仅保留非 Facade 用途；容器重启后导入/调优/摘要功能正常
- **影响文件**：`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改 — 删除 Facade）、`src/A_memorix/core/utils/web_import_manager.py`（修改）、`src/A_memorix/core/utils/retrieval_tuning_manager.py`（修改）、`src/A_memorix/core/utils/summary_importer.py`（修改）、`src/A_memorix/core/runtime/search_runtime_initializer.py`（修改）、`src/A_memorix/core/utils/search_execution_service.py`（修改）
- **优先级**：极高
- **复杂度**：高

#### TASK-7D-02: 消除 getattr（52 → ≤5）

- [ ] 对 `sdk_memory_kernel.py` 中剩余的 `getattr` 调用逐一审查和消除：
  - 对 `global_config.a_memorix.integration` 的 getattr 访问 → 已由 `FeedbackConfig` / `FuzzyModifyConfig` / `VectorPoolConfig` 替代，确认已消除
  - 对已知接口的 getattr（如 `store.dimension`、`store.num_vectors`）→ 替换为直接属性访问
  - 对动态能力检测的 getattr（如 `encode_batch`、`iter_vectors_by_ids`）→ 通过 Protocol 接口统一，消除运行时能力探测
  - 对 `plugin_instance` 的 getattr → 已在 TASK-7D-01 中消除
- [ ] 对 `services/` 和 `admin/` 中新提取的代码中的 `getattr` 进行同步消除
- [ ] 仅保留真正需要动态检测的场景（≤5 处），并添加注释说明保留原因
- **需求ID**：REQ-CLEANUP-004
- **依赖**：TASK-7D-01、TASK-7B-08（FeedbackCorrectionService 配置合并）、TASK-7B-09（FuzzyModifyService 配置合并）
- **验收标准**：`rg "getattr" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 匹配数 ≤ 5；`rg "getattr" src/A_memorix/core/runtime/services/` — 匹配数 ≤ 3；每个保留的 `getattr` 有注释说明原因
- **影响文件**：`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改）、`src/A_memorix/core/runtime/services/*.py`（修改）、`src/A_memorix/core/runtime/admin/*.py`（修改）
- **优先级**：高
- **复杂度**：高

#### TASK-7D-03: 消除过度防御（618 处 `or ""` → ≤150）

- [ ] 对 `sdk_memory_kernel.py` 中的 `or ""` 模式逐一审查和消除：
  - 对已知类型为 str 的变量（函数参数有类型注解、配置值已知为字符串），删除 `or ""` 兜底
  - 对 `dict.get(key, "")` 已提供默认值的调用，删除后续的 `or ""`
  - 对 `str(x or "").strip()` 链式调用，当 x 已知为 str 时简化为 `x.strip()`
  - 对 `int(x or 0)`、`float(x or 0.0)` 等数值兜底，当 x 已知为数值类型时删除兜底
- [ ] 对 `services/` 和 `admin/` 中新提取的代码同步消除 `or ""`
- [ ] 仅保留真正可能为 None 的场景（≤150 处），对删除的兜底添加简要注释说明"类型注解保证非 None"
- **需求ID**：REQ-CLEANUP-005
- **依赖**：TASK-7D-01、TASK-7D-02
- **验收标准**：`rg 'or ""' src/A_memorix/core/runtime/sdk_memory_kernel.py` — 匹配数 ≤ 150；容器重启后无新增 AttributeError
- **影响文件**：`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改）、`src/A_memorix/core/runtime/services/*.py`（修改）、`src/A_memorix/core/runtime/admin/*.py`（修改）
- **优先级**：高
- **复杂度**：高

#### TASK-7D-04: Kernel 公共方法改为委托服务 + 删除已委托方法

- [ ] 审查 `sdk_memory_kernel.py` 中所有公共方法：
  - 确认所有已提取到服务的方法在 Kernel 中改为委托调用
  - 对于外部无直接调用的委托方法，删除方法定义，外部调用改为通过服务实例
  - 对于外部有直接调用的委托方法（如 `host_service` 调用的 `search_memory`、`ingest_text` 等），保留委托方法作为公共 API
- [ ] 确认 Kernel 的 `initialize()` 方法正确创建和注入所有服务实例
- [ ] 确认 Kernel 的 `shutdown()` 方法正确委托到 `BackgroundTaskScheduler.stop_all()` 和各服务的清理逻辑
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-002
- **依赖**：TASK-7B-01 ~ TASK-7B-09、TASK-7C-01 ~ TASK-7C-11
- **验收标准**：Kernel 中所有业务逻辑方法改为委托调用或已删除；`host_service` 调用的公共 API 签名不变；容器重启后功能正常
- **影响文件**：`src/A_memorix/core/runtime/sdk_memory_kernel.py`（修改）
- **优先级**：极高
- **复杂度**：中

#### TASK-7D-05: 验证 Kernel 行数 ≤ 800

- [ ] 统计 `sdk_memory_kernel.py` 的代码行数
- [ ] 如果行数 > 800，识别剩余的大块逻辑，评估是否需要进一步提取
- [ ] 确认 Kernel 仅保留：`__init__`（创建服务实例）、`initialize()`（初始化存储层和服务）、`shutdown()`（委托到调度器和服务）、公共 API 委托方法（`search_memory`、`ingest_text`、`get_person_profile`、`maintain_memory`、`memory_stats`、`memory_*_admin`）、`_cfg` / `_set_cfg` 配置读取
- **需求ID**：REQ-CLEANUP-001
- **依赖**：TASK-7D-01、TASK-7D-02、TASK-7D-03、TASK-7D-04
- **验收标准**：`(Get-Content src/A_memorix/core/runtime/sdk_memory_kernel.py | Measure-Object -Line).Lines` ≤ 800
- **影响文件**：`src/A_memorix/core/runtime/sdk_memory_kernel.py`（确认）
- **优先级**：极高
- **复杂度**：中

---

### 阶段 7E：验证 — 全量功能回归

> 最终验证确保重构后所有功能正常，核心隔离合规。

#### TASK-7E-01: 核心隔离合规验证

- [ ] 执行以下核心隔离检查：
  - `rg "from src.chat.message_receive.chat_manager import" src/A_memorix/` — 应为 0 匹配
  - `rg "from src.services.send_service import" src/A_memorix/` — 应为 0 匹配
  - `rg "from ..sdk_memory_kernel import SDKMemoryKernel" src/A_memorix/core/runtime/services/ src/A_memorix/core/runtime/admin/` — 应为 0 匹配
  - `rg "_KernelRuntimeFacade" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配
- **需求ID**：REQ-CLEANUP-008、REQ-CLEANUP-009
- **依赖**：TASK-7D-01 ~ TASK-7D-05
- **验收标准**：上述所有检查通过
- **影响文件**：无（验证任务）
- **优先级**：极高
- **复杂度**：低

#### TASK-7E-02: 代码质量验证

- [ ] 执行以下代码质量检查：
  - `rg "getattr" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 匹配数 ≤ 5
  - `rg 'or ""' src/A_memorix/core/runtime/sdk_memory_kernel.py` — 匹配数 ≤ 150
  - `(Get-Content src/A_memorix/core/runtime/sdk_memory_kernel.py | Measure-Object -Line).Lines` — ≤ 800
  - `rg "_feedback_cfg_" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配
  - `rg "_fuzzy_modify_cfg_" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配
  - `rg "_dual_vector_pools_enabled" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配（已移入 VectorPoolManager）
  - `rg "_embedding_fallback_enabled" src/A_memorix/core/runtime/sdk_memory_kernel.py` — 应为 0 匹配（已移入 VectorPoolConfig）
- **需求ID**：REQ-CLEANUP-001、REQ-CLEANUP-004、REQ-CLEANUP-005、REQ-CLEANUP-007
- **依赖**：TASK-7E-01
- **验收标准**：上述所有检查通过
- **影响文件**：无（验证任务）
- **优先级**：高
- **复杂度**：低

#### TASK-7E-03: 外部 API 兼容性验证

- [ ] 验证以下外部调用方式不变：
  - `host_service.invoke()` 调用 `kernel.search_memory()` / `kernel.ingest_text()` / `kernel.ingest_summary()` / `kernel.get_person_profile()` / `kernel.maintain_memory()` / `kernel.memory_stats()` / `kernel.enqueue_feedback_task()` / `kernel.memory_*_admin()` — 签名和行为不变
  - `AMemorixMemoryServicePort` 调用 `kernel.search_memory()` / `kernel.get_person_profile()` — 签名和行为不变
  - `plugin.py` 调用方式不变
- **需求ID**：REQ-CLEANUP-009
- **依赖**：TASK-7E-01
- **验收标准**：所有外部调用方式不变；返回值结构不变
- **影响文件**：无（验证任务）
- **优先级**：极高
- **复杂度**：低

#### TASK-7E-04: 端到端功能回归验证

- [ ] 在容器内执行端到端功能验证：
  - 记忆检索 → `search_memory()` 返回正确结果
  - 文本摄入 → `ingest_text()` 正确写入 metadata + 向量 + 实体 + 关系
  - 摘要导入 → `ingest_summary()` 正确导入
  - 人物画像 → `get_person_profile()` 返回正确画像
  - 记忆维护 → 衰减/冻结/修剪/孤立 GC 正常运行
  - 反馈纠错 → 信号检测/分类器调用/纠错应用/回退执行正常
  - 模糊修改 → 预览/执行/回滚正常
  - 向量重建 → 全量重建/双池迁移正常
  - Admin API → 所有 `memory_*_admin` 操作正常
  - WebUI 管理 → 所有管理界面操作正常
  - 后台循环 → 9 个后台循环正常启动和运行
- **需求ID**：REQ-CLEANUP-009
- **依赖**：TASK-7E-01、TASK-7E-02、TASK-7E-03
- **验收标准**：所有端到端场景验证通过；无功能回归
- **影响文件**：无（验证任务）
- **优先级**：极高
- **复杂度**：中