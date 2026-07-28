# ChatManager Protocol 接口层补全 — 编码任务清单

## 迁移总览

- **目标**：补全 ChatManager 的 Protocol 接口层，消灭 BotChatSession 可变引用泄漏，使所有模块通过 Protocol 访问 ChatManager
- **约束**：ChatManager 本体不拆分，每个阶段可独立验证和回滚
- **阶段数**：5 个阶段，按依赖关系串行推进
- **总任务数**：5 个主任务组，22 个子任务

---

## 1. 阶段1：Protocol 定义 + 适配器实现（零风险引入）

**目标**：新增 3 个 Protocol 定义、扩展 SessionInfo、实现 ChatManagerAdapter、扩展注册机制。纯增量，无消费者，零风险。

### 1.1 扩展 SessionInfo 数据模型

- [ ] 在 `src/core/types.py` 的 `SessionInfo` frozen dataclass 中新增 3 个字段：`account_id: str = ""`、`scope: str = ""`、`user_cardname: str = ""`，并添加字段注释说明用途
- **涉及文件**：`src/core/types.py`
- **验收标准**：SessionInfo 可正常实例化（新字段有默认值，向后兼容）；已有代码无需修改
- **依赖**：无

### 1.2 新增 SessionLifecyclePort Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `SessionLifecyclePort` Protocol，包含 4 个方法：`get_or_create_session_id()`（异步）、`save_all_sessions()`（同步）、`initialize()`（异步）、`regularly_save_sessions()`（异步），每个方法需有完整 docstring
- **涉及文件**：`src/core/protocols.py`
- **验收标准**：Protocol 定义可被 `@runtime_checkable` 检查；方法签名与 design.md 2.2.2 节一致
- **依赖**：无

### 1.3 新增 SessionQueryPort Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `SessionQueryPort` Protocol，包含 6 个方法：`resolve_sessions_by_target()`、`resolve_session_ids_by_target()`、`get_last_message()`、`list_sessions()`、`get_route_metadata()`、`get_session_count()`，每个方法需有完整 docstring
- **涉及文件**：`src/core/protocols.py`
- **验收标准**：方法签名与 design.md 2.2.2 节一致；`get_route_metadata()` 返回 `Dict[str, object]`
- **依赖**：无

### 1.4 新增 MessageRegistryPort Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `MessageRegistryPort` Protocol，包含 1 个方法：`register_message(message)`，需有 docstring 说明 ValueError 异常
- **涉及文件**：`src/core/protocols.py`
- **验收标准**：Protocol 定义可被 `@runtime_checkable` 检查
- **依赖**：无

### 1.5 实现 ChatManagerAdapter 统一适配器

- [ ] 新建 `src/core/adapters/chat_manager_adapter.py`，实现 `ChatManagerAdapter` 类，同时满足 `SessionLifecyclePort`、`SessionQueryPort`、`MessageRegistryPort`、`SessionRepository`、`SessionInfoPort` 五个 Protocol
- **涉及文件**：`src/core/adapters/chat_manager_adapter.py`（新建）
- **实现要点**：
  1. 延迟导入 chat_manager（与现有适配器一致）
  2. 从 `ChatManagerSessionRepository` 迁移 `_build_session_info()` 逻辑，扩展映射 `account_id`、`scope`、`user_cardname` 三个新字段，消除 `getattr` 改为直接属性访问
  3. `get_or_create_session_id()`：委托 `chat_manager.get_or_create_session()`，返回 `session_id` 字符串
  4. `save_all_sessions()`：委托 `chat_manager.save_all_sessions()`
  5. `initialize()`：委托 `chat_manager.initialize()`
  6. `regularly_save_sessions()`：委托 `chat_manager.regularly_save_sessions()`
  7. `resolve_sessions_by_target()`：委托后转换为 `List[SessionInfo]`
  8. `resolve_session_ids_by_target()`：委托后返回 `set[str]`
  9. `get_last_message()`：从 `chat_manager.last_messages` 获取
  10. `list_sessions()`：遍历 `chat_manager.sessions.values()`，过滤后转换为 `List[SessionInfo]`
  11. `get_route_metadata()`：获取 BotChatSession → 检查 context → 提取 `additional_config` 中的路由键（`RouteKeyFactory.ACCOUNT_ID_KEYS` + `RouteKeyFactory.SCOPE_KEYS`），返回字典
  12. `get_session_count()`：统计 `chat_manager.sessions` 数量
  13. `register_message()`：委托 `chat_manager.register_message()`
  14. 复用 `SessionRepository` 的 `get_session()`、`get_session_name()`
  15. 复用 `SessionInfoPort` 的 `get_session_info()`、`get_existing_session_info()`
