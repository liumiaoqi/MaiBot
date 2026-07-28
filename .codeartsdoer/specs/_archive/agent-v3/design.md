# 1. 实现模型

## 1.1 上下文视图

当前插件架构（v2.1）的决策循环为**单次线性流程**：

```
perceive → reason（单次 LLM 调用）→ act → reflect
```

v3.0 升级为 **ReAct 循环驱动的多轮推理**：

```
perceive → ReAct 循环（LLM ↔ AgentTool 多轮交互）→ [反思子智能体] → act → reflect
```

核心变化：
- `reason()` 从单次 LLM 调用变为 ReAct 循环，LLM 可主动查询信息
- 新增 `agent_tools.py` 模块，定义 AgentTool 注册表和内置工具
- 新增 `event_bus.py` 模块，统一管理事件广播
- 新增 `context_compressor.py` 模块，管理上下文压缩
- 新增反思子智能体逻辑（集成在 `agent.py` 中）
- `deepseek_client.py` 新增 `analyze_with_tools()` 方法，支持 tool_use 格式

## 1.2 服务/组件总体架构

```
plugin.py (入口，不变)
  ├── AgentCore (agent.py，重构 reason → react_loop)
  │     ├── AgentToolRegistry (agent_tools.py，新增)
  │     │     ├── get_recent_messages
  │     │     ├── get_cooldown_status
  │     │     ├── get_stream_activity
  │     │     ├── search_memory
  │     │     └── submit_decision
  │     ├── EventBus (event_bus.py，新增)
  │     └── ContextCompressor (context_compressor.py，新增)
  ├── CooldownManager (cooldown.py，不变)
  ├── DeepSeekClient (deepseek_client.py，扩展)
  ├── PersistenceManager (persistence.py，扩展 DecisionRecord)
  ├── WebUIServer (webui.py，扩展展示)
  └── SmartCleaner (smart_cleanup.py，不变)
```

## 1.3 实现设计文档

### 1.3.1 AgentTool 系统（新文件 `agent_tools.py`）

**设计思路**：借鉴 MiMo-Code 的 `tool/registry.ts` 和 `tool/tool.ts`，但大幅简化。MiMo-Code 使用 Effect-TS + Zod schema，我们用 Python dataclass + dict schema。

**核心类**：

```python
@dataclass
class AgentToolDef:
    name: str
    description: str
    parameters: dict  # JSON Schema 格式，传给 DeepSeek tools 定义
    execute: Callable[..., AwaitAny]

class AgentToolRegistry:
    _tools: dict[str, AgentToolDef]

    def register(self, tool: AgentToolDef) -> None
    def get(self, name: str) -> AgentToolDef | None
    def get_all_definitions() -> list[dict]  # 返回 DeepSeek tools 格式
    def execute_tool(self, name: str, args: dict, ctx: ToolContext) -> str
```

**ToolContext**（工具执行上下文，注入插件内部状态）：

```python
@dataclass
class ToolContext:
    stream_id: str
    ctx: Any           # MaiBot PluginContext
    config: ProactiveChatConfig
    cooldown_manager: CooldownManager
    persistence_manager: PersistenceManager
```

**内置工具实现**：

1. `get_recent_messages`：复用 `AgentCore._get_recent_messages()` 逻辑，参数 `limit`（默认 10，最大 30）
2. `get_cooldown_status`：调用 `CooldownManager.is_cooled_down()` 和内部 `_records`，返回冷却剩余秒数和最近触发意图
3. `get_stream_activity`：调用 `ctx.message.get_by_time_in_chat()` 计算消息频率，返回最近 N 分钟消息数、最后消息时间、平均间隔
4. `search_memory`：复用 `AgentCore._search_memory()` 逻辑，参数 `query`（关键词）
5. `submit_decision`：解析参数返回 AnalysisResult，不执行任何写操作

**DeepSeek tools 格式**（供 `analyze_with_tools()` 使用）：

