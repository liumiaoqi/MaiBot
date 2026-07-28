# proactive-chat v3.2 编码任务

> 任务编号从 162 开始（v3.1 任务编号为 111-161，已完成）

---

## 1. 配置扩展

### #162 新增 DeepseekOptimizationConfig 配置段

- [ ] 在 `config.py` 中新增 `DeepseekOptimizationConfig` 类
  - 字段：`robust_reasoning_enabled: bool`（默认 True）、`adaptive_effort_enabled: bool`（默认 True）、`step_classifier_enabled: bool`（默认 True）、`loop_detection_enabled: bool`（默认 True）、`repeated_step_threshold: int`（默认 3，范围 2-10）、`ngram_window_size: int`（默认 3，范围 2-5）、`ngram_repeat_threshold: int`（默认 3，范围 2-10）、`strict_mode_enabled: bool`（默认 False）、`deepseek_prompt_enabled: bool`（默认 True）、`enhanced_retry_enabled: bool`（默认 True）、`sse_chunk_timeout_seconds: int`（默认 480，范围 60-900）、`retry_base_delay_ms: int`（默认 500，范围 100-5000）、`retry_max_retries: int`（默认 10，范围 1-20）、`retry_max_backoff_ms: int`（默认 60000，范围 1000-300000）
  - UI 标签：`__ui_label__ = "DeepSeek 优化"`、`__ui_icon__ = "rocket"`、`__ui_order__ = 17`
  - 涉及文件：`config.py`
  - 验收标准：配置段可正常实例化，14 个字段默认值符合预期；WebUI 可正确渲染配置表单

### #163 新增 AgentOptimizationConfig 配置段

- [ ] 在 `config.py` 中新增 `AgentOptimizationConfig` 类
  - 字段：`topic_tracking_enabled: bool`（默认 True）、`sentiment_analysis_enabled: bool`（默认 True）、`participant_profile_enabled: bool`（默认 True）、`participant_profile_max_entries: int`（默认 5，范围 1-10）、`adaptive_steps_enabled: bool`（默认 True）、`enhanced_memory_enabled: bool`（默认 True）、`enhanced_reflection_enabled: bool`（默认 True）、`prompt_optimization_enabled: bool`（默认 True）、`context_aware_compress_enabled: bool`（默认 True）、`quality_stats_window_size: int`（默认 100，范围 10-1000）
  - UI 标签：`__ui_label__ = "智能体优化"`、`__ui_icon__ = "trending-up"`、`__ui_order__ = 18`
  - 涉及文件：`config.py`
  - 验收标准：配置段可正常实例化，10 个字段默认值符合预期

### #164 ProactiveChatConfig 注册新配置段与版本升级

- [ ] 在 `ProactiveChatConfig` 中新增 2 个配置段字段：`deepseek_optimization`、`agent_optimization`
  - 将 `config_version` 从 `3.1.0` 升级为 `3.2.0`
  - 确保新增配置段有默认值，向后兼容 v3.1 配置
  - 涉及文件：`config.py`
  - 验收标准：v3.1 配置文件加载后新增字段使用默认值；config_version 显示为 3.2.0

### #165 更新 config.toml 配置模板

- [ ] 更新配置模板文件，新增 2 个配置段的注释和示例
  - 每个配置段包含中文注释说明
  - 不修改实际 bot_config.toml，仅更新模板
  - 涉及文件：配置模板文件
  - 验收标准：模板文件包含 2 个新配置段的注释和默认值

---

## 2. reasoning_content 回传健壮性

### #166 实现 _validate_reasoning_content 方法

- [ ] 在 `DeepSeekClient` 中新增 `_validate_reasoning_content()` 方法
  - 遍历消息列表中所有 `role=assistant` 且包含 `tool_calls` 的消息
  - 检查是否携带 `reasoning_content`，缺失时记录警告日志
  - 涉及文件：`deepseek_client.py`
  - 验收标准：工具调用消息缺少 reasoning_content → 记录警告日志；所有消息均包含 → 无日志

### #167 实现 _fix_reasoning_content 方法

- [ ] 在 `DeepSeekClient` 中新增 `_fix_reasoning_content()` 方法
  - 补全遗漏的 reasoning_content：工具调用消息缺少时填充 `"[思维链已补全]"`
  - 在请求体副本上操作，不修改原始消息
  - 记录警告日志
  - 涉及文件：`deepseek_client.py`
  - 验收标准：工具调用消息缺少 reasoning_content → 补全为 "[思维链已补全]"；非工具调用消息不受影响

### #168 集成回传健壮性到 analyze_with_thinking

- [ ] 在 `analyze_with_thinking()` 方法中集成回传健壮性逻辑
  - 当 `config.deepseek_optimization.robust_reasoning_enabled` 为 True 时，发送请求前调用 `_validate_reasoning_content()`
  - 捕获 400 错误时调用 `_fix_reasoning_content()` 补全后重试
  - 重试仍返回 400 时降级为非思考模式，记录错误日志
  - 简化写法追加消息：响应对象包含 role、content、tool_calls、reasoning_content 等所有字段
  - 涉及文件：`deepseek_client.py`
  - 验收标准：robust_reasoning_enabled=True → 请求前验证回传完整性；400 错误 → 自动补全重试；重试仍失败 → 降级为非思考模式

---

## 3. reasoning_effort 自适应调节

### #169 实现 _assess_complexity 方法

- [ ] 在 `DeepSeekClient` 中新增 `_assess_complexity()` 方法
  - 评估维度：信号数量（silence_signal、missed_reply_signal、话题关联度 > 0.5）、消息数量、情感转折
  - 复杂场景：3+ 信号 或 15+ 条消息 或 有情感转折 → "high"
  - 普通场景：1+ 信号 或 5+ 条消息 → "medium"
  - 简单场景：其余 → "low"
  - 涉及文件：`deepseek_client.py`
  - 验收标准：3 个信号 + 20 条消息 → "high"；1 个信号 + 3 条消息 → "medium"；0 个信号 + 2 条消息 → "low"

### #170 实现 compute_adaptive_effort 方法

- [ ] 在 `DeepSeekClient` 中新增 `compute_adaptive_effort()` 方法
  - 参数：`perception_data`、`step`、`has_tool_calls`、`config`
  - 非思考模式不传递 reasoning_effort，返回空字符串
  - 自适应未启用时使用 v3.1 固定逻辑：工具调用轮次 max，其余用配置值
  - 工具调用轮次（step > 1 或 has_tool_calls）强制 max
  - 复杂度高 → max，其余 → high
  - 涉及文件：`deepseek_client.py`
  - 验收标准：非思考模式 → 返回 ""；工具调用轮次 → "max"；复杂度低 + 非工具调用 → "high"