- **验收标准**：ChatManagerAdapter 可实例化；所有 Protocol 方法可正常委托 chat_manager；SessionInfo 新增字段正确映射
- **依赖**：1.1, 1.2, 1.3, 1.4

### 1.6 扩展注册机制

- [ ] 在 `src/core/session_port_registry.py` 中新增 3 对注册/获取函数：`register_session_lifecycle_port()`/`get_session_lifecycle_port()`、`register_session_query_port()`/`get_session_query_port()`、`register_message_registry_port()`/`get_message_registry_port()`；同时将 `get_last_message()` 从直接导入 chat_manager 改为通过 SessionQueryPort 获取
- **涉及文件**：`src/core/session_port_registry.py`
- **验收标准**：注册/获取函数可正常工作；`get_last_message()` 不再直接导入 chat_manager
- **依赖**：1.5

### 阶段1 验证

- [ ] 验证 ChatManagerAdapter 可实例化并委托 chat_manager
- [ ] 验证 SessionInfo 新增字段正确映射（account_id/scope/user_cardname）
- [ ] 验证现有功能不受影响（纯增量，无消费者）
- [ ] 验证 `get_route_metadata()` 能正确提取路由元数据
- **验证方法**：启动系统，确认无报错；手动调用适配器方法检查返回值

---

## 2. 阶段2：核心层消费者迁移

**目标**：将 main.py 和 session_port_registry 的 chat_manager 直接导入替换为 Protocol 调用，使核心层零 chat_manager 直接导入。

### 2.1 迁移 main.py 到 SessionLifecyclePort

- [ ] 将 `src/main.py` 中 `from src.chat.message_receive.chat_manager import chat_manager` 替换为 `from src.core.session_port_registry import get_session_lifecycle_port`；将 `await chat_manager.initialize()` 替换为 `await port.initialize()`；将 `asyncio.create_task(chat_manager.regularly_save_sessions())` 替换为 `asyncio.create_task(port.regularly_save_sessions())`；更新注册代码使用 ChatManagerAdapter 统一注册所有 Protocol
- **涉及文件**：`src/main.py`
- **验收标准**：main.py 不再直接导入 chat_manager；启动流程正常（初始化、定期保存）
- **依赖**：1.5, 1.6
- ⚠️ **高风险**：main.py 是系统启动入口，修改后需验证完整启动流程

### 2.2 确认 heartflow_manager 已通过 Protocol 访问

- [ ] 验证 `src/chat/heart_flow/heartflow_manager.py` 的延迟导入 chat_manager 仅用于适配器层内部，核心逻辑已通过 SessionRepository 访问；如有残留直接导入需迁移
- **涉及文件**：`src/chat/heart_flow/heartflow_manager.py`
- **验收标准**：heartflow_manager 核心逻辑不直接导入 chat_manager
- **依赖**：1.5

### 阶段2 验证

- [ ] 执行 `grep -r "from src.chat.message_receive.chat_manager import" src/main.py src/core/`，确认零匹配（适配器层除外）
- [ ] 验证系统启动流程正常（main.py → initialize → regularly_save_sessions）
- [ ] 验证 session_port_registry.get_last_message() 功能正常
- **验证方法**：启动系统，确认完整初始化无报错

---

## 3. 阶段3：BotChatSession 可变引用消除

**目标**：消除回复/生成层、运行时层、发送服务层、数据库服务层的 BotChatSession 类型依赖，改为 SessionInfo 或 session_id。

### 3.1 迁移 maisaka_generator_base 到 SessionInfo

- [ ] 将 `src/chat/replyer/maisaka_generator_base.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession` 替换为 `from src.core.types import SessionInfo`；将 `chat_stream: Optional[BotChatSession]` 参数类型改为 `Optional[SessionInfo]`；将内部 `chat_stream.session_id`、`chat_stream.is_group_session` 等访问改为 `session_info.session_id`、`session_info.is_group_session`；消除 `getattr(chat_stream, "session_id", "")` 改为直接属性访问
- **涉及文件**：`src/chat/replyer/maisaka_generator_base.py`
- **验收标准**：文件不再导入 BotChatSession；生成器通过 SessionInfo 字段访问所需信息
- **依赖**：1.1

### 3.2 迁移 maisaka_generator 到 SessionInfo

