# v3.0 智能体升级编码任务

> 前置文档：`spec.md`（需求规格）、`design.md`（实现方案）
> 任务编号从 93 开始（v2.1 任务 76-92 已完成）

## 阶段一：基础设施（任务 93-97）

### 任务 93：新增 event_bus.py 事件总线模块

**目标**：创建 EventBus 类，统一管理智能体事件广播

**实现**：
- 新建 `event_bus.py`
- 实现 `AgentEvent` dataclass（event_type, timestamp, stream_id, data）
- 实现 `EventBus` 类：subscribe/unsubscribe/publish/get_recent_events
- publish 内置 1 秒去重（dedup_key = event_type:stream_id）
- 订阅者异常不影响其他订阅者
- 内部 deque(maxlen=100) 记录最近事件

**验证**：单元测试 publish/subscribe/去重/异常隔离

### 任务 94：新增 agent_tools.py AgentTool 注册表

**目标**：创建 AgentTool 定义和注册表

**实现**：
- 新建 `agent_tools.py`
- 实现 `AgentToolDef` dataclass（name, description, parameters, execute）
- 实现 `ToolContext` dataclass（stream_id, ctx, config, cooldown_manager, persistence_manager）
- 实现 `AgentToolRegistry`：register/get/get_all_definitions/execute_tool
- `get_all_definitions()` 返回 DeepSeek tools 格式的 list[dict]
- `execute_tool()` 参数验证 + 超时保护（10s）+ 错误返回文本

**验证**：单元测试注册/查询/格式输出/参数验证/超时

### 任务 95：扩展 deepseek_client.py 支持 tool_use

**目标**：DeepSeek API 调用支持 tools 参数和 tool_calls 响应解析

**实现**：
- 新增 `ToolCallInfo` dataclass（id, name, arguments, raw）
- 新增 `ToolCallResponse` dataclass（text, tool_calls, has_tool_calls 属性）
- 新增 `analyze_with_tools()` 方法，接收 messages + tools 参数
- `_call_api()` 扩展：body 可选添加 `tools` 和 `tool_choice` 字段
- 新增 `_call_api_with_tools()` 方法，解析 `choices[0].message.tool_calls`
- tool_calls 中 arguments 字符串解析为 dict，JSON 解析失败返回空 dict

**验证**：单元测试 ToolCallResponse 解析/analyze_with_tools 参数构建

### 任务 96：扩展 persistence.py DecisionRecord 新增 4 个字段

**目标**：DecisionRecord 新增 react_steps/react_total_steps/reflection_result/context_compressed

**实现**：
- DecisionRecord 新增 4 个字段（带默认值）
- `_fill_record_defaults()` 新增 4 个 setdefault
- `_dict_to_record()` 新增 4 个字段映射
- 确保旧 JSONL 记录读取时自动填充默认值

**验证**：单元测试旧记录兼容/新字段默认值/asdict 输出

### 任务 97：扩展 config.py 新增 ReActConfig 和 ContextCompressConfig

**目标**：新增两个配置段，config_version 升级到 3.0.0

**实现**：
- 新增 `ReActConfig`（react_enabled/max_react_steps/reflect_subagent_enabled/reflect_confidence_threshold）
- 新增 `ContextCompressConfig`（compress_enabled/compress_token_threshold/compress_retained_messages/compress_max_tokens）
- `ProactiveChatConfig` 新增 `react` 和 `context_compress` 字段
- `PluginSectionConfig.config_version` 默认值改为 `"3.0.0"`
- 同步更新 `config.toml` 模板

**验证**：单元测试默认值/序列化/反序列化

## 阶段二：ReAct 循环核心（任务 98-101）

### 任务 98：注册内置 AgentTool

**目标**：在 agent_tools.py 中实现 5 个内置工具

**实现**：
- `get_recent_messages`：复用 AgentCore._get_recent_messages 逻辑，参数 limit（默认 10，最大 30）
- `get_cooldown_status`：调用 CooldownManager.is_cooled_down() + _records，返回冷却剩余秒数
- `get_stream_activity`：调用 ctx.message.get_by_time_in_chat()，计算消息频率/最后消息时间/平均间隔
- `search_memory`：复用 AgentCore._search_memory 逻辑，参数 query
- `submit_decision`：解析参数返回 dict（should_trigger/intent/reason/confidence/timing_score），不执行写操作
- 每个工具的 parameters 使用 JSON Schema 格式

**验证**：单元测试每个工具的参数验证/执行/返回格式