### #171 集成自适应 effort 到 analyze_with_thinking

- [ ] 在 `analyze_with_thinking()` 方法中集成自适应 reasoning_effort
  - 当 `config.deepseek_optimization.adaptive_effort_enabled` 为 True 时，调用 `compute_adaptive_effort()` 计算 effort
  - 将计算结果设置到请求体的 `extra_body.thinking.reasoning_effort`
  - 非自适应模式保持 v3.1 的固定逻辑
  - 涉及文件：`deepseek_client.py`
  - 验收标准：adaptive_effort_enabled=True → 请求体包含动态 reasoning_effort；adaptive_effort_enabled=False → 使用 v3.1 固定逻辑

---

## 4. 步骤分类器

### #172 新增 StepCategory 枚举和 StepClassification 数据类

- [ ] 在新文件 `step_classifier.py` 中定义 `StepCategory` 枚举和 `StepClassification` 数据类
  - StepCategory 枚举值：FINAL、CONTINUE、TOOL_CALL、FILTERED、THINK_ONLY、INVALID、FAILED
  - StepClassification 字段：`category: StepCategory`（默认 INVALID）、`tool_name: str`、`has_reasoning_content: bool`、`has_content: bool`、`signature: str`
  - 涉及文件：`step_classifier.py`（新增）
  - 验收标准：StepCategory 枚举包含 7 个值；StepClassification 可正常实例化

### #173 实现 StepClassifier.classify 方法

- [ ] 在 `StepClassifier` 中实现 `classify()` 方法
  - 分类逻辑：error 非空 → FAILED；思考模式 + 有 reasoning_content + 无 content + 无 tool_calls → THINK_ONLY；无 content + 无 tool_calls → INVALID；有 tool_calls → TOOL_CALL（含签名计算）；content 包含最终决策 → FINAL；其余 → FILTERED
  - `_compute_signature()`：计算 tool_name + 参数哈希的签名
  - `_is_final_decision()`：检测 content 中是否包含 submit_decision 或明确决策关键词
  - 涉及文件：`step_classifier.py`
  - 验收标准：LLM 返回工具调用 → TOOL_CALL；思考模式仅 reasoning_content → THINK_ONLY；空响应 → INVALID；包含 submit_decision → FINAL

### #174 实现 get_handling_strategy 方法

- [ ] 在 `StepClassifier` 中实现 `get_handling_strategy()` 方法
  - 返回分类对应的处理策略标识：final → "end_loop"、tool-call → "execute_tool"、think-only → "retry_with_reasoning"、filtered → "retry_with_hint"、invalid → "retry"、failed → "handle_error"
  - 涉及文件：`step_classifier.py`
  - 验收标准：FINAL → "end_loop"；THINK_ONLY → "retry_with_reasoning"；INVALID → "retry"

---

## 5. 循环检测

### #175 新增 LoopDetectionResult 数据类

- [ ] 在新文件 `loop_detector.py` 中定义 `LoopDetectionResult` 数据类
  - 字段：`is_loop: bool`（默认 False）、`loop_type: str`（"repeated_step" / "ngram_text" / ""）、`repeated_signature: str`、`repeat_count: int`、`ngram_pattern: str`
  - 涉及文件：`loop_detector.py`（新增）
  - 验收标准：LoopDetectionResult 可正常实例化，默认值符合预期

### #176 实现 LoopDetector 重复步骤签名检测

- [ ] 在 `LoopDetector` 中实现 `_check_repeated_step()` 方法
  - 维护 `_step_signatures: dict[str, int]` 签名计数器
  - 当同一签名出现次数超过 `config.deepseek_optimization.repeated_step_threshold`（默认 3）时判定为循环
  - 检测到循环时递增 `_consecutive_detections` 计数器
  - 涉及文件：`loop_detector.py`
  - 验收标准：同一签名第 3 次出现 → is_loop=True, loop_type="repeated_step"；第 2 次出现 → is_loop=False

### #177 实现 LoopDetector n-gram 文本循环检测

- [ ] 在 `LoopDetector` 中实现 `_check_ngram_loop()` 方法
  - 提取响应文本中所有 n-gram（窗口大小从配置读取，默认 3）
  - 检测同一 n-gram 出现次数超过阈值（默认 3）的循环
  - 忽略纯空白 n-gram
  - 文本长度不足 20 字符时跳过检测
  - 涉及文件：`loop_detector.py`
  - 验收标准：文本中 "我认为应该" 出现 4 次 → is_loop=True, loop_type="ngram_text"；短文本 → 不检测

### #178 实现 LoopDetector.detect 和 get_interruption_message

- [ ] 在 `LoopDetector` 中实现 `detect()` 和 `get_interruption_message()` 方法
  - detect()：依次调用 `_check_repeated_step()` 和 `_check_ngram_loop()`，任一检测到循环即返回
  - get_interruption_message()：repeated_step → "错误：重复调用同一工具，请尝试其他工具或直接提交决策"；ngram_text → "提示：你的输出中存在重复表述，请避免重复并直接给出决策"
  - reset()：每次决策循环开始时清空签名计数器和连续检测计数
  - 涉及文件：`loop_detector.py`
  - 验收标准：检测到重复步骤 → 返回对应中断消息；检测到 n-gram 循环 → 返回对应中断消息；reset 后状态清空

---

## 6. strict 模式集成

### #179 实现 _apply_strict_mode 方法

- [ ] 在 `DeepSeekClient` 中新增 `_apply_strict_mode()` 方法
  - 检查 strict 模式启用状态（兼容 v3.1 的 `deepseek_v4.strict_mode_enabled` 和 v3.2 的 `deepseek_optimization.strict_mode_enabled`）
  - 启用时：切换 base_url 为 `https://api.deepseek.com/beta`，为每个工具添加 `strict: true` 和 `parameters.additionalProperties: false`
  - 在请求体副本上操作
  - 涉及文件：`deepseek_client.py`
  - 验收标准：strict 模式启用 → base_url 为 beta 端点 + 工具定义包含 strict: true；未启用 → 请求体不变

### #180 实现 _send_with_strict_fallback 方法

- [ ] 在 `DeepSeekClient` 中新增 `_send_with_strict_fallback()` 方法
  - 先尝试 strict 模式请求（beta 端点）
  - beta 端点返回 404 或 503 时自动降级为标准端点重试
  - 降级时移除 strict 标记和 additionalProperties
  - 记录降级警告日志
  - 涉及文件：`deepseek_client.py`
  - 验收标准：beta 端点 404 → 自动降级为标准端点 → 重试成功 → 记录警告

### #181 集成 strict 模式到 API 调用流程