- [ ] 将 `src/chat/replyer/maisaka_generator.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession` 替换为 `from src.core.types import SessionInfo`；将 `chat_stream: Optional[BotChatSession]` 参数类型改为 `Optional[SessionInfo]`；将内部 BotChatSession 属性访问改为 SessionInfo 字段访问
- **涉及文件**：`src/chat/replyer/maisaka_generator.py`
- **验收标准**：文件不再导入 BotChatSession
- **依赖**：3.1

### 3.3 迁移 replyer_manager 到 SessionInfo

- [ ] 将 `src/chat/replyer/replyer_manager.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession, chat_manager as _chat_manager` 替换为 `from src.core.types import SessionInfo` + SessionRepository 导入；将 `chat_stream: Optional[BotChatSession]` 参数类型改为 `Optional[SessionInfo]`；将 `_chat_manager` 调用替换为 SessionRepository/SessionQueryPort 调用
- **涉及文件**：`src/chat/replyer/replyer_manager.py`
- **验收标准**：文件不再导入 BotChatSession 和 chat_manager
- **依赖**：3.2

### 3.4 迁移 generator_service 到 SessionInfo

- [ ] 将 `src/services/generator_service.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession` 替换为 `from src.core.types import SessionInfo`；将所有 `chat_stream: Optional[BotChatSession]` 参数类型改为 `Optional[SessionInfo]`
- **涉及文件**：`src/services/generator_service.py`
- **验收标准**：文件不再导入 BotChatSession
- **依赖**：3.1

### 3.5 迁移 runtime.py 消除 BotChatSession 可变引用

- [ ] 将 `src/maisaka/runtime.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession` 替换；将 `self.chat_stream: BotChatSession = chat_stream` 改为使用 `self._session_info: SessionInfo`（已有字段）；将所有 `self.chat_stream.xxx` 访问改为 `self._session_info.xxx`；评估 L145 和 L1485 的延迟导入 chat_manager 是否可通过 Protocol 替代
- **涉及文件**：`src/maisaka/runtime.py`
- **验收标准**：runtime.py 不再持有 BotChatSession 可变引用；不再导入 BotChatSession 类型；运行时生命周期正常
- **依赖**：1.1
- ⚠️ **高风险**：runtime.py 是心流核心，修改后需验证运行时创建/销毁/智能体切换

### 3.6 迁移 send_service 到路由元数据字典

- [ ] 将 `src/services/send_service.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession, chat_manager as _chat_manager` 替换为 SessionQueryPort 导入；将 `_inherit_platform_io_route_metadata(target_stream: BotChatSession)` 改为 `_inherit_platform_io_route_metadata(route_metadata: Dict[str, object])`；调用方在发送前通过 `SessionQueryPort.get_route_metadata(session_id)` 获取字典传入；方法内部从字典直接读取路由键，不再访问 BotChatSession
- **涉及文件**：`src/services/send_service.py`
- **验收标准**：send_service 不再导入 BotChatSession 和 chat_manager；消息发送路由元数据正确继承
- **依赖**：1.5
- ⚠️ **高风险**：send_service 是消息发送核心，路由元数据丢失会导致多账号场景消息发错

### 3.7 迁移 database_service 参数类型

- [ ] 将 `src/services/database_service.py` 中 `chat_stream: "BotChatSession"` 参数类型改为 `chat_stream: str`（session_id）；将函数内部 `chat_stream.session_id` 等访问改为直接使用 session_id 字符串
- **涉及文件**：`src/services/database_service.py`
- **验收标准**：database_service 不再导入 BotChatSession（含 TYPE_CHECKING 导入）
- **依赖**：1.1

### 3.8 迁移 maisaka_cli 到 SessionInfo + SessionLifecyclePort

- [ ] 将 `src/cli/maisaka_cli.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession, chat_manager` 替换为 SessionInfo + SessionLifecyclePort 导入；将 `self._session: BotChatSession | None` 改为 `self._session_info: SessionInfo | None`；将 chat_manager 调用替换为 Protocol 调用
- **涉及文件**：`src/cli/maisaka_cli.py`
- **验收标准**：CLI 不再导入 BotChatSession 和 chat_manager
- **依赖**：1.2, 1.5

### 阶段3 验证

