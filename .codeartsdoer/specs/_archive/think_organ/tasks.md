# ThinkingOrgan 替代旧 Planner — 任务列表

## 批次 1：基础设施（ThinkResult/ThinkAction 扩展 + ThinkingOrgan 构造改造）

### T1.1 ThinkResult/ThinkAction 扩展
- 在 `src/core/types.py` 中扩展 ThinkResult：新增 tool_calls_count、duration_ms、rounds、wait_seconds 字段
- 在 ThinkAction 枚举中新增 WAIT 值
- 确保所有现有消费者（Orchestrator 插话/提醒、ParallelThinkScheduler）兼容新字段

**验证**：现有测试通过 + 新字段有默认值不破坏旧代码

### T1.2 ThinkContext 扩展
- 在 `src/core/types.py` 中扩展 ThinkContext：新增 session_id、is_group_chat、deferred_tools 字段
- 更新 Orchestrator._build_think_context() 填充新字段

**验证**：现有测试通过 + 新字段有默认值

### T1.3 ThinkingOrganFactory 扩展
- 在 `src/maisaka/agent_autonomy/thinking_organ.py` 中扩展 ThinkingOrganFactory
- 新增 chat_loop_service_factory 和 tool_registry 参数
- 修改 create() 方法，创建 ThinkingOrgan 时注入新依赖
- 更新 Orchestrator._init_agent_autonomy() 传入工厂依赖

**验证**：ThinkingOrgan 能获取到 chat_loop_service 和 tool_registry

---

## 批次 2：ThinkingOrgan 工具循环核心

### T2.1 ThinkingOrgan 持有 ChatLoopService
- 修改 ThinkingOrgan.__init__() 接受 chat_loop_service 和 tool_registry
- 保留旧的 _call_llm() 作为 fallback（chat_loop_service 为 None 时使用）
- 新增 _build_chat_loop_service() 工厂方法

**验证**：ThinkingOrgan 可通过 chat_loop_service.chat_loop_step() 调用 LLM

### T2.2 工具循环核心 — _think_with_tools()
- 新增 _think_with_tools() 方法，实现完整的工具循环
- 从旧 ReasoningEngine._handle_tool_calls() 迁移工具执行逻辑
- 支持 visible/deferred 工具分离
- 支持思考相似度检测（防止死循环）
- 最多 10 轮内部 round

**验证**：LLM 输出 tool_calls → 工具执行 → 结果写回 → LLM 继续推理 → 循环结束

### T2.3 上下文注入 — _build_injected_messages()
- 新增 _build_injected_messages() 方法
- 注入项：deferred_tools_reminder、heuristic_memory、person_profile
- 注入项：行为表现参考、黑话参考、中期记忆参考
- 复用旧 MaisakaChatLoopService 的注入逻辑

**验证**：ThinkingOrgan 的注入消息与旧 Planner 一致

### T2.4 工具定义构建 — _build_tool_definitions()
- 新增 _build_tool_definitions() 方法
- 复用旧 ReasoningEngine._build_action_tool_definitions() 的 visible/deferred 分离逻辑
- 支持 tool_search 发现 deferred 工具

**验证**：LLM 只看到 visible 工具定义，deferred 工具需通过 tool_search 发现

---

## 批次 3：Orchestrator 主回复调度

### T3.1 MessageTurnScheduler 提取
- 从旧 ReasoningEngine 提取消息调度逻辑到新 MessageTurnScheduler 类
- 包含：消息排队（asyncio.Queue）、去重（drain_ready_turn_triggers）、打断（取消当前任务）
- 放在 `src/maisaka/agent_autonomy/message_turn_scheduler.py`

**验证**：快速连发 3 条消息 → 只触发 1 次思考

### T3.2 ReplyFrequencyController 提取
- 从旧 ReasoningEngine 提取回复频率控制逻辑到新 ReplyFrequencyController 类
- 包含：talk_value 计算、消息阈值判断、回复必要性评分
- 放在 `src/maisaka/agent_autonomy/reply_frequency.py`

**验证**：群聊低价值消息 → Orchestrator 判定不回复

### T3.3 Orchestrator.handle_message 改造
- 在 handle_message 中新增主回复调度逻辑
- 非通知消息 → _should_reply() 判断 → schedule_message_turn()
- 新增 _execute_think_cycle() 方法，调用主智能体 ThinkingOrgan.think()
- 启动 MessageTurnScheduler.run_loop()

**验证**：enabled=true → 用户消息 → Orchestrator → ThinkingOrgan.think → 回复发送

### T3.4 runtime.py 路由改造
- 修改 register_message()：当 Orchestrator 活跃时跳过旧 _schedule_message_turn()
- 确保 enabled=false 时完全回退到旧路径

**验证**：enabled=true → 日志无 "Planner" 字样；enabled=false → 行为与迁移前一致

---

## 批次 4：上下文管理迁移

### T4.1 上下文选择迁移
- 将旧 MaisakaChatLoopService.select_llm_context_messages() 的逻辑适配到 ThinkingOrgan
- ThinkingOrgan 在调用 chat_loop_step() 前准备历史消息
- 支持 CONTEXT_RESTORE 类型始终保留

**验证**：相同历史 → 相同的上下文选择结果

### T4.2 视觉消息处理迁移
- 将旧 ReasoningEngine 的视觉消息处理逻辑适配到 ThinkingOrgan
- 图片识图、占位刷新、最新图片数量限制

**验证**：发送图片 → ThinkingOrgan 正确识图

### T4.3 历史裁切迁移
- 将旧 ReasoningEngine 的历史裁切逻辑适配到 ThinkingOrgan
- 每轮循环结束后保证用户消息数量不超过 max_context_size
- 被裁切消息用于生成中期记忆摘要

**验证**：长对话 → 早期消息被裁切 → 中期记忆摘要生成

---

## 批次 5：插件 Hook 兼容 + 回复管道保留

### T5.1 插件 Hook 集成
- 在 ThinkingOrgan._think_with_tools() 中集成 5 个 Hook 规格
- before_request：可改写 messages 和 tool_definitions
- after_response：可改写 response 和 tool_calls
- 确保 Hook 调用时机与旧 ReasoningEngine 一致

**验证**：插件注册 Hook → ThinkingOrgan 工具循环中 Hook 被正确调用

### T5.2 replyer 管道验证
- 确认 reply 工具通过 ToolRegistry 调用时，replyer 二次生成管道正常工作
- 确认 rich_reply 检查器正常工作
- 确认表达方式选择正常工作

**验证**：LLM 调用 reply 工具 → replyer 二次 LLM 生成 → 发送

---

## 批次 6：集成验证 + 旧代码退役

### T6.1 端到端集成测试
- enabled=true 场景：主回复/插话/提醒全部走 ThinkingOrgan
- enabled=false 场景：完全回退到旧 Planner
- 群聊场景：回复频率控制、消息去重、打断
- 工具场景：reply/wait/send_image/query_memory/MCP 工具

**验证**：所有场景行为与旧 Planner 一致（除日志格式外）

### T6.2 日志格式对齐
- 确保新路径的日志格式与旧 ReasoningEngine 兼容
- 确保 WebUI 推理详情页面正常显示
- 确保结构化记录（logs/maisaka_prompt/）正常生成

**验证**：WebUI 推理详情页面正常显示新路径的思考过程

### T6.3 旧代码退役（稳定运行后执行）
- 删除 MaisakaReasoningEngine
- 删除 runtime.py 中的旧路径分支
- 删除 IdleBackoffController
- 将 agent_autonomy.enabled 默认值改为 true

**验证**：删除后所有功能正常