# proactive-chat v3.1 编码任务

> 任务编号从 111 开始（v3.0 任务编号为 93-110，已完成）

---

## 1. DeepSeek v4 适配

### #111 新增 ThinkingResponse 数据类

- [ ] 在 `deepseek_client.py` 中新增 `ThinkingResponse` 数据类
  - 字段：`reasoning_content: str`、`content: str`、`tool_calls: list[ToolCallInfo]`
  - 属性：`has_tool_calls: bool`（判断 tool_calls 非空）
  - 涉及文件：`deepseek_client.py`
  - 验收标准：`ThinkingResponse` 可正常实例化，`has_tool_calls` 属性在 tool_calls 为空时返回 False、非空时返回 True

### #112 实现 analyze_with_thinking 方法

- [ ] 在 `DeepSeekClient` 中新增 `analyze_with_thinking()` 异步方法
  - 参数：`system_prompt`、`messages`、`config`、`tools`（可选）、`is_tool_call_round`（默认 False）
  - 请求体构建：思考模式启用时添加 `extra_body={"thinking": {"type": "enabled"}}`，不传递 temperature/top_p
  - reasoning_effort 控制：`is_tool_call_round=True` 时自动设为 `max`，否则使用配置值
  - strict 模式：启用时切换 base_url 为 beta 端点，工具定义中设置 `strict: true` 和 `additionalProperties: false`
  - 响应解析：提取 `reasoning_content` 和 `content`，解析 `tool_calls`（复用现有 ToolCallInfo 解析逻辑）
  - 返回 `ThinkingResponse` 实例
  - 涉及文件：`deepseek_client.py`
  - 验收标准：思考模式启用时 API 请求体包含 thinking 参数且不含 temperature/top_p；strict 模式启用时工具定义包含 strict: true；响应正确解析为 ThinkingResponse

### #113 实现 analyze_with_json_output 方法

- [ ] 在 `DeepSeekClient` 中新增 `analyze_with_json_output()` 异步方法
  - 参数：`system_prompt`、`user_prompt`、`config`、`json_format_example`（可选）
  - 请求体构建：添加 `response_format={"type": "json_object"}`
  - 重试逻辑：空 content 时重试最多 2 次（共 3 次尝试）
  - 降级逻辑：重试耗尽后删除 response_format 参数，降级为普通文本模式，记录警告日志
  - 涉及文件：`deepseek_client.py`
  - 验收标准：JSON Output 模式下 API 请求体包含 response_format 参数；空 content 时触发重试；重试耗尽后降级为普通模式并记录警告

### #114 旧模型名称兼容与弃用警告

- [ ] 在 `_call_api`、`_call_api_with_tools`、`analyze_with_thinking` 中添加旧模型名称检测
  - 当 `model == "deepseek-chat"` 时记录弃用警告日志：`deepseek-chat 模型名称已弃用，建议更新为 deepseek-v4-flash`
  - 不自动切换模型，允许继续使用
  - 涉及文件：`deepseek_client.py`
  - 验收标准：配置 model=deepseek-chat 时 API 调用正常，日志中出现弃用警告

---

## 2. 溢出管理器

### #115 新增 OverflowState 数据类

- [ ] 在新文件 `overflow_manager.py` 中定义 `OverflowState` 数据类
  - 字段：`pressure_level: int`（默认 0）、`token_count: int`（默认 0）、`usable_limit: int`（默认 0）、`ratio: float`（默认 0.0）、`action_taken: str`（默认 "none"）
  - action_taken 可选值："none" / "soft_prune" / "hard_prune" / "hard_prune+compress"
  - 涉及文件：`overflow_manager.py`（新增）
  - 验收标准：OverflowState 可正常实例化，默认值符合预期

### #116 实现压力等级计算