- [ ] 执行 `grep -r "BotChatSession" src/chat/replyer/ src/services/ src/maisaka/runtime.py src/cli/`，确认零匹配
- [ ] 验证回复生成功能正常（群聊 + 私聊）
- [ ] 验证消息发送路由元数据正确继承（多账号场景）
- [ ] 验证运行时生命周期正常（创建/销毁/切换智能体）
- [ ] 验证数据库存储功能正常（tool_info/action_info 使用 session_id）
- **验证方法**：启动系统，发送消息验证回复链路；检查多账号路由是否正确

---

## 4. 阶段4：外围模块导入消除

**目标**：将 WebUI、学习器、插件运行时、工具/配置、person_info、event_helpers、statistic 等外围模块的 chat_manager 直接导入替换为 Protocol 调用。

### 4.1 迁移 WebUI 路由到 SessionQueryPort

- [ ] 将以下 6 个 WebUI 路由文件中的 `from src.chat.message_receive.chat_manager import chat_manager as _chat_manager`（或等价导入）替换为 `from src.core.session_port_registry import get_session_query_port`；将 `_chat_manager.xxx()` 调用替换为 `get_session_query_port().xxx()`；将 BotChatSession 属性访问改为 SessionInfo 属性访问：
  - `src/webui/routers/chat/routes.py`
  - `src/webui/routers/agent.py`
  - `src/webui/routers/memory.py`
  - `src/webui/routers/expression.py`
  - `src/webui/routers/jargon.py`
  - `src/webui/routers/reasoning_process.py`
- **涉及文件**：6 个 WebUI 路由文件
- **验收标准**：WebUI 路由不再直接导入 chat_manager；所有页面功能正常
- **依赖**：1.5

### 4.2 迁移学习器到 SessionQueryPort

- [ ] 将以下 4 个学习器文件中的延迟导入 `from src.chat.message_receive.chat_manager import chat_manager` 替换为 `from src.core.session_port_registry import get_session_query_port`；将 `chat_manager.resolve_sessions_by_target()` 替换为 `port.resolve_sessions_by_target()`；将 `chat_manager.resolve_session_ids_by_target()` 替换为 `port.resolve_session_ids_by_target()`；将返回值从 `List[BotChatSession]` 改为 `List[SessionInfo]`，后续属性访问对应调整：
  - `src/learners/jargon_learner.py`
  - `src/learners/expression_learner.py`
  - `src/learners/behavior_learner.py`
  - `src/learners/behavior_pattern_store.py`
- **涉及文件**：4 个学习器文件
- **验收标准**：学习器不再直接导入 chat_manager；学习功能正常
- **依赖**：1.5

### 4.3 迁移插件运行时到 SessionLifecyclePort + SessionQueryPort

- [ ] 将 `src/plugin_runtime/capabilities/data.py` 中 `from src.chat.message_receive.chat_manager import BotChatSession` 和延迟导入 chat_manager 替换为 SessionQueryPort；将 `_list_sessions()` 改为通过 `SessionQueryPort.list_sessions()` 获取 `List[SessionInfo]`；将 `_serialize_stream(stream: BotChatSession)` 改为 `_serialize_stream(stream: SessionInfo)`；将 `_cap_chat_open_session()` 改为通过 `SessionLifecyclePort.get_or_create_session_id()` 获取 session_id
- [ ] 将 `src/plugin_runtime/capabilities/core.py` 中延迟导入 chat_manager 替换为 SessionLifecyclePort
- **涉及文件**：`src/plugin_runtime/capabilities/data.py`、`src/plugin_runtime/capabilities/core.py`
- **验收标准**：插件运行时不再导入 BotChatSession 和 chat_manager；插件功能正常
- **依赖**：1.5

### 4.4 迁移工具/配置层到 SessionQueryPort

- [ ] 将以下 4 个文件中的延迟导入 chat_manager 替换为 SessionQueryPort：
  - `src/common/utils/utils_config.py`（5 处延迟导入）
  - `src/chat/utils/utils.py`（顶层导入）
  - `src/chat/utils/statistic.py`（延迟导入）
  - `src/chat/event_helpers.py`（2 处延迟导入）
- **涉及文件**：4 个工具/配置文件
- **验收标准**：上述文件不再直接导入 chat_manager
- **依赖**：1.5

### 4.5 迁移 person_info 到 SessionQueryPort

- [ ] 将 `src/person_info/person_info.py` 中 `from src.chat.message_receive.chat_manager import chat_manager as _chat_manager` 替换为 SessionQueryPort；将 `_chat_manager.resolve_sessions_by_target()` 等调用替换为 Protocol 调用
- **涉及文件**：`src/person_info/person_info.py`
- **验收标准**：person_info 不再直接导入 chat_manager
- **依赖**：1.5

