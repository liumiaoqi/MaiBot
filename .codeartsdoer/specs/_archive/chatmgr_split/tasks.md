# SSD-2：ChatManager 单例拆分 — 编码任务

## 阶段1：SessionStore 提取

### 1.1 创建 SessionStore 类
- [ ] 在 `src/chat/message_receive/` 下新建 `session_store.py`，实现 `SessionStore` 类
- [ ] 包含 `sessions: Dict[str, BotChatSession]`、`get()`、`get_existing()`、`add()`、`remove()`、`values()`、`__len__()`、`__contains__()`
- [ ] `get()` 方法接受 MessageRegistry 引用，自动设置 `session.set_context(last_msg)`
- [ ] `save()` 方法实现单条会话持久化（原 `_save_session`）
- [ ] `set_message_registry()` 延迟注入方法（避免循环依赖）
- **涉及文件**：`src/chat/message_receive/session_store.py`（新建）
- **验收标准**：SessionStore 类可实例化，所有方法语法正确

### 1.2 ChatManager 委托 SessionStore
- [ ] 在 ChatManager.__init__ 中创建 `self.session_store = SessionStore()`
- [ ] 将 `self.sessions` 替换为 `self.session_store.sessions`（属性代理保持向后兼容）
- [ ] 将 `get_session_by_session_id()` 委托给 `self.session_store.get()`
- [ ] 将 `get_existing_session_by_session_id()` 委托给 `self.session_store.get_existing()`
- [ ] 将 `_save_session()` 委托给 `self.session_store.save()`
- [ ] 将 `_load_sessions_from_db()` 委托给 `self.session_store.load_all_from_db()`
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：ChatManager 所有会话查询方法通过 SessionStore 委托

### 1.3 修复 routes.py sessions.pop
- [ ] 将 `chat_manager.sessions.pop(session_id, None)` 替换为 `chat_manager.session_store.remove(session_id)`
- [ ] 移除 routes.py 中对 `src.chat.message_receive.chat_manager` 的直接导入
- **涉及文件**：`src/webui/routers/chat/routes.py`
- **验收标准**：routes.py 不再直接导入 chat_manager

### 阶段1 验证
- [ ] `grep -r "chat_manager.sessions" src/` 零匹配（除 chat_manager.py 自身）
- [ ] ChatManagerAdapter 所有方法正常工作

---

## 阶段2：MessageRegistry 提取

### 2.1 创建 MessageRegistry 类
- [ ] 在 `src/chat/message_receive/` 下新建 `message_registry.py`，实现 `MessageRegistry` 类
- [ ] 包含 `last_messages: Dict[str, SessionMessage]`、`register()`、`get_last()`
- [ ] `register()` 内部调用 `update_session_identity()` + `session_store.save()`（身份更新 + 持久化）
- [ ] `update_session_identity()` 迁移自原 `_update_session_identity()`
- [ ] 构造函数接受 `session_store: SessionStore` 引用
- **涉及文件**：`src/chat/message_receive/message_registry.py`（新建）
- **验收标准**：MessageRegistry 类可实例化

### 2.2 ChatManager 委托 MessageRegistry
- [ ] 在 ChatManager.__init__ 中创建 `self.message_registry = MessageRegistry(self.session_store)`
- [ ] 将 `self.last_messages` 替换为 `self.message_registry.last_messages`（属性代理）
- [ ] 将 `register_message()` 委托给 `self.message_registry.register()`
- [ ] 将 `_update_session_identity()` 迁移到 MessageRegistry
- [ ] 调用 `self.session_store.set_message_registry(self.message_registry)` 完成双向注入
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：消息注册和身份更新通过 MessageRegistry 委托

### 阶段2 验证
- [ ] 消息注册功能正常
- [ ] 会话身份更新功能正常（群名/用户昵称自动补齐）

---

## 阶段3：SessionNameCache 提取

### 3.1 创建 SessionNameCache 类
- [ ] 在 `src/chat/message_receive/` 下新建 `session_name_cache.py`，实现 `SessionNameCache` 类
- [ ] 包含 `get()` 方法，从 SessionStore 实时推断名称
- [ ] 依赖 SessionStore 获取会话信息
- [ ] 迁移原 `get_session_name()` 的名称推断逻辑
- **涉及文件**：`src/chat/message_receive/session_name_cache.py`（新建）
- **验收标准**：SessionNameCache 类可实例化

### 3.2 ChatManager 委托 SessionNameCache
- [ ] 在 ChatManager.__init__ 中创建 `self.name_cache = SessionNameCache(self.session_store)`
- [ ] 将 `get_session_name()` 委托给 `self.name_cache.get()`
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：会话名称查询通过 SessionNameCache 委托