- [ ] 在 `analyze_with_thinking()` 和 `analyze_with_tools()` 中集成 strict 模式
  - 发送请求前调用 `_apply_strict_mode()` 构建请求体
  - 使用 `_send_with_strict_fallback()` 替代直接 `_send_request()`
  - strict 模式 + 思考模式组合冲突时优先保留思考模式，降级 strict 模式
  - 涉及文件：`deepseek_client.py`
  - 验收标准：strict_mode_enabled=True → 请求使用 beta 端点；beta 不可用 → 自动降级；组合冲突 → 保留思考模式

---

## 7. 思考模式参数兼容

### #182 实现思考模式参数互斥处理

- [ ] 在 `DeepSeekClient` 中实现思考模式参数互斥处理
  - 思考模式启用时，在请求构建前自动移除 temperature、top_p、presence_penalty、frequency_penalty
  - 每次请求前重新检查思考模式状态，确保参数一致性
  - 涉及文件：`deepseek_client.py`
  - 验收标准：thinking_enabled=True → API 请求体中不包含 temperature/top_p/presence_penalty/frequency_penalty；thinking_enabled=False → 正常传递

### #183 实现参数互斥启动警告

- [ ] 在插件初始化或配置加载时检查参数互斥并记录警告
  - 当 thinking_enabled=True 且配置了互斥参数值时，记录警告日志："思考模式下 temperature 参数不生效"
  - 不修改用户配置文件中的参数值
  - 涉及文件：`deepseek_client.py` 或 `plugin.py`
  - 验收标准：thinking_enabled=True + temperature=0.7 → 启动日志中出现参数互斥警告

---

## 8. DeepSeek 专用 prompt 优化

### #184 新增 DeepSeek 专用 prompt 模板

- [ ] 在 `prompts.py` 中新增 `DEEPSEEK_WORKFLOW_PROMPT` 和 `DEEPSEEK_TOOL_PROTOCOL` 常量
  - DEEPSEEK_WORKFLOW_PROMPT：6 步工作流指导（Understand → Explore → Plan → Execute → Verify → Summarize）
  - DEEPSEEK_TOOL_PROTOCOL：5 步工具使用协议 + "不要重复调用同一工具"提示
  - 涉及文件：`prompts.py`
  - 验收标准：两个模板常量可正常使用 format() 填充；内容包含 6 步工作流和 5 步工具协议

### #185 新增场景示例和决策边界模板

- [ ] 在 `prompts.py` 中新增 `SCENARIO_EXAMPLES` 和 `DECISION_BOUNDARY` 常量
  - SCENARIO_EXAMPLES：4 种场景示例（silence_break、missed_reply、topic_supplement、no_trigger），每种包含场景描述和 JSON 决策样例
  - DECISION_BOUNDARY：不应触发的边界条件列表（对话节奏正常、话题无关、冷却期内、用户互相讨论、纯表情包寒暄）
  - 涉及文件：`prompts.py`
  - 验收标准：SCENARIO_EXAMPLES 包含 4 种场景；DECISION_BOUNDARY 包含 5 条以上边界条件

### #186 扩展 build_system_prompt 支持 DeepSeek 专用 prompt

- [ ] 在 `build_system_prompt()` 中新增 `deepseek_prompt_enabled: bool = False`、`scenario_signals: list[str] | None = None`、`prompt_optimization_enabled: bool = False` 参数
  - deepseek_prompt_enabled=True 时追加 DEEPSEEK_WORKFLOW_PROMPT；react_enabled=True 时追加 DEEPSEEK_TOOL_PROTOCOL
  - prompt_optimization_enabled=True 且有 scenario_signals 时注入对应场景示例
  - prompt_optimization_enabled=True 时追加 DECISION_BOUNDARY
  - 不影响现有调用行为（默认参数均为 False/None）
  - 涉及文件：`prompts.py`
  - 验收标准：deepseek_prompt_enabled=False → 输出与 v3.1 一致；deepseek_prompt_enabled=True → 包含工作流和工具协议；prompt_optimization_enabled=True → 包含场景示例和决策边界

---

## 9. SSE 超时与重试策略

### #187 实现 _send_with_enhanced_retry 方法

- [ ] 在 `DeepSeekClient` 中新增 `_send_with_enhanced_retry()` 异步方法
  - 当 `config.deepseek_optimization.enhanced_retry_enabled` 为 False 时，使用 v3.1 的固定重试逻辑
  - 启用时：SSE 超时检测（通过 asyncio.wait_for 包装），超时时间从 `sse_chunk_timeout_seconds` 读取
  - 指数退避重试：base_delay * 2^k，最大退避时间 max_backoff，最多 max_retries 次
  - 重试耗尽后尝试非流式调用（移除 stream 参数）
  - 非流式也失败时抛出最后一个错误
  - 涉及文件：`deepseek_client.py`
  - 验收标准：第 1 次重试延迟 500ms → 第 2 次延迟 1000ms → 第 3 次延迟 2000ms；10 次重试耗尽 → 尝试非流式

### #188 集成增强重试到 API 调用流程

- [ ] 在 `analyze_with_thinking()` 和 `analyze_with_tools()` 中集成增强重试
  - 当 `config.deepseek_optimization.enhanced_retry_enabled` 为 True 时，使用 `_send_with_enhanced_retry()` 替代 `_send_request()`
  - 未启用时保持 v3.1 的固定重试逻辑
  - 涉及文件：`deepseek_client.py`
  - 验收标准：enhanced_retry_enabled=True → SSE 超时触发指数退避重试；enhanced_retry_enabled=False → 使用 v3.1 固定重试

---

## 10. 感知增强模块

### #189 新增 TopicInfo、SentimentInfo、ParticipantProfile 数据类

- [ ] 在新文件 `perception_enhancer.py` 中定义 3 个数据类
  - TopicInfo：`topic: str`（最大 100 字符）、`topic_relevance: float`（0.0-1.0）、`topic_changed: bool`、`previous_topic: str`（最大 100 字符）、`confidence: float`（0.0-1.0）
  - SentimentInfo：`polarity: str`（positive/neutral/negative）、`confidence: float`（0.0-1.0）、`sentiment_shift: bool`、`shift_direction: str`
  - ParticipantProfile：`participant_id: str`、`message_frequency: int`、`last_active_at: float`、`interaction_pattern: str`（frequent_asker/casual_talker/bot_interactor/unknown）、`mention_bot: bool`
  - 涉及文件：`perception_enhancer.py`（新增）
  - 验收标准：3 个数据类可正常实例化，字段类型和默认值符合预期

### #190 新增感知增强注入模板

