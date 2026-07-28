# 1. 实现模型

## 1.1 上下文视图

v3.5 在 v3.4.1 基础上沿三个方向改进：

```
决策记录聊天流名称解析（_stream_display_cache 复用 + 降级策略）   ← 后端修复：webui.py 决策/冷却端点
DeepSeek API 兼容性对齐（strict 空参数工具 required 字段修复）     ← 后端修复：deepseek_client.py _apply_strict_to_tools()
决策调试界面（替代智能体对话，重新定位为决策调试器）               ← 全栈重构：前后端全面改造
```

核心变化：
- 修改 `webui.py`，在 `_handle_decisions()` 和 `_handle_cooldown()` 中复用 `_stream_display_cache` 解析 stream_name，缓存未命中时降级为 `stream_id[:8] + "..."`
- 修改 `deepseek_client.py`，在 `_apply_strict_to_tools()` 中为空参数工具始终设置 `required: []`，与主程序 bd077ae5 修复对齐
- 重构 `agent_chat.py`，将"智能体对话"重新定位为"决策调试器"，新增 `DebugSession`/`DebugMessage` 数据模型替代 `AgentChatSession`/`AgentChatMessage`
- 新增 `debug_api.py` 模块，实现决策调试专用 API 端点（上下文查看、调试指令执行、决策日志查询）
- 修改 `prompts.py`，新增 `DEBUG_SYSTEM_PROMPT` 替代 `AGENT_CHAT_SYSTEM_PROMPT`，将智能体定位从"指令执行助手"改为"决策引擎"
- 重构前端 `webui_static/`，将"智能体对话"Tab 改造为"决策调试"Tab，采用左侧聊天流列表 + 右侧调试面板的布局
- 修改 `config.py`，将 `AgentChatConfig` 重命名为 `DebugConfig` 并调整配置项语义
- 保留原有 agent_chat API 端点（标记为 deprecated），确保向后兼容

## 1.2 服务/组件总体架构

```
plugin.py (入口，微调：DebugService 注入)
  ├── AgentCore (agent.py，不变)
  ├── DebugService (debug_service.py，重构自 agent_chat.py)  ← v3.5 核心变更
  │     ├── 调试会话管理（替代原会话管理）
  │     ├── 调试指令执行（替代原消息收发）
  │     ├── 决策上下文获取（新增：复用 AgentCore 感知数据）
  │     ├── 智能偏好提取（增强：从对话中自动提取喜好，包装为"决策调优指令"）
  │     ├── 聊天流上下文注入（保留）
  │     ├── 持久化同步（保留：JSONL 文件持久化）
  │     └── 编辑意图执行（保留：偏好文件编辑）
  ├── DebugApiController (debug_api.py，新增)  ← v3.5
  │     ├── GET /api/proactive-chat/debug/context      — 获取决策上下文
  │     ├── POST /api/proactive-chat/debug/instruction — 发送调试指令
  │     ├── GET /api/proactive-chat/debug/log           — 获取决策日志
  │     ├── POST /api/proactive-chat/debug/trigger      — 强制触发决策
  │     └── POST /api/proactive-chat/debug/cooldown/reset — 重置冷却
  ├── DeepSeekClient (deepseek_client.py，修复)
  │     └── _apply_strict_to_tools() 空参数工具 required 字段修复
  ├── WebUIServer (webui.py，扩展)
  │     ├── 决策记录 stream_name 解析（复用 _stream_display_cache）
  │     ├── 冷却记录 stream_name 解析（复用 _stream_display_cache）
  │     └── 新增 debug API 路由注册
  ├── 前端重构 (webui_static/，全面改造)
  │     ├── 决策调试 Tab（替代智能体对话 Tab）
  │     ├── 左侧：聊天流选择列表
  │     ├── 右侧：调试面板（上下文区 + 指令区 + 日志区）
  │     └── UI 按钮 + 文本指令混合交互
  └── 配置调整 (config.py)
        └── AgentChatConfig → DebugConfig（语义调整 + 新增配置项）
```

## 1.3 实现设计文档

### 1.3.1 决策记录聊天流名称解析（修改 `webui.py`）

**设计思路**：复用 WebUIServer 已有的 `_stream_display_cache` 缓存，在决策记录和冷却记录查询时将 stream_id 解析为可读名称。缓存由 `_handle_streams()` 端点在聊天流列表请求时更新，决策记录查询时不主动调用聊天流列表 API（性能考虑），缓存未命中时降级显示 stream_id 前 8 位加"..."。

**`_handle_decisions()` 修改**：

```python
async def _handle_decisions(self, request: web.Request) -> web.Response:
    # ... 现有查询逻辑不变 ...

    records = []
    for d in page_decisions:
        entry = asdict(d)
        # v3.5: 使用缓存解析 stream_name
        entry["stream_name"] = self._resolve_stream_name(d.stream_id)
        records.append(entry)

    return web.json_response({...})
```

**`_handle_cooldown()` 修改**：

```python
async def _handle_cooldown(self, request: web.Request) -> web.Response:
    # ... 现有查询逻辑不变 ...

    records = []
    for sid, rec in all_records.items():
        # ... 现有字段 ...
        records.append({
            ...
            "stream_name": self._resolve_stream_name(rec.stream_id),  # v3.5
            ...
        })
```

**新增 `_resolve_stream_name()` 方法**：

```python
def _resolve_stream_name(self, stream_id: str) -> str:
    """将 stream_id 解析为可读的聊天流名称。

    复用 _stream_display_cache 缓存，缓存未命中时降级显示截断 ID。
    不主动调用聊天流列表 API（避免决策记录查询时的额外延迟）。
    """
    if not stream_id:
        return ""
    info = self._stream_display_cache.get(stream_id)
    if info:
        display_name, chat_type = info
        prefix = "[群聊] " if chat_type == "group" else "[私聊] "
        return prefix + display_name
    # 降级：显示 stream_id 前 8 位加"..."
    return stream_id[:8] + "..."
```

**与 `_get_stream_display_name()` 的关系**：`_get_stream_display_name()` 用于 agent_chat 会话列表（带 `[群聊]`/`[私聊]` 前缀），`_resolve_stream_name()` 用于决策记录列表（同样带前缀），两者逻辑一致。考虑将 `_get_stream_display_name()` 重构为调用 `_resolve_stream_name()` 以消除重复。

### 1.3.2 DeepSeek strict 模式空参数工具修复（修改 `deepseek_client.py`）

**设计思路**：当前 `_apply_strict_to_tools()` 仅在有 `prop_names` 时设置 `required` 字段，空参数工具（无 properties 的工具）可能遗漏 `required` 字段，导致 DeepSeek API 在 strict 模式下返回 400 错误。修复方式：始终设置 `required` 字段，与主程序 bd077ae5 修复保持一致。

**`_apply_strict_to_tools()` 修改**：

```python
@staticmethod
def _apply_strict_to_tools(tools: list[dict]) -> list[dict]:
    result = []
    for tool in tools:
        tool_copy = dict(tool)
        func = dict(tool_copy.get("function", {}))
        func["strict"] = True
        params = dict(func.get("parameters", {}))
        params["additionalProperties"] = False
        # v3.5: 始终设置 required 字段，空参数工具设为 []
        prop_names = list(params.get("properties", {}).keys())
        params["required"] = prop_names  # 空参数时 prop_names 为 []，符合 DeepSeek API 要求
        func["parameters"] = params
        tool_copy["function"] = func
        result.append(tool_copy)
    return result
```

