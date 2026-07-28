# SSD-3 架构债务消除 — 编码任务清单

## 概述

消除 ChatManager 全局单例物理耦合和 maisaka → chat 跨层物理依赖，实现适配器层依赖注入和智能体层物理隔离。

3 阶段 / 7 批次，每批次可独立验证。

---

## 1. 阶段1：子模块直接注入

**目标**：ChatManagerAdapter 不再持有 ChatManager 单例引用，改为直接持有 6 个子模块实例。ChatManagerRoutingAdapter 不再延迟导入 chat_manager，改为构造注入 AgentRouter。

**风险等级**：中（核心适配器改造，影响所有 Protocol 端口调用链路）
**回滚策略**：git revert 整批，ChatManager 单例仍可用作 fallback

### 1.1 ChatManagerAdapter 构造函数改造

- [ ] 修改 `src/core/adapters/chat_manager_adapter.py` 的 `ChatManagerAdapter.__init__`，将参数从 `chat_manager: Any` 改为 6 个子模块实例 + routing_service：
  - `routing_service: AgentRoutingService`（保留）
  - `session_store: SessionStore`（必填）
  - `message_registry: MessageRegistry`（必填）
  - `name_cache: SessionNameCache`（必填）
  - `resolver: SessionResolver`（必填）
  - `binding_restorer: Optional[BindingRestorer] = None`（延迟初始化）
  - `session_lifecycle: Optional[SessionLifecycle] = None`（延迟初始化）
  - 必填参数为 None 时构造函数抛出 TypeError
- [ ] 删除 `_ensure_chat_manager()` 方法
- [ ] 删除 `_chat_manager` 实例属性
- [ ] 修改 `_build_session_info` 方法签名，移除 `chat_manager` 参数，改为使用 `self._name_cache.get(session_id)` 获取会话名称

**验证**：
```bash
grep "_ensure_chat_manager" src/core/adapters/chat_manager_adapter.py  # → 零匹配
grep "_chat_manager" src/core/adapters/chat_manager_adapter.py  # → 零匹配
```

### 1.2 ChatManagerAdapter 方法委托改造

- [ ] 逐方法将 `chat_manager.xxx()` 替换为子模块直接调用：
  - `get_session()` → `self._session_store.get(session_id)`
  - `get_session_name()` → `self._name_cache.get(session_id)`
  - `get_session_info()` → `self._session_store.get(session_id)`
  - `get_existing_session_info()` → `self._session_store.get_existing(session_id)`
  - `get_or_create_session_id()` → `self._session_lifecycle.get_or_create_session()`
  - `save_all_sessions()` → `self._session_lifecycle.save_all_sessions()`
  - `initialize()` → `self._session_lifecycle.initialize()`
  - `regularly_save_sessions()` → `self._session_lifecycle.regularly_save_sessions()`
  - `resolve_sessions_by_target()` → `self._resolver.resolve_by_target()`
  - `resolve_session_ids_by_target()` → `self._resolver.resolve_ids_by_target()`
  - `get_last_messages()` → `self._message_registry.last_messages.get()`
  - `list_sessions()` → `self._session_store.sessions.values()`
  - `get_route_metadata()` → `self._build_route_metadata(session_id)`（私有助手方法，内部使用 `self._session_store.get(session_id)` + RouteKeyFactory）
  - `get_session_count()` → `len(self._session_store.sessions)`
  - `register_message()` → `self._message_registry.register()`
- [ ] 对 `binding_restorer` 和 `session_lifecycle` 的延迟初始化，在适配器内部保留 `_ensure_binding_restorer()` / `_ensure_session_lifecycle()` 方法，未注入时抛出 RuntimeError

**验证**：
```bash
grep "chat_manager\." src/core/adapters/chat_manager_adapter.py  # → 零匹配（不含注释/文档字符串）
```

### 1.3 ChatManagerRoutingAdapter 构造注入改造

- [ ] 修改 `src/core/adapters/routing_adapter.py` 的 `ChatManagerRoutingAdapter.__init__`，新增 `agent_router: AgentRouter` 参数
- [ ] 删除 `_ensure_router()` 方法及其延迟导入 `from src.chat.message_receive.chat_manager import chat_manager`
- [ ] 所有方法改为直接使用 `self._agent_router`

