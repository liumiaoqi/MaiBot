# 1. 实现模型

## 1.1 上下文视图

当前插件架构（v3.0）的决策循环为 **ReAct 循环驱动的多轮推理**：

```
perceive → ReAct 循环（LLM ↔ AgentTool 多轮交互）→ [反思子智能体] → act → reflect
```

v3.1 在此基础上新增五大能力模块，不改变核心决策循环流程：

```
perceive（+智能体记忆注入）
  → ReAct 循环（+1M 上下文溢出检测 + 分级剪枝 + DeepSeek v4 适配）
  → [反思子智能体]
  → act
  → reflect
```

核心变化：
- 新增 `overflow_manager.py` 模块，实现 4 级压力模型 + 软/硬剪枝 + 分级压缩
- 新增 `agent_chat.py` 模块，实现 WebUI 智能体对话服务
- 新增 `agent_memory.py` 模块，实现跨决策循环记忆
- 扩展 `deepseek_client.py`，适配 DeepSeek v4 思考模式、JSON Output、strict 模式
- 扩展 `config.py`，新增 4 个配置段
- 扩展 `prompts.py`，新增智能体记忆注入模板、JSON Output 格式样例
- 扩展 `webui.py`，新增智能体对话 API 端点

## 1.2 服务/组件总体架构

```
plugin.py (入口，不变)
  ├── AgentCore (agent.py，扩展 perceive 注入记忆 + reason/react_loop 集成溢出管理)
  │     ├── AgentToolRegistry (agent_tools.py，不变)
  │     ├── EventBus (event_bus.py，新增 context_overflow 事件)
  │     ├── ContextCompressor (context_compressor.py，1M 模式下由 OverflowManager 替代)
  │     ├── OverflowManager (overflow_manager.py，新增)
  │     │     ├── 压力等级计算（借鉴 MiMo-Code overflow.ts）
  │     │     ├── 软剪枝（截断长工具输出，借鉴 MiMo-Code prune.ts level 1）
  │     │     └── 硬剪枝（移除旧工具输出，借鉴 MiMo-Code prune.ts level 2）
  │     └── AgentMemory (agent_memory.py，新增)
  │           └── DecisionRecord 摘要提取 + 衰减
  ├── CooldownManager (cooldown.py，不变)
  ├── DeepSeekClient (deepseek_client.py，扩展 v4 适配)
  │     ├── 思考模式（thinking + reasoning_content 回传）
  │     ├── JSON Output 模式（response_format）
  │     └── strict 模式（beta base_url）
  ├── PersistenceManager (persistence.py，不变)
  ├── WebUIServer (webui.py，扩展智能体对话端点)
  │     └── AgentChatService (agent_chat.py，新增)
  ├── SmartCleaner (smart_cleanup.py，不变)
  └── 新增配置段：
        ├── DeepseekContextConfig（1M 上下文）
        ├── AgentChatConfig（智能体对话）
        ├── DeepseekV4Config（v4 适配）
        └── AgentMemoryConfig（智能体记忆）
```

## 1.3 实现设计文档

### 1.3.1 溢出管理器（新文件 `overflow_manager.py`）

**设计思路**：借鉴 MiMo-Code 的 `overflow.ts` 4 级压力模型和 `prune.ts` 软/硬剪枝策略，适配 proactive-chat 的消息格式（OpenAI Chat Completions 格式的 dict 列表）。

**核心数据类**：

```python
@dataclass
class OverflowState:
    pressure_level: int = 0          # 0/1/2/3
    token_count: int = 0             # 当前 token 估算值
    usable_limit: int = 0            # 可用 token 上限
    ratio: float = 0.0               # token_count / usable_limit
    action_taken: str = "none"       # "none" / "soft_prune" / "hard_prune" / "hard_prune+compress"
```

**核心类**：

```python
class OverflowManager:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
        data_dir: Path,
    ) -> None

    async def get_managed_context(
        self,
        stream_id: str,
        messages: list[dict],
        config: ProactiveChatConfig,
    ) -> tuple[list[dict], OverflowState]:
        """根据压力等级返回管理后的消息列表和溢出状态。
        在消息副本上操作，不修改原始消息。"""

    def compute_pressure_level(
        self,
        token_count: int,
        usable_limit: int,
        config: ProactiveChatConfig,
    ) -> int:
        """计算压力等级（0/1/2/3）。"""

    def soft_prune(
        self,
        messages: list[dict],
        threshold: int,
    ) -> list[dict]:
        """软剪枝：截断工具输出消息中超过阈值的字符。"""

    def hard_prune(
        self,
        messages: list[dict],
        usable_limit: int,
        config: ProactiveChatConfig,
    ) -> list[dict]:
        """硬剪枝：移除最早的工具调用-响应消息对。"""

    async def _compress_with_llm(
        self,
        stream_id: str,
        messages: list[dict],
        config: ProactiveChatConfig,
    ) -> str:
        """LLM 摘要压缩（复用 ContextCompressor 的压缩逻辑）。"""

    @staticmethod
    def estimate_messages_tokens(messages: list[dict]) -> int:
        """估算消息列表的 token 数。"""
```

**压力等级计算**（借鉴 MiMo-Code `overflow.ts` `pressureLevel()`）：

```python
def compute_pressure_level(self, token_count: int, usable_limit: int, config: ProactiveChatConfig) -> int:
    if not config.deepseek_context.context_1m_enabled:
        return 0
    if usable_limit == 0:
        return 0
    ratio = token_count / usable_limit
    level_2_ratio = config.deepseek_context.pressure_level_2_ratio  # 默认 0.75
    level_3_ratio = config.deepseek_context.pressure_level_3_ratio  # 默认 0.90
    if ratio < 0.50:
        return 0
    if ratio < level_2_ratio:
        return 1
    if ratio < level_3_ratio:
        return 2
    return 3
```