**变更点**：移除 `if prop_names:` 条件判断，使 `params["required"] = prop_names` 始终执行。当 `prop_names` 为空列表时，`required: []` 符合 DeepSeek strict 模式要求。

### 1.3.3 决策调试服务（重构 `agent_chat.py` → `debug_service.py`）

**设计思路**：将 `AgentChatService` 重构为 `DebugService`，核心定位从"智能体对话"改为"决策调试器"。保留偏好编辑功能，重新包装为"决策调优指令"，增强智能偏好提取能力。保留 JSONL 持久化机制不变。

**核心数据模型**：

```python
@dataclass
class DebugMessage:
    """调试消息，替代 AgentChatMessage。"""
    role: str = ""          # "system" | "debug_instruction" | "decision_result"
    content: str = ""
    timestamp: float = 0.0
    reasoning: str = ""     # 决策推理过程（仅 decision_result）
    edit_performed: bool = False  # 是否执行了偏好编辑


@dataclass
class DebugSession:
    """调试会话，替代 AgentChatSession。"""
    session_id: str = ""
    stream_id: str = ""     # 必须关联聊天流（调试必须针对具体聊天流）
    messages: list[DebugMessage] = field(default_factory=list)
    created_at: float = 0.0
    last_active_at: float = 0.0
    token_estimate: int = 0
    is_responding: bool = False
    context_snapshot: dict = field(default_factory=dict)  # 决策上下文快照
```

**DebugService 核心方法**：

```python
class DebugService:
    """决策调试服务，替代 AgentChatService。"""

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
        persistence_manager: PersistenceManager,
        message_api: Any = None,
    ) -> None:
        self._deepseek = deepseek_client
        self._event_bus = event_bus
        self._persistence = persistence_manager
        self._message_api = message_api
        self._sessions: dict[str, DebugSession] = {}
        self._file_editor: FileEditor | None = None
        self._preference_cache: dict = {}
        # 持久化（保留 v3.4.1 机制）
        self._session_persistence: Any = None
        self._persistence_enabled: bool = False
        self._max_persisted_sessions: int = 20
        self._max_persisted_messages: int = 200
        self._retention_days: int = 30

    async def create_session(self, stream_id: str) -> DebugSession:
        """创建调试会话。stream_id 为必填参数。"""

    async def get_decision_context(self, stream_id: str) -> dict:
        """获取指定聊天流的决策上下文。"""

    async def execute_instruction(
        self,
        session_id: str,
        instruction: str,
        config: ProactiveChatConfig,
        bot_nickname: str = "",
        personality: str = "",
        alias_names: list[str] | None = None,
        reply_style: str = "",
        custom_prompt: str = "",
    ) -> DebugMessage:
        """执行调试指令，返回决策结果。"""

    async def get_decision_log(self, stream_id: str, limit: int = 20) -> list[dict]:
        """获取指定聊天流的决策日志。"""

    async def clear_session(self, session_id: str) -> bool: ...
    def get_session(self, session_id: str) -> DebugSession | None: ...
    def list_sessions(self) -> list[dict]: ...
```

**`create_session()` 实现**：

```python
async def create_session(self, stream_id: str) -> DebugSession:
    """创建调试会话。stream_id 为必填参数（调试必须针对具体聊天流）。"""
    if not stream_id:
        raise ValueError("调试会话必须关联聊天流")

    session = DebugSession(
        session_id=uuid.uuid4().hex[:16],
        stream_id=stream_id,
        created_at=time.time(),
        last_active_at=time.time(),
    )

    # 淘汰旧会话
    max_sessions = self._max_persisted_sessions if self._persistence_enabled else 5
    if len(self._sessions) >= max_sessions:
        oldest_id = min(self._sessions, key=lambda k: self._sessions[k].last_active_at)
        del self._sessions[oldest_id]

    # 注入聊天流上下文
    await self._inject_stream_context(session, stream_id)

    # 获取决策上下文快照
    session.context_snapshot = await self.get_decision_context(stream_id)

    # 加载偏好缓存
    self._preference_cache = self._load_preferences()

    self._sessions[session.session_id] = session

    # 持久化
    if self._persistence_enabled and self._session_persistence:
        from .session_persistence import SessionMetadata
        self._session_persistence.save_session_metadata(SessionMetadata(
            session_id=session.session_id,
            created_at=session.created_at,
            last_active_at=session.last_active_at,
            stream_context_id=session.stream_id,
            message_count=len(session.messages),
        ))

    return session
```

**`get_decision_context()` 实现**：

```python
async def get_decision_context(self, stream_id: str) -> dict:
    """获取指定聊天流的决策上下文。

    复用 AgentCore 已有的感知数据获取能力。
    """
    context: dict[str, Any] = {
        "stream_id": stream_id,
        "recent_messages": [],
        "cooldown_status": {},
        "activity_metrics": {},
        "recent_decisions": [],
    }

    # 1. 获取近期消息
    try:
        recent = await self._get_recent_messages(stream_id, limit=10)
        context["recent_messages"] = [
            {
                "sender_name": msg.get("sender_name", "未知"),
                "content": (msg.get("content", "") or "")[:100],
                "timestamp": msg.get("timestamp", 0),
            }
            for msg in recent
        ]
    except Exception as e:
        logger.debug("[proactive-chat] 获取近期消息失败(%s): %s", type(e).__name__, e)

    # 2. 获取冷却状态（从 PersistenceManager 查询最近决策记录推断）
    try:
        recent_decisions, _ = await self._persistence.query_decisions(
            stream_id=stream_id, limit=1,
        )
        if recent_decisions:
            last_decision = recent_decisions[0]
            context["cooldown_status"] = {
                "last_trigger_time": last_decision.ts,
                "last_action": last_decision.action_taken,
                "last_summary": last_decision.input_summary,
            }
    except Exception as e:
        logger.debug("[proactive-chat] 获取冷却状态失败(%s): %s", type(e).__name__, e)

    # 3. 获取近期决策记录摘要
    try:
        decisions, _ = await self._persistence.query_decisions(
            stream_id=stream_id, limit=5,
        )
        context["recent_decisions"] = [
            {
                "time": d.time,
                "action_taken": d.action_taken,
                "intent": (d.analysis_result or {}).get("intent", ""),
                "confidence": (d.analysis_result or {}).get("confidence", 0.0),
                "reason": (d.analysis_result or {}).get("reason", ""),
                "react_steps": d.react_steps if hasattr(d, "react_steps") else [],
            }
            for d in decisions
        ]
    except Exception as e:
        logger.debug("[proactive-chat] 获取决策记录失败(%s): %s", type(e).__name__, e)

    return context
```

**`execute_instruction()` 实现**：