### 阶段3 验证
- [ ] 会话名称查询功能正常

---

## 阶段4：SessionResolver 提取

### 4.1 创建 SessionResolver 类
- [ ] 在 `src/chat/message_receive/` 下新建 `session_resolver.py`，实现 `SessionResolver` 类
- [ ] 包含 `resolve_by_target()`、`resolve_ids_by_target()`
- [ ] 依赖 SessionStore 获取会话列表
- [ ] 含数据库懒加载逻辑（内存未命中时查数据库并添加到 SessionStore）
- [ ] 迁移原 `_session_matches_target()` 静态方法
- **涉及文件**：`src/chat/message_receive/session_resolver.py`（新建）
- **验收标准**：SessionResolver 类可实例化

### 4.2 ChatManager 委托 SessionResolver
- [ ] 在 ChatManager.__init__ 中创建 `self.resolver = SessionResolver(self.session_store)`
- [ ] 将 `resolve_sessions_by_target()` 委托给 `self.resolver.resolve_by_target()`
- [ ] 将 `resolve_session_ids_by_target()` 委托给 `self.resolver.resolve_ids_by_target()`
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：路由解析通过 SessionResolver 委托

### 阶段4 验证
- [ ] 路由解析功能正常

---

## 阶段5：BindingRestorer 提取

### 5.1 创建 BindingRestorer 类
- [ ] 在 `src/chat/message_receive/` 下新建 `binding_restorer.py`，实现 `BindingRestorer` 类
- [ ] 包含 `restore_bindings()`、`restore_orchestrator()`
- [ ] 依赖 AgentRouter 引用
- [ ] 迁移原 `_restore_bindings_from_db()` 和 `_restore_orchestrator_from_db()`
- **涉及文件**：`src/chat/message_receive/binding_restorer.py`（新建）
- **验收标准**：BindingRestorer 类可实例化

### 5.2 ChatManager 委托 BindingRestorer
- [ ] 在 ChatManager.__init__ 中创建 `self.binding_restorer = BindingRestorer(self._ensure_agent_router())`
- [ ] 将 `_restore_bindings_from_db()` 委托给 `self.binding_restorer.restore_bindings()`
- [ ] 将 `_restore_orchestrator_from_db()` 委托给 `self.binding_restorer.restore_orchestrator()`
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：启动恢复通过 BindingRestorer 委托

### 阶段5 验证
- [ ] 启动时智能体绑定恢复正常

---

## 阶段6：SessionLifecycle 提取

### 6.1 创建 SessionLifecycle 类
- [ ] 在 `src/chat/message_receive/` 下新建 `session_lifecycle.py`，实现 `SessionLifecycle` 类
- [ ] 包含 `get_or_create_session()`、`initialize()`、`save_all_sessions()`、`regularly_save_sessions()`
- [ ] 构造函数接受 `session_store: SessionStore` + `message_registry: MessageRegistry` + `agent_router: AgentRouter`
- [ ] 迁移原 `_apply_route_metadata()` 和 `_normalize_route_value()` 静态方法
- [ ] `initialize()` 委托 SessionStore.load_all_from_db() + BindingRestorer
- **涉及文件**：`src/chat/message_receive/session_lifecycle.py`（新建）
- **验收标准**：SessionLifecycle 类可实例化

### 6.2 ChatManager 委托 SessionLifecycle
- [ ] 在 ChatManager.__init__ 中创建 `self.session_lifecycle = SessionLifecycle(self.session_store, self.message_registry, self._ensure_agent_router())`
- [ ] 将 `get_or_create_session()` 委托给 `self.session_lifecycle.get_or_create_session()`
- [ ] 将 `initialize()` 委托给 `self.session_lifecycle.initialize()`
- [ ] 将 `save_all_sessions()` 委托给 `self.session_lifecycle.save_all_sessions()`
- [ ] 将 `regularly_save_sessions()` 委托给 `self.session_lifecycle.regularly_save_sessions()`
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：会话生命周期操作通过 SessionLifecycle 委托

### 6.3 清理 ChatManager 残留逻辑
- [ ] 确认 ChatManager 只保留子模块实例化、属性代理和委托方法
- [ ] 确认 ChatManager 行数降至 200 行以下
- [ ] 确认无循环依赖
- **涉及文件**：`src/chat/message_receive/chat_manager.py`
- **验收标准**：ChatManager 为薄协调层

### 阶段6 验证
- [ ] 全量功能测试通过
- [ ] ChatManager 行数 < 200
- [ ] 无循环依赖