**软剪枝规则**（借鉴 MiMo-Code `prune.ts` level 1 `soft-trim`）：

```python
def soft_prune(self, messages: list[dict], threshold: int) -> list[dict]:
    result = []
    for msg in messages:
        msg_copy = dict(msg)
        # 仅截断 role=tool 的消息内容
        if msg_copy.get("role") == "tool":
            content = msg_copy.get("content", "")
            if isinstance(content, str) and len(content) > threshold:
                msg_copy["content"] = content[:threshold] + "[已截断]"
        result.append(msg_copy)
    return result
```

**硬剪枝规则**（借鉴 MiMo-Code `prune.ts` level 2 `hard-prune`）：

```python
def hard_prune(self, messages, usable_limit, config) -> list[dict]:
    retained_count = config.context_compress.compress_retained_messages
    # 从最早的消息开始，移除完整的工具调用-响应消息对
    # 保留最近 N 条消息不被剪枝
    # 迭代移除直到压力等级降至 3 以下或消息耗尽
```

**`get_managed_context()` 主流程**：

```python
async def get_managed_context(self, stream_id, messages, config):
    if not config.deepseek_context.context_1m_enabled:
        # 非 1M 模式，返回原始消息副本
        return list(messages), OverflowState()

    usable_limit = config.deepseek_context.context_max_tokens - config.analysis.max_analysis_tokens
    token_count = self.estimate_messages_tokens(messages)
    pressure = self.compute_pressure_level(token_count, usable_limit, config)

    state = OverflowState(
        pressure_level=pressure,
        token_count=token_count,
        usable_limit=usable_limit,
        ratio=token_count / usable_limit if usable_limit > 0 else 0.0,
    )

    if pressure <= 1:
        state.action_taken = "none"
        return list(messages), state

    # 等级 2：软剪枝
    if pressure == 2:
        pruned = self.soft_prune(messages, config.deepseek_context.soft_prune_threshold)
        state.action_taken = "soft_prune"
        self._publish_overflow_event(stream_id, state)
        return pruned, state

    # 等级 3：硬剪枝
    pruned = self.hard_prune(messages, usable_limit, config)
    new_count = self.estimate_messages_tokens(pruned)
    new_pressure = self.compute_pressure_level(new_count, usable_limit, config)

    if new_pressure >= 3:
        # 硬剪枝后仍溢出，触发 LLM 摘要
        summary = await self._compress_with_llm(stream_id, pruned, config)
        if summary:
            retained_count = config.context_compress.compress_retained_messages
            recent = pruned[-retained_count:] if len(pruned) > retained_count else pruned
            result = [{"role": "system", "content": f"[对话历史摘要]\n{summary}"}] + recent
            state.action_taken = "hard_prune+compress"
            state.token_count = self.estimate_messages_tokens(result)
            state.pressure_level = self.compute_pressure_level(state.token_count, usable_limit, config)
            self._publish_overflow_event(stream_id, state)
            return result, state
        # 摘要失败，降级为硬剪枝结果
        state.action_taken = "hard_prune"
        state.token_count = new_count
        state.pressure_level = new_pressure
    else:
        state.action_taken = "hard_prune"
        state.token_count = new_count
        state.pressure_level = new_pressure

    self._publish_overflow_event(stream_id, state)
    return pruned, state
```

**与现有模块的集成点**：

- `AgentCore._react_loop()` 中，在调用 `analyze_with_tools()` 前调用 `OverflowManager.get_managed_context()` 管理消息列表
- `AgentCore.reason()` 中，在调用 `analyze()` 前同样处理
- 非 1M 模式下，`OverflowManager.get_managed_context()` 直接返回原始消息，不影响现有 `ContextCompressor` 的逻辑

### 1.3.2 智能体对话服务（新文件 `agent_chat.py`）

**设计思路**：实现轻量级 WebUI 智能体对话功能，纯文本对话（无 ReAct 工具调用），内存级会话管理。

**核心数据类**：

```python
@dataclass
class AgentChatMessage:
    role: str          # "user" / "assistant" / "system"
    content: str       # 最大 4000 字符
    timestamp: float   # Unix 时间戳（毫秒）

@dataclass
class AgentChatSession:
    session_id: str                # UUID 格式
    messages: list[AgentChatMessage]
    created_at: float
    last_active_at: float
    token_estimate: int
    stream_context_id: str         # 注入的聊天流 ID，空表示无注入
    is_responding: bool = False    # 是否正在响应中（防并发）
```

**核心类**：

```python
class AgentChatService:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
        persistence_manager: PersistenceManager,
    ) -> None:
        self._deepseek = deepseek_client
        self._event_bus = event_bus
        self._persistence = persistence_manager
        self._sessions: dict[str, AgentChatSession] = {}

    async def create_session(
        self,
        stream_context_id: str = "",
    ) -> AgentChatSession:
        """创建新会话，可选注入聊天流上下文。"""

    async def send_message(
        self,
        session_id: str,
        user_content: str,
        config: ProactiveChatConfig,
        bot_nickname: str = "",
        personality: str = "",
        alias_names: list[str] | None = None,
        reply_style: str = "",
        custom_prompt: str = "",
    ) -> AgentChatMessage:
        """发送用户消息并获取智能体响应。"""

    async def clear_session(self, session_id: str) -> bool:
        """清除指定会话。"""

    def get_session(self, session_id: str) -> AgentChatSession | None:
        """获取会话信息。"""

    def list_sessions(self) -> list[dict]:
        """列出所有活跃会话。"""

    async def _inject_stream_context(
        self,
        session: AgentChatSession,
        stream_id: str,
    ) -> None:
        """注入指定聊天流的近期消息作为上下文。"""

    def _auto_cleanup_if_needed(
        self,
        session: AgentChatSession,
        config: ProactiveChatConfig,
    ) -> None:
        """会话 token 超过阈值时自动清除早期消息。"""
```