```json
{
  "type": "function",
  "function": {
    "name": "get_recent_messages",
    "description": "...",
    "parameters": {
      "type": "object",
      "properties": {"limit": {"type": "integer", "description": "...", "default": 10}},
      "required": []
    }
  }
}
```

### 1.3.2 ReAct 循环（重构 `agent.py` 的 `reason()`）

**设计思路**：借鉴 MiMo-Code `prompt.ts` 的 `runLoop` while(true) 模式，但简化为有限步数循环。

**核心方法**：将 `reason()` 重构为 `_react_loop()`

```python
async def _react_loop(
    self,
    stream_id: str,
    perception: PerceptionData,
    config: ProactiveChatConfig,
    ctx: Any,
) -> tuple[AnalysisResult, list[ReActStep]]:
```

**循环逻辑**：

```python
messages = [初始 perception 上下文]  # system + user（perception 数据）
react_steps = []
invalid_tool_count = 0

for step in range(1, max_steps + 1):
    # 1. 调用 LLM（带 tools 定义）
    response = await self._deepseek.analyze_with_tools(
        system_prompt, messages, tools=registry.get_all_definitions(), config
    )

    # 2. 检查是否有 tool_calls
    if response.has_tool_calls:
        for tool_call in response.tool_calls:
            step_record = ReActStep(step_index=step, tool_name=tool_call.name, ...)

            # 特殊处理 submit_decision
            if tool_call.name == "submit_decision":
                result = self._parse_decision_from_args(tool_call.arguments)
                react_steps.append(step_record)
                return result, react_steps

            # 执行普通工具
            tool_result = await registry.execute_tool(tool_call.name, tool_call.arguments, tool_ctx)

            # 追加到消息历史
            messages.append({"role": "assistant", "tool_calls": [tool_call.raw]})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_result})

            step_record.tool_result = tool_result[:2000]
            react_steps.append(step_record)

            # 广播事件
            self._event_bus.publish("react_step", {...})
    else:
        # LLM 未输出 tool_use，尝试从文本解析决策
        result = self.parse_analysis_result(response.text)
        return result, react_steps

    # 达到最大步数，追加提示要求决策
    if step == max_steps:
        messages.append({"role": "user", "content": "请立即使用 submit_decision 工具提交最终决策。"})
        # 最后一次 LLM 调用...

# 超出步数，降级
return AnalysisResult(should_trigger=False), react_steps
```

**关键决策**：

- `max_steps` 默认 3（配置项 `react.max_react_steps`），最大 5
- 循环总超时 30 秒（硬编码，与 DFX 约束一致）
- `submit_decision` 是唯一的决策出口，确保 LLM 输出结构化结果
- 当 LLM 不输出 tool_use 时，降级到 `parse_analysis_result()` 解析文本（兼容旧模式）

### 1.3.3 DeepSeek tool_use 支持（扩展 `deepseek_client.py`）

**新增方法**：`analyze_with_tools()`

```python
async def analyze_with_tools(
    self,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    config: ProactiveChatConfig,
) -> ToolCallResponse:
```

**请求体变化**：在 `_call_api()` 的 body 中新增 `tools` 字段

```python
body = {
    "model": model,
    "messages": messages,
    "temperature": temperature,
    "max_tokens": max_tokens,
}
if tools:
    body["tools"] = tools
    body["tool_choice"] = "auto"
```

**响应解析**：新增 `ToolCallResponse` 数据类

```python
@dataclass
class ToolCallInfo:
    id: str
    name: str
    arguments: dict
    raw: dict  # 原始 tool_call 对象，用于追加到消息历史

@dataclass
class ToolCallResponse:
    text: str = ""
    tool_calls: list[ToolCallInfo] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
```

**响应解析逻辑**：