- [ ] 在 `prompts.py` 中新增 `TOPIC_TRACKING_TEMPLATE`、`SENTIMENT_ANALYSIS_TEMPLATE`、`PARTICIPANT_PROFILE_TEMPLATE` 常量
  - TOPIC_TRACKING_TEMPLATE：包含当前话题、话题关联度、话题切换信息
  - SENTIMENT_ANALYSIS_TEMPLATE：包含情感极性、置信度、情感转折信息
  - PARTICIPANT_PROFILE_TEMPLATE：包含参与者行为摘要
  - 涉及文件：`prompts.py`
  - 验收标准：3 个模板常量可正常使用 format() 填充

### #191 实现 PerceptionEnhancer.analyze_topic 方法

- [ ] 在 `PerceptionEnhancer` 中实现 `analyze_topic()` 异步方法
  - 当 `config.agent_optimization.topic_tracking_enabled` 为 False 时返回 None
  - 消息不足 3 条时跳过，返回 None
  - 通过 `DeepSeekClient.analyze_with_json_output()` 调用 LLM 识别话题
  - 解析 JSON 响应，构建 TopicInfo（topic 截断到 100 字符，topic_relevance 截断到 0.0-1.0）
  - LLM 调用失败或 JSON 解析失败时返回 None，记录警告日志
  - 涉及文件：`perception_enhancer.py`
  - 验收标准：3+ 条消息 + LLM 返回有效 JSON → 返回 TopicInfo；消息不足 → None；LLM 失败 → None + 警告日志

### #192 实现 PerceptionEnhancer.analyze_sentiment 方法

- [ ] 在 `PerceptionEnhancer` 中实现 `analyze_sentiment()` 异步方法
  - 当 `config.agent_optimization.sentiment_analysis_enabled` 为 False 时返回 None
  - 消息不足 3 条时跳过
  - 通过 LLM 分析情感极性和转折
  - 极性值不在预定义范围内时降级为 "neutral"
  - LLM 调用失败时返回 None，记录警告日志
  - 不在提示词中包含用户原始消息内容
  - 涉及文件：`perception_enhancer.py`
  - 验收标准：LLM 返回有效情感 → 返回 SentimentInfo；极性异常 → 降级为 neutral；LLM 失败 → None + 警告日志

### #193 实现 PerceptionEnhancer.build_participant_profiles 方法

- [ ] 在 `PerceptionEnhancer` 中实现 `build_participant_profiles()` 方法（纯本地操作）
  - 当 `config.agent_optimization.participant_profile_enabled` 为 False 时返回空列表
  - 检查内存缓存（5 分钟有效期），缓存有效时直接返回
  - 从消息元数据中提取参与者信息：发言频率、最近发言时间、@bot 检测
  - 判断互动模式：发言 ≥ 5 → frequent_asker，@bot → bot_interactor，其余 → casual_talker
  - 容量限制：按发言频率排序，截取前 `participant_profile_max_entries` 条
  - 更新内存缓存
  - 涉及文件：`perception_enhancer.py`
  - 验收标准：3 个活跃用户 → 返回 3 个 ParticipantProfile；5 分钟内第 2 次调用 → 返回缓存；超过 max_entries → 截取

### #194 实现 PerceptionEnhancer 格式化方法

- [ ] 在 `PerceptionEnhancer` 中实现 `format_topic_for_prompt()`、`format_sentiment_for_prompt()`、`format_profiles_for_prompt()` 方法
  - 使用 prompts.py 中的模板格式化
  - None/空输入返回空字符串
  - 涉及文件：`perception_enhancer.py`
  - 验收标准：TopicInfo → 格式化为含话题和关联度的文本；None → 空字符串

---

## 11. 记忆增强注入

### #195 扩展 AgentMemoryEntry 数据类

- [ ] 在 `agent_memory.py` 中为 `AgentMemoryEntry` 新增 2 个字段
  - `category: str = "unknown"`（"triggered" / "not_triggered" / "unknown"）
  - `context_relevance: float = 0.0`（0.0-1.0）
  - 涉及文件：`agent_memory.py`
  - 验收标准：AgentMemoryEntry 新增字段可正常实例化，默认值符合预期

### #196 新增增强记忆模板

- [ ] 在 `prompts.py` 中新增 `ENHANCED_MEMORY_HISTORY_TEMPLATE` 和 `ENHANCED_MEMORY_ENTRY_TEMPLATE` 常量
  - ENHANCED_MEMORY_HISTORY_TEMPLATE：包含 `[历史决策记忆]` 标题、`{memory_entries}` 占位符、注意事项
  - ENHANCED_MEMORY_ENTRY_TEMPLATE：`"- [{category}] {time}：{summary}（行动: {action_taken}，关联度: {context_relevance:.1f}）"`
  - 涉及文件：`prompts.py`
  - 验收标准：模板常量可正常使用 format() 填充

### #197 实现记忆分类和上下文关联

- [ ] 在 `AgentMemory` 中实现 `_classify_memory()` 和 `_compute_context_relevance()` 方法
  - _classify_memory()：action_taken 非空且非 skip/no_action → "triggered"；trigger_reason 包含 "未触发" → "not_triggered"；其余 → "unknown"
  - _compute_context_relevance()：冷场信号 + 摘要含"冷场" → +0.5；漏回信号 + 摘要含"漏回" → +0.5；话题关联 → +0.3；截断到 1.0
  - 涉及文件：`agent_memory.py`
  - 验收标准：action_taken="silence_break" → category="triggered"；冷场信号 + 冷场摘要 → context_relevance ≥ 0.5

### #198 实现语义去重和容量动态调整

- [ ] 在 `AgentMemory` 中实现 `_deduplicate_memories()` 和 `_adjust_capacity()` 方法
  - _deduplicate_memories()：提取摘要中意图关键词（逗号前部分或前 30 字符）作为去重 key，同一 key 仅保留权重最高的
  - _adjust_capacity()：根据 token 预算动态调整记忆条数，超过 80% 预算时减少条数
  - 涉及文件：`agent_memory.py`
  - 验收标准：3 条摘要关键词相同 → 仅保留权重最高的 1 条；token 预算紧张 → 记忆条数减少

### #199 实现 get_enhanced_memories 和 format_enhanced_memories_for_prompt

- [ ] 在 `AgentMemory` 中实现 `get_enhanced_memories()` 异步方法和 `format_enhanced_memories_for_prompt()` 方法
  - get_enhanced_memories()：调用现有 get_memories() 获取基础列表 → 分类 → 计算上下文关联 → 去重 → 按关联度排序 → 容量调整
  - format_enhanced_memories_for_prompt()：使用 ENHANCED_MEMORY_HISTORY_TEMPLATE 和 ENHANCED_MEMORY_ENTRY_TEMPLATE 格式化
  - 空列表返回空字符串
  - 涉及文件：`agent_memory.py`
  - 验收标准：5 条历史记忆 → 分类 + 去重 + 排序 → 格式化为含分类标签和关联度的文本；空列表 → 空字符串