**`send_message()` 核心流程**：

```python
async def send_message(self, session_id, user_content, config, **kwargs):
    # 1. 查找或创建会话
    session = self._sessions.get(session_id)
    if not session:
        session = await self.create_session()
        session_id = session.session_id

    # 2. 并发保护
    if session.is_responding:
        raise RuntimeError("会话正在响应中，请等待完成")

    # 3. 追加用户消息
    user_msg = AgentChatMessage(role="user", content=user_content[:4000], timestamp=time.time() * 1000)
    session.messages.append(user_msg)

    # 4. 自动清理（token > 80% 上限）
    self._auto_cleanup_if_needed(session, config)

    # 5. 构建系统提示词（复用 build_system_prompt，react_enabled=False）
    system_prompt = build_system_prompt(
        bot_nickname=kwargs.get("bot_nickname", ""),
        alias_names=kwargs.get("alias_names"),
        personality=kwargs.get("personality", ""),
        reply_style=kwargs.get("reply_style", ""),
        custom_prompt=kwargs.get("custom_prompt", ""),
        react_enabled=False,  # 智能体对话不启用 ReAct 工具
    )

    # 6. 构建 API 消息列表
    api_messages = [{"role": "system", "content": system_prompt}]
    for msg in session.messages:
        api_messages.append({"role": msg.role, "content": msg.content})

    # 7. 调用 LLM（不携带 tools 参数）
    session.is_responding = True
    try:
        response_text = await self._deepseek.analyze_with_params(
            system_prompt=system_prompt,
            user_prompt=user_content[:4000],
            model=config.deepseek.deepseek_model,
            temperature=config.agent_chat.chat_temperature,
            max_tokens=config.agent_chat.chat_max_tokens,
        )
    finally:
        session.is_responding = False

    # 8. 追加助手响应
    assistant_msg = AgentChatMessage(role="assistant", content=response_text, timestamp=time.time() * 1000)
    session.messages.append(assistant_msg)
    session.last_active_at = time.time()
    session.token_estimate = self._estimate_session_tokens(session)

    # 9. 广播事件
    self._event_bus.publish("agent_chat_response", session_id, {
        "session_id": session_id,
        "content": response_text,
        "token_estimate": session.token_estimate,
    })

    return assistant_msg
```

**与现有模块的集成点**：

- `WebUIServer` 新增 API 端点调用 `AgentChatService`
- `AgentChatService` 复用 `build_system_prompt()` 构建系统提示词
- `AgentChatService` 复用 `DeepSeekClient.analyze_with_params()` 调用 LLM
- `AgentChatService` 通过 `EventBus` 广播 `agent_chat_response` 事件
- `AgentChatService` 通过 `PersistenceManager` 读取聊天流上下文

### 1.3.3 智能体记忆模块（新文件 `agent_memory.py`）

**设计思路**：从 DecisionRecord JSONL 文件中提取同一聊天流的历史决策摘要，在 perceive 阶段注入到用户提示词中。不依赖 A_Memorix，仅使用插件自身的 DecisionRecord 作为记忆源。

**核心数据类**：

```python
@dataclass
class AgentMemoryEntry:
    chat_stream_id: str     # 聊天流唯一标识
    summary: str            # 决策摘要文本，最大 500 字符
    timestamp: float        # 决策时间戳（毫秒）
    weight: float           # 记忆权重 0.0-1.0（基于衰减天数计算）
    trigger_reason: str     # 触发原因，最大 200 字符
    action_taken: str       # 采取行动，最大 200 字符
```

**核心类**：

```python
class AgentMemory:
    def __init__(
        self,
        persistence_manager: PersistenceManager,
    ) -> None:
        self._persistence = persistence_manager

    async def get_memories(
        self,
        stream_id: str,
        config: ProactiveChatConfig,
    ) -> list[AgentMemoryEntry]:
        """获取指定聊天流的历史决策记忆。"""

    def format_memories_for_prompt(
        self,
        memories: list[AgentMemoryEntry],
    ) -> str:
        """将记忆列表格式化为可注入提示词的文本。"""

    def _compute_weight(
        self,
        timestamp: float,
        decay_days: int,
    ) -> float:
        """基于衰减天数计算记忆权重。"""

    def _extract_summary(
        self,
        record: DecisionRecord,
    ) -> AgentMemoryEntry | None:
        """从 DecisionRecord 提取记忆摘要。"""
```

**`get_memories()` 核心流程**：

```python
async def get_memories(self, stream_id, config):
    if not config.agent_memory.memory_enabled:
        return []

    # 1. 读取该聊天流的历史 DecisionRecord
    records, _ = await self._persistence.query_decisions(
        stream_id=stream_id,
        limit=config.agent_memory.memory_max_entries * 2,  # 多读一些，过滤后可能不足
    )

    if not records:
        return []

    # 2. 按衰减天数过滤
    now = time.time()
    decay_days = config.agent_memory.memory_decay_days
    cutoff = now - decay_days * 86400

    entries = []
    for rec in records:
        if rec.ts < cutoff:
            continue  # 已衰减
        entry = self._extract_summary(rec)
        if entry:
            entries.append(entry)

    # 3. 按容量截取（最近的优先）
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    entries = entries[:config.agent_memory.memory_max_entries]

    # 4. 计算权重
    for entry in entries:
        entry.weight = self._compute_weight(entry.timestamp / 1000, decay_days)

    return entries
```