```python
data = response.json()
choice = data["choices"][0]
message = choice["message"]

result = ToolCallResponse()
result.text = message.get("content", "") or ""

if message.get("tool_calls"):
    for tc in message["tool_calls"]:
        function = tc.get("function", {})
        args_str = function.get("arguments", "{}")
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}
        result.tool_calls.append(ToolCallInfo(
            id=tc.get("id", ""),
            name=function.get("name", ""),
            arguments=args,
            raw=tc,
        ))

return result
```

### 1.3.4 反思子智能体（集成在 `agent.py`）

**设计思路**：借鉴 MiMo-Code 的 subagent 模式（`actor/spawn.ts`），但极度简化——不需要 Actor 注册表、ForkContext、独立 session，只是一个带独立系统提示词的 LLM 调用。

**核心方法**：

```python
async def _reflect_with_subagent(
    self,
    perception: PerceptionData,
    result: AnalysisResult,
    config: ProactiveChatConfig,
) -> ReflectionResult | None:
```

**反思系统提示词**（`prompts.py` 新增）：

```
你是一个决策反思智能体，负责评估主动对话决策的合理性。

你需要审查以下决策：
- 感知数据：{perception_summary}
- 决策结果：should_trigger={should_trigger}, intent={intent}, confidence={confidence}, reason={reason}

请从以下维度评估：
1. 决策是否与感知数据一致
2. 置信度是否合理（不过高也不过低）
3. 是否存在误触发风险（如对话节奏正常时强行介入）

返回 JSON：
{"verdict": "confirmed 或 vetoed", "reason": "理由", "confidence": 0.0-1.0}
```

**调用方式**：复用 `DeepSeekClient.analyze_with_params()`，使用独立的 max_tokens=200

**超时保护**：`asyncio.wait_for(coro, timeout=15.0)`，超时返回 None（视为 confirmed）

### 1.3.5 事件总线（新文件 `event_bus.py`）

**设计思路**：借鉴 MiMo-Code 的 `bus/index.ts` PubSub 模式，但用 Python asyncio 简化实现。当前 `_broadcast_if_available()` 分散在 agent.py 和 cooldown.py 中，统一到 EventBus。

**核心类**：

```python
@dataclass
class AgentEvent:
    event_type: str
    timestamp: float
    stream_id: str
    data: dict

class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[AgentEvent], Awaitable[None]]] = []
        self._dedup_cache: dict[str, float] = {}  # event_type:stream_id -> last_publish_ts
        self._event_log: deque[AgentEvent] = deque(maxlen=100)

    def subscribe(self, callback: Callable[[AgentEvent], Awaitable[None]]) -> None
    def unsubscribe(self, callback: Callable) -> None
    async def publish(self, event_type: str, stream_id: str, data: dict) -> None
    def get_recent_events(self, limit: int = 50) -> list[AgentEvent]
```

**发布逻辑**：

```python
async def publish(self, event_type: str, stream_id: str, data: dict) -> None:
    # 去重：1秒内同一 event_type+stream_id 不重复发布
    dedup_key = f"{event_type}:{stream_id}"
    now = time.time()
    last_ts = self._dedup_cache.get(dedup_key, 0)
    if now - last_ts < 1.0:
        return
    self._dedup_cache[dedup_key] = now

    event = AgentEvent(event_type=event_type, timestamp=now, stream_id=stream_id, data=data)
    self._event_log.append(event)

    for callback in self._subscribers:
        try:
            await callback(event)
        except Exception:
            pass  # 订阅者异常不影响其他订阅者
```

**与 WebUI 集成**：WebUI 的 `broadcast_event()` 注册为 EventBus 订阅者

```python
# plugin.py on_load 中
async def _webui_subscriber(event: AgentEvent) -> None:
    await self._webui.broadcast_event(event.event_type, {**event.data, "stream_id": event.stream_id})
self._event_bus.subscribe(_webui_subscriber)
```

**替换现有 `_broadcast_if_available()`**：agent.py 和 cooldown.py 中的 `_broadcast_if_available()` 改为调用 `self._event_bus.publish()`