- [ ] 在 `OverflowManager` 中实现 `compute_pressure_level()` 方法
  - 非 1M 模式直接返回 0
  - 计算 ratio = token_count / usable_limit
  - 等级 0：ratio < 0.50；等级 1：0.50 ≤ ratio < level_2_ratio；等级 2：level_2_ratio ≤ ratio < level_3_ratio；等级 3：ratio ≥ level_3_ratio
  - level_2_ratio 和 level_3_ratio 从 `config.deepseek_context` 读取（默认 0.75 和 0.90）
  - 涉及文件：`overflow_manager.py`
  - 验收标准：ratio=0.3 → 等级 0；ratio=0.6 → 等级 1；ratio=0.82 → 等级 2；ratio=0.95 → 等级 3

### #117 实现 token 估算方法

- [ ] 在 `OverflowManager` 中实现 `estimate_messages_tokens()` 静态方法
  - 基于 OpenAI tiktoken 估算规则：每条消息基础 4 token，每个键值对加 2 token，内容按 1 token ≈ 1.5 中文字符或 0.75 英文单词估算
  - 涉及文件：`overflow_manager.py`
  - 验收标准：给定消息列表返回合理的 token 估算值（与实际 API 返回值偏差 < 30%）

### #118 实现软剪枝

- [ ] 在 `OverflowManager` 中实现 `soft_prune()` 方法
  - 遍历消息列表，仅截断 `role=tool` 的消息内容
  - 超过阈值（默认 500 字符）的内容截断为 `content[:threshold] + "[已截断]"`
  - 在消息副本上操作，不修改原始消息
  - 涉及文件：`overflow_manager.py`
  - 验收标准：工具输出 1200 字符 → 截断为 500 字符 + "[已截断]"；非 tool 角色消息不受影响；原始消息列表不变

### #119 实现硬剪枝

- [ ] 在 `OverflowManager` 中实现 `hard_prune()` 方法
  - 从最早的消息开始，移除完整的工具调用-响应消息对（assistant tool_calls + tool result）
  - 保留最近 N 条消息（N = config.context_compress.compress_retained_messages）
  - 迭代移除直到压力等级降至 3 以下或消息耗尽
  - 在消息副本上操作
  - 涉及文件：`overflow_manager.py`
  - 验收标准：5 对工具消息 → 移除最早的 2 对 → 压力等级从 3 降至 2；最近 N 条消息完整保留

### #120 实现 LLM 摘要压缩

- [ ] 在 `OverflowManager` 中实现 `_compress_with_llm()` 私有异步方法
  - 对剩余早期对话消息（非工具消息）生成 LLM 摘要
  - 复用 `DeepSeekClient.analyze_with_params()` 调用 LLM
  - 摘要失败时返回空字符串（调用方负责降级处理）
  - 涉及文件：`overflow_manager.py`
  - 验收标准：给定早期对话消息 → 返回摘要文本；LLM 调用失败时返回空字符串

### #121 实现 get_managed_context 主流程

- [ ] 在 `OverflowManager` 中实现 `get_managed_context()` 异步方法
  - 非 1M 模式直接返回原始消息副本和空 OverflowState
  - 计算 usable_limit = context_max_tokens - max_analysis_tokens
  - 估算 token 数，计算压力等级
  - 等级 0-1：返回原始消息副本
  - 等级 2：执行软剪枝，广播 context_overflow 事件
  - 等级 3：执行硬剪枝；若仍 ≥ 3 则触发 LLM 摘要压缩，替换为摘要 + 最近消息
  - 摘要失败时降级为硬剪枝结果
  - 涉及文件：`overflow_manager.py`
  - 验收标准：等级 0-1 返回原始消息；等级 2 返回软剪枝后消息；等级 3 返回硬剪枝或摘要后消息；任何操作后原始消息列表不变

### #122 OverflowManager 事件广播与统计计数