```python
async def execute_instruction(
    self,
    session_id: str,
    instruction: str,
    config: ProactiveChatConfig,
    bot_nickname: str = "",
    personality: str = "",
    alias_names: list[str] | None = None,
    reply_style: str = "",
    custom_prompt: str = "",
) -> DebugMessage:
    """执行调试指令。

    调试指令以系统消息形式注入到智能体的决策流程中，
    不作为用户消息参与对话，目的是影响决策行为而非获取闲聊回复。
    """
    session = self._sessions.get(session_id)
    if not session:
        raise ValueError("调试会话不存在")

    if session.is_responding:
        raise RuntimeError("调试会话正在响应中，请等待完成")

    # 记录调试指令
    debug_msg = DebugMessage(
        role="debug_instruction",
        content=instruction[:4000],
        timestamp=time.time() * 1000,
    )
    session.messages.append(debug_msg)

    # 持久化
    if self._persistence_enabled and self._session_persistence:
        self._session_persistence.save_message(
            session_id, "debug_instruction", debug_msg.content, debug_msg.timestamp,
        )

    # 自动清理
    self._auto_cleanup_if_needed(session, config)

    # 构建偏好摘要
    preference_summary = self._build_preference_summary(
        self._preference_cache,
        config.agent_chat.preference_summary_token_limit,
    )

    # 构建系统提示词（使用调试专用提示词）
    from .prompts import build_debug_system_prompt
    system_prompt = build_debug_system_prompt(
        bot_nickname=bot_nickname,
        alias_names=alias_names,
        personality=personality,
        reply_style=reply_style,
        custom_prompt=custom_prompt,
        preference_summary=preference_summary,
    )

    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]
    for msg in session.messages:
        if msg.role == "system":
            messages.append({"role": "system", "content": msg.content})
        elif msg.role == "debug_instruction":
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == "decision_result":
            messages.append({"role": "assistant", "content": msg.content})

    # LLM 调用
    session.is_responding = True
    try:
        response_text = await self._deepseek.analyze_with_messages(
            messages=messages,
            model=config.deepseek.deepseek_model,
            temperature=config.agent_chat.chat_temperature,
            max_tokens=config.agent_chat.chat_max_tokens,
        )
    except Exception as e:
        logger.warning("[proactive-chat] 调试指令 LLM 调用失败(%s): %s", type(e).__name__, e)
        raise
    finally:
        session.is_responding = False

    # 解析编辑意图（偏好提取 → 决策调优指令）
    edit_intent_dict, clean_response = parse_edit_intent(response_text)
    edit_performed = False

    if edit_intent_dict and config.agent_chat.file_edit_enabled:
        edit_result = self._execute_edit_intent(edit_intent_dict, session_id)
        if edit_result.success and not edit_result.is_duplicate:
            edit_performed = True
            self._update_preference_cache(
                edit_intent_dict["category"],
                edit_intent_dict["value"],
                edit_intent_dict["action"],
            )
        elif not edit_result.success:
            clean_response += f"\n\n⚠ {edit_result.message}"

    # 记录决策结果
    result_msg = DebugMessage(
        role="decision_result",
        content=clean_response,
        timestamp=time.time() * 1000,
        edit_performed=edit_performed,
    )
    session.messages.append(result_msg)
    session.last_active_at = time.time()
    session.token_estimate = self._estimate_session_tokens(session)

    # 持久化
    if self._persistence_enabled and self._session_persistence:
        self._session_persistence.save_message(
            session_id, "decision_result", result_msg.content, result_msg.timestamp,
        )
        from .session_persistence import SessionMetadata
        self._session_persistence.save_session_metadata(SessionMetadata(
            session_id=session_id,
            created_at=session.created_at,
            last_active_at=session.last_active_at,
            stream_context_id=session.stream_id,
            message_count=len(session.messages),
        ))

    return result_msg
```

**智能偏好提取增强**：

偏好编辑功能保留并增强，重新包装为"决策调优指令"：

1. **显式调优指令**：管理员明确输入偏好指令（如"记住我喜欢XX"），系统通过 EDIT_INTENT 机制执行偏好编辑
2. **隐式偏好提取**：系统在对话中自动识别管理员自然表达的喜好，通过 `source: "auto"` 标记自动提取的偏好
3. **偏好注入决策引擎**：偏好摘要作为系统提示词的一部分注入，影响智能体的后续决策行为

偏好提取规则保持不变（likes/dislikes/habits/rules 四类），但系统提示词中的描述从"偏好识别"改为"决策调优"：

```
## 决策调优指令

当管理员自然表达偏好时，主动识别并记录为决策调优指令：
- 喜好表达（"我喜欢/爱/偏好XX"）→ likes
- 厌恶表达（"我讨厌/不喜欢/反感XX"）→ dislikes
- 习惯描述（"我习惯/通常/一般XX"）→ habits
- 行为倾向（"我总是/从不/一定要XX"）→ rules

这些偏好将作为决策调优依据，影响后续决策行为。
```

### 1.3.4 决策调试 API（新增 `debug_api.py`）

**设计思路**：新增独立的 API 控制器模块，实现决策调试专用端点。与原有 agent_chat API 并存，原有端点标记为 deprecated 但保留功能。

**API 端点设计**：

| 端点 | 方法 | 用途 | 对应原端点 |
|------|------|------|-----------|
| `/api/proactive-chat/debug/streams` | GET | 获取可调试的聊天流列表 | 复用 `/streams` |
| `/api/proactive-chat/debug/context` | GET | 获取指定聊天流的决策上下文 | 新增 |
| `/api/proactive-chat/debug/sessions` | GET | 获取调试会话列表 | 改造自 `/agent/chat/sessions` |
| `/api/proactive-chat/debug/sessions` | POST | 创建调试会话（必须指定 stream_id） | 改造自 `/agent/chat/sessions` |
| `/api/proactive-chat/debug/sessions/{id}` | GET | 获取调试会话详情 | 改造自 `/agent/chat/sessions/{id}` |
| `/api/proactive-chat/debug/instruction` | POST | 发送调试指令 | 改造自 `/agent/chat/send` |
| `/api/proactive-chat/debug/sessions/{id}/clear` | POST | 清除调试会话 | 复用 `/agent/chat/sessions/{id}/clear` |
| `/api/proactive-chat/debug/trigger` | POST | 强制触发决策循环 | 复用 `/trigger` |
| `/api/proactive-chat/debug/cooldown/reset` | POST | 重置指定聊天流冷却 | 复用 `/cooldown/reset` |
| `/api/proactive-chat/debug/log` | GET | 获取指定聊天流的决策日志 | 新增 |

**`DebugApiController` 核心实现**：