**验证**：
```bash
grep "_ensure_router" src/core/adapters/routing_adapter.py  # → 零匹配
grep "from src.chat.message_receive.chat_manager" src/core/adapters/routing_adapter.py  # → 零匹配
```

### 1.4 main.py 启动编排改造

- [ ] 修改 `src/main.py` 的 `_init_components()` 方法，将当前的：
  ```python
  from src.chat.message_receive.chat_manager import chat_manager
  _adapter = ChatManagerAdapter(ChatManagerRoutingAdapter(), chat_manager=chat_manager)
  ```
  改为显式构造子模块并注入：
  ```python
  from src.chat.message_receive.session_store import SessionStore
  from src.chat.message_receive.message_registry import MessageRegistry
  from src.chat.message_receive.session_name_cache import SessionNameCache
  from src.chat.message_receive.session_resolver import SessionResolver
  from src.chat.message_receive.binding_restorer import BindingRestorer
  from src.chat.message_receive.session_lifecycle import SessionLifecycle
  from src.maisaka.agent.router import AgentRouter
  from src.maisaka.agent.registry import AgentConfigRegistry

  # 构造子模块
  session_store = SessionStore()
  message_registry = MessageRegistry(session_store)
  session_store.set_message_registry(message_registry)
  name_cache = SessionNameCache(session_store)
  resolver = SessionResolver(session_store)
  agent_router = AgentRouter(AgentConfigRegistry())
  binding_restorer = BindingRestorer(agent_router)
  session_lifecycle = SessionLifecycle(session_store, message_registry, agent_router)

  # 构造适配器
  routing_adapter = ChatManagerRoutingAdapter(agent_router)
  _adapter = ChatManagerAdapter(
      routing_service=routing_adapter,
      session_store=session_store,
      message_registry=message_registry,
      name_cache=name_cache,
      resolver=resolver,
      binding_restorer=binding_restorer,
      session_lifecycle=session_lifecycle,
  )
  ```
- [ ] 将 `chat_manager` 单例的 `agent_router` 属性指向同一个 `agent_router` 实例，确保 `chat_manager._agent_router = agent_router`（向后兼容，直到阶段3退役单例）
- [ ] 将 `chat_manager` 单例的 `binding_restorer` 和 `session_lifecycle` 也指向同一实例

**验证**：
```bash
# 启动后所有 Protocol 端口行为与迁移前一致
# 适配器在未注入子模块时立即抛出 TypeError
docker exec maim-bot-core python -c "from src.core.adapters.chat_manager_adapter import ChatManagerAdapter; ChatManagerAdapter(None)"  # → TypeError
```

---

## 2. 阶段2：maisaka 跨层依赖消除

**目标**：`src/maisaka/` 目录下零 `from src.chat.*` 导入，零 `_chat_manager` 访问。

**风险等级**：中高（涉及 maisaka 核心运行时改造，需逐项验证功能不回归）
**回滚策略**：每批次独立 git commit，可精确 revert 单批次

### 2.1 process_llm_response 物理迁移

- [ ] 在 `src/maisaka/context/post_processor.py` 中物理定义 `process_llm_response` 函数，从 `src/chat/utils/utils.py` 迁移函数体及以下辅助依赖：
  - `protect_kaomoji` / `recover_kaomoji` — 颜文字保护/恢复
  - `split_into_sentences_w_remove_punctuation` — 分句
  - `_is_stage_direction` — 舞台指示判断
  - `merge_sentences_to_max_count` — 合并句子
  - `get_western_ratio` — 西文字符比例
  - `_get_random_default_reply` — 默认回复
  - `ChineseTypoGenerator` — 从 `src/chat/utils/typo_generator.py` 一并迁移到 `src/maisaka/context/typo_generator.py`
- [ ] 删除 `post_processor.py` 末尾的 re-export 行：`from src.chat.utils.utils import process_llm_response as process_llm_response`
- [ ] 在 `src/chat/utils/utils.py` 原位置添加 re-export：`from src.maisaka.context.post_processor import process_llm_response`（保持 `generator_service.py` 兼容）
- [ ] 在 `src/chat/utils/typo_generator.py` 原位置添加 re-export：`from src.maisaka.context.typo_generator import ChineseTypoGenerator`（保持 chat 层其他模块兼容）
- [ ] 确认 `src/services/generator_service.py` 无需修改（通过 re-export 兼容）