**`_extract_summary()` 提取逻辑**：

```python
def _extract_summary(self, record):
    ar = record.analysis_result or {}
    intent = ar.get("intent", "")
    reason = ar.get("reason", "")
    confidence = ar.get("confidence", 0.0)
    should_trigger = ar.get("should_trigger", False)

    if not intent and not reason:
        return None

    summary = f"意图: {intent}，原因: {reason}，置信度: {confidence:.2f}，结果: {'触发' if should_trigger else '未触发'}"
    return AgentMemoryEntry(
        chat_stream_id=record.stream_id,
        summary=summary[:500],
        timestamp=record.ts * 1000,
        weight=1.0,
        trigger_reason=reason[:200],
        action_taken=record.action_taken[:200],
    )
```

**与现有模块的集成点**：

- `AgentCore.perceive()` 中，在感知阶段调用 `AgentMemory.get_memories()` 获取记忆
- 记忆注入到用户提示词中，格式化为 `MEMORY_HISTORY_TEMPLATE` 模板
- 仅读取 `PersistenceManager`，不写入新字段到 DecisionRecord

### 1.3.4 DeepSeek v4 适配（扩展 `deepseek_client.py`）

**设计思路**：在现有 `DeepSeekClient` 基础上新增思考模式、JSON Output、strict 模式支持，通过配置开关控制，不影响现有调用行为。

**新增数据类**：

```python
@dataclass
class ThinkingResponse:
    reasoning_content: str = ""   # 思维链内容
    content: str = ""             # 最终回答
    tool_calls: list[ToolCallInfo] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
```

**新增方法**：

```python
class DeepSeekClient:
    # ... 现有方法不变 ...

    async def analyze_with_thinking(
        self,
        system_prompt: str,
        messages: list[dict],
        config: ProactiveChatConfig,
        tools: list[dict] | None = None,
        is_tool_call_round: bool = False,
    ) -> ThinkingResponse:
        """支持思考模式的 LLM 调用。"""

    async def analyze_with_json_output(
        self,
        system_prompt: str,
        user_prompt: str,
        config: ProactiveChatConfig,
        json_format_example: str = "",
    ) -> str:
        """支持 JSON Output 模式的 LLM 调用。"""
```

**思考模式请求体构建**：

```python
async def analyze_with_thinking(self, system_prompt, messages, config, tools=None, is_tool_call_round=False):
    if not self._api_key_available or not self._client:
        raise RuntimeError("DeepSeek API Key 不可用")

    v4_config = config.deepseek_v4
    model = v4_config.default_model if v4_config.default_model != "deepseek-chat" else config.deepseek.deepseek_model

    url = f"{self._base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {self._api_key}",
        "Content-Type": "application/json",
    }

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    body: dict[str, Any] = {
        "model": model,
        "messages": full_messages,
        "max_tokens": config.analysis.max_analysis_tokens,
    }

    # 思考模式：添加 thinking 参数，移除 temperature/top_p
    if v4_config.thinking_enabled:
        body["extra_body"] = {"thinking": {"type": "enabled"}}
        # reasoning_effort：Agent 类请求自动设为 max
        effort = "max" if is_tool_call_round else v4_config.reasoning_effort
        body["extra_body"]["thinking"]["reasoning_effort"] = effort
        # 不传递 temperature 和 top_p
    else:
        body["temperature"] = config.deepseek.deepseek_temperature

    # 工具调用
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    # strict 模式
    if v4_config.strict_mode_enabled and tools:
        body["base_url"] = "https://api.deepseek.com/beta"
        for tool in tools:
            tool_def = tool.get("function", {})
            tool_def["strict"] = True
            params = tool_def.get("parameters", {})
            params["additionalProperties"] = False

    # reasoning_content 回传：在消息中保留工具调用轮次的 reasoning_content
    # 由调用方（AgentCore）在构建 messages 时处理

    response = await self._client.post(url, json=body, headers=headers)
    # ... 错误处理同现有逻辑 ...

    data = response.json()
    message = data["choices"][0]["message"]

    result = ThinkingResponse()
    result.reasoning_content = message.get("reasoning_content", "") or ""
    result.content = str(message.get("content", "") or "").strip()

    if message.get("tool_calls"):
        for tc in message["tool_calls"]:
            # ... 同现有 ToolCallInfo 解析逻辑 ...
            result.tool_calls.append(ToolCallInfo(...))

    return result
```

**reasoning_content 回传机制**：

在 `AgentCore._react_loop()` 中，当思考模式启用时，工具调用轮次返回的 `reasoning_content` 需要在后续请求中回传。实现方式：

```python
# 在 _react_loop 中追加 assistant 消息时
if config.deepseek_v4.thinking_enabled and response.reasoning_content:
    messages.append({
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call.raw],
        "reasoning_content": response.reasoning_content,  # 回传思维链
    })
else:
    messages.append({
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call.raw],
    })
```

**JSON Output 模式**：

```python
async def analyze_with_json_output(self, system_prompt, user_prompt, config, json_format_example=""):
    body = {
        "model": config.deepseek_v4.default_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.deepseek.deepseek_temperature,
        "max_tokens": config.analysis.max_analysis_tokens,
        "response_format": {"type": "json_object"},
    }

    # 重试逻辑：空 content 重试最多 2 次
    for attempt in range(3):
        response = await self._client.post(url, json=body, headers=headers)
        data = response.json()
        content = data["choices"][0]["message"].get("content", "") or ""
        if content.strip():
            return content.strip()
        if attempt < 2:
            logger.warning("[proactive-chat] JSON Output 返回空 content，第 %d 次重试", attempt + 1)

    # 重试耗尽，降级为普通文本模式
    logger.warning("[proactive-chat] JSON Output 重试耗尽，降级为普通文本模式")
    del body["response_format"]
    response = await self._client.post(url, json=body, headers=headers)
    data = response.json()
    return str(data["choices"][0]["message"].get("content", "")).strip()
```