```python
class DebugApiController:
    """决策调试 API 控制器。"""

    def __init__(
        self,
        debug_service: DebugService,
        webui_server: WebUIServer,
        config_getter: Callable | None = None,
    ) -> None:
        self._debug_service = debug_service
        self._webui = webui_server
        self._config_getter = config_getter

    def register_routes(self, app: web.Application) -> None:
        """注册调试 API 路由。"""
        app.router.add_get("/api/proactive-chat/debug/context", self._handle_context)
        app.router.add_get("/api/proactive-chat/debug/sessions", self._handle_sessions)
        app.router.add_post("/api/proactive-chat/debug/sessions", self._handle_create_session)
        app.router.add_get("/api/proactive-chat/debug/sessions/{id}", self._handle_session_detail)
        app.router.add_post("/api/proactive-chat/debug/instruction", self._handle_instruction)
        app.router.add_post("/api/proactive-chat/debug/sessions/{id}/clear", self._handle_clear)
        app.router.add_get("/api/proactive-chat/debug/log", self._handle_log)

    async def _handle_context(self, request: web.Request) -> web.Response:
        """GET /api/proactive-chat/debug/context?stream_id=xxx"""
        stream_id = request.query.get("stream_id", "")
        if not stream_id:
            return web.json_response({"success": False, "error": "缺少 stream_id"})
        context = await self._debug_service.get_decision_context(stream_id)
        return web.json_response({"success": True, "context": context})

    async def _handle_instruction(self, request: web.Request) -> web.Response:
        """POST /api/proactive-chat/debug/instruction"""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"success": False, "error": "无效请求"})
        session_id = body.get("session_id", "")
        instruction = body.get("instruction", "")
        if not instruction:
            return web.json_response({"success": False, "error": "调试指令不能为空"})
        config = self._config_getter() if self._config_getter else None
        if not config:
            return web.json_response({"success": False, "error": "配置不可用"})
        try:
            result = await self._debug_service.execute_instruction(
                session_id=session_id,
                instruction=instruction,
                config=config,
                bot_nickname=self._webui._agent.bot_nickname if self._webui._agent else "",
                personality=self._webui._agent.personality if self._webui._agent else "",
                alias_names=self._webui._agent.alias_names if self._webui._agent else None,
                reply_style=self._webui._agent.reply_style if self._webui._agent else "",
                custom_prompt=config.prompt.custom_prompt,
            )
            session = self._debug_service.get_session(session_id)
            return web.json_response({
                "success": True,
                "content": result.content,
                "session_id": session.session_id if session else session_id,
                "token_estimate": session.token_estimate if session else 0,
                "edit_performed": result.edit_performed,
            })
        except (ValueError, RuntimeError) as e:
            return web.json_response({"success": False, "error": str(e)})

    async def _handle_log(self, request: web.Request) -> web.Response:
        """GET /api/proactive-chat/debug/log?stream_id=xxx&limit=20"""
        stream_id = request.query.get("stream_id", "")
        if not stream_id:
            return web.json_response({"success": False, "error": "缺少 stream_id"})
        limit = min(100, max(1, int(request.query.get("limit", "20"))))
        log = await self._debug_service.get_decision_log(stream_id, limit)
        return web.json_response({"success": True, "log": log})
```

### 1.3.5 决策调试系统提示词（修改 `prompts.py`）

**设计思路**：新增 `DEBUG_SYSTEM_PROMPT` 替代 `AGENT_CHAT_SYSTEM_PROMPT`，将智能体定位从"指令执行助手"改为"决策引擎"。保留偏好编辑的 EDIT_INTENT 机制，但重新包装为"决策调优指令"。

**`DEBUG_SYSTEM_PROMPT`**：

```python
DEBUG_SYSTEM_PROMPT = """你是一个决策引擎，负责接收管理员的调试指令并响应。
{personality_section}
## 核心职责

1. **解释决策依据**：当管理员询问决策原因时，基于感知数据和推理过程给出解释
2. **响应调试指令**：执行管理员下达的调优指令（偏好设定、行为调整等）
3. **展示推理过程**：当管理员要求时，展示决策的推理步骤和中间结果
4. **智能偏好提取**：主动识别管理员自然表达的偏好并记录为决策调优指令

## 调试指令类型

- **查看类**：查看当前决策依据、查看记忆内容、查看冷却状态
- **注入类**：注入额外上下文信息、模拟特定场景
- **指导类**：调整决策倾向（如"下次遇到XX场景时优先触发"）

## 决策调优指令

当管理员自然表达偏好时，主动识别并记录为决策调优指令：
- 喜好表达（"我喜欢/爱/偏好XX"）→ likes
- 厌恶表达（"我讨厌/不喜欢/反感XX"）→ dislikes
- 习惯描述（"我习惯/通常/一般XX"）→ habits
- 行为倾向（"我总是/从不/一定要XX"）→ rules

**不记录的情况**：
- 临时性陈述（"今天好累"、"现在好饿"）
- 客观事实（"今天下雨了"、"Python是编程语言"）
- 他人偏好（"他说他喜欢Java"）

这些偏好将作为决策调优依据，影响后续决策行为。

## 文件编辑格式

当需要记录偏好或执行调优指令时，在回复末尾单独一行输出编辑意图：

EDIT_INTENT: {{"action": "add/remove/update", "category": "likes/dislikes/habits/rules", "value": "偏好内容", "source": "explicit/auto", "old_value": ""}}

字段说明：
- action：add（新增）、remove（移除）、update（更新）
- category：likes、dislikes、habits、rules 之一
- value：偏好内容（简短描述）
- source：explicit（管理员显式指令）或 auto（智能体主动识别）
- old_value：仅 update 时填写被替换的旧值

## 回复规则

1. 以决策引擎的身份回复，而非聊天机器人
2. 解释决策依据时引用具体的感知数据和推理步骤
3. 执行调优指令后简洁反馈结果
4. 禁止无目的的闲聊和角色扮演
5. 不要输出 JSON 或其他结构化格式（EDIT_INTENT 行除外）
{custom_prompt_section}"""
```

**`build_debug_system_prompt()` 函数**：

```python
def build_debug_system_prompt(
    bot_nickname: str = "",
    alias_names: list[str] | None = None,
    personality: str = "",
    reply_style: str = "",
    custom_prompt: str = "",
    preference_summary: str = "",
) -> str:
    """构建决策调试系统提示词。"""
    personality_section = ""
    if bot_nickname or personality or reply_style:
        alias_section = ""
        if alias_names:
            alias_section = ALIAS_TEMPLATE.format(alias_names="、".join(alias_names))
        personality_detail = ""
        if personality:
            personality_detail = PERSONALITY_DETAIL_TEMPLATE.format(personality=personality)
        reply_style_detail = ""
        if reply_style:
            reply_style_detail = REPLY_STYLE_TEMPLATE.format(reply_style=reply_style)
        personality_section = PERSONALITY_TEMPLATE.format(
            bot_nickname=bot_nickname or "Bot",
            alias_section=alias_section,
            personality_section=personality_detail,
            reply_style_section=reply_style_detail,
        )

    custom_prompt_section = ""
    if custom_prompt and custom_prompt.strip():
        custom_prompt_section = f"\n{custom_prompt.strip()}"

    result = DEBUG_SYSTEM_PROMPT.format(
        personality_section=personality_section,
        custom_prompt_section=custom_prompt_section,
    )

    if preference_summary and preference_summary.strip():
        result += f"\n\n{preference_summary.strip()}"

    return result
```

### 1.3.6 决策调试前端界面（重构 `webui_static/`）

**设计思路**：将"智能体对话"Tab 改造为"决策调试"Tab，采用左侧聊天流列表 + 右侧调试面板的布局。调试面板分为三个区域：上下文区（展示决策上下文）、指令区（发送调试指令 + UI 按钮）、日志区（展示决策推理过程）。常用操作使用 UI 按钮，高级操作使用文本指令。

#### 1.3.6.1 整体布局