---

## 12. 上下文感知压缩

### #200 实现 soft_prune_with_relevance 方法

- [ ] 在 `OverflowManager` 中新增 `soft_prune_with_relevance()` 方法
  - 参数：`messages`、`threshold`、`perception_signals: list[str] | None`
  - 无感知信号时降级为 v3.1 的 `soft_prune()`
  - 有感知信号时：与信号相关的工具输出放宽截断阈值（2 倍），无关的正常截断
  - 在消息副本上操作
  - 涉及文件：`overflow_manager.py`
  - 验收标准：2 条工具输出，1 条含感知信号关键词 → 放宽截断；1 条无关 → 正常截断；无感知信号 → 降级为 v3.1 逻辑

### #201 实现 hard_prune_with_priority 和 _compute_message_priority

- [ ] 在 `OverflowManager` 中新增 `hard_prune_with_priority()` 和 `_compute_message_priority()` 方法
  - _compute_message_priority()：包含感知信号关键词 → 2（高）；工具输出且无关 → 0（低）；其余 → 1（中）
  - hard_prune_with_priority()：按优先级从低到高移除消息，高优先级最后移除
  - 无感知信号时降级为 v3.1 的 `hard_prune()`
  - 涉及文件：`overflow_manager.py`
  - 验收标准：包含 @bot 的消息 → 优先级 2 → 最后被移除；无关工具输出 → 优先级 0 → 最先被移除

### #202 扩展 get_managed_context 支持感知信号

- [ ] 在 `OverflowManager.get_managed_context()` 中新增 `perception_signals: list[str] | None = None` 参数
  - 当 `config.agent_optimization.context_aware_compress_enabled` 为 True 时，使用 `soft_prune_with_relevance()` 和 `hard_prune_with_priority()`
  - 未启用时使用 v3.1 的 `soft_prune()` 和 `hard_prune()`
  - 涉及文件：`overflow_manager.py`
  - 验收标准：context_aware_compress_enabled=True + 有感知信号 → 使用上下文感知剪枝；未启用 → 使用 v3.1 逻辑

---

## 13. 反思子智能体增强

### #203 新增 EnhancedReflectionResult 数据类

- [ ] 在 `agent.py` 中定义 `EnhancedReflectionResult` 数据类，继承 `ReflectionResult`
  - 新增字段：`dimensions: dict[str, float]`（默认包含 consistency/topic_relevance/timing_rationality/duplicate_risk，各 0.5）、`veto_dimension: str`
  - 涉及文件：`agent.py`
  - 验收标准：EnhancedReflectionResult 可正常实例化，dimensions 包含 4 个维度默认值

### #204 新增增强反思提示词模板

- [ ] 在 `prompts.py` 中新增 `ENHANCED_REFLECTION_USER_TEMPLATE` 常量
  - 包含感知数据、决策结果、话题信息、情感信息
  - 要求从 4 个维度评估：consistency、topic_relevance、timing_rationality、duplicate_risk
  - 输出 JSON 格式：verdict、reason、dimensions、veto_dimension
  - 涉及文件：`prompts.py`
  - 验收标准：模板包含 4 个评估维度和 JSON 输出格式要求

### #205 实现增强反思输入构建和结果解析

- [ ] 在 `AgentCore` 中实现 `_build_enhanced_reflection_input()` 和 `_parse_enhanced_reflection()` 方法
  - _build_enhanced_reflection_input()：在 v3.1 基础上追加话题信息和情感信息
  - _parse_enhanced_reflection()：解析 4 个维度评分，缺失维度使用默认值 0.5，评分截断到 0.0-1.0
  - 加权平均计算：各维度等权，加权平均 < 0.5 时接受否决
  - 涉及文件：`agent.py`
  - 验收标准：反思输入包含话题和情感信息；维度评分缺失 → 默认 0.5；评分超出范围 → 截断

---

## 14. 决策质量统计

### #206 新增 DecisionQualityMetrics 和内存级 DecisionRecord 数据类

- [ ] 在新文件 `quality_stats.py` 中定义 2 个数据类
  - DecisionQualityMetrics：`trigger_accuracy: float`、`false_trigger_rate: float`、`missed_trigger_rate: float`、`avg_react_steps: float`、`avg_decision_duration_ms: float`、`tool_hit_rate: float`、`sample_size: int`
  - 内存级 DecisionRecord：`stream_id: str`、`triggered: bool`、`vetoed: bool`、`error: bool`、`has_signal: bool`、`react_steps: int`、`duration_ms: float`、`tool_calls: int`、`tool_hits: int`
  - 涉及文件：`quality_stats.py`（新增）
  - 验收标准：2 个数据类可正常实例化，字段类型和默认值符合预期

### #207 实现 QualityStats 核心方法

- [ ] 在 `QualityStats` 中实现 `record_decision()` 和 `get_metrics()` 方法
  - record_decision()：将决策记录追加到 `collections.deque(maxlen=1000)`
  - get_metrics()：从滑动窗口（大小从配置读取）中计算指标
  - 触发准确率 = 正常触发 / 总触发；误触发率 = 被否决或异常的触发 / 总触发；漏触发率 = 未触发但存在明确信号 / 总未触发
  - 效率指标：平均步数、平均耗时、工具命中率
  - 涉及文件：`quality_stats.py`
  - 验收标准：100 次决策中 30 次触发、28 次正常、2 次异常 → 触发准确率 93.3%；70 次未触发中 5 次有信号 → 漏触发率 7.1%

### #208 实现 QualityStats 指标广播

- [ ] 在 `QualityStats` 中实现指标广播逻辑
  - 每次 `record_decision()` 后通过 EventBus 广播 `decision_quality` 事件
  - 事件数据包含 DecisionQualityMetrics 的所有字段
  - 广播失败时不影响决策循环
  - 涉及文件：`quality_stats.py`
  - 验收标准：决策记录后 EventBus 收到 decision_quality 事件；广播失败 → 不阻塞

---

## 15. AgentCore 集成

### #209 PerceptionData 新增 v3.2 字段

- [ ] 在 `agent.py` 的 `PerceptionData` 数据类中新增 3 个字段
  - `topic_info: TopicInfo | None = None`
  - `sentiment_info: SentimentInfo | None = None`
  - `participant_profiles: list[ParticipantProfile] = field(default_factory=list)`
  - 涉及文件：`agent.py`
  - 验收标准：PerceptionData 实例包含 3 个新字段，默认值符合预期

### #210 perceive 阶段集成感知增强