### 任务 99：扩展 prompts.py 新增 ReAct 工具引导和反思/压缩提示词

**目标**：系统提示词新增工具引导段落，新增反思和压缩提示词

**实现**：
- `AGENT_SYSTEM_PROMPT` 新增 `## 可用工具` 和 `## 工具使用策略` 段落
- 新增 `REACT_TOOL_SECTION` 模板（条件插入，react_enabled 时注入）
- 新增 `REFLECTION_SYSTEM_PROMPT` 和 `REFLECTION_USER_TEMPLATE`
- 新增 `COMPRESSION_SYSTEM_PROMPT` 和 `COMPRESSION_USER_TEMPLATE`
- `build_system_prompt()` 新增 `react_enabled` 参数，控制工具引导段落注入
- 同步修改英文和日文文件（如有）

**验证**：单元测试提示词生成/条件注入

### 任务 100：实现 AgentCore._react_loop() 核心循环

**目标**：将 reason() 重构为 ReAct 循环

**实现**：
- 新增 `ReActStep` 和 `ReflectionResult` dataclass
- 新增 `_react_loop()` 方法：
  - 初始化消息历史（system + user perception 数据）
  - for step in range(1, max_steps+1) 循环
  - 调用 `_deepseek.analyze_with_tools()` 带 tools 定义
  - 处理 tool_calls：执行工具 → 追加消息 → 广播 react_step 事件
  - submit_decision 特殊处理：解析参数返回 AnalysisResult
  - 非 tool_use 响应：降级到 parse_analysis_result()
  - 达到 max_steps 追加"请立即决策"提示
  - 循环总超时 30s（asyncio.wait_for）
  - 连续 2 次无效工具名 → 强制终止
- AgentCore.__init__ 新增 `_tool_registry` 和 `_event_bus` 属性
- 保留 `reason()` 方法不变（v2.1 兼容路径）

**验证**：单元测试单步决策/多步循环/submit_decision/无效工具/超时/max_steps

### 任务 101：重构 decision_loop 集成 ReAct 循环和反思子智能体

**目标**：decision_loop 中 reason 调用替换为 _react_loop，插入反思子智能体

**实现**：
- decision_loop 中 reason() 调用位置改为条件分支：
  - react_enabled=True → 调用 _react_loop()
  - react_enabled=False → 调用 reason()（v2.1 兼容）
- 新增 `_reflect_with_subagent()` 方法：
  - 使用 REFLECTION_SYSTEM_PROMPT + REFLECTION_USER_TEMPLATE
  - 调用 _deepseek.analyze_with_params()（独立 max_tokens=200）
  - asyncio.wait_for(timeout=15.0)，超时返回 None
  - 解析 JSON 响应为 ReflectionResult，解析失败视为 confirmed
- 反思插入位置：reason/react_loop 之后、act 之前
  - 条件：reflect_subagent_enabled and should_trigger and confidence >= threshold
  - vetoed → action_taken="vetoed_by_reflection"，跳过 act
- reflect() 新增 react_steps/react_total_steps/reflection_result/context_compressed 字段
- perceive 阶段集成 ContextCompressor（任务 103 实现后接入）

**验证**：单元测试 ReAct 路径/兼容路径/反思 confirmed/vetoed/超时/降级

## 阶段三：上下文压缩（任务 102-103）

### 任务 102：新增 context_compressor.py 上下文压缩模块

**目标**：实现上下文压缩器，长对话历史自动压缩

**实现**：
- 新建 `context_compressor.py`
- 实现 `ContextSummary` dataclass
- 实现 `ContextCompressor` 类：
  - `get_context()`：估算 token → 判断是否压缩 → 缓存检查 → 压缩/返回
  - `_compress()`：LLM 驱动摘要生成，使用 COMPRESSION_SYSTEM_PROMPT
  - `_estimate_tokens()`：粗略估算（中文 1.5 字/token，英文 4 字符/token）
  - `_get_cache_path()` / `_read_cache()` / `_write_cache()`
  - `_is_cache_valid()`：比较最近 N 条消息的 hash
- 缓存文件路径：`data/proactive-chat/summaries/{stream_id}.json`
- 压缩失败降级：截断到 max_tokens

**验证**：单元测试 token 估算/压缩/缓存读写/缓存失效/降级

### 任务 103：集成 ContextCompressor 到 AgentCore.perceive()

**目标**：perceive 阶段使用 ContextCompressor 优化消息上下文