**旧模型名称兼容**：

```python
# 在 _call_api / _call_api_with_tools / analyze_with_thinking 中
if model == "deepseek-chat":
    logger.warning("[proactive-chat] deepseek-chat 模型名称已弃用，建议更新为 deepseek-v4-flash")
```

**与现有模块的集成点**：

- `AgentCore._react_loop()` 中，当 `config.deepseek_v4.thinking_enabled` 时调用 `analyze_with_thinking()` 替代 `analyze_with_tools()`
- `AgentCore.reason()` 中，当 `config.deepseek_v4.json_output_enabled` 时调用 `analyze_with_json_output()` 替代 `analyze()`
- `ContextCompressor._compress()` 和 `AgentCore._reflect_with_subagent()` 不受影响（使用 `analyze_with_params()`，不涉及思考模式）

### 1.3.5 配置扩展（修改 `config.py`）

**新增 4 个配置段**：

```python
class DeepseekContextConfig(PluginConfigBase):
    __ui_label__ = "1M 上下文"
    __ui_icon__ = "maximize"
    __ui_order__ = 13

    context_1m_enabled: bool = Field(
        default=False,
        description="是否启用 1M 上下文模式",
    )
    soft_prune_threshold: int = Field(
        default=500, ge=100, le=2000,
        description="软剪枝的字符截断阈值",
    )
    pressure_level_2_ratio: float = Field(
        default=0.75, ge=0.5, le=0.9,
        description="压力等级 2 的比值阈值",
    )
    pressure_level_3_ratio: float = Field(
        default=0.90, ge=0.75, le=0.98,
        description="压力等级 3 的比值阈值",
    )
    context_max_tokens: int = Field(
        default=1000000,
        description="1M 模式下的最大上下文 token 数",
    )


class AgentChatConfig(PluginConfigBase):
    __ui_label__ = "智能体对话"
    __ui_icon__ = "message-circle"
    __ui_order__ = 14

    agent_chat_enabled: bool = Field(
        default=False,
        description="是否启用 WebUI 智能体对话",
    )
    chat_max_tokens: int = Field(
        default=500, ge=100, le=2000,
        description="智能体对话 LLM 调用的最大 token 数",
    )
    chat_max_sessions: int = Field(
        default=5, ge=1, le=20,
        description="最大同时活跃会话数",
    )
    chat_session_token_limit: int = Field(
        default=800000, ge=100000, le=900000,
        description="会话自动清除的 token 阈值",
    )
    chat_temperature: float = Field(
        default=0.7, ge=0.0, le=2.0,
        description="智能体对话的 LLM 温度",
    )


class DeepseekV4Config(PluginConfigBase):
    __ui_label__ = "DeepSeek v4"
    __ui_icon__ = "sparkles"
    __ui_order__ = 15

    thinking_enabled: bool = Field(
        default=False,
        description="是否启用 DeepSeek v4 思考模式",
    )
    reasoning_effort: str = Field(
        default="high",
        description="思考模式强度，可选 high 或 max",
        json_schema_extra={"options": ["high", "max"]},
    )
    json_output_enabled: bool = Field(
        default=True,
        description="是否启用 JSON Output 模式（决策分析调用）",
    )
    default_model: str = Field(
        default="deepseek-v4-flash",
        description="默认模型名称",
        json_schema_extra={"options": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"]},
    )
    strict_mode_enabled: bool = Field(
        default=False,
        description="是否启用 strict 模式（Beta）",
    )


class AgentMemoryConfig(PluginConfigBase):
    __ui_label__ = "智能体记忆"
    __ui_icon__ = "brain"
    __ui_order__ = 16

    memory_enabled: bool = Field(
        default=False,
        description="是否启用智能体记忆",
    )
    memory_decay_days: int = Field(
        default=7, ge=1, le=90,
        description="记忆衰减天数",
    )
    memory_max_entries: int = Field(
        default=10, ge=1, le=50,
        description="单次注入记忆条数上限",
    )
```

**ProactiveChatConfig 新增字段**：

```python
class ProactiveChatConfig(PluginConfigBase):
    # ... 现有字段不变 ...
    deepseek_context: DeepseekContextConfig = Field(default_factory=DeepseekContextConfig)
    agent_chat: AgentChatConfig = Field(default_factory=AgentChatConfig)
    deepseek_v4: DeepseekV4Config = Field(default_factory=DeepseekV4Config)
    agent_memory: AgentMemoryConfig = Field(default_factory=AgentMemoryConfig)
```

**config_version 升级**：`3.0.0` → `3.1.0`

### 1.3.6 提示词扩展（修改 `prompts.py`）

**新增智能体记忆注入模板**：

```python
MEMORY_HISTORY_TEMPLATE = """[历史决策记忆] 以下是该聊天流的历史决策记录摘要，供你参考：

{memory_entries}

注意：这些是历史决策记录，仅作为上下文参考，不要被过去的决策过度影响当前判断。"""

MEMORY_ENTRY_TEMPLATE = "- {time}：{summary}（行动: {action_taken}，权重: {weight:.1f}）"
```

**JSON Output 格式样例（追加到系统提示词末尾）**：

```python
JSON_OUTPUT_HINT = """

## 输出格式约束

你的输出必须是合法的 JSON 格式，严格遵循以下结构：
{{
  "should_trigger": bool,
  "intent": "意图标签",
  "reason": "原因描述",
  "confidence": float,
  "timing_score": float
}}"""
```