- [ ] 在 `AgentCore.perceive()` 方法中集成感知增强逻辑
  - 当 `self._perception_enhancer is not None` 时，依次调用话题追踪、情感分析、参与者画像
  - 各功能受对应配置开关控制
  - 感知增强失败时不影响决策循环（降级为无对应信息）
  - 感知增强结果通过 EventBus 广播（topic_analyzed、sentiment_analyzed 事件）
  - 涉及文件：`agent.py`
  - 验收标准：topic_tracking_enabled=True → perception.topic_info 非空；分析失败 → topic_info 为 None + 决策循环正常

### #211 perceive 阶段集成记忆增强注入

- [ ] 在 `AgentCore.perceive()` 方法中集成记忆增强注入
  - 当 `config.agent_optimization.enhanced_memory_enabled` 为 True 时，调用 `get_enhanced_memories()` 替代 `get_memories()`
  - 未启用时保持 v3.1 的 `get_memories()` 行为不变
  - 涉及文件：`agent.py`
  - 验收标准：enhanced_memory_enabled=True → 使用增强记忆格式和排序；enhanced_memory_enabled=False → 使用 v3.1 原始格式

### #212 _react_loop 集成步骤分类器

- [ ] 在 `AgentCore._react_loop()` 方法中集成步骤分类器
  - 当 `config.deepseek_optimization.step_classifier_enabled` 为 True 时，使用 `StepClassifier.classify()` 替代 `has_tool_calls` 判断
  - 根据分类结果执行不同处理策略：FINAL → 结束循环；TOOL_CALL → 执行工具；THINK_ONLY → 追加 reasoning_content 重新请求（消耗步数）；FILTERED → 追加格式提示（不消耗步数）；INVALID → 重试（最多 2 次，不消耗步数）；FAILED → 按重试策略处理
  - 连续 3 次 THINK_ONLY 步骤时结束循环，action_taken="error_think_only_loop"
  - 分类结果通过 EventBus 广播 `step_classified` 事件
  - 未启用时使用 v3.1 的 has_tool_calls 判断
  - 涉及文件：`agent.py`
  - 验收标准：step_classifier_enabled=True → 使用步骤分类器；THINK_ONLY → 追加 reasoning_content + 步数+1；INVALID → 最多重试 2 次；未启用 → v3.1 逻辑

### #213 _react_loop 集成循环检测

- [ ] 在 `AgentCore._react_loop()` 方法中集成循环检测
  - 当 `config.deepseek_optimization.loop_detection_enabled` 为 True 时，步骤分类后调用 `LoopDetector.detect()`
  - 重复步骤签名循环：拒绝工具调用，返回错误信息给 LLM
  - n-gram 文本循环：追加系统消息提示 LLM 避免重复
  - 连续 3 次循环检测触发后强制结束 ReAct 循环
  - 每次决策循环开始时调用 `LoopDetector.reset()`
  - 循环检测触发不消耗步数
  - 检测结果通过 EventBus 广播 `loop_detected` 事件
  - 涉及文件：`agent.py`
  - 验收标准：重复步骤签名 → 工具调用被拒绝 + LLM 收到提示；n-gram 循环 → 追加提示消息；连续 3 次 → 强制结束循环

### #214 _react_loop 集成自适应步数

- [ ] 在 `AgentCore._react_loop()` 方法中集成自适应步数
  - 当 `config.agent_optimization.adaptive_steps_enabled` 为 True 时，根据感知数据复杂度动态调整最大步数
  - 简单场景（1 个信号、消息 < 5）：建议 1-2 步
  - 普通场景（1-2 个信号、消息 5-15）：建议 2-3 步
  - 复杂场景（3+ 信号、消息 15+）：建议 3-5 步
  - 自适应步数不超过配置的 max_react_steps 上限
  - 计算异常时降级为默认 max_react_steps
  - 涉及文件：`agent.py`
  - 验收标准：简单场景 → max_steps=2；复杂场景 → max_steps=4；不超过 max_react_steps

### #215 _react_loop 集成感知信号传递和增强用户提示词

- [ ] 在 `AgentCore._react_loop()` 方法中集成感知信号传递和增强用户提示词构建
  - 构建 `_extract_perception_signals()`：从 PerceptionData 提取感知信号关键词列表
  - 构建 `_build_enhanced_user_prompt()`：将话题追踪、情感分析、参与者画像信息格式化注入到用户提示词
  - 构建 `_detect_scenario_signals()`：检测当前场景信号类型（silence_break、missed_reply 等）
  - 将感知信号传递给 `OverflowManager.get_managed_context()`
  - 涉及文件：`agent.py`
  - 验收标准：感知信号正确提取 → 传递给溢出管理器；用户提示词包含话题/情感/画像段落

### #216 _react_loop 集成 DeepSeek 专用 prompt 和场景示例

- [ ] 在 `AgentCore._react_loop()` 方法中集成 DeepSeek 专用 prompt
  - 调用 `build_system_prompt()` 时传入 `deepseek_prompt_enabled` 和 `scenario_signals` 参数
  - 模型名称包含 "deepseek" 时自动启用 DeepSeek 专用 prompt（即使配置未显式开启）
  - 涉及文件：`agent.py`
  - 验收标准：deepseek_prompt_enabled=True → 系统提示词包含工作流和工具协议；模型含 "deepseek" → 自动启用

### #217 reflect 阶段集成反思子智能体增强

- [ ] 在 `AgentCore._reflect_with_subagent()` 方法中集成增强反思
  - 当 `config.agent_optimization.enhanced_reflection_enabled` 为 True 时，使用 `_build_enhanced_reflection_input()` 和 `_parse_enhanced_reflection()`
  - 未启用时使用 v3.1 的基础反思逻辑
  - 涉及文件：`agent.py`
  - 验收标准：enhanced_reflection_enabled=True → 反思使用 4 维度评估；未启用 → v3.1 基础评估

### #218 AgentCore 新增依赖注入

- [ ] 在 `AgentCore.__init__()` 中新增 4 个可选依赖字段
  - `self._step_classifier: StepClassifier | None = None`
  - `self._loop_detector: LoopDetector | None = None`
  - `self._perception_enhancer: PerceptionEnhancer | None = None`
  - `self._quality_stats: QualityStats | None = None`
  - 涉及文件：`agent.py`
  - 验收标准：AgentCore 可正常实例化，新字段默认为 None

### #219 决策循环完成后记录质量统计

- [ ] 在 `AgentCore.decision_loop()` 完成后调用 `QualityStats.record_decision()`
  - 构建 DecisionRecord：从决策结果中提取 triggered/vetoed/error/has_signal/react_steps/duration_ms/tool_calls/tool_hits
  - 当 `self._quality_stats is not None` 时记录
  - 涉及文件：`agent.py`
  - 验收标准：决策完成后 QualityStats 收到 DecisionRecord；统计数据可通过 get_metrics() 查询