**验证**：
```bash
grep "from src.chat.utils.utils import process_llm_response" src/maisaka/  # → 零匹配
python -c "from src.chat.utils.utils import process_llm_response; print('re-export OK')"  # → re-export OK
python -c "from src.maisaka.context.post_processor import process_llm_response; print('direct import OK')"  # → direct import OK
```

### 2.2 ReplyerServicePort 接口化

- [ ] 在 `src/core/protocols.py` 新增 `ReplyerServicePort` Protocol：
  ```python
  @runtime_checkable
  class ReplyerServicePort(Protocol):
      def get_replyer(
          self,
          chat_stream: Optional[SessionInfo] = None,
          chat_id: Optional[str] = None,
          request_type: str = "replyer",
          replyer_type: str = "default",
      ) -> Optional[MaisakaReplyGenerator]: ...
  ```
  - `MaisakaReplyGenerator` 类型通过 `TYPE_CHECKING` 导入，运行时无依赖
- [ ] 新增 `src/core/adapters/replyer_service_adapter.py`，实现 `ReplyerServicePort`：
  - 构造函数接收 `ReplyerManager` 实例
  - `get_replyer()` 直接委托到 `ReplyerManager.get_replyer()`
- [ ] 新增 `src/core/replyer_port_registry.py`，提供 `register_replyer_service_port()` / `get_replyer_service_port()` 注册点
- [ ] 修改 `src/maisaka/builtin_tool/reply.py`，将 `from src.chat.replyer.replyer_manager import replyer_manager` 替换为通过 `get_replyer_service_port()` 获取接口，调用 `port.get_replyer()`
- [ ] 修改 `src/main.py`，在 `_init_components()` 中注册 ReplyerServicePort：
  ```python
  from src.chat.replyer.replyer_manager import ReplyerManager
  from src.core.adapters.replyer_service_adapter import ReplyerServiceAdapter
  from src.core.replyer_port_registry import register_replyer_service_port
  register_replyer_service_port(ReplyerServiceAdapter(ReplyerManager()))
  ```

**验证**：
```bash
grep "from src.chat.replyer.replyer_manager import replyer_manager" src/maisaka/  # → 零匹配
grep "ReplyerServicePort" src/core/protocols.py  # → 有匹配
```

### 2.3 ImageDescriptionPort 接口化

- [ ] 在 `src/core/protocols.py` 新增 `ImageDescriptionPort` Protocol：
  ```python
  @runtime_checkable
  class ImageDescriptionPort(Protocol):
      async def get_image_description(
          self,
          image_hash: str,
          image_bytes: bytes,
          wait_for_build: bool = True,
      ) -> str: ...
  ```
- [ ] 新增 `src/core/adapters/image_description_adapter.py`，实现 `ImageDescriptionPort`：
  - 构造函数接收 `ImageManager` 实例
  - `get_image_description()` 直接委托到 `ImageManager.get_image_description()`
- [ ] 新增 `src/core/image_port_registry.py`，提供 `register_image_description_port()` / `get_image_description_port()` 注册点
- [ ] 修改 `src/maisaka/runtime.py` 的 `_recognize_sent_images()` 方法，将延迟导入 `from src.chat.image_system.image_manager import image_manager` 替换为通过 `get_image_description_port()` 获取接口，调用 `port.get_image_description()`
- [ ] 修改 `src/main.py`，在 `_init_components()` 中注册 ImageDescriptionPort：
  ```python
  from src.chat.image_system.image_manager import ImageManager
  from src.core.adapters.image_description_adapter import ImageDescriptionAdapter
  from src.core.image_port_registry import register_image_description_port
  register_image_description_port(ImageDescriptionAdapter(ImageManager()))
  ```
  - 注意：`ImageManager()` 在 `image_manager.py` 模块级已有实例 `image_manager`，直接传入该实例即可

**验证**：
```bash
grep "from src.chat.image_system.image_manager import image_manager" src/maisaka/  # → 零匹配
grep "ImageDescriptionPort" src/core/protocols.py  # → 有匹配
```

### 2.4 fork_context 消除 `_chat_manager` 访问