- [ ] 实现 `_publish_overflow_event()` 私有方法，通过 EventBus 广播 `context_overflow` 事件
  - 事件数据：`pressure_level`、`action_taken`、`token_count`、`usable_limit`、`ratio`
  - 在 `OverflowManager.__init__` 中初始化统计计数器：`total_soft_prunes`、`total_hard_prunes`、`total_compressions`
  - 每次执行对应操作时递增计数器
  - 涉及文件：`overflow_manager.py`
  - 验收标准：剪枝/压缩操作后 EventBus 收到 context_overflow 事件；统计计数器正确递增

---

## 3. 智能体记忆

### #123 新增 AgentMemoryEntry 数据类

- [ ] 在新文件 `agent_memory.py` 中定义 `AgentMemoryEntry` 数据类
  - 字段：`chat_stream_id: str`、`summary: str`（最大 500 字符）、`timestamp: float`（毫秒）、`weight: float`（0.0-1.0）、`trigger_reason: str`（最大 200 字符）、`action_taken: str`（最大 200 字符）
  - 涉及文件：`agent_memory.py`（新增）
  - 验收标准：AgentMemoryEntry 可正常实例化，字段类型和默认值符合预期

### #124 实现记忆摘要提取

- [ ] 在 `AgentMemory` 中实现 `_extract_summary()` 方法
  - 从 DecisionRecord 中提取 intent、reason、confidence、should_trigger
  - 格式化为摘要文本：`"意图: {intent}，原因: {reason}，置信度: {confidence:.2f}，结果: {'触发' if should_trigger else '未触发'}"`
  - intent 和 reason 均为空时返回 None
  - 涉及文件：`agent_memory.py`
  - 验收标准：DecisionRecord 包含 analysis_result → 提取为 AgentMemoryEntry；analysis_result 为空 → 返回 None

### #125 实现记忆衰减计算

- [ ] 在 `AgentMemory` 中实现 `_compute_weight()` 方法
  - 基于衰减天数计算权重：weight = max(0.0, 1.0 - (now - timestamp) / (decay_days * 86400))
  - 涉及文件：`agent_memory.py`
  - 验收标准：当天决策 → weight ≈ 1.0；衰减天数临界 → weight ≈ 0.0；超过衰减天数 → weight = 0.0

### #126 实现 get_memories 核心方法

- [ ] 在 `AgentMemory` 中实现 `get_memories()` 异步方法
  - 记忆未启用时返回空列表
  - 通过 PersistenceManager.query_decisions() 读取历史 DecisionRecord
  - 按衰减天数过滤（超过 cutoff 的跳过）
  - 调用 _extract_summary 提取摘要
  - 按时间倒序排列，截取前 memory_max_entries 条
  - 计算每条记忆的权重
  - 涉及文件：`agent_memory.py`
  - 验收标准：聊天流有 3 条历史 DecisionRecord → 返回 3 条 AgentMemoryEntry；超过衰减天数的记录被过滤；条数不超过 memory_max_entries

### #127 实现 format_memories_for_prompt 方法

- [ ] 在 `AgentMemory` 中实现 `format_memories_for_prompt()` 方法
  - 使用 `MEMORY_HISTORY_TEMPLATE` 和 `MEMORY_ENTRY_TEMPLATE` 格式化记忆列表
  - 每条记忆格式化为：`"- {time}：{summary}（行动: {action_taken}，权重: {weight:.1f}）"`
  - 空列表返回空字符串
  - 涉及文件：`agent_memory.py`
  - 验收标准：3 条记忆 → 格式化为包含 3 行摘要的文本；空列表 → 返回空字符串

---

## 4. 智能体对话

### #128 新增 AgentChatMessage 和 AgentChatSession 数据类

- [ ] 在新文件 `agent_chat.py` 中定义 `AgentChatMessage` 和 `AgentChatSession` 数据类
  - AgentChatMessage 字段：`role: str`（"user"/"assistant"/"system"）、`content: str`（最大 4000 字符）、`timestamp: float`（毫秒）
  - AgentChatSession 字段：`session_id: str`（UUID）、`messages: list[AgentChatMessage]`、`created_at: float`、`last_active_at: float`、`token_estimate: int`、`stream_context_id: str`、`is_responding: bool`（默认 False）
  - 涉及文件：`agent_chat.py`（新增）
  - 验收标准：两个数据类可正常实例化，字段类型和默认值符合预期