### 1.3.6 上下文压缩（新文件 `context_compressor.py`）

**设计思路**：借鉴 MiMo-Code 的 `compaction.ts`，保留 tail + 摘要策略。

**核心类**：

```python
@dataclass
class ContextSummary:
    stream_id: str
    summary_text: str
    original_message_count: int
    retained_message_count: int
    created_at: float
    token_estimate: int

class ContextCompressor:
    def __init__(self, deepseek_client: DeepSeekClient, data_dir: Path) -> None:
        self._deepseek = deepseek_client
        self._cache_dir = data_dir / "summaries"

    async def get_context(
        self, stream_id: str, messages: list[dict], config: ProactiveChatConfig,
    ) -> tuple[str, bool]:
        """返回 (格式化消息文本, 是否使用了压缩)"""

    async def _compress(self, stream_id: str, old_messages: list[dict], config: ProactiveChatConfig) -> str:
        """LLM 驱动的摘要生成"""

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数（中文约 1.5 字/token，英文约 4 字符/token）"""

    def _get_cache_path(self, stream_id: str) -> Path
    async def _read_cache(self, stream_id: str) -> ContextSummary | None
    async def _write_cache(self, summary: ContextSummary) -> None
    def _is_cache_valid(self, summary: ContextSummary, current_messages: list[dict]) -> bool:
```

**压缩流程**：

1. `get_context()` 接收原始消息列表
2. 估算 token 数，低于阈值直接格式化返回
3. 超过阈值：检查缓存 → 有效则使用缓存摘要 + 最近 N 条消息 → 无效则 LLM 压缩
4. 压缩后缓存到 `data/proactive-chat/summaries/{stream_id}.json`

**缓存失效条件**：最近 N 条消息的 hash 与缓存记录不一致

**压缩提示词**（`prompts.py` 新增）：

```
请将以下对话历史压缩为简洁的摘要，保留关键信息：
- 讨论的主要话题
- 各参与者的立场和观点
- 未解决的问题或待办事项
- 与 bot（{bot_nickname}）相关的提及

对话历史：
{messages_text}

请输出摘要（不超过 300 字）：
```

### 1.3.7 DecisionRecord 扩展（修改 `persistence.py`）

**新增字段**：

```python
@dataclass
class DecisionRecord:
    # ... 现有 16 个字段不变 ...
    react_steps: list[dict] = field(default_factory=list)      # ReActStep 列表
    react_total_steps: int = 0                                   # ReAct 总步数
    reflection_result: dict | None = None                        # ReflectionResult
    context_compressed: bool = False                             # 是否使用压缩上下文
```

**`_fill_record_defaults()` 新增**：

```python
data.setdefault("react_steps", [])
data.setdefault("react_total_steps", 0)
data.setdefault("reflection_result", None)
data.setdefault("context_compressed", False)
```

**`_dict_to_record()` 新增**：

```python
react_steps=data.get("react_steps", []),
react_total_steps=data.get("react_total_steps", 0),
reflection_result=data.get("reflection_result", None),
context_compressed=data.get("context_compressed", False),
```

### 1.3.8 ReActStep 数据类（`agent.py` 新增）

```python
@dataclass
class ReActStep:
    step_index: int = 0
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    tool_error: str = ""
    duration_ms: float = 0.0
```

### 1.3.9 ReflectionResult 数据类（`agent.py` 新增）

```python
@dataclass
class ReflectionResult:
    verdict: str = "confirmed"   # "confirmed" 或 "vetoed"
    reason: str = ""
    confidence: float = 0.0
    error: str = ""
```

### 1.3.10 配置扩展（修改 `config.py`）

**新增配置段**：

