# 1. 实现模型

## 1.1 上下文视图

```
                    ┌─────────────────────────────────────────────┐
                    │              runtime.py (薄壳)               │
                    │  _init_agent_autonomy() → 创建 Orchestrator  │
                    │  register_message() → 路由到 Orchestrator    │
                    └──────────┬──────────────────────┬───────────┘
                               │                      │
              enabled=true     │                      │  enabled=false
                               ▼                      ▼
                    ┌──────────────────┐   ┌──────────────────────┐
                    │   Orchestrator    │   │  旧 ReasoningEngine  │
                    │  (统一调度)       │   │  (旧 Planner 路径)    │
                    └────────┬─────────┘   └──────────────────────┘
                             │
                    ┌────────┼────────┐
                    │        │        │
                    ▼        ▼        ▼
              ┌─────────┐ ┌──────┐ ┌──────────┐
              │主回复    │ │插话  │ │提醒      │
              │Thinking │ │Thinking│ │Thinking  │
              │Organ    │ │Organ  │ │Organ     │
              └────┬────┘ └───┬──┘ └─────┬────┘
                   │          │          │
                   ▼          ▼          ▼
              ┌─────────────────────────────────┐
              │         ToolRegistry             │
              │  (Builtin + Plugin + MCP)        │
              └─────────────────────────────────┘
                         │
                    reply 工具
                         │
                         ▼
              ┌─────────────────────────────────┐
              │         MessagePortV2            │
              └─────────────────────────────────┘
```

## 1.2 服务/组件总体架构

### 核心设计决策

**决策 1：ThinkingOrgan 委托 MaisakaChatLoopService 执行 LLM 调用**

ThinkingOrgan 不重写 LLM 调用逻辑，而是持有 MaisakaChatLoopService 实例，委托其完成：
- 系统提示词构建（复用 embodied 模板）
- 上下文选择（复用 select_llm_context_messages）
- 请求消息构造（复用 _build_request_messages）
- LLM 调用（复用 chat_loop_step）

理由：MaisakaChatLoopService 已包含完整的 prompt 构建、上下文管理、视觉处理、黑话注入等逻辑，重写成本极高且容易引入 bug。委托模式保持"ThinkingOrgan 决定思考什么，ChatLoopService 决定怎么调 LLM"的职责分离。

**决策 2：工具循环逻辑放在 ThinkingOrgan 内部**

ThinkingOrgan 新增 `think_with_tools()` 方法，包含完整的工具循环：
1. 调用 ChatLoopService.chat_loop_step() 获取 LLM 响应
2. 如果有 tool_calls → 调用 ToolRegistry.invoke() → 结果写回历史 → 回到步骤 1
3. 如果无 tool_calls → 循环结束

理由：工具循环是"思考"的一部分，应由 ThinkingOrgan 拥有。旧 ReasoningEngine 的工具循环逻辑（_handle_tool_calls）迁移到 ThinkingOrgan，保持代码同构。

**决策 3：消息调度/去重/打断放在 Orchestrator**

Orchestrator 新增 `MessageTurnScheduler`（从旧 ReasoningEngine 提取），负责：
- 消息排队（asyncio.Queue）
- 去重（drain_ready_turn_triggers）
- 打断（新消息到达时取消正在进行的思考任务）
- 回复频率控制（talk_value + 消息阈值 + 回复必要性评分）

理由：Orchestrator 是"谁在思考"的决策者，消息调度是调度逻辑的一部分。ThinkingOrgan 是被动的"被调用"组件，不应持有调度状态。

**决策 4：上下文注入由 ThinkingOrgan 编排，ChatLoopService 执行**

ThinkingOrgan 在调用 ChatLoopService 之前，构建 injected_user_messages（deferred_tools_reminder、heuristic_memory、person_profile、行为表现参考、黑话参考、中期记忆参考），作为参数传入 ChatLoopService。

理由：注入内容的决策权在 ThinkingOrgan（它知道当前智能体的内心状态），执行权在 ChatLoopService（它知道如何将注入项组装到请求消息中）。

### 组件关系

```
ThinkingOrgan
  ├── EmbodiedPlannerPromptBuilder  (已有，构建角色化提示词)
  ├── MaisakaChatLoopService        (新增持有，执行 LLM 调用)
  ├── ToolRegistry                  (新增持有，工具调用)
  └── ThinkContext → injected_user_messages  (新增，上下文注入)

Orchestrator
  ├── MessageTurnScheduler          (新增，从旧 ReasoningEngine 提取)
  ├── AutonomousAgent[]             (已有，每个持有 ThinkingOrgan)
  ├── Butler                        (已有，插话协调)
  ├── VitalityManager               (已有，生命力管理)
  └── ReplyFrequencyController      (新增，从旧 ReasoningEngine 提取)
```

## 1.3 实现设计文档

### 1.3.1 ThinkingOrgan 改造