---

## 16. WebUI 扩展

### #220 新增决策质量统计 API 端点

- [ ] 在 `webui.py` 中新增 2 个 API 端点处理方法
  - `_handle_quality_metrics()`：GET /api/proactive-chat/quality → 返回 DecisionQualityMetrics
  - `_handle_quality_details()`：GET /api/proactive-chat/quality/details → 返回详细质量统计
  - 每个端点检查 `self._quality_stats` 是否可用
  - 涉及文件：`webui.py`
  - 验收标准：端点可正常响应；QualityStats 未初始化时返回 `{"success": false, "error": "决策质量统计未启用"}`

### #221 注册决策质量统计路由

- [ ] 在 `WebUIServer.start()` 方法中注册 2 个决策质量统计路由
  - 添加路由映射到对应的处理方法
  - 涉及文件：`webui.py`
  - 验收标准：路由注册后 HTTP 请求可正确路由到处理方法

### #222 stats 接口扩展

- [ ] 在 `GET /api/proactive-chat/stats` 响应中新增 `quality_stats`、`deepseek_optimization`、`agent_optimization` 字段
  - quality_stats：trigger_accuracy、false_trigger_rate、missed_trigger_rate、sample_size
  - deepseek_optimization：step_classifier_enabled、loop_detection_enabled、strict_mode_enabled、adaptive_effort_enabled、enhanced_retry_enabled
  - agent_optimization：topic_tracking_enabled、sentiment_analysis_enabled、participant_profile_enabled、enhanced_memory_enabled、enhanced_reflection_enabled、prompt_optimization_enabled、context_aware_compress_enabled
  - 涉及文件：`webui.py`
  - 验收标准：stats 响应包含 3 个新增字段；各功能状态正确反映配置值

### #223 WebSocket 新增事件类型

- [ ] 在 WebSocket 推送中支持 `decision_quality`、`step_classified`、`loop_detected`、`topic_analyzed`、`sentiment_analyzed` 事件类型
  - 确保 EventBus 的事件可正确通过 WebSocket 推送到前端
  - 涉及文件：`webui.py`
  - 验收标准：决策完成后前端收到 decision_quality 事件；步骤分类后前端收到 step_classified 事件

---

## 17. plugin.py 集成

### #224 初始化新模块并注入依赖

- [ ] 在 `plugin.py` 的初始化逻辑中创建新模块实例并注入到 AgentCore
  - 创建 `StepClassifier` 实例
  - 创建 `LoopDetector` 实例
  - 创建 `PerceptionEnhancer` 实例（依赖 DeepSeekClient、EventBus）
  - 创建 `QualityStats` 实例（依赖 EventBus）
  - 将新模块注入到 AgentCore：`agent._step_classifier = step_classifier` 等
  - 将 QualityStats 注入到 WebUIServer
  - 涉及文件：`plugin.py`
  - 验收标准：插件启动后 AgentCore 的 4 个新依赖不为 None；WebUIServer 的 _quality_stats 不为 None

---

## 18. 测试

### #225 配置扩展单元测试

- [ ] 在 `tests/test_config.py` 中扩展测试
  - 测试 `DeepseekOptimizationConfig` 的 14 个字段默认值
  - 测试 `AgentOptimizationConfig` 的 10 个字段默认值
  - 测试 ProactiveChatConfig 包含新配置段字段
  - 测试向后兼容性（v3.1 配置加载后新字段使用默认值）
  - 测试 config_version 升级到 3.2.0
  - 涉及文件：`tests/test_config.py`（扩展）
  - 验收标准：所有测试通过；新配置段默认值正确；v3.1 配置向后兼容

### #226 reasoning_content 回传健壮性单元测试

- [ ] 在 `tests/test_deepseek_client.py` 中扩展测试
  - 测试 `_validate_reasoning_content()` 检测缺失的 reasoning_content
  - 测试 `_fix_reasoning_content()` 补全逻辑
  - 测试 400 错误自动修复流程
  - 测试修复失败后降级为非思考模式
  - 测试 robust_reasoning_enabled=False 时使用 v3.1 逻辑
  - 涉及文件：`tests/test_deepseek_client.py`（扩展）
  - 验收标准：所有测试通过；覆盖验证、修复、降级场景

### #227 reasoning_effort 自适应调节单元测试

- [ ] 在 `tests/test_deepseek_client.py` 中扩展测试
  - 测试 `_assess_complexity()` 各复杂度场景
  - 测试 `compute_adaptive_effort()` 各映射规则
  - 测试非思考模式不传递 reasoning_effort
  - 测试工具调用轮次强制 max
  - 测试无效 effort 值映射
  - 涉及文件：`tests/test_deepseek_client.py`（扩展）
  - 验收标准：所有测试通过；覆盖复杂度评估、effort 映射、边界场景

### #228 步骤分类器单元测试

- [ ] 在 `tests/test_step_classifier.py` 中编写单元测试
  - 测试 7 类步骤分类正确性（FINAL、TOOL_CALL、THINK_ONLY、INVALID、FILTERED、FAILED、CONTINUE）
  - 测试 `_compute_signature()` 签名计算
  - 测试 `get_handling_strategy()` 策略映射
  - 测试 think-only 步骤分类条件
  - 测试 filtered 步骤分类条件
  - 涉及文件：`tests/test_step_classifier.py`（新增）
  - 验收标准：所有测试通过；覆盖 7 类分类和策略映射

### #229 循环检测单元测试

- [ ] 在 `tests/test_loop_detector.py` 中编写单元测试
  - 测试重复步骤签名检测（阈值触发、未触发）
  - 测试 n-gram 文本循环检测（重复模式检测、短文本跳过）
  - 测试 `get_interruption_message()` 中断消息
  - 测试 `reset()` 状态重置
  - 测试连续检测强制结束
  - 涉及文件：`tests/test_loop_detector.py`（新增）
  - 验收标准：所有测试通过；覆盖签名检测、n-gram 检测、重置、强制结束

### #230 strict 模式单元测试

- [ ] 在 `tests/test_deepseek_client.py` 中扩展测试
  - 测试 `_apply_strict_mode()` 请求体构建（beta 端点、strict: true、additionalProperties: false）
  - 测试 `_send_with_strict_fallback()` 降级逻辑
  - 测试 strict 模式 + 思考模式组合
  - 测试 v3.1 配置兼容（deepseek_v4.strict_mode_enabled）
  - 涉及文件：`tests/test_deepseek_client.py`（扩展）
  - 验收标准：所有测试通过；覆盖 strict 模式构建、降级、组合、兼容

### #231 思考模式参数兼容单元测试

