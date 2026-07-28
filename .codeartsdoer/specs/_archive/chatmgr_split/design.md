# 1. 实现模型

## 1.1 上下文视图

SSD-2 在 SSD-1 完成的基础上，将 ChatManager 604行单例拆分为职责单一的子模块。外部 Protocol 接口不变，ChatManagerAdapter 仍为唯一外部入口。

```
ChatManagerAdapter (5 Protocol)
    ↓ 委托
ChatManager (薄协调层, < 200行)
    ↓ 组合
    ├── SessionStore        — 会话存储 CRUD + 单条持久化
    ├── MessageRegistry     — 消息注册 + 缓存 + 身份更新
    ├── SessionLifecycle    — 创建/获取 + 批量持久化 + 初始化
    ├── SessionNameCache    — 名称查询
    ├── SessionResolver     — 路由解析（含数据库懒加载）
    └── BindingRestorer     — 启动时智能体绑定恢复
```

## 1.2 服务/组件总体架构

### 拆分策略

ChatManager 从"胖单例"变为"薄协调层"——它持有 6 个子模块实例，对外暴露的方法逐一委托给子模块。外部通过 ChatManagerAdapter 访问，不感知内部拆分。

### 子模块间依赖关系

```
SessionStore ←── MessageRegistry (查询会话 + 持久化变更)
SessionStore ←── SessionLifecycle (查询/添加会话)
SessionStore ←── SessionNameCache (查询会话信息)
SessionStore ←── SessionResolver  (查询会话列表)
MessageRegistry ←── SessionLifecycle (查询 last_messages)
AgentRouter ←── SessionLifecycle (新会话智能体解析)
AgentRouter ←── BindingRestorer   (恢复绑定)
```

### 拆分原则

1. **Protocol 接口签名零变更**：ChatManagerAdapter 的 15 个方法签名不变
2. **渐进式拆分**：每个子模块独立提取，可分批完成
3. **不引入循环依赖**：子模块不反向持有 ChatManager 引用
4. **sessions.pop 封装**：通过 SessionStore.remove() 替代直接字典操作
5. **向后兼容属性代理**：`chat_manager.sessions` 和 `chat_manager.last_messages` 代理到子模块

## 1.3 实现设计文档

### SessionStore

```python
class SessionStore:
    """会话存储 — 管理 sessions 字典的 CRUD + 单条持久化。"""
    
    def __init__(self) -> None:
        self.sessions: Dict[str, BotChatSession] = {}
        self._message_registry: Optional[MessageRegistry] = None  # 延迟注入，避免循环
    
    def set_message_registry(self, registry: MessageRegistry) -> None: ...
    
    def get(self, session_id: str) -> Optional[BotChatSession]:
        """查询会话，自动设置 context（从 last_messages）。"""
        session = self.sessions.get(session_id)
        if session and self._message_registry:
            last_msg = self._message_registry.get_last(session_id)
            if last_msg:
                session.set_context(last_msg)
        return session
    
    def get_existing(self, session_id: str) -> Optional[BotChatSession]:
        """内存未命中时从数据库加载。"""
        ...
    
    def add(self, session: BotChatSession) -> None: ...
    def remove(self, session_id: str) -> Optional[BotChatSession]: ...
    def values(self) -> Iterable[BotChatSession]: ...
    def __len__(self) -> int: ...
    def __contains__(self, session_id: str) -> bool: ...
    
    def save(self, session: BotChatSession) -> None:
        """单条会话持久化（原 _save_session）。"""
        ...
```

### MessageRegistry

```python
class MessageRegistry:
    """消息注册 — 管理入站消息注册、缓存和会话身份更新。"""
    
    def __init__(self, session_store: SessionStore) -> None:
        self._store = session_store
        self.last_messages: Dict[str, SessionMessage] = {}
    
    def register(self, message: SessionMessage) -> None:
        """注册消息 + 更新会话身份 + 持久化变更。"""
        ...
    
    def get_last(self, session_id: str) -> Optional[SessionMessage]: ...
    
    def update_session_identity(self, session: BotChatSession, message: SessionMessage) -> bool:
        """用入站消息补齐会话显示身份（原 _update_session_identity）。"""
        ...
```

### SessionLifecycle

```python
class SessionLifecycle:
    """会话生命周期 — 创建/获取 + 路由元数据 + 批量持久化 + 初始化。"""
    
    def __init__(
        self,
        store: SessionStore,
        message_registry: MessageRegistry,
        agent_router: AgentRouter,
    ) -> None:
        self._store = store
        self._registry = message_registry
        self._agent_router = agent_router
    
    async def get_or_create_session(self, **kwargs) -> BotChatSession:
        """获取或创建会话，含路由元数据应用和身份更新。"""
        ...
    
    async def initialize(self) -> None:
        """加载全部会话 + 恢复绑定。"""
        ...
    
    def save_all_sessions(self) -> None: ...
    async def regularly_save_sessions(self, interval_seconds: float = 300) -> None: ...
```