```python
class ReActConfig(PluginConfigBase):
    __ui_label__ = "ReAct 循环"
    __ui_icon__ = "refresh-cw"
    __ui_order__ = 11

    react_enabled: bool = Field(default=True, description="是否启用 ReAct 循环（禁用后回退到 v2.1 单次推理模式）")
    max_react_steps: int = Field(default=3, ge=1, le=5, description="ReAct 循环最大步数")
    reflect_subagent_enabled: bool = Field(default=False, description="是否启用反思子智能体")
    reflect_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="反思子智能体启动的置信度阈值")

class ContextCompressConfig(PluginConfigBase):
    __ui_label__ = "上下文压缩"
    __ui_icon__ = "minimize-2"
    __ui_order__ = 12

    compress_enabled: bool = Field(default=True, description="是否启用上下文压缩")
    compress_token_threshold: int = Field(default=4000, ge=1000, le=8000, description="触发压缩的 token 估算阈值")
    compress_retained_messages: int = Field(default=5, ge=2, le=15, description="压缩时保留的最近消息条数")
    compress_max_tokens: int = Field(default=300, ge=100, le=1000, description="压缩 LLM 调用的最大 token 数")
```

**ProactiveChatConfig 新增**：

```python
class ProactiveChatConfig(PluginConfigBase):
    # ... 现有字段不变 ...
    react: ReActConfig = Field(default_factory=ReActConfig)
    context_compress: ContextCompressConfig = Field(default_factory=ContextCompressConfig)
```

**config_version 升级**：`2.1.0` → `3.0.0`

### 1.3.11 提示词扩展（修改 `prompts.py`）

**系统提示词新增 ReAct 工具引导段落**：

```
## 可用工具

你可以使用以下工具获取更多信息来辅助决策：

1. **get_recent_messages**：获取当前聊天流的近期消息（参数：limit，默认 10）
2. **get_cooldown_status**：获取当前聊天流的冷却状态
3. **get_stream_activity**：获取当前聊天流的活跃度指标
4. **search_memory**：检索与关键词相关的记忆（参数：query）

当你收集了足够信息后，**必须**使用 submit_decision 工具提交最终决策。

## 工具使用策略

- 如果初始上下文已足够清晰，可以直接提交决策
- 如果需要更多信息（如不确定对话节奏、需要验证记忆内容），先调用感知工具
- 不要为了使用工具而使用工具，每次工具调用都应有明确目的
```

**反思子智能体提示词**（新增 `REFLECTION_SYSTEM_PROMPT` 和 `REFLECTION_USER_TEMPLATE`）

**压缩提示词**（新增 `COMPRESSION_SYSTEM_PROMPT` 和 `COMPRESSION_USER_TEMPLATE`）

### 1.3.12 decision_loop 重构（修改 `agent.py`）

**核心变化**：`reason()` 调用替换为 `_react_loop()`

```python
# 原有 reason() 调用位置（decision_loop 中约 L359）
# 旧：result = await self.reason(stream_id, perception, config)
# 新：
if config.react.react_enabled:
    result, react_steps = await self._react_loop(stream_id, perception, config, ctx)
else:
    result = await self.reason(stream_id, perception, config)  # v2.1 兼容
    react_steps = []
```

**reflect() 新增字段**：

```python
updates = {
    # ... 现有字段不变 ...
    "react_steps": [asdict(s) for s in react_steps],
    "react_total_steps": len(react_steps),
    "reflection_result": asdict(reflection_result) if reflection_result else None,
    "context_compressed": context_compressed,
}
```

**反思子智能体插入位置**：在 reason/react_loop 之后、act 之前

```python
# reason/react_loop 完成后
reflection_result = None
if (
    config.react.reflect_subagent_enabled
    and result.should_trigger
    and result.confidence >= config.react.reflect_confidence_threshold
):
    reflection_result = await self._reflect_with_subagent(perception, result, config)
    if reflection_result and reflection_result.verdict == "vetoed":
        action_taken = "vetoed_by_reflection"
        # 跳过 act，直接进入 reflect
```

### 1.3.13 WebUI 扩展（修改 `webui.py`）