**`build_system_prompt()` 扩展**：

```python
def build_system_prompt(
    bot_nickname: str = "",
    alias_names: list[str] | None = None,
    personality: str = "",
    reply_style: str = "",
    custom_prompt: str = "",
    react_enabled: bool = True,
    json_output_enabled: bool = False,  # 新增参数
) -> str:
    # ... 现有逻辑不变 ...
    json_section = JSON_OUTPUT_HINT if json_output_enabled else ""
    return AGENT_SYSTEM_PROMPT.format(...) + react_section + json_section
```

### 1.3.7 AgentCore 集成变更（修改 `agent.py`）

**perceive 阶段新增智能体记忆注入**：

```python
async def perceive(self, stream_id, ctx, config):
    perception = PerceptionData()
    # ... 现有逻辑不变 ...

    # 智能体记忆注入（新增）
    if config.agent_memory.memory_enabled and self._agent_memory is not None:
        memories = await self._agent_memory.get_memories(stream_id, config)
        if memories:
            perception.memory_history = self._agent_memory.format_memories_for_prompt(memories)

    return perception
```

**PerceptionData 新增字段**：

```python
@dataclass
class PerceptionData:
    recent_messages: list[dict] = field(default_factory=list)
    silence_signal: bool = False
    silence_seconds: int = 0
    missed_reply_signal: bool = False
    memory_result: str = ""
    message_summary: str = ""
    memory_history: str = ""  # 新增：智能体历史决策记忆
```

**reason() 方法集成 JSON Output**：

```python
async def reason(self, stream_id, perception, config):
    # ... 现有逻辑 ...
    system_prompt, user_prompt = self._build_prompts(perception, config)

    # JSON Output 模式
    if config.deepseek_v4.json_output_enabled:
        raw_response = await self._deepseek.analyze_with_json_output(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            config=config,
        )
    else:
        raw_response = await self._deepseek.analyze(system_prompt, user_prompt, config)

    result = self.parse_analysis_result(raw_response)
    # ... 其余逻辑不变 ...
```

**_react_loop() 方法集成思考模式 + 溢出管理**：

```python
async def _react_loop(self, stream_id, perception, config, ctx):
    # ... 现有初始化逻辑 ...

    user_prompt = ANALYSIS_USER_TEMPLATE.format(...)
    messages: list[dict] = [{"role": "user", "content": user_prompt}]

    # 溢出管理（新增）
    if self._overflow_manager is not None and config.deepseek_context.context_1m_enabled:
        messages, overflow_state = await self._overflow_manager.get_managed_context(
            stream_id, messages, config,
        )
        context_compressed = overflow_state.action_taken != "none"

    tools = self._tool_registry.get_all_definitions()

    for step in range(1, max_steps + 1):
        # 思考模式分支（新增）
        if config.deepseek_v4.thinking_enabled:
            response = await self._deepseek.analyze_with_thinking(
                system_prompt, messages, config, tools=tools,
                is_tool_call_round=(step > 1),  # 非首轮自动设为 max
            )
            # reasoning_content 处理
            if response.reasoning_content:
                logger.debug("[proactive-chat] 思考模式 reasoning_content: %.200s", response.reasoning_content[:200])

            if not response.has_tool_calls:
                result = self.parse_analysis_result(response.content)
                return result, react_steps

            for tool_call in response.tool_calls:
                # ... 同现有逻辑 ...
                # 追加 assistant 消息时回传 reasoning_content
                assistant_msg = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call.raw],
                }
                if response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                messages.append(assistant_msg)
                # ... 追加 tool result 消息 ...
        else:
            # 现有 analyze_with_tools 逻辑不变
            response = await self._deepseek.analyze_with_tools(
                system_prompt, messages, tools, config,
            )
            # ... 现有逻辑 ...

    # ... 其余逻辑不变 ...
```

**AgentCore.__init__ 新增依赖注入**：

```python
class AgentCore:
    def __init__(self, deepseek_client, persistence_manager, cooldown_manager):
        # ... 现有字段不变 ...
        self._overflow_manager: OverflowManager | None = None  # 新增
        self._agent_memory: AgentMemory | None = None          # 新增
        self._agent_chat_service: AgentChatService | None = None  # 新增
```

### 1.3.8 WebUI 扩展（修改 `webui.py`）

**新增 API 端点**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/proactive-chat/agent/chat/sessions` | GET | 列出所有活跃会话 |
| `/api/proactive-chat/agent/chat/sessions` | POST | 创建新会话 |
| `/api/proactive-chat/agent/chat/send` | POST | 发送消息并获取响应 |
| `/api/proactive-chat/agent/chat/sessions/{id}/clear` | POST | 清除指定会话 |

**端点实现**：

```python
async def _handle_agent_chat_sessions(self, request: web.Request) -> web.Response:
    """GET /api/proactive-chat/agent/chat/sessions"""
    if not self._agent_chat_service:
        return web.json_response({"success": False, "error": "智能体对话服务未启用"})
    sessions = self._agent_chat_service.list_sessions()
    return web.json_response({"success": True, "sessions": sessions})

async def _handle_agent_chat_create(self, request: web.Request) -> web.Response:
    """POST /api/proactive-chat/agent/chat/sessions"""
    if not self._agent_chat_service:
        return web.json_response({"success": False, "error": "智能体对话服务未启用"})
    body = await request.json()
    stream_context_id = body.get("stream_context_id", "")
    session = await self._agent_chat_service.create_session(stream_context_id)
    return web.json_response({"success": True, "session_id": session.session_id})