- [ ] 修改 `src/maisaka/subagent/fork_context.py` 的 `ForkContextCapturer.__init__`，新增 `session_info_port: Optional[SessionInfoPort] = None` 参数
- [ ] 修改 `_capture_system_messages()` 方法：
  - 将 `self._runtime._chat_manager.get_session(session_id)` 替换为 `self._session_info_port.get_session_info(session_id)`（如果 `session_info_port` 已注入）
  - 删除 `bot_chat_session._last_prompt_context` 的访问（这是 BotChatSession 私有属性，无法通过 Protocol 安全暴露）
  - system 消息捕获改为从 `AgentConfigRegistry` 获取 system prompt 模板名称，或简化为返回空列表（ForkContext 捕获是子智能体功能，当前使用频率低）
- [ ] 确保 `ForkContextCapturer` 在 `session_info_port` 为 None 时降级为返回空列表（不抛异常）

**验证**：
```bash
grep "_chat_manager" src/maisaka/subagent/fork_context.py  # → 零匹配
```

### 2.5 session_recovery 消除 ChatManager 依赖

- [ ] 修改 `src/maisaka/agent_autonomy/session_recovery.py` 的 `SessionRecoveryService.recover_all()`：
  - 参数从 `chat_manager: Any` 改为 `session_query_port: SessionQueryPort`
  - 内部 `chat_manager.get_existing_session_by_session_id(record.session_id)` 替换为 `session_query_port.get_existing_session_info(record.session_id)`
  - 注意：原代码检查 `chat_session is None`，迁移后检查 `session_info is None` 即可
- [ ] 修改 `src/maisaka/runtime.py` 的自主性架构初始化代码（约 L1520-1528）：
  - 将 `_query_port._ensure_chat_manager()` 替换为 `get_session_query_port()` 直接传入
  - 删除 `from src.core.adapters.chat_manager_adapter import ChatManagerAdapter` 的 isinstance 检查
  - 改为：
    ```python
    _query_port = get_session_query_port()
    if _query_port is not None:
        asyncio.create_task(recovery.recover_all(_query_port))
    ```

**验证**：
```bash
grep "_ensure_chat_manager" src/maisaka/  # → 零匹配
grep "chat_manager" src/maisaka/agent_autonomy/session_recovery.py  # → 零匹配（不含注释）
```

### 2.6 maisaka 跨层依赖消除全量验证

- [ ] 确认 `src/maisaka/` 目录下零 `from src.chat.*` 导入
- [ ] 确认 `src/maisaka/` 目录下零 `_chat_manager` 访问
- [ ] 回复工具正常获取 replyer 并生成回复
- [ ] 图片描述功能正常触发
- [ ] ForkContext 捕获不抛异常（system 消息可能为空列表）
- [ ] session_recovery 正常恢复智能体关联

**验证**：
```bash
rg "from src\.chat\." src/maisaka/  # → 零匹配
rg "_chat_manager" src/maisaka/  # → 零匹配
```

---

## 3. 阶段3：ChatManager 单例退役 + ruff 守卫

**目标**：ChatManager 模块级单例移除，ruff TID251 守卫覆盖 maisaka 目录。

**风险等级**：高（删除全局单例，需确认所有消费者已迁移）
**回滚策略**：恢复 `chat_manager = ChatManager()` 行 + 恢复 `__init__.py` re-export

### 3.1 ChatManager 单例移除

- [ ] 删除 `src/chat/message_receive/chat_manager.py` 末尾的 `chat_manager = ChatManager()` 模块级单例
- [ ] 修改 `src/chat/message_receive/__init__.py`，移除 `from src.chat.message_receive.chat_manager import chat_manager`
- [ ] 修改 `src/chat/__init__.py`，移除 `from src.chat.message_receive.chat_manager import chat_manager`
- [ ] 修改 `src/chat/message_receive/bot.py`，将 `from .chat_manager import chat_manager` 替换为通过注册点获取端口：
  - `chat_manager.register_message(message)` → `get_message_registry_port().register(message)`
  - `chat_manager.get_or_create_session()` → `get_session_lifecycle_port().get_or_create_session()`
  - 注意：需确认 `_init_components()` 中 SessionLifecyclePort 和 MessageRegistryPort 在 bot.py 被 import 前已注册