**决策记录表格新增列**：
- ReAct 步数（`react_total_steps`，v2.1 旧记录显示 `-`）
- 反思结果 badge（`reflection_result.verdict`，无则不显示）
- 压缩标识（`context_compressed`，小图标）

**统计卡片新增**：
- ReAct 平均步数
- 反思否决率

**事件总线集成**：
- WebUI 的 `broadcast_event()` 注册为 EventBus 订阅者
- 新增 `react_step` 和 `react_complete` 事件的 WebSocket 推送

# 2. 接口设计

## 2.1 总体设计

v3.0 不新增外部 API 端点。所有变更在插件内部，WebUI API 复用现有端点，仅扩展响应字段。

## 2.2 接口清单

| 接口 | 变更类型 | 说明 |
|------|----------|------|
| `GET /api/proactive-chat/decisions` | 扩展响应 | 新增 react_steps/react_total_steps/reflection_result/context_compressed 字段 |
| `GET /api/proactive-chat/stats` | 扩展响应 | 新增 react_avg_steps/reflection_veto_rate 字段 |
| `GET /api/proactive-chat/events` | 新增事件 | react_step/react_complete/reflection_result/context_compressed |
| `POST /api/proactive-chat/trigger` | 不变 | - |
| WebSocket 推送 | 扩展事件 | 新增 react_step/react_complete/reflection_result/context_compressed 事件类型 |

# 4. 数据模型

## 4.1 设计目标

1. 向后兼容 v2.1 JSONL 记录格式（新增字段有默认值）
2. 新增 ReAct 循环和反思子智能体的数据结构
3. 上下文压缩摘要独立缓存，不混入决策记录

## 4.2 模型实现

### DecisionRecord（persistence.py，扩展现有）

```python
@dataclass
class DecisionRecord:
    # v2.1 现有字段（16个，不变）
    ts: float = 0.0
    time: str = ""
    stream_id: str = ""
    input_summary: str = ""
    analysis_result: dict = field(default_factory=dict)
    action_taken: str = ""
    error: str = ""
    record_status: str = "completed"
    processing_phase: str = ""
    dedup_key: str = ""
    retry_count: int = 0
    trigger_anomaly: bool = False
    trigger_time: float = 0.0
    duration_ms: float = 0.0
    timing_score: float = 1.0
    # v3.0 新增字段
    react_steps: list[dict] = field(default_factory=list)
    react_total_steps: int = 0
    reflection_result: dict | None = None
    context_compressed: bool = False
```

### ReActStep（agent.py，新增）

```python
@dataclass
class ReActStep:
    step_index: int = 0
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    tool_error: str = ""
    duration_ms: float = 0.0
```

### ReflectionResult（agent.py，新增）

```python
@dataclass
class ReflectionResult:
    verdict: str = "confirmed"
    reason: str = ""
    confidence: float = 0.0
    error: str = ""
```

### ContextSummary（context_compressor.py，新增）

```python
@dataclass
class ContextSummary:
    stream_id: str
    summary_text: str
    original_message_count: int
    retained_message_count: int
    created_at: float
    token_estimate: int
```

### AgentEvent（event_bus.py，新增）

```python
@dataclass
class AgentEvent:
    event_type: str
    timestamp: float
    stream_id: str
    data: dict
```

### ToolCallInfo / ToolCallResponse（deepseek_client.py，新增）

```python
@dataclass
class ToolCallInfo:
    id: str
    name: str
    arguments: dict
    raw: dict

@dataclass
class ToolCallResponse:
    text: str = ""
    tool_calls: list[ToolCallInfo] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
```

### 摘要缓存文件格式（`data/proactive-chat/summaries/{stream_id}.json`）

```json
{
  "stream_id": "xxx",
  "summary_text": "对话摘要...",
  "original_message_count": 25,
  "retained_message_count": 5,
  "created_at": 1719500000.0,
  "token_estimate": 5200,
  "last_message_hash": "abc123"
}
```

`last_message_hash`：保留的最近 N 条消息内容的 hash，用于判断缓存是否失效。