```
┌──────────────────────────────────────────────────────────────────┐
│  决策调试                                              [刷新]    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ 💡 注入 MaiBot 提示词是为了让智能体更好地理解上下文做出决策， │ │
│  │    而不是和智能体聊天。你可以通过调试指令观察和干预决策行为。 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│ ┌──────────────┐ ┌────────────────────────────────────────────┐ │
│ │ 聊天流列表    │ │ 调试面板                                    │ │
│ │              │ │ ┌────────────────────────────────────────┐ │ │
│ │ [群聊] 测试群 │ │ │ 上下文区                                │ │ │
│ │ [私聊] 张三  │ │ │ 近期消息 │ 冷却状态 │ 活跃度           │ │ │
│ │ [群聊] 开发群 │ │ │ ...上下文内容...                        │ │ │
│ │              │ │ └────────────────────────────────────────┘ │ │
│ │              │ │ ┌────────────────────────────────────────┐ │ │
│ │              │ │ │ 日志区（决策推理过程）                    │ │ │
│ │              │ │ │ 14:30 [触发] 话题补充 置信度 0.75       │ │ │
│ │              │ │ │   → 感知: 检测到Python话题...           │ │ │
│ │              │ │ │   → 推理: 话题与bot知识相关...           │ │ │
│ │              │ │ │   → 决策: should_trigger=true           │ │ │
│ │              │ │ └────────────────────────────────────────┘ │ │
│ │              │ │ ┌────────────────────────────────────────┐ │ │
│ │              │ │ │ 指令区                                  │ │ │
│ │              │ │ │ [查看上下文] [强制触发] [重置冷却]       │ │ │
│ │              │ │ │ ┌──────────────────────────────┐ [发送] │ │ │
│ │              │ │ │ │ 输入调试指令...               │       │ │ │
│ │              │ │ │ └──────────────────────────────┘       │ │ │
│ │              │ │ └────────────────────────────────────────┘ │ │
│ └──────────────┘ └────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

#### 1.3.6.2 左侧聊天流列表

**数据来源**：复用 `/api/proactive-chat/streams` 端点，展示所有可调试的聊天流。

**列表项结构**：

```html
<div class="debug-stream-item active" onclick="selectDebugStream('stream_123')">
  <div class="stream-row-1">
    <span class="stream-type-badge group">群</span>
    <span class="stream-name">测试群</span>
    <span class="stream-cooldown">冷却中</span>
  </div>
  <div class="stream-row-2">
    <span class="stream-last-action">话题补充 · 14:30</span>
  </div>
</div>
```

**聊天流名称显示**：优先显示聊天流实际名称（群名或"XX 的私聊"），而非 stream_id。复用 streams API 返回的 `display_name` 字段。

#### 1.3.6.3 右侧调试面板

**上下文区**：

展示选中聊天流的决策上下文，数据来源为 `/api/proactive-chat/debug/context`。

```html
<div class="debug-context-panel">
  <div class="context-header">
    <span class="context-title">决策上下文</span>
    <button class="btn-sm" onclick="refreshContext()">刷新</button>
  </div>
  <div class="context-sections">
    <div class="context-section">
      <h4>近期消息</h4>
      <div class="context-messages">
        <div class="context-msg">[张三] 大家好，最近在学Python</div>
        <div class="context-msg">[李四] Python很好用啊</div>
      </div>
    </div>
    <div class="context-section">
      <h4>冷却状态</h4>
      <div class="context-cooldown">
        上次触发: 14:25 · 话题补充 · 剩余冷却 4分30秒
      </div>
    </div>
    <div class="context-section">
      <h4>近期决策</h4>
      <div class="context-decisions">
        <div class="decision-item triggered">14:25 话题补充 (0.75)</div>
        <div class="decision-item skipped">14:10 不触发 (0.3)</div>
      </div>
    </div>
  </div>
</div>
```

**日志区**：

展示选中聊天流的决策推理过程，数据来源为 `/api/proactive-chat/debug/log` 和调试会话中的消息。

```html
<div class="debug-log-panel">
  <div class="log-header">
    <span class="log-title">决策日志</span>
  </div>
  <div class="log-entries">
    <!-- 调试指令 -->
    <div class="log-entry instruction">
      <div class="log-entry-header">
        <span class="log-role">调试指令</span>
        <span class="log-time">14:30</span>
      </div>
      <div class="log-entry-content">查看当前决策依据</div>
    </div>
    <!-- 决策结果 -->
    <div class="log-entry result">
      <div class="log-entry-header">
        <span class="log-role">决策引擎</span>
        <span class="log-time">14:30</span>
      </div>
      <div class="log-entry-content markdown-body">
        <p>当前决策依据如下：</p>
        <ul>
          <li>感知：检测到Python话题，与bot知识领域相关</li>
          <li>推理：话题补充场景，置信度 0.75</li>
          <li>决策：should_trigger=true</li>
        </ul>
      </div>
    </div>
  </div>
</div>
```

**指令区**：

混合交互设计：常用操作使用 UI 按钮，高级操作使用文本指令输入框。

```html
<div class="debug-instruction-panel">
  <!-- UI 按钮组 -->
  <div class="instruction-buttons">
    <button class="btn-debug" onclick="viewContext()" title="查看当前决策上下文">
      📋 查看上下文
    </button>
    <button class="btn-debug" onclick="forceTrigger()" title="强制触发一次决策循环">
      ⚡ 强制触发
    </button>
    <button class="btn-debug" onclick="resetCooldown()" title="重置该聊天流的冷却">
      🔄 重置冷却
    </button>
  </div>
  <!-- 文本指令输入 -->
  <div class="instruction-input">
    <input type="text" id="debug-instruction-input"
           placeholder="输入调试指令，如：下次遇到XX场景时优先触发"
           onkeydown="if(event.key==='Enter')sendDebugInstruction()">
    <button class="btn-send" onclick="sendDebugInstruction()">发送</button>
  </div>
</div>
```

**UI 按钮与文本指令的映射**：

| UI 按钮 | 实际操作 | 对应文本指令（等价） |
|---------|---------|-------------------|
| 📋 查看上下文 | 调用 `GET /debug/context` 并刷新上下文区 | — |
| ⚡ 强制触发 | 调用 `POST /trigger` 触发决策循环 | — |
| 🔄 重置冷却 | 调用 `POST /cooldown/reset` 重置冷却 | — |
| 文本指令输入 | 调用 `POST /debug/instruction` 发送调试指令 | 任意文本 |

**UI 按钮操作不经过 LLM**，直接调用对应 API 端点；文本指令经过 LLM 推理后返回决策结果。

#### 1.3.6.4 前端 JS 核心逻辑

```javascript
// === 状态管理 ===
let debugStreams = [];          // 可调试的聊天流列表
let currentDebugStreamId = '';  // 当前选中的聊天流 ID
let currentDebugSessionId = ''; // 当前调试会话 ID
let debugContext = {};          // 当前决策上下文
let debugLog = [];              // 决策日志

// === 聊天流列表 ===
async function loadDebugStreams() {
    const resp = await fetch('/api/proactive-chat/streams');
    const data = await resp.json();
    if (data.success) {
        debugStreams = data.streams;
        renderDebugStreamList();
    }
}

function renderDebugStreamList() {
    const el = document.getElementById('debug-stream-list');
    if (!debugStreams.length) {
        el.innerHTML = '<div class="empty-hint">暂无可调试的聊天流</div>';
        return;
    }
    el.innerHTML = debugStreams.map(s => {
        const active = s.stream_id === currentDebugStreamId ? 'active' : '';
        const typeBadge = s.chat_type === 'group'
            ? '<span class="stream-type-badge group">群</span>'
            : '<span class="stream-type-badge private">私</span>';
        const cooldown = s.is_cooled_down ? '' : '<span class="stream-cooldown">冷却中</span>';
        return `<div class="debug-stream-item ${active}"
                     onclick="selectDebugStream('${s.stream_id}')">
            <div class="stream-row-1">
                ${typeBadge}
                <span class="stream-name">${escapeHtml(s.display_name)}</span>
                ${cooldown}
            </div>
        </div>`;
    }).join('');
}