### #129 实现会话管理方法

- [ ] 在 `AgentChatService` 中实现 `create_session()`、`get_session()`、`list_sessions()`、`clear_session()` 方法
  - create_session：生成 UUID 作为 session_id，可选注入聊天流上下文，检查并发会话限制（默认 5）
  - get_session：按 session_id 查找会话
  - list_sessions：返回所有活跃会话的摘要信息
  - clear_session：移除指定会话
  - 涉及文件：`agent_chat.py`
  - 验收标准：创建会话 → 获取会话 → 列出会话 → 清除会话；第 6 个会话创建请求返回错误

### #130 实现 send_message 核心方法

- [ ] 在 `AgentChatService` 中实现 `send_message()` 异步方法
  - 查找或创建会话（session_id 不存在时自动创建）
  - 并发保护：`is_responding=True` 时抛出 RuntimeError
  - 追加用户消息（content 截断到 4000 字符）
  - 自动清理：token 超过阈值时清除早期 50% 消息
  - 构建系统提示词（复用 build_system_prompt，react_enabled=False）
  - 调用 LLM（不携带 tools 参数，使用 chat_max_tokens 和 chat_temperature）
  - 追加助手响应，更新 token 估算
  - 广播 `agent_chat_response` 事件
  - 涉及文件：`agent_chat.py`
  - 验收标准：发送消息 → 获取响应 → 会话历史包含用户和助手消息；并发请求被拒绝；LLM 调用失败时已有消息不丢失

### #131 实现聊天流上下文注入

- [ ] 在 `AgentChatService` 中实现 `_inject_stream_context()` 私有异步方法
  - 通过 PersistenceManager 读取指定聊天流的近期消息
  - 将消息摘要注入到会话的系统提示词中
  - 聊天流无近期消息时不注入，正常创建会话
  - 涉及文件：`agent_chat.py`
  - 验收标准：选择聊天流 → 系统提示词包含该聊天流近期消息摘要；无消息时不注入

### #132 实现会话 token 自动清理

- [ ] 在 `AgentChatService` 中实现 `_auto_cleanup_if_needed()` 私有方法
  - 当 token_estimate 超过 chat_session_token_limit（默认 800000）时，清除最早的 50% 消息
  - 清理后更新 token_estimate
  - 涉及文件：`agent_chat.py`
  - 验收标准：token 估算 > 800000 → 自动清除早期 50% 消息；清理后 token_estimate 下降

---

## 5. 配置扩展

### #133 新增 DeepseekContextConfig 配置段

- [ ] 在 `config.py` 中新增 `DeepseekContextConfig` 类
  - 字段：`context_1m_enabled: bool`（默认 False）、`soft_prune_threshold: int`（默认 500，范围 100-2000）、`pressure_level_2_ratio: float`（默认 0.75，范围 0.5-0.9）、`pressure_level_3_ratio: float`（默认 0.90，范围 0.75-0.98）、`context_max_tokens: int`（默认 1000000）
  - UI 标签：`__ui_label__ = "1M 上下文"`、`__ui_icon__ = "maximize"`、`__ui_order__ = 13`
  - 涉及文件：`config.py`
  - 验收标准：配置段可正常实例化，默认值符合预期；WebUI 可正确渲染配置表单

### #134 新增 AgentChatConfig 配置段

- [ ] 在 `config.py` 中新增 `AgentChatConfig` 类
  - 字段：`agent_chat_enabled: bool`（默认 False）、`chat_max_tokens: int`（默认 500，范围 100-2000）、`chat_max_sessions: int`（默认 5，范围 1-20）、`chat_session_token_limit: int`（默认 800000，范围 100000-900000）、`chat_temperature: float`（默认 0.7，范围 0.0-2.0）
  - UI 标签：`__ui_label__ = "智能体对话"`、`__ui_icon__ = "message-circle"`、`__ui_order__ = 14`
  - 涉及文件：`config.py`
  - 验收标准：配置段可正常实例化，默认值符合预期