**当前**（224行）：
```python
class ThinkingOrgan:
    def __init__(self, agent_id, prompt_builder)
    async def think(self, context: ThinkContext) -> ThinkResult
    async def think_proactive(self, reason, context: ThinkContext) -> ThinkResult
    async def _call_llm(self, system_prompt, personality_prompt, user_text) -> str | None
```

**目标**：
```python
class ThinkingOrgan:
    def __init__(self, agent_id, prompt_builder, chat_loop_service, tool_registry)
    
    async def think(self, context: ThinkContext) -> ThinkResult:
        """主回复思考 — 含完整工具循环"""
        return await self._think_with_tools(context, request_kind="planner")
    
    async def think_proactive(self, reason, context: ThinkContext) -> ThinkResult:
        """主动思考 — 含完整工具循环"""
        return await self._think_with_tools(context, request_kind="proactive", reason=reason)
    
    async def _think_with_tools(self, context, *, request_kind, reason=None) -> ThinkResult:
        """工具循环核心"""
        injected = self._build_injected_messages(context)
        tools = self._build_tool_definitions(context)
        
        for round_idx in range(MAX_INTERNAL_ROUNDS):
            response = await self._chat_loop_service.chat_loop_step(
                chat_history=self._history,
                injected_user_messages=injected,
                tool_definitions=tools,
                ...
            )
            
            if not response.tool_calls:
                return ThinkResult(action=ThinkAction.SILENT)
            
            should_pause, pause_tool, summaries, _ = await self._handle_tool_calls(response.tool_calls, response.thought)
            
            if should_pause:
                if pause_tool == "wait":
                    return ThinkResult(action=ThinkAction.WAIT, ...)
                break
            
            # 工具结果写回历史，继续下一轮
            self._append_tool_results(response.tool_calls, summaries)
            injected = []  # 后续轮次不再重复注入
        
        return ThinkResult(action=ThinkAction.SILENT)
    
    async def _handle_tool_calls(self, tool_calls, thought) -> tuple[bool, str, list, list]:
        """执行工具调用 — 从旧 ReasoningEngine._handle_tool_calls 迁移"""
        ...
    
    def _build_injected_messages(self, context: ThinkContext) -> list:
        """构建上下文注入消息"""
        ...
    
    def _build_tool_definitions(self, context: ThinkContext) -> list:
        """构建工具定义 — visible/deferred 分离"""
        ...
```

### 1.3.2 Orchestrator 改造

**新增 MessageTurnScheduler**（从旧 ReasoningEngine 提取）：

```python
class MessageTurnScheduler:
    """消息调度器 — 管理消息排队、去重、打断"""
    
    def __init__(self, orchestrator):
        self._queue = asyncio.Queue()
        self._running = False
        self._current_task: asyncio.Task | None = None
    
    async def schedule_message_turn(self, message) -> None:
        """消息入队，可能打断当前思考"""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()  # 打断
        await self._queue.put(message)
    
    async def run_loop(self) -> None:
        """消费队列，调度 ThinkingOrgan 思考"""
        self._running = True
        while self._running:
            trigger = await self._queue.get()
            triggers = self._drain_ready_turn_triggers()
            await self._orchestrator._execute_think_cycle(triggers)
```

**Orchestrator.handle_message 改造**：

```python
async def handle_message(self, message: CoreMessage) -> None:
    # 1. 通知分类 + 生命力更新（已有）
    # 2. 激活主智能体（已有）
    # 3. 同步待命智能体（已有）
    
    # 4. [新增] 主回复调度
    if not message.is_notify or notice_kind == NoticeKind.INTERACTION:
        if self._should_reply(message):  # 回复频率控制
            await self._turn_scheduler.schedule_message_turn(message)
    
    # 5. 管家提醒创建（已有）
    # 6. 插话调度（已有）
```

**Orchestrator._execute_think_cycle 新增**：

```python
async def _execute_think_cycle(self, triggers) -> None:
    """执行主智能体思考周期"""
    primary = self._active_agents.get(self._primary_agent_id)
    if primary is None:
        return
    
    think_context = await self._build_think_context(primary, ...)
    task = self._think_scheduler.schedule(self._primary_agent_id, primary.thinking_organ, think_context)
    self._turn_scheduler._current_task = task
    result = await task
    # 结果已通过 reply 工具发送，无需额外处理
```

### 1.3.3 runtime.py 路由改造

**register_message 改造**：

```python
async def register_message(self, message: SessionMessage) -> None:
    # ... 消息预处理 ...
    
    if self._agent_orchestrator is not None:
        # [新路径] Orchestrator 统一调度
        core_msg = self._to_core_message(message)
        await self._agent_orchestrator.handle_message(core_msg)
        
        if not is_ambient_notice:
            return  # Orchestrator 已接管，跳过旧 Planner
    
    # [旧路径] enabled=false 时的回退
    if is_ambient_notice:
        return
    self._schedule_message_turn()
```