// === 选择聊天流 ===
async function selectDebugStream(streamId) {
    currentDebugStreamId = streamId;
    renderDebugStreamList();  // 更新高亮

    // 1. 获取决策上下文
    await refreshContext();

    // 2. 获取决策日志
    await refreshDecisionLog();

    // 3. 创建或获取调试会话
    await ensureDebugSession(streamId);
}

// === 决策上下文 ===
async function refreshContext() {
    if (!currentDebugStreamId) return;
    const resp = await fetch(`/api/proactive-chat/debug/context?stream_id=${currentDebugStreamId}`);
    const data = await resp.json();
    if (data.success) {
        debugContext = data.context;
        renderDebugContext();
    }
}

function renderDebugContext() {
    const el = document.getElementById('debug-context-content');
    if (!debugContext || !debugContext.recent_messages?.length) {
        el.innerHTML = '<div class="empty-hint">暂无决策上下文</div>';
        return;
    }
    // 渲染近期消息、冷却状态、近期决策
    let html = '<div class="context-section"><h4>近期消息</h4>';
    html += debugContext.recent_messages.map(m =>
        `<div class="context-msg">[${escapeHtml(m.sender_name)}] ${escapeHtml(m.content)}</div>`
    ).join('');
    html += '</div>';

    if (debugContext.cooldown_status?.last_trigger_time) {
        html += '<div class="context-section"><h4>冷却状态</h4>';
        html += `<div class="context-cooldown">上次触发: ${debugContext.cooldown_status.last_summary || '无'}</div>`;
        html += '</div>';
    }

    if (debugContext.recent_decisions?.length) {
        html += '<div class="context-section"><h4>近期决策</h4>';
        html += debugContext.recent_decisions.map(d => {
            const cls = d.action_taken === 'triggered' ? 'triggered' : 'skipped';
            return `<div class="decision-item ${cls}">${d.time} ${d.intent || '无意图'} (${d.confidence})</div>`;
        }).join('');
        html += '</div>';
    }

    el.innerHTML = html;
}

// === 调试会话管理 ===
async function ensureDebugSession(streamId) {
    // 检查是否已有该聊天流的调试会话
    const resp = await fetch('/api/proactive-chat/debug/sessions');
    const data = await resp.json();
    if (data.success) {
        const existing = data.sessions.find(s => s.stream_id === streamId);
        if (existing) {
            currentDebugSessionId = existing.session_id;
            await loadDebugMessages();
            return;
        }
    }
    // 创建新会话
    const createResp = await fetch('/api/proactive-chat/debug/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({stream_id: streamId}),
    });
    const createData = await createResp.json();
    if (createData.success) {
        currentDebugSessionId = createData.session_id;
    }
}

// === 发送调试指令 ===
async function sendDebugInstruction() {
    const input = document.getElementById('debug-instruction-input');
    const instruction = input.value.trim();
    if (!instruction || !currentDebugSessionId) return;

    input.value = '';

    // 在日志区显示调试指令
    appendDebugLog('debug_instruction', instruction);

    const resp = await fetch('/api/proactive-chat/debug/instruction', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            session_id: currentDebugSessionId,
            instruction: instruction,
        }),
    });
    const data = await resp.json();
    if (data.success) {
        // 在日志区显示决策结果
        appendDebugLog('decision_result', data.content, data.edit_performed);
    } else {
        appendDebugLog('error', data.error);
    }
}

// === UI 按钮操作 ===
async function viewContext() {
    await refreshContext();
}

async function forceTrigger() {
    if (!currentDebugStreamId) return;
    const resp = await fetch('/api/proactive-chat/trigger', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({stream_id: currentDebugStreamId}),
    });
    const data = await resp.json();
    if (data.success) {
        appendDebugLog('system', '已触发决策循环');
    } else {
        appendDebugLog('error', data.error);
    }
}

async function resetCooldown() {
    if (!currentDebugStreamId) return;
    const resp = await fetch('/api/proactive-chat/cooldown/reset', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({stream_id: currentDebugStreamId}),
    });
    const data = await resp.json();
    if (data.success) {
        appendDebugLog('system', '已重置冷却');
        await refreshContext();
    } else {
        appendDebugLog('error', data.error);
    }
}

// === 决策日志 ===
async function refreshDecisionLog() {
    if (!currentDebugStreamId) return;
    const resp = await fetch(`/api/proactive-chat/debug/log?stream_id=${currentDebugStreamId}&limit=20`);
    const data = await resp.json();
    if (data.success) {
        debugLog = data.log;
        renderDecisionLog();
    }
}

function appendDebugLog(role, content, editPerformed = false) {
    const el = document.getElementById('debug-log-entries');
    const time = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit'});

    let roleLabel = '';
    let cssClass = '';
    if (role === 'debug_instruction') {
        roleLabel = '调试指令';
        cssClass = 'instruction';
    } else if (role === 'decision_result') {
        roleLabel = '决策引擎';
        cssClass = 'result';
    } else if (role === 'system') {
        roleLabel = '系统';
        cssClass = 'system';
    } else if (role === 'error') {
        roleLabel = '错误';
        cssClass = 'error';
    }

    const rendered = (role === 'decision_result')
        ? renderMarkdown(content)
        : escapeHtml(content);

    const editBadge = editPerformed ? ' <span class="edit-badge">已调优</span>' : '';

    const entry = document.createElement('div');
    entry.className = `log-entry ${cssClass}`;
    entry.innerHTML = `
        <div class="log-entry-header">
            <span class="log-role">${roleLabel}</span>
            <span class="log-time">${time}</span>
        </div>
        <div class="log-entry-content">${rendered}${editBadge}</div>
    `;
    el.appendChild(entry);
    el.scrollTop = el.scrollHeight;
}
```

#### 1.3.6.5 CSS 样式要点

```css
/* 决策调试主布局 */
.debug-layout {
    display: flex;
    height: 100%;
    gap: 0;
}

.debug-stream-list {
    width: 240px;
    border-right: 1px solid var(--border);
    overflow-y: auto;
    flex-shrink: 0;
}

.debug-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* 上下文区 */
.debug-context-panel {
    border-bottom: 1px solid var(--border);
    padding: 12px;
    max-height: 200px;
    overflow-y: auto;
}

/* 日志区 */
.debug-log-panel {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
}

/* 指令区 */
.debug-instruction-panel {
    border-top: 1px solid var(--border);
    padding: 12px;
}

.instruction-buttons {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
}

.btn-debug {
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.2s;
}

.btn-debug:hover {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
}

/* 日志条目 */
.log-entry {
    margin-bottom: 12px;
    padding: 8px 12px;
    border-radius: 8px;
}

.log-entry.instruction {
    background: rgba(108, 92, 231, 0.1);
    border-left: 3px solid var(--accent);
}

.log-entry.result {
    background: var(--bg);
    border: 1px solid var(--border);
}

.log-entry.system {
    background: rgba(52, 152, 219, 0.1);
    text-align: center;
    font-size: 0.8rem;
    color: var(--text2);
}

.log-entry.error {
    background: rgba(231, 76, 60, 0.1);
    border-left: 3px solid #e74c3c;
}