### 阶段4 验证

- [ ] 执行 `grep -r "from src.chat.message_receive.chat_manager import" src/ --include="*.py"`，确认仅匹配适配器层（`src/core/adapters/`）、chat 包内部模块（`src/chat/message_receive/__init__.py`、`src/chat/__init__.py`）
- [ ] 验证 WebUI 所有页面功能正常
- [ ] 验证学习器功能正常
- [ ] 验证插件运行时功能正常
- [ ] 验证 person_info 功能正常
- **验证方法**：启动系统，逐一验证各模块功能

---

## 5. 阶段5：旧适配器清理

**目标**：删除 ChatManagerSessionRepository（功能已被 ChatManagerAdapter 包含），统一注册逻辑。

### 5.1 删除 ChatManagerSessionRepository

- [ ] 删除 `src/core/adapters/session_repository.py` 中的 `ChatManagerSessionRepository` 类；确保 `ChatManagerAdapter` 已包含 `SessionRepository` + `SessionInfoPort` 的所有方法（`get_session`、`get_session_name`、`get_session_info`、`get_existing_session_info`）；更新所有引用 `ChatManagerSessionRepository` 的代码改为使用 `ChatManagerAdapter`
- **涉及文件**：`src/core/adapters/session_repository.py`、`src/main.py`（注册代码）
- **验收标准**：ChatManagerSessionRepository 不再存在；所有功能由 ChatManagerAdapter 提供
- **依赖**：阶段2、阶段3、阶段4 全部完成

### 5.2 统一注册逻辑

- [ ] 更新 `src/main.py` 中的注册代码，统一使用 ChatManagerAdapter 实例注册所有 Protocol（SessionRepository、SessionInfoPort、SessionLifecyclePort、SessionQueryPort、MessageRegistryPort）；确认所有注册点指向同一个 ChatManagerAdapter 实例
- **涉及文件**：`src/main.py`、`src/core/session_port_registry.py`
- **验收标准**：所有 Protocol 注册点指向 ChatManagerAdapter 实例；注册逻辑简洁清晰
- **依赖**：5.1

### 5.3 更新测试文件

- [ ] 更新 `pytests/` 下引用 `ChatManagerSessionRepository` 或 `BotChatSession` 的测试文件，改为使用 ChatManagerAdapter 和 SessionInfo：
  - `pytests/common_test/test_expression_learner.py`
  - `pytests/common_test/test_chat_config_utils.py`
  - `pytests/A_memorix_test/test_chat_summary_writeback_integration.py`
  - `pytests/utils_test/test_session_utils.py`
- **涉及文件**：4 个测试文件
- **验收标准**：测试文件不再导入 ChatManagerSessionRepository 和 BotChatSession（chat_manager.py 自身除外）
- **依赖**：5.1

### 阶段5 验证

- [ ] 全量功能测试通过
- [ ] 无 ChatManagerSessionRepository 的残留引用
- [ ] 所有 Protocol 注册点指向 ChatManagerAdapter 实例
- [ ] 执行 `grep -r "ChatManagerSessionRepository" src/ --include="*.py"`，确认零匹配
- **验证方法**：启动系统，执行完整功能验证；运行测试套件

---

## 风险标注汇总

| 阶段 | 任务 | 风险等级 | 风险说明 |
|------|------|---------|---------|
| 2 | 2.1 main.py 迁移 | ⚠️ 高 | 系统启动入口，修改后需验证完整启动流程 |
| 3 | 3.5 runtime.py 迁移 | ⚠️ 高 | 心流核心，需验证运行时创建/销毁/智能体切换 |
| 3 | 3.6 send_service 迁移 | ⚠️ 高 | 消息发送核心，路由元数据丢失会导致多账号场景消息发错 |

## 回滚策略

| 阶段 | 回滚方式 | 影响范围 |
|------|---------|---------|
| 阶段1 | 删除新增文件和 Protocol 定义 | 零影响（纯增量，无消费者） |
| 阶段2 | 恢复 main.py 和 session_port_registry.py 的原始导入 | 仅核心入口 |
| 阶段3 | 恢复 BotChatSession 参数类型 | 回复/生成/发送/运行时层 |
| 阶段4 | 恢复外围模块的 chat_manager 直接导入 | WebUI/学习器/插件/工具层 |
| 阶段5 | 恢复 ChatManagerSessionRepository | 适配器层 |