async def _handle_agent_chat_send(self, request: web.Request) -> web.Response:
    """POST /api/proactive-chat/agent/chat/send"""
    if not self._agent_chat_service:
        return web.json_response({"success": False, "error": "智能体对话服务未启用"})
    body = await request.json()
    session_id = body.get("session_id", "")
    content = body.get("content", "")
    if not content:
        return web.json_response({"success": False, "error": "消息内容不能为空"})
    config = self._config_getter() if self._config_getter else None
    if not config:
        return web.json_response({"success": False, "error": "配置不可用"})
    try:
        response_msg = await self._agent_chat_service.send_message(
            session_id=session_id,
            user_content=content,
            config=config,
            bot_nickname=self._agent._bot_nickname if self._agent else "",
            personality=self._agent._personality if self._agent else "",
            alias_names=self._agent._alias_names if self._agent else None,
            reply_style=self._agent._reply_style if self._agent else "",
            custom_prompt=config.prompt.custom_prompt,
        )
        session = self._agent_chat_service.get_session(session_id) or self._agent_chat_service.get_session(
            next(s.session_id for s in self._agent_chat_service._sessions.values()
                 if s.messages and s.messages[-1] is response_msg)
        )
        return web.json_response({
            "success": True,
            "content": response_msg.content,
            "session_id": session.session_id if session else session_id,
            "token_estimate": session.token_estimate if session else 0,
        })
    except RuntimeError as e:
        return web.json_response({"success": False, "error": str(e)})

async def _handle_agent_chat_clear(self, request: web.Request) -> web.Response:
    """POST /api/proactive-chat/agent/chat/sessions/{id}/clear"""
    if not self._agent_chat_service:
        return web.json_response({"success": False, "error": "智能体对话服务未启用"})
    session_id = request.match_info.get("id", "")
    ok = await self._agent_chat_service.clear_session(session_id)
    return web.json_response({"success": ok})
```

**路由注册（在 `start()` 方法中）**：

```python
# 智能体对话端点
self._app.router.add_get("/api/proactive-chat/agent/chat/sessions", self._handle_agent_chat_sessions)
self._app.router.add_post("/api/proactive-chat/agent/chat/sessions", self._handle_agent_chat_create)
self._app.router.add_post("/api/proactive-chat/agent/chat/send", self._handle_agent_chat_send)
self._app.router.add_post("/api/proactive-chat/agent/chat/sessions/{id}/clear", self._handle_agent_chat_clear)
```

**WebSocket 新增事件类型**：

- `agent_chat_response`：智能体对话响应
- `context_overflow`：上下文溢出状态变更

**统计卡片新增**：

- 1M 上下文压力等级指示器
- 智能体记忆条数

### 1.3.9 EventBus 新增事件类型

| 事件类型 | 数据字段 | 触发时机 |
|---------|---------|---------|
| `context_overflow` | `pressure_level`, `action_taken`, `token_count`, `usable_limit`, `ratio` | 溢出检测执行剪枝/压缩时 |
| `agent_chat_response` | `session_id`, `content`, `token_estimate` | 智能体对话响应完成时 |
| `agent_chat_session_created` | `session_id`, `stream_context_id` | 智能体对话会话创建时 |

# 2. 接口设计

## 2.1 总体设计

v3.1 新增 WebUI 智能体对话 API 端点，其余变更在插件内部。所有新增功能默认关闭，通过配置项启用。

## 2.2 接口清单

| 接口 | 变更类型 | 说明 |
|------|----------|------|
| `GET /api/proactive-chat/agent/chat/sessions` | 新增 | 列出智能体对话活跃会话 |
| `POST /api/proactive-chat/agent/chat/sessions` | 新增 | 创建智能体对话会话 |
| `POST /api/proactive-chat/agent/chat/send` | 新增 | 发送智能体对话消息 |
| `POST /api/proactive-chat/agent/chat/sessions/{id}/clear` | 新增 | 清除智能体对话会话 |
| `GET /api/proactive-chat/decisions` | 扩展响应 | 无新增字段（v3.1 不新增 DecisionRecord 字段） |
| `GET /api/proactive-chat/stats` | 扩展响应 | 新增 `overflow_stats` 和 `memory_stats` 字段 |
| `GET /api/proactive-chat/events` | 新增事件 | `context_overflow` / `agent_chat_response` / `agent_chat_session_created` |
| WebSocket 推送 | 扩展事件 | 新增 `context_overflow` / `agent_chat_response` 事件类型 |

### 2.2.1 创建智能体对话会话

**请求**：`POST /api/proactive-chat/agent/chat/sessions`

```json
{
  "stream_context_id": "可选，注入聊天流 ID"
}
```

**响应**：

```json
{
  "success": true,
  "session_id": "uuid-string"
}
```

### 2.2.2 发送智能体对话消息

**请求**：`POST /api/proactive-chat/agent/chat/send`

```json
{
  "session_id": "会话 ID，不存在则自动创建",
  "content": "用户消息内容"
}
```

**响应**：

```json
{
  "success": true,
  "content": "智能体响应文本",
  "session_id": "会话 ID",
  "token_estimate": 1234
}
```

### 2.2.3 统计接口扩展

**响应新增字段**：

```json
{
  "overflow_stats": {
    "1m_enabled": true,
    "current_pressure_level": 0,
    "total_soft_prunes": 0,
    "total_hard_prunes": 0,
    "total_compressions": 0
  },
  "memory_stats": {
    "memory_enabled": true,
    "total_memories_loaded": 0,
    "avg_memory_entries_per_stream": 0.0
  }
}
```

# 4. 数据模型

## 4.1 设计目标

1. 向后兼容 v3.0 的所有配置格式（新增配置段有默认值）
2. 向后兼容 v3.0 的 DecisionRecord 格式（不新增字段）
3. 溢出状态通过事件总线广播，不持久化到决策记录
4. 智能体对话会话仅保存在内存中，重启后清除
5. 智能体记忆仅读取 DecisionRecord，不写入新字段

## 4.2 模型实现

### OverflowState（overflow_manager.py，新增）

```python
@dataclass
class OverflowState:
    pressure_level: int = 0          # 0/1/2/3
    token_count: int = 0             # 当前 token 估算值
    usable_limit: int = 0            # 可用 token 上限
    ratio: float = 0.0               # token_count / usable_limit
    action_taken: str = "none"       # "none" / "soft_prune" / "hard_prune" / "hard_prune+compress"