/* 聊天流类型徽标 */
.stream-type-badge {
    display: inline-block;
    width: 20px;
    height: 20px;
    border-radius: 4px;
    text-align: center;
    line-height: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    margin-right: 6px;
}

.stream-type-badge.group {
    background: rgba(46, 204, 113, 0.2);
    color: #2ecc71;
}

.stream-type-badge.private {
    background: rgba(52, 152, 219, 0.2);
    color: #3498db;
}

/* 调优徽标 */
.edit-badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(46, 204, 113, 0.2);
    color: #2ecc71;
    font-size: 0.7rem;
    margin-left: 4px;
}

/* 提示横幅 */
.debug-hint-banner {
    background: rgba(52, 152, 219, 0.1);
    border: 1px solid rgba(52, 152, 219, 0.3);
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 12px;
    font-size: 0.8rem;
    color: var(--text2);
}
```

### 1.3.7 配置调整（修改 `config.py`）

**设计思路**：将 `AgentChatConfig` 的 UI 标签和描述从"智能体对话"改为"决策调试"，新增调试相关配置项。保留原有配置项的键名以确保向后兼容（配置文件中的字段名不变）。

```python
class AgentChatConfig(PluginConfigBase):
    __ui_label__ = "决策调试"
    __ui_icon__ = "bug"
    __ui_order__ = 14

    agent_chat_enabled: bool = Field(
        default=False,
        description="是否启用 WebUI 决策调试功能",
    )
    chat_max_tokens: int = Field(
        default=500, ge=100, le=2000,
        description="调试指令 LLM 调用的最大 token 数",
    )
    chat_max_sessions: int = Field(
        default=5, ge=1, le=20,
        description="最大同时活跃调试会话数",
    )
    chat_session_token_limit: int = Field(
        default=800000, ge=100000, le=900000,
        description="调试会话自动清除的 token 阈值",
    )
    chat_temperature: float = Field(
        default=0.7, ge=0.0, le=2.0,
        description="调试指令的 LLM 温度",
    )
    file_edit_enabled: bool = Field(
        default=False,
        description="是否启用决策调优指令的文件编辑能力",
    )
    editable_files: list[str] = Field(
        default_factory=lambda: ["user_preferences.yaml"],
        description="可编辑文件白名单（相对于插件数据目录的文件路径）",
    )
    edit_backup_enabled: bool = Field(
        default=True,
        description="是否启用编辑前备份",
    )
    auto_preference_enabled: bool = Field(
        default=True,
        description="是否启用智能偏好提取（决策调优指令自动识别）",
    )
    preference_summary_token_limit: int = Field(
        default=500, ge=100, le=2000,
        description="偏好摘要注入系统提示词的最大 Token 数",
    )
    session_persistence_enabled: bool = Field(
        default=True,
        description="是否启用调试会话持久化（容器重启后保留会话数据）",
    )
    max_persisted_sessions: int = Field(
        default=20, ge=1, le=100,
        description="最大持久化调试会话数",
    )
    max_persisted_messages_per_session: int = Field(
        default=200, ge=10, le=1000,
        description="每个调试会话最大持久化消息数",
    )
    session_retention_days: int = Field(
        default=30, ge=0, le=365,
        description="调试会话保留天数，0 表示不清理",
    )
```

**注意**：配置项的 Python 字段名保持不变（`agent_chat` 分组），仅修改 UI 标签和描述文案。这确保了 v3.4.1 的配置文件可以直接升级到 v3.5，无需迁移。

### 1.3.8 插件启动流程集成（修改 `plugin.py`）

**设计思路**：在插件初始化时，创建 `DebugService` 实例（替代 `AgentChatService`），注入 `WebUIServer`，并注册调试 API 路由。

```python
# 在插件初始化逻辑中（伪代码）
async def _init_debug_service(self):
    """初始化决策调试服务。"""
    # 创建 DebugService（替代 AgentChatService）
    from .debug_service import DebugService
    self._debug_service = DebugService(
        deepseek_client=self._deepseek_client,
        event_bus=self._event_bus,
        persistence_manager=self._persistence_manager,
        message_api=self._message_api,
    )

    # 注入 FileEditor
    if config.agent_chat.file_edit_enabled:
        from .file_editor import FileEditor
        self._debug_service.set_file_editor(FileEditor(self._data_dir))

    # 持久化集成
    config = self._config_getter()
    if config.agent_chat.session_persistence_enabled:
        from .session_persistence import SessionPersistence
        persistence = SessionPersistence(data_dir=self._data_dir)
        self._debug_service.set_session_persistence(
            persistence=persistence,
            enabled=True,
            max_sessions=config.agent_chat.max_persisted_sessions,
            max_messages_per_session=config.agent_chat.max_persisted_messages_per_session,
            retention_days=config.agent_chat.session_retention_days,
        )
        await self._debug_service.restore_sessions()

    # 注入到 WebUIServer
    self._webui_server.set_debug_service(self._debug_service)

    # 注册调试 API 路由
    from .debug_api import DebugApiController
    self._debug_api = DebugApiController(
        debug_service=self._debug_service,
        webui_server=self._webui_server,
        config_getter=self._config_getter,
    )
    self._debug_api.register_routes(self._webui_server._app)