### #135 新增 DeepseekV4Config 配置段

- [ ] 在 `config.py` 中新增 `DeepseekV4Config` 类
  - 字段：`thinking_enabled: bool`（默认 False）、`reasoning_effort: str`（默认 "high"，可选 "high"/"max"）、`json_output_enabled: bool`（默认 True）、`default_model: str`（默认 "deepseek-v4-flash"，可选 "deepseek-v4-flash"/"deepseek-v4-pro"/"deepseek-chat"）、`strict_mode_enabled: bool`（默认 False）
  - UI 标签：`__ui_label__ = "DeepSeek v4"`、`__ui_icon__ = "sparkles"`、`__ui_order__ = 15`
  - 涉及文件：`config.py`
  - 验收标准：配置段可正常实例化，默认值符合预期

### #136 新增 AgentMemoryConfig 配置段

- [ ] 在 `config.py` 中新增 `AgentMemoryConfig` 类
  - 字段：`memory_enabled: bool`（默认 False）、`memory_decay_days: int`（默认 7，范围 1-90）、`memory_max_entries: int`（默认 10，范围 1-50）
  - UI 标签：`__ui_label__ = "智能体记忆"`、`__ui_icon__ = "brain"`、`__ui_order__ = 16`
  - 涉及文件：`config.py`
  - 验收标准：配置段可正常实例化，默认值符合预期

### #137 ProactiveChatConfig 注册新配置段与版本升级

- [ ] 在 `ProactiveChatConfig` 中新增 4 个配置段字段：`deepseek_context`、`agent_chat`、`deepseek_v4`、`agent_memory`
  - 将 `config_version` 从 `3.0.0` 升级为 `3.1.0`
  - 确保新增配置段有默认值，向后兼容 v3.0 配置
  - 涉及文件：`config.py`
  - 验收标准：v3.0 配置文件加载后新增字段使用默认值；config_version 显示为 3.1.0

### #138 更新 config.toml 配置模板

- [ ] 更新配置模板文件，新增 4 个配置段的注释和示例
  - 每个配置段包含中文注释说明
  - 不修改实际 bot_config.toml，仅更新模板
  - 涉及文件：配置模板文件
  - 验收标准：模板文件包含 4 个新配置段的注释和默认值

---

## 6. 提示词扩展

### #139 新增智能体记忆注入模板

- [ ] 在 `prompts.py` 中新增 `MEMORY_HISTORY_TEMPLATE` 和 `MEMORY_ENTRY_TEMPLATE` 常量
  - MEMORY_HISTORY_TEMPLATE：包含 `[历史决策记忆]` 标题、`{memory_entries}` 占位符、注意事项说明
  - MEMORY_ENTRY_TEMPLATE：`"- {time}：{summary}（行动: {action_taken}，权重: {weight:.1f}）"`
  - 涉及文件：`prompts.py`
  - 验收标准：模板常量可正常使用 format() 填充

### #140 新增 JSON Output 格式样例

- [ ] 在 `prompts.py` 中新增 `JSON_OUTPUT_HINT` 常量
  - 包含 `## 输出格式约束` 标题
  - JSON 结构样例：should_trigger、intent、reason、confidence、timing_score
  - 涉及文件：`prompts.py`
  - 验收标准：JSON_OUTPUT_HINT 包含 "json" 字样和格式样例，满足 DeepSeek JSON Output 的 prompt 约束

### #141 扩展 build_system_prompt 函数