### 1.3.4 旧代码退役策略

**阶段 1（当前→迁移完成）**：双路径并存，配置开关控制
- enabled=true → Orchestrator 路径
- enabled=false → 旧 ReasoningEngine 路径

**阶段 2（迁移验证通过后）**：默认切换为 enabled=true
- 旧 ReasoningEngine 标记为 deprecated
- 保留回退能力

**阶段 3（稳定运行后）**：删除旧代码
- 删除 MaisakaReasoningEngine
- 删除 runtime.py 中的旧路径分支
- 删除 MessageTurnScheduler（旧版）
- 删除 IdleBackoffController

# 2. 接口设计

## 2.1 总体设计

ThinkingOrgan 的接口变更遵循"扩展不修改"原则：
- `think()` 和 `think_proactive()` 签名不变，内部行为从"单次 LLM 调用"升级为"完整工具循环"
- `ThinkResult` 新增字段（tool_calls_count、duration_ms），不影响现有消费者
- 新增 `ThinkAction.WAIT` 枚举值，用于 wait 工具暂停

## 2.2 接口清单

### ThinkingOrgan 接口变更

| 方法 | 变更类型 | 说明 |
|------|----------|------|
| `__init__` | 扩展 | 新增 chat_loop_service、tool_registry 参数 |
| `think(context)` | 行为变更 | 从单次 LLM 调用升级为完整工具循环 |
| `think_proactive(reason, context)` | 行为变更 | 同上 |
| `_call_llm()` | 删除 | 由 chat_loop_service.chat_loop_step 替代 |
| 新增 `_think_with_tools()` | 新增 | 工具循环核心逻辑 |
| 新增 `_handle_tool_calls()` | 新增 | 从旧 ReasoningEngine 迁移 |
| 新增 `_build_injected_messages()` | 新增 | 上下文注入编排 |
| 新增 `_build_tool_definitions()` | 新增 | visible/deferred 工具分离 |

### ThinkResult 扩展

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_calls_count` | int | 本轮思考的工具调用总次数 |
| `duration_ms` | float | 本轮思考的耗时（毫秒） |
| `rounds` | int | 工具循环轮次 |

### ThinkAction 扩展

| 枚举值 | 说明 |
|--------|------|
| `WAIT` | wait 工具暂停，等待新消息后继续 |

### Orchestrator 新增接口

| 方法 | 说明 |
|------|------|
| `_execute_think_cycle(triggers)` | 执行主智能体思考周期 |
| `_should_reply(message)` | 回复频率控制判断 |

### MessageTurnScheduler 新增

| 方法 | 说明 |
|------|------|
| `schedule_message_turn(message)` | 消息入队，可能打断当前思考 |
| `run_loop()` | 消费队列，调度思考 |
| `stop()` | 停止调度循环 |

# 4. 数据模型

## 4.1 设计目标

- ThinkContext 扩展以支持工具循环所需的上下文注入
- ThinkResult 扩展以携带工具循环的统计信息
- 旧 ReasoningEngine 的 CycleDetail/CycleEnd 等数据模型迁移到 ThinkingOrgan

## 4.2 模型实现

### ThinkContext 扩展

```python
@dataclass(frozen=True, slots=True)
class ThinkContext:
    messages: tuple[CoreMessage, ...]
    emotion_state_text: str = ""
    inner_voice_text: str = ""
    memory_personality_params: dict[str, Any] | None = None
    trigger_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # 新增字段
    session_id: str = ""                    # 会话 ID，工具执行需要
    is_group_chat: bool = False             # 群聊/私聊标记
    deferred_tools: list[str] = field(default_factory=list)  # 已发现的 deferred 工具
```

### ThinkResult 扩展

```python
@dataclass(frozen=True, slots=True)
class ThinkResult:
    action: ThinkAction
    text: str = ""
    error_message: str = ""
    # 新增字段
    tool_calls_count: int = 0
    duration_ms: float = 0.0
    rounds: int = 1
    wait_seconds: float = 0.0  # action=WAIT 时有效
```

### ThinkAction 扩展

```python
class ThinkAction(Enum):
    REPLY = "reply"
    SILENT = "silent"
    ERROR = "error"
    WAIT = "wait"  # 新增
```

### ThinkingOrganFactory 扩展

```python
class ThinkingOrganFactory:
    def __init__(self, chat_loop_service_factory, tool_registry):
        self._chat_loop_service_factory = chat_loop_service_factory
        self._tool_registry = tool_registry
    
    def create(self, agent_id: str, prompt_builder) -> ThinkingOrgan:
        chat_loop_service = self._chat_loop_service_factory(agent_id)
        return ThinkingOrgan(
            agent_id=agent_id,
            prompt_builder=prompt_builder,
            chat_loop_service=chat_loop_service,
            tool_registry=self._tool_registry,
        )
```