```

### 1.3.9 向后兼容处理

**设计思路**：v3.5 保留原有 agent_chat API 端点，标记为 deprecated，确保 v3.4.1 的前端代码仍可正常工作。

**兼容策略**：

1. 原有 `/api/proactive-chat/agent/chat/*` 端点保留，内部重定向到 DebugService 对应方法
2. `AgentChatService` 类保留但标记为 deprecated，内部委托给 `DebugService`
3. 前端新增"决策调试"Tab，保留"智能体对话"Tab 但标记为 deprecated
4. 配置文件字段名不变，仅修改 UI 标签

**`AgentChatService` 兼容包装**：

```python
class AgentChatService:
    """[deprecated] 请使用 DebugService 替代。保留用于向后兼容。"""

    def __init__(self, debug_service: DebugService) -> None:
        self._debug_service = debug_service

    async def create_session(self, stream_context_id: str = "") -> AgentChatSession:
        """[deprecated] 创建会话。"""
        debug_session = await self._debug_service.create_session(stream_context_id or "")
        return self._convert_session(debug_session)

    async def send_message(self, session_id, user_content, config, **kwargs) -> AgentChatMessage:
        """[deprecated] 发送消息。"""
        result = await self._debug_service.execute_instruction(
            session_id=session_id,
            instruction=user_content,
            config=config,
            **kwargs,
        )
        return AgentChatMessage(
            role="assistant",
            content=result.content,
            timestamp=result.timestamp,
            edit_performed=result.edit_performed,
        )

    # ... 其他方法委托给 DebugService ...
```

# 2. 接口设计

## 2.1 总体设计

v3.5 的接口变更集中在三个方面：
1. **新增调试 API 端点**：`/api/proactive-chat/debug/*` 系列端点
2. **现有端点扩展**：决策记录和冷却记录返回数据新增 `stream_name` 字段
3. **现有端点保留**：`/api/proactive-chat/agent/chat/*` 端点标记为 deprecated 但保留功能

## 2.2 接口清单

### 2.2.1 新增调试 API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/proactive-chat/debug/context` | GET | 获取指定聊天流的决策上下文 |
| `/api/proactive-chat/debug/sessions` | GET | 获取调试会话列表 |
| `/api/proactive-chat/debug/sessions` | POST | 创建调试会话（必须指定 stream_id） |
| `/api/proactive-chat/debug/sessions/{id}` | GET | 获取调试会话详情 |
| `/api/proactive-chat/debug/instruction` | POST | 发送调试指令 |
| `/api/proactive-chat/debug/sessions/{id}/clear` | POST | 清除调试会话 |
| `/api/proactive-chat/debug/log` | GET | 获取指定聊天流的决策日志 |

**GET /api/proactive-chat/debug/context**：

请求参数：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| stream_id | string | 是 | 聊天流 ID |

响应：
```json
{
  "success": true,
  "context": {
    "stream_id": "stream_123",
    "recent_messages": [
      {"sender_name": "张三", "content": "大家好", "timestamp": 1719565200.0}
    ],
    "cooldown_status": {
      "last_trigger_time": 1719564900.0,
      "last_action": "triggered",
      "last_summary": "话题补充"
    },
    "activity_metrics": {},
    "recent_decisions": [
      {
        "time": "14:25",
        "action_taken": "triggered",
        "intent": "topic_supplement",
        "confidence": 0.75,
        "reason": "话题与bot知识相关",
        "react_steps": []
      }
    ]
  }
}
```

**POST /api/proactive-chat/debug/instruction**：

请求体：
```json
{
  "session_id": "a1b2c3d4e5f6g7h8",
  "instruction": "查看当前决策依据"
}
```

响应：
```json
{
  "success": true,
  "content": "当前决策依据如下：...",
  "session_id": "a1b2c3d4e5f6g7h8",
  "token_estimate": 800,
  "edit_performed": false
}
```

**GET /api/proactive-chat/debug/log**：

请求参数：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| stream_id | string | 是 | 聊天流 ID |
| limit | int | 否 | 返回条数，默认 20，最大 100 |

响应：
```json
{
  "success": true,
  "log": [
    {
      "time": "14:25:30",
      "action_taken": "triggered",
      "intent": "topic_supplement",
      "confidence": 0.75,
      "reason": "话题与bot知识相关",
      "react_steps": [
        {"step_index": 1, "tool_name": "get_recent_messages", "tool_result": "..."}
      ]
    }
  ]
}
```

### 2.2.2 现有端点变更

| 端点 | 方法 | 变更类型 | 变更内容 |
|------|------|----------|----------|
| `/api/proactive-chat/decisions` | GET | **响应扩展** | 返回数据新增 `stream_name` 字段 |
| `/api/proactive-chat/cooldown` | GET | **响应扩展** | 返回数据新增 `stream_name` 字段 |

**decisions 端点响应扩展**：

```json
{
  "records": [
    {
      "ts": 1719565200.0,
      "stream_id": "stream_123",
      "stream_name": "[群聊] 测试群",
      "action_taken": "triggered",
      ...
    }
  ]
}
```

### 2.2.3 Deprecated 端点

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/proactive-chat/agent/chat/sessions` | GET | deprecated | 请使用 `/debug/sessions` |
| `/api/proactive-chat/agent/chat/sessions` | POST | deprecated | 请使用 `/debug/sessions` |
| `/api/proactive-chat/agent/chat/sessions/{id}` | GET | deprecated | 请使用 `/debug/sessions/{id}` |
| `/api/proactive-chat/agent/chat/send` | POST | deprecated | 请使用 `/debug/instruction` |
| `/api/proactive-chat/agent/chat/sessions/{id}/clear` | POST | deprecated | 请使用 `/debug/sessions/{id}/clear` |

# 4. 数据模型

## 4.1 设计目标

1. 与 v3.4.1 的 JSONL 持久化模式保持一致
2. 支持调试会话和调试消息的独立模型
3. 支持决策上下文快照
4. 保持向后兼容（v3.4.1 的持久化数据可被 v3.5 读取）

## 4.2 模型实现

### 4.2.1 DebugMessage（替代 AgentChatMessage）

```python
@dataclass
class DebugMessage:
    """调试消息。"""
    role: str = ""          # "system" | "debug_instruction" | "decision_result"
    content: str = ""
    timestamp: float = 0.0
    reasoning: str = ""     # 决策推理过程（仅 decision_result）
    edit_performed: bool = False
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| role | string | 是 | 消息角色："system"、"debug_instruction"、"decision_result" |
| content | string | 是 | 消息内容，最大 4000 字符 |
| timestamp | float | 是 | 消息时间戳，Unix 时间戳（毫秒） |
| reasoning | string | 否 | 决策推理过程，仅 decision_result 角色使用 |
| edit_performed | bool | 否 | 是否执行了偏好编辑 |

**JSONL 持久化格式**（与 v3.4.1 兼容）：

```json
{"role": "debug_instruction", "content": "查看决策依据", "timestamp": 1719565200000.0}
```

v3.4.1 的 `role: "user"` 在 v3.5 中映射为 `role: "debug_instruction"`，`role: "assistant"` 映射为 `role: "decision_result"`。恢复数据时自动转换。

### 4.2.2 DebugSession（替代 AgentChatSession）

```python
@dataclass
class DebugSession:
    """调试会话。"""
    session_id: str = ""
    stream_id: str = ""     # 必须关联聊天流
    messages: list[DebugMessage] = field(default_factory=list)
    created_at: float = 0.0
    last_active_at: float = 0.0
    token_estimate: int = 0
    is_responding: bool = False
    context_snapshot: dict = field(default_factory=dict)
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话唯一标识，16 位十六进制 |
| stream_id | string | 是 | 关联的聊天流 ID（调试必须针对具体聊天流） |
| messages | list[DebugMessage] | 是 | 调试消息列表 |
| created_at | float | 是 | 创建时间，Unix 时间戳（秒） |
| last_active_at | float | 是 | 最后活跃时间，Unix 时间戳（秒） |
| token_estimate | int | 是 | Token 估算值 |
| is_responding | bool | 是 | 是否正在响应 |
| context_snapshot | dict | 否 | 决策上下文快照 |

**与 v3.4.1 的兼容性**：`stream_id` 对应 v3.4.1 的 `stream_context_id`，恢复数据时自动映射。

### 4.2.3 会话元数据扩展（sessions_index.jsonl）

```json
{
  "session_id": "a1b2c3d4e5f6g7h8",
  "created_at": 1719561600.0,
  "last_active_at": 1719565200.0,
  "stream_context_id": "stream_123",
  "message_count": 5
}
```

与 v3.4.1 格式完全一致，`stream_context_id` 字段在 v3.5 中映射为 `DebugSession.stream_id`。

### 4.2.4 决策上下文快照

```python
@dataclass
class DecisionContextSnapshot:
    """决策上下文快照，在调试会话创建时捕获。"""
    stream_id: str = ""
    recent_messages: list[dict] = field(default_factory=list)
    cooldown_status: dict = field(default_factory=dict)
    activity_metrics: dict = field(default_factory=dict)
    recent_decisions: list[dict] = field(default_factory=list)
```

不持久化到 JSONL 文件（上下文快照仅用于内存展示，容器重启后重新获取）。

### 4.2.5 决策记录 stream_name 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| stream_name | string | 否 | 聊天流的可读显示名称，缓存命中时为"[群聊] 测试群"格式，未命中时为 stream_id 前 8 位加"..." |

该字段为计算字段，不持久化到决策记录文件中，在 API 响应时动态计算。