```

### AgentChatMessage（agent_chat.py，新增）

```python
@dataclass
class AgentChatMessage:
    role: str          # "user" / "assistant" / "system"
    content: str       # 最大 4000 字符
    timestamp: float   # Unix 时间戳（毫秒）
```

### AgentChatSession（agent_chat.py，新增）

```python
@dataclass
class AgentChatSession:
    session_id: str                # UUID 格式字符串
    messages: list[AgentChatMessage]
    created_at: float              # Unix 时间戳
    last_active_at: float          # Unix 时间戳
    token_estimate: int            # 当前会话 token 估算值
    stream_context_id: str         # 注入的聊天流 ID，空表示无注入
    is_responding: bool = False    # 是否正在响应中
```

### AgentMemoryEntry（agent_memory.py，新增）

```python
@dataclass
class AgentMemoryEntry:
    chat_stream_id: str     # 聊天流唯一标识
    summary: str            # 决策摘要文本，最大 500 字符
    timestamp: float        # 决策时间戳（毫秒）
    weight: float           # 记忆权重 0.0-1.0
    trigger_reason: str     # 触发原因，最大 200 字符
    action_taken: str       # 采取行动，最大 200 字符
```

### ThinkingResponse（deepseek_client.py，新增）

```python
@dataclass
class ThinkingResponse:
    reasoning_content: str = ""   # 思维链内容
    content: str = ""             # 最终回答
    tool_calls: list[ToolCallInfo] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
```

### PerceptionData（agent.py，扩展）

```python
@dataclass
class PerceptionData:
    recent_messages: list[dict] = field(default_factory=list)
    silence_signal: bool = False
    silence_seconds: int = 0
    missed_reply_signal: bool = False
    memory_result: str = ""
    message_summary: str = ""
    memory_history: str = ""  # 新增：智能体历史决策记忆
```

### DecisionRecord（persistence.py，不变）

v3.1 不新增 DecisionRecord 字段。上下文溢出状态通过事件总线广播，不持久化到决策记录。

### 新增配置段（config.py）

详见 1.3.5 节。

## 4.3 新增文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `overflow_manager.py` | 新增 | 溢出管理器，4 级压力模型 + 软/硬剪枝 + 分级压缩 |
| `agent_chat.py` | 新增 | 智能体对话服务，会话管理 + LLM 对话 |
| `agent_memory.py` | 新增 | 智能体记忆模块，DecisionRecord 摘要提取 + 衰减 |

## 4.4 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `deepseek_client.py` | 扩展 | 新增 `ThinkingResponse`、`analyze_with_thinking()`、`analyze_with_json_output()` |
| `agent.py` | 扩展 | perceive 注入记忆、reason 集成 JSON Output、_react_loop 集成思考模式 + 溢出管理 |
| `config.py` | 扩展 | 新增 4 个配置段，config_version 升级 |
| `prompts.py` | 扩展 | 新增 `MEMORY_HISTORY_TEMPLATE`、`JSON_OUTPUT_HINT`，`build_system_prompt()` 新增参数 |
| `webui.py` | 扩展 | 新增 4 个智能体对话 API 端点，stats 扩展 |
| `event_bus.py` | 不变 | 无需修改，事件类型由发布方定义 |
| `persistence.py` | 不变 | 不新增 DecisionRecord 字段 |
| `context_compressor.py` | 不变 | 1M 模式下由 OverflowManager 替代，非 1M 模式下行为不变 |

## 4.5 测试策略

### 单元测试

| 模块 | 测试重点 |
|------|---------|
| `overflow_manager.py` | 压力等级计算正确性、软剪枝截断逻辑、硬剪枝消息对移除、分级压缩降级 |
| `agent_chat.py` | 会话创建/清除、并发保护、token 自动清理、LLM 调用失败处理 |
| `agent_memory.py` | 记忆提取正确性、衰减过滤、容量截取、空记录降级 |
| `deepseek_client.py` | 思考模式请求体构建、reasoning_content 回传、JSON Output 重试/降级、strict 模式 |
| `config.py` | 新增配置段默认值、向后兼容性 |

### 集成测试

| 场景 | 验证点 |
|------|--------|
| 1M 上下文完整流程 | 消息加载 → 压力计算 → 剪枝 → API 调用 → 事件广播 |
| 智能体对话完整流程 | 创建会话 → 发送消息 → 获取响应 → WebSocket 推送 |
| 思考模式 + ReAct 循环 | reasoning_content 回传 → 工具调用 → 无 400 错误 |
| 智能体记忆注入 | DecisionRecord 读取 → 摘要提取 → 提示词注入 → 决策执行 |
| 向后兼容 | 所有新功能关闭时，v3.1 行为与 v3.0 完全一致 |

### 性能测试

| 指标 | 目标 |
|------|------|
| 溢出检测耗时 | < 50ms |
| 软/硬剪枝耗时 | < 100ms |
| 智能体记忆加载耗时 | < 100ms |
| 智能体对话首 token 响应 | < 5s（不含 LLM API 延迟） |