- [ ] 在 `build_system_prompt()` 中新增 `json_output_enabled: bool = False` 参数
  - json_output_enabled=True 时追加 `JSON_OUTPUT_HINT` 到系统提示词末尾
  - 不影响现有调用行为（默认 False）
  - 涉及文件：`prompts.py`
  - 验收标准：json_output_enabled=False 时输出与 v3.0 一致；json_output_enabled=True 时输出包含 JSON 格式约束

---

## 7. AgentCore 集成

### #142 PerceptionData 新增 memory_history 字段

- [ ] 在 `agent.py` 的 `PerceptionData` 数据类中新增 `memory_history: str = ""` 字段
  - 涉及文件：`agent.py`
  - 验收标准：PerceptionData 实例包含 memory_history 字段，默认为空字符串

### #143 perceive 阶段注入智能体记忆

- [ ] 在 `AgentCore.perceive()` 方法中新增智能体记忆注入逻辑
  - 当 `config.agent_memory.memory_enabled` 且 `self._agent_memory is not None` 时，调用 `get_memories()` 获取记忆
  - 有记忆时调用 `format_memories_for_prompt()` 格式化，赋值给 `perception.memory_history`
  - 无记忆时不注入记忆段落
  - 涉及文件：`agent.py`
  - 验收标准：记忆启用且有历史决策 → perception.memory_history 非空；记忆未启用 → memory_history 为空

### #144 reason 方法集成 JSON Output

- [ ] 在 `AgentCore.reason()` 方法中集成 JSON Output 模式
  - 当 `config.deepseek_v4.json_output_enabled` 时调用 `analyze_with_json_output()` 替代 `analyze()`
  - 传递 `json_format_example` 参数（使用 JSON_OUTPUT_HINT）
  - 非 JSON Output 模式保持现有逻辑不变
  - 涉及文件：`agent.py`
  - 验收标准：json_output_enabled=True → 调用 analyze_with_json_output；json_output_enabled=False → 调用 analyze（行为与 v3.0 一致）

### #145 _react_loop 集成思考模式

- [ ] 在 `AgentCore._react_loop()` 方法中集成思考模式分支
  - 当 `config.deepseek_v4.thinking_enabled` 时调用 `analyze_with_thinking()` 替代 `analyze_with_tools()`
  - 非首轮（step > 1）自动设置 `is_tool_call_round=True`
  - reasoning_content 处理：记录到日志（截断到 200 字符），仅将 content 用于后续决策
  - 追加 assistant 消息时回传 reasoning_content（工具调用轮次）
  - 非思考模式保持现有逻辑不变
  - 涉及文件：`agent.py`
  - 验收标准：思考模式启用 → 调用 analyze_with_thinking；工具调用轮次的 reasoning_content 在后续请求中回传；非思考模式行为与 v3.0 一致

### #146 _react_loop 集成溢出管理

- [ ] 在 `AgentCore._react_loop()` 方法中集成溢出管理
  - 在调用 LLM 前调用 `OverflowManager.get_managed_context()` 管理消息列表
  - 当 `self._overflow_manager is not None` 且 `config.deepseek_context.context_1m_enabled` 时启用
  - 根据 overflow_state.action_taken 设置 context_compressed 标记
  - 非 1M 模式不影响现有 ContextCompressor 逻辑
  - 涉及文件：`agent.py`
  - 验收标准：1M 模式启用 → 消息列表经过溢出管理；非 1M 模式 → 行为与 v3.0 一致

### #147 AgentCore 新增依赖注入

- [ ] 在 `AgentCore.__init__()` 中新增 3 个可选依赖字段
  - `self._overflow_manager: OverflowManager | None = None`
  - `self._agent_memory: AgentMemory | None = None`
  - `self._agent_chat_service: AgentChatService | None = None`
  - 涉及文件：`agent.py`
  - 验收标准：AgentCore 可正常实例化，新字段默认为 None

---

## 8. WebUI 扩展

### #148 新增智能体对话 API 端点