- [ ] 修改 `src/webui/routers/chat/routes.py` 的 `_release_deleted_chat_runtime()`，将 `from src.chat.message_receive.chat_manager import chat_manager as _chat_manager_for_mutation` 替换为通过 `get_session_lifecycle_port()` 访问，`session_store.remove(session_id)` 改为 `session_lifecycle_port.remove_session(session_id)`（需在 SessionLifecyclePort 新增 `remove_session` 方法，或在 SessionQueryPort 中新增）
- [ ] 全局搜索 `from src.chat.message_receive.chat_manager import chat_manager`，确保零残留（适配器层除外——适配器层已不导入单例）

**验证**：
```bash
rg "chat_manager = ChatManager\(\)" src/  # → 零匹配
rg "from src.chat.message_receive.chat_manager import chat_manager" src/  # → 零匹配
```

### 3.2 ChatManager 类删除

- [ ] 确认 ChatManager 类已无消费者（bot.py 和 webui 已改为通过 Protocol 接口访问）
- [ ] 删除 `src/chat/message_receive/chat_manager.py` 中的 `ChatManager` 类定义
- [ ] 确认 `sessions` / `last_messages` 等向后兼容属性无外部消费者
- [ ] 更新 `src/chat/message_receive/chat_manager.py` 的模块文档字符串，标注已废弃

**验证**：
```bash
rg "ChatManager\(\)" src/  # → 零匹配（不含类定义本身）
```

### 3.3 ruff TID251 守卫

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 中新增：
  ```toml
  "src.chat.message_receive.chat_manager.chat_manager" = {msg = "禁止导入 ChatManager 单例，请通过 SessionLifecyclePort/SessionQueryPort 等 Protocol 接口访问"}
  "src.chat.replyer.replyer_manager.replyer_manager" = {msg = "maisaka 禁止直接导入 replyer_manager，请通过 ReplyerServicePort 接口访问"}
  "src.chat.image_system.image_manager.image_manager" = {msg = "maisaka 禁止直接导入 image_manager，请通过 ImageDescriptionPort 接口访问"}
  ```
- [ ] 确认 `src/maisaka/**` 不在 `per-file-ignores` 的 TID251 豁免列表中（当前不在，确认即可）
- [ ] 确认 `src/core/adapters/*`、`src/main.py`、`src/services/generator_service.py` 保留 TID251 豁免
- [ ] 新增 `src/services/generator_service.py` 的 TID251 豁免（如果尚未添加）

**验证**：
```bash
ruff check src/maisaka/ --select TID251  # → 零错误
ruff check src/core/adapters/ --select TID251  # → 零错误（豁免生效）
```

### 3.4 全量集成验证

- [ ] 启动容器，确认所有功能无回归：
  - 消息收发正常
  - 会话创建/持久化/恢复正常
  - 回复工具正常获取 replyer
  - 图片描述功能正常
  - 子智能体 ForkContext 不抛异常
  - session_recovery 正常恢复
  - WebUI 聊天流管理正常
- [ ] CI 全量检查通过（ruff + mypy + pytest）

**验证**：
```bash
ruff check src/  # → 零错误
rg "from src\.chat\." src/maisaka/  # → 零匹配
rg "_chat_manager" src/maisaka/  # → 零匹配
rg "chat_manager = ChatManager\(\)" src/  # → 零匹配
```

---

## 4. 文档与规则同步

### 4.1 架构文档同步

- [ ] 更新 `AGENTS.md` 中"存量债务"表格：
  - "chat_manager 全局单例导入"状态从"✅ 核心模块已通过Protocol隔离"更新为"✅ 已消除（子模块直接注入 + 单例移除）"
  - "maisaka → chat 物理依赖"状态从"⬜ 待架构革命推进"更新为"✅ 已消除（3 处直接导入 + 3 处间接访问全部迁移）"
  - "chat_manager 单例物理退役"状态从"⬜ 待 SSD-3 推进"更新为"✅ 已完成"
- [ ] 更新 `AGENTS.md` 中"核心接口层"表格，新增 ReplyerServicePort 和 ImageDescriptionPort 两行
- [ ] 更新 `AGENTS.md` 中"核心禁止项"状态：
  - "禁止核心直接导入 chat_manager" → ✅ 已消除 + ruff TID251 守卫
- [ ] 同步更新 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc` 中对应表格和状态

**验证**：
```bash
grep "ReplyerServicePort" AGENTS.md  # → 有匹配
grep "ImageDescriptionPort" AGENTS.md  # → 有匹配
```