### SessionNameCache

```python
class SessionNameCache:
    """会话名称查询 — 从 SessionStore 实时推断名称。"""
    
    def __init__(self, store: SessionStore) -> None:
        self._store = store
    
    def get(self, session_id: str) -> Optional[str]:
        """推断会话显示名称（群名/用户昵称+私聊）。"""
        ...
```

### SessionResolver

```python
class SessionResolver:
    """路由解析 — 按平台/目标匹配会话（含数据库懒加载）。"""
    
    def __init__(self, store: SessionStore) -> None:
        self._store = store
    
    def resolve_by_target(self, *, platform, target_id, chat_type) -> List[BotChatSession]: ...
    def resolve_ids_by_target(self, *, platform, target_id, chat_type) -> set[str]: ...
```

### BindingRestorer

```python
class BindingRestorer:
    """智能体绑定恢复 — 启动时从数据库恢复绑定和 Orchestrator 状态。"""
    
    def __init__(self, agent_router: AgentRouter) -> None:
        self._agent_router = agent_router
    
    def restore_bindings(self) -> None:
        """从数据库恢复会话-智能体绑定（原 _restore_bindings_from_db）。"""
        ...
    
    def restore_orchestrator(self) -> None:
        """从数据库恢复 Orchestrator 活跃状态（原 _restore_orchestrator_from_db）。"""
        ...
```

### ChatManager 重构后

```python
class ChatManager:
    """薄协调层 — 持有子模块实例，对外暴露方法逐一委托。"""
    
    def __init__(self) -> None:
        self.session_store = SessionStore()
        self.message_registry = MessageRegistry(self.session_store)
        self.session_store.set_message_registry(self.message_registry)
        self._agent_router: Optional[AgentRouter] = None
        self.binding_restorer: Optional[BindingRestorer] = None
        self.session_lifecycle: Optional[SessionLifecycle] = None
        self.name_cache = SessionNameCache(self.session_store)
        self.resolver = SessionResolver(self.session_store)
    
    @property
    def sessions(self) -> Dict[str, BotChatSession]:
        return self.session_store.sessions
    
    @property
    def last_messages(self) -> Dict[str, SessionMessage]:
        return self.message_registry.last_messages
    
    @property
    def agent_router(self) -> AgentRouter:
        return self._ensure_agent_router()
    
    # 对外方法逐一委托给子模块
    def get_session_by_session_id(self, session_id):
        return self.session_store.get(session_id)
    
    def register_message(self, message):
        return self.message_registry.register(message)
    
    def get_session_name(self, session_id):
        return self.name_cache.get(session_id)
    
    # ... 其他方法类似委托
```

# 2. 接口设计

## 2.1 总体设计

Protocol 接口签名零变更。ChatManagerAdapter 内部实现不变（仍然调用 chat_manager 的方法），只是 chat_manager 内部从直接实现变为委托子模块。

## 2.2 接口清单

无新增接口。所有 Protocol 接口保持 SSD-1 完成后的状态。

# 3. 迁移策略

## 3.1 渐进式拆分（6 批）

| 批次 | 拆分模块 | 风险 | 验证方式 |
|------|---------|------|---------|
| 1 | SessionStore（会话存储 CRUD + 单条持久化） | 低 | sessions 属性向后兼容 |
| 2 | MessageRegistry（消息注册 + 缓存 + 身份更新） | 中 | register_message 含身份更新副作用 |
| 3 | SessionNameCache（名称查询） | 低 | get_session_name 行为不变 |
| 4 | SessionResolver（路由解析 + 数据库懒加载） | 低 | resolve_by_target 行为不变 |
| 5 | BindingRestorer（智能体绑定恢复） | 低 | 仅 initialize 时调用 |
| 6 | SessionLifecycle（创建/获取 + 批量持久化 + 初始化） | 中 | 涉及数据库操作和 AgentRouter |

## 3.2 向后兼容

- `chat_manager.sessions` → 属性代理到 `session_store.sessions`
- `chat_manager.last_messages` → 属性代理到 `message_registry.last_messages`
- `chat_manager.agent_router` → 属性代理到 `_ensure_agent_router()`
- 所有 `chat_manager.xxx()` 方法 → 委托给对应子模块

## 3.3 routes.py sessions.pop 修复

将 `chat_manager.sessions.pop(session_id, None)` 替换为 `chat_manager.session_store.remove(session_id)`，消除外部对内部字典的直接操作。

# 4. 数据模型

## 4.1 设计目标

不改变现有数据模型。BotChatSession、SessionInfo、SessionMessage 等数据结构保持不变。

## 4.2 模型实现

无新增数据模型。拆分仅涉及 ChatManager 内部代码组织，不涉及数据结构变更。