**实现**：
- AgentCore.__init__ 新增 `_compressor` 属性
- perceive() 中 `_format_message_summary()` 调用前，先通过 compressor 获取上下文
- compress_enabled=True 时使用压缩上下文，False 时保持原逻辑
- 压缩结果标记 context_compressed=True

**验证**：单元测试压缩集成/禁用时行为

## 阶段四：事件总线集成（任务 104-105）

### 任务 104：替换 agent.py 和 cooldown.py 中的 _broadcast_if_available

**目标**：统一使用 EventBus 替代分散的 _broadcast_if_available

**实现**：
- AgentCore.__init__ 接收 EventBus 实例
- agent.py 中 `_broadcast_if_available()` 全部替换为 `self._event_bus.publish()`
- cooldown.py 中 `_broadcast_if_available()` 全部替换为 `self._event_bus.publish()`
- 新增事件类型：react_step、react_complete、reflection_result、context_compressed
- 保留 phase_changed、new_decision、cooldown_started、cooldown_expired 事件

**验证**：单元测试事件发布/订阅/去重

### 任务 105：plugin.py 集成 EventBus 和 AgentToolRegistry

**目标**：插件入口初始化 EventBus 和 AgentToolRegistry，注入到各组件

**实现**：
- on_load 中创建 EventBus 实例
- on_load 中创建 AgentToolRegistry，注册 5 个内置工具
- 将 EventBus 注入到 AgentCore、CooldownManager
- 将 AgentToolRegistry 注入到 AgentCore
- 将 ContextCompressor 注入到 AgentCore
- WebUI 的 broadcast_event 注册为 EventBus 订阅者
- on_unload 中清理 EventBus 订阅者

**验证**：集成测试组件初始化/依赖注入

## 阶段五：WebUI 扩展（任务 106-108）

### 任务 106：WebUI 决策记录表格新增 ReAct/反思/压缩列

**目标**：决策记录展示新增 react_total_steps/reflection_result/context_compressed

**实现**：
- 表格新增"步数"列（react_total_steps，v2.1 旧记录显示 `-`）
- 行展开详情新增 ReAct 步骤列表（step_index/tool_name/tool_args/tool_result 摘要）
- 新增反思结果 badge（confirmed 绿/vetoed 红）
- 新增压缩标识小图标（context_compressed=True 时显示）
- 统计卡片新增 ReAct 平均步数、反思否决率

**验证**：手动验证 WebUI 展示

### 任务 107：WebUI 事件总线集成和新增事件推送

**目标**：WebUI WebSocket 推送新增 react_step/react_complete/reflection_result/context_compressed 事件

**实现**：
- WebUI 的 broadcast_event 注册为 EventBus 订阅者
- WebSocket 推送新增 4 种事件类型
- 决策记录行更新时包含新字段

**验证**：手动验证 WebSocket 推送

### 任务 108：WebUI 配置面板新增 ReAct 和上下文压缩配置

**目标**：配置在线编辑新增 ReActConfig 和 ContextCompressConfig

**实现**：
- 配置面板新增"ReAct 循环"和"上下文压缩"两个折叠区域
- 展示 react_enabled/max_react_steps/reflect_subagent_enabled/reflect_confidence_threshold
- 展示 compress_enabled/compress_token_threshold/compress_retained_messages/compress_max_tokens
- 保存时同步更新 config.toml

**验证**：手动验证配置编辑/保存/生效

## 阶段六：配置和文档（任务 109-110）

### 任务 109：更新 config.toml 模板和 _manifest.json

**目标**：配置模板新增 ReAct 和上下文压缩段，版本号升级

**实现**：
- config.toml 新增 `[react]` 和 `[context_compress]` 段
- _manifest.json config_version 升级到 3.0.0
- 确保默认值等价于 v2.1 行为（react_enabled=True 但 reflect_subagent_enabled=False）

**验证**：配置加载测试

### 任务 110：更新测试和集成验证

**目标**：确保所有新增和修改的测试通过

**实现**：
- 新增 test_event_bus.py
- 新增 test_agent_tools.py
- 扩展 test_deepseek_client.py（tool_use 相关）
- 扩展 test_persistence.py（新字段）
- 扩展 test_config.py（新配置段）
- 扩展 test_agent.py（_react_loop/反思/压缩集成）
- 扩展 test_plugin.py（EventBus/AgentToolRegistry 集成）
- 运行全量测试确保通过

**验证**：全量测试通过