- [ ] 在 `tests/test_deepseek_client.py` 中扩展测试
  - 测试思考模式启用时互斥参数被移除
  - 测试思考模式未启用时参数正常传递
  - 测试参数互斥启动警告
  - 涉及文件：`tests/test_deepseek_client.py`（扩展）
  - 验收标准：所有测试通过；覆盖参数移除、正常传递、警告

### #232 SSE 超时与重试策略单元测试

- [ ] 在 `tests/test_deepseek_client.py` 中扩展测试
  - 测试 `_send_with_enhanced_retry()` 指数退避延迟计算
  - 测试 SSE 超时检测触发
  - 测试重试耗尽后非流式降级
  - 测试 enhanced_retry_enabled=False 时使用 v3.1 逻辑
  - 涉及文件：`tests/test_deepseek_client.py`（扩展）
  - 验收标准：所有测试通过；覆盖指数退避、超时检测、降级

### #233 感知增强模块单元测试

- [ ] 在 `tests/test_perception_enhancer.py` 中编写单元测试
  - 测试 `analyze_topic()` 正常分析和 LLM 失败降级
  - 测试 `analyze_sentiment()` 正常分析和极性异常降级
  - 测试 `build_participant_profiles()` 画像构建、缓存、容量限制
  - 测试 3 个格式化方法
  - 测试各功能配置开关控制
  - 涉及文件：`tests/test_perception_enhancer.py`（新增）
  - 验收标准：所有测试通过；覆盖话题、情感、画像、格式化、降级

### #234 记忆增强注入单元测试

- [ ] 在 `tests/test_agent_memory.py` 中扩展测试
  - 测试 `_classify_memory()` 分类逻辑
  - 测试 `_compute_context_relevance()` 关联度计算
  - 测试 `_deduplicate_memories()` 去重逻辑
  - 测试 `_adjust_capacity()` 容量调整
  - 测试 `get_enhanced_memories()` 完整流程
  - 测试 `format_enhanced_memories_for_prompt()` 增强格式
  - 涉及文件：`tests/test_agent_memory.py`（扩展）
  - 验收标准：所有测试通过；覆盖分类、关联、去重、容量、增强格式

### #235 上下文感知压缩单元测试

- [ ] 在 `tests/test_overflow_manager.py` 中扩展测试
  - 测试 `soft_prune_with_relevance()` 相关性排序截断
  - 测试 `hard_prune_with_priority()` 优先级标注移除
  - 测试 `_compute_message_priority()` 优先级计算
  - 测试无感知信号时降级为 v3.1 逻辑
  - 涉及文件：`tests/test_overflow_manager.py`（扩展）
  - 验收标准：所有测试通过；覆盖相关性剪枝、优先级剪枝、降级

### #236 决策质量统计单元测试

- [ ] 在 `tests/test_quality_stats.py` 中编写单元测试
  - 测试 `record_decision()` 记录追加
  - 测试 `get_metrics()` 各指标计算（触发准确率、误触发率、漏触发率、效率指标）
  - 测试滑动窗口大小控制
  - 测试空记录时返回默认指标
  - 涉及文件：`tests/test_quality_stats.py`（新增）
  - 验收标准：所有测试通过；覆盖指标计算、窗口控制、空记录

### #237 提示词扩展单元测试

- [ ] 在 `tests/test_prompts.py` 中扩展测试
  - 测试 `DEEPSEEK_WORKFLOW_PROMPT` 和 `DEEPSEEK_TOOL_PROTOCOL` 内容
  - 测试 `SCENARIO_EXAMPLES` 和 `DECISION_BOUNDARY` 内容
  - 测试 `ENHANCED_MEMORY_HISTORY_TEMPLATE` 和 `ENHANCED_MEMORY_ENTRY_TEMPLATE` 格式化
  - 测试 `ENHANCED_REFLECTION_USER_TEMPLATE` 格式化
  - 测试感知增强模板格式化
  - 测试 `build_system_prompt()` 新增参数行为
  - 涉及文件：`tests/test_prompts.py`（扩展）
  - 验收标准：所有测试通过；模板格式化正确；build_system_prompt 新参数行为正确

### #238 AgentCore 集成单元测试

- [ ] 在 `tests/test_agent.py` 中扩展测试
  - 测试 `perceive()` 感知增强集成（话题追踪、情感分析、参与者画像）
  - 测试 `perceive()` 记忆增强注入
  - 测试 `_react_loop()` 步骤分类器集成
  - 测试 `_react_loop()` 循环检测集成
  - 测试 `_react_loop()` 自适应步数
  - 测试 `_react_loop()` DeepSeek 专用 prompt
  - 测试 `reflect()` 增强反思集成
  - 测试决策循环完成后质量统计记录
  - 涉及文件：`tests/test_agent.py`（扩展）
  - 验收标准：所有测试通过；覆盖感知增强、步骤分类、循环检测、自适应步数、增强反思

### #239 WebUI 扩展单元测试

- [ ] 在 `tests/test_webui.py` 中扩展测试
  - 测试 2 个决策质量统计 API 端点的正常和异常响应
  - 测试 stats 接口新增字段
  - 测试 WebSocket 新增事件类型
  - 测试 QualityStats 未初始化时的错误响应
  - 涉及文件：`tests/test_webui.py`（扩展）
  - 验收标准：所有测试通过；端点正常/异常场景覆盖

### #240 向后兼容集成测试

- [ ] 编写向后兼容集成测试
  - 所有 v3.2 新功能关闭时，行为与 v3.1 完全一致
  - robust_reasoning_enabled=False → 回传逻辑与 v3.1 一致
  - adaptive_effort_enabled=False → effort 逻辑与 v3.1 一致
  - step_classifier_enabled=False → 使用 has_tool_calls 判断
  - loop_detection_enabled=False → 无循环检测
  - strict_mode_enabled=False → 无 strict 模式
  - deepseek_prompt_enabled=False → 使用 v3.1 通用提示词
  - enhanced_retry_enabled=False → 使用 v3.1 固定重试
  - topic_tracking_enabled=False → 无话题追踪
  - sentiment_analysis_enabled=False → 无情感分析
  - participant_profile_enabled=False → 无参与者画像
  - enhanced_memory_enabled=False → 使用 v3.1 记忆格式
  - enhanced_reflection_enabled=False → 使用 v3.1 基础反思
  - prompt_optimization_enabled=False → 无场景示例和决策边界
  - context_aware_compress_enabled=False → 使用 v3.1 按位置剪枝
  - 涉及文件：`tests/test_backward_compat.py`（扩展）
  - 验收标准：所有 v3.2 功能关闭时，决策循环、LLM 调用、WebUI 行为与 v3.1 一致