- [ ] 在 `webui.py` 中新增 4 个 API 端点处理方法
  - `_handle_agent_chat_sessions()`：GET /api/proactive-chat/agent/chat/sessions
  - `_handle_agent_chat_create()`：POST /api/proactive-chat/agent/chat/sessions
  - `_handle_agent_chat_send()`：POST /api/proactive-chat/agent/chat/send
  - `_handle_agent_chat_clear()`：POST /api/proactive-chat/agent/chat/sessions/{id}/clear
  - 每个端点检查 `self._agent_chat_service` 是否可用
  - 涉及文件：`webui.py`
  - 验收标准：4 个端点可正常响应；服务未启用时返回 `{"success": false, "error": "智能体对话服务未启用"}`

### #149 注册智能体对话路由

- [ ] 在 `WebUIServer.start()` 方法中注册 4 个智能体对话路由
  - 添加路由映射到对应的处理方法
  - 涉及文件：`webui.py`
  - 验收标准：路由注册后 HTTP 请求可正确路由到处理方法

### #150 stats 接口扩展

- [ ] 在 `GET /api/proactive-chat/stats` 响应中新增 `overflow_stats` 和 `memory_stats` 字段
  - overflow_stats：1m_enabled、current_pressure_level、total_soft_prunes、total_hard_prunes、total_compressions
  - memory_stats：memory_enabled、total_memories_loaded、avg_memory_entries_per_stream
  - 涉及文件：`webui.py`
  - 验收标准：stats 响应包含新增字段；1M 模式未启用时 overflow_stats.1m_enabled=False

### #151 WebSocket 新增事件类型

- [ ] 在 WebSocket 推送中支持 `context_overflow` 和 `agent_chat_response` 事件类型
  - 确保 EventBus 的事件可正确通过 WebSocket 推送到前端
  - 涉及文件：`webui.py`
  - 验收标准：剪枝/压缩操作后前端收到 context_overflow 事件；智能体对话响应后前端收到 agent_chat_response 事件

---

## 9. plugin.py 集成

### #152 初始化新模块并注入依赖

- [ ] 在 `plugin.py` 的初始化逻辑中创建新模块实例并注入到 AgentCore
  - 创建 `OverflowManager` 实例（依赖 DeepSeekClient、EventBus、data_dir）
  - 创建 `AgentMemory` 实例（依赖 PersistenceManager）
  - 创建 `AgentChatService` 实例（依赖 DeepSeekClient、EventBus、PersistenceManager）
  - 将新模块注入到 AgentCore：`agent._overflow_manager = overflow_manager` 等
  - 将 AgentChatService 注入到 WebUIServer
  - 涉及文件：`plugin.py`
  - 验收标准：插件启动后 AgentCore 的 _overflow_manager、_agent_memory、_agent_chat_service 不为 None；WebUIServer 的 _agent_chat_service 不为 None

---

## 10. 测试

### #153 溢出管理器单元测试

- [ ] 在 `tests/test_overflow_manager.py` 中编写单元测试
  - 测试 `compute_pressure_level()` 各阈值场景
  - 测试 `soft_prune()` 截断逻辑和原始消息不变性
  - 测试 `hard_prune()` 消息对移除和最近 N 条保留
  - 测试 `get_managed_context()` 各压力等级分支
  - 测试非 1M 模式返回原始消息
  - 涉及文件：`tests/test_overflow_manager.py`（新增）
  - 验收标准：所有测试通过；覆盖等级 0/1/2/3 场景；覆盖降级场景

### #154 智能体记忆单元测试

- [ ] 在 `tests/test_agent_memory.py` 中编写单元测试
  - 测试 `_extract_summary()` 正常提取和空记录返回 None
  - 测试 `_compute_weight()` 衰减计算
  - 测试 `get_memories()` 衰减过滤、容量截取
  - 测试 `format_memories_for_prompt()` 格式化输出
  - 测试记忆未启用时返回空列表
  - 涉及文件：`tests/test_agent_memory.py`（新增）
  - 验收标准：所有测试通过；覆盖衰减边界、容量截取、空记录降级

### #155 智能体对话单元测试

- [ ] 在 `tests/test_agent_chat.py` 中编写单元测试
  - 测试会话创建/获取/列表/清除
  - 测试并发会话限制
  - 测试 `send_message()` 正常流程
  - 测试并发保护（is_responding 时拒绝）
  - 测试 token 自动清理
  - 测试 LLM 调用失败时消息不丢失
  - 涉及文件：`tests/test_agent_chat.py`（新增）
  - 验收标准：所有测试通过；覆盖并发、清理、失败降级场景

### #156 DeepSeek v4 适配单元测试

- [ ] 在 `tests/test_deepseek_client.py` 中扩展测试
  - 测试 `analyze_with_thinking()` 请求体构建（thinking 参数、reasoning_effort、strict 模式）
  - 测试思考模式下不传递 temperature/top_p
  - 测试 `analyze_with_json_output()` 重试和降级逻辑
  - 测试旧模型名称弃用警告
  - 测试 ThinkingResponse 数据类
  - 涉及文件：`tests/test_deepseek_client.py`（扩展）
  - 验收标准：所有测试通过；覆盖思考模式、JSON Output、strict 模式、旧模型兼容

### #157 配置扩展单元测试

- [ ] 在 `tests/test_config.py` 中扩展测试
  - 测试 4 个新配置段的默认值
  - 测试 ProactiveChatConfig 包含新配置段字段
  - 测试向后兼容性（v3.0 配置加载后新字段使用默认值）
  - 测试 config_version 升级
  - 涉及文件：`tests/test_config.py`（扩展）
  - 验收标准：所有测试通过；新配置段默认值正确；v3.0 配置向后兼容

### #158 提示词扩展单元测试

- [ ] 在 `tests/test_prompts.py` 中扩展测试
  - 测试 `MEMORY_HISTORY_TEMPLATE` 和 `MEMORY_ENTRY_TEMPLATE` 格式化
  - 测试 `JSON_OUTPUT_HINT` 包含 "json" 字样和格式样例
  - 测试 `build_system_prompt()` 新增 `json_output_enabled` 参数
  - 测试 json_output_enabled=False 时输出与 v3.0 一致
  - 涉及文件：`tests/test_prompts.py`（扩展）
  - 验收标准：所有测试通过；模板格式化正确；build_system_prompt 新参数行为正确

### #159 AgentCore 集成单元测试

- [ ] 在 `tests/test_agent.py` 中扩展测试
  - 测试 `perceive()` 记忆注入逻辑
  - 测试 `reason()` JSON Output 集成
  - 测试 `_react_loop()` 思考模式分支
  - 测试 `_react_loop()` 溢出管理集成
  - 测试 reasoning_content 回传机制
  - 涉及文件：`tests/test_agent.py`（扩展）
  - 验收标准：所有测试通过；覆盖记忆注入、JSON Output、思考模式、溢出管理集成

### #160 WebUI 扩展单元测试

- [ ] 在 `tests/test_webui.py` 中扩展测试
  - 测试 4 个智能体对话 API 端点的正常和异常响应
  - 测试 stats 接口新增字段
  - 测试服务未启用时的错误响应
  - 涉及文件：`tests/test_webui.py`（扩展）
  - 验收标准：所有测试通过；端点正常/异常场景覆盖

### #161 向后兼容集成测试

- [ ] 编写向后兼容集成测试
  - 所有新功能关闭时，v3.1 行为与 v3.0 完全一致
  - 不启用 1M 上下文时，ContextCompressor 逻辑不变
  - 不启用智能体对话时，WebUI 与 v3.0 一致
  - 不启用思考模式时，LLM 调用行为不变
  - 不启用智能体记忆时，决策行为不变
  - 涉及文件：`tests/test_backward_compat.py`（新增）
  - 验收标准：所有新功能关闭时，决策循环、LLM 调用、WebUI 行为与 v3.0 一致