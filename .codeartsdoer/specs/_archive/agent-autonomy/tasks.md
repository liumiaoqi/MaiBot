# 智能体自主性架构 — 编码任务

> 基于需求规格 spec.md 和设计方案 design.md 生成，按5个阶段渐进实现。

---

## 阶段一：基础架构（最小可用）

> 验收标准：启用自主性架构后，银狼的 Planner 提示词变为"你是银狼，你在思考如何回应"，思维输出体现角色内心独白。

### Task 1.1: AgentAutonomyConfig 配置模型

- **文件**：`src/config/official_configs.py`
- **内容**：
  1. 新增 `AgentAutonomySectionConfig` 类，字段与 spec §6.5 一致（enabled, max_active_agents, auto_exit_timeout_minutes, interjection_enabled, interjection_intent_threshold, interjection_cooldown_minutes, max_interjections_per_hour, max_interjections_per_session_per_hour, interaction_signal_intent_bonus, embodied_planner_enabled, speaker_tag_format, orchestrator_strategy, intent_expiry_seconds）
  2. 在 `Config` 类中新增 `agent_autonomy: AgentAutonomySectionConfig` 字段
  3. 配置版本号升级
  4. 更新 `bot_config.toml` 模板（三语 i18n key 同步）
- **验证**：`Config` 实例化后 `config.agent_autonomy.enabled` 默认为 `False`，所有字段有合理默认值

### Task 1.2: maisaka_chat_embodied.prompt 角色化提示词模板

- **文件**：`prompts/zh-CN/maisaka_chat_embodied.prompt`、`prompts/en-US/maisaka_chat_embodied.prompt`、`prompts/ja-JP/maisaka_chat_embodied.prompt`
- **内容**：
  1. 基于 `maisaka_chat.prompt` 创建 embodied 版本
  2. 核心变更：将"你不是 {bot_name} 本人，不要替 {bot_name} 发言"翻转为"你是 {bot_name}，你在思考如何回应"
  3. 保留所有 slot 占位符（{identity}, {emotion_state}, {relationship}, {memory}, {agent_interaction_memory} 等）
  4. 工具调用指引从"判断 {bot_name} 应该回复"变为"我决定是否回复"
  5. 三语同步
- **验证**：模板渲染后，银狼的系统提示词为内部视角而非旁观者视角

### Task 1.3: EmbodiedPlannerPromptBuilder 角色化提示词构建器

- **文件**：`src/maisaka/agent_autonomy/prompt_builder.py`
- **内容**：
  1. 新建 `EmbodiedPlannerPromptBuilder` 类
  2. `build_system_prompt(agent_id, tools_section)` 方法：加载 `maisaka_chat_embodied.prompt` 模板，注入角色化上下文
  3. `build_personality_prompt(agent_id)` 方法：返回"你是{角色名}，你在思考如何回应"格式的人格提示词
  4. 降级支持：构建失败时回退到 `maisaka_chat.prompt` 旁观者模板
- **验证**：调用 `build_system_prompt("silver_wolf", tools_section)` 返回角色化系统提示词

### Task 1.4: ThinkingOrgan 思维器官

- **文件**：`src/maisaka/agent_autonomy/thinking_organ.py`
- **内容**：
  1. 新建 `ThinkingOrgan` 类，持有 `agent_id` 和 `EmbodiedPlannerPromptBuilder` 引用
  2. `build_system_prompt(tools_section)` 方法：委托给 `EmbodiedPlannerPromptBuilder`
  3. `get_prompt_template_name()` 方法：返回 `"maisaka_chat_embodied"` 或降级时 `"maisaka_chat"`
  4. 降级标记：`is_degraded` 属性
- **验证**：`ThinkingOrgan("silver_wolf", builder).get_prompt_template_name()` 返回 `"maisaka_chat_embodied"`

### Task 1.5: ChatLoopServiceAdapter 对话循环服务适配器

- **文件**：`src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py`
- **内容**：
  1. 新建 `ChatLoopServiceAdapter` 类，包装 `MaisakaChatLoopService`
  2. `switch_agent_context(agent_id)` 方法：
     - 更新 `_agent_id`
     - 重新调用 `_build_personality_prompt()` 构建人格提示词
     - 从 `AgentEmotionManagerRegistry` 获取情绪状态文本并更新
     - 从 `AgentRelationshipManager` 获取关系信息并更新
  3. `switch_to_embodied_prompt()` / `switch_to_observer_prompt()` 方法：切换提示词模板
  4. `current_agent_id` 属性
- **验证**：调用 `switch_agent_context("bronya")` 后，`current_agent_id` 为 `"bronya"`，人格提示词为布洛妮娅的

### Task 1.6: AutonomousAgent 自主智能体基础类

- **文件**：`src/maisaka/agent_autonomy/agent.py`
- **内容**：
  1. 新建 `AutonomousAgent` 类
  2. 构造函数：接收 `agent_id`，从 `AgentConfigRegistry` 加载 `AgentConfig`，从 `AgentEmotionManagerRegistry` 获取 `EmotionManager`，从 `AgentRelationshipManager` 获取关系管理器，从 `AgentMemoryAdapter` 获取记忆适配器
  3. 构建 `ThinkingOrgan` 和 `ExpressionOrgan`（阶段一 ExpressionOrgan 为占位实现）
  4. `build_embodied_prompt_context(tools_section)` 方法：构建角色化提示词上下文字典
  5. `build_embodied_personality_prompt()` 方法：返回角色化人格提示词
  6. 属性：`agent_id`, `agent_config`, `thinking_organ`, `expression_organ`, `emotion_manager`, `relationship_manager`, `memory_adapter`
- **验证**：`AutonomousAgent("silver_wolf").build_embodied_personality_prompt()` 返回"你是银狼，你在思考如何回应"

### Task 1.7: 单智能体角色化集成

- **文件**：`src/maisaka/runtime.py`、`src/maisaka/chat_loop_service.py`
- **内容**：
  1. 在 `MaisakaHeartFlowChatting.__init__()` 中，当 `config.agent_autonomy.enabled` 为 `True` 时：
     - 创建 `AutonomousAgent` 实例
     - 创建 `ChatLoopServiceAdapter` 包装 `_chat_loop_service`
     - 调用 `switch_to_embodied_prompt()` 切换到角色化模板
  2. 在 `MaisakaChatLoopService._get_chat_prompt_name()` 中支持返回 `"maisaka_chat_embodied"`
  3. 未启用自主性架构时行为与当前完全一致
- **验证**：启用自主性架构后，银狼的 Planner 以角色内心独白思考；未启用时行为不变

### Task 1.8: 阶段一集成测试

- **文件**：`tests/test_agent_autonomy/test_phase1.py`
- **内容**：
  1. 测试 `AgentAutonomySectionConfig` 默认值
  2. 测试 `EmbodiedPlannerPromptBuilder` 构建角色化提示词
  3. 测试 `ThinkingOrgan` 返回 embodied 模板名
  4. 测试 `ChatLoopServiceAdapter.switch_agent_context()` 上下文切换
  5. 测试 `AutonomousAgent` 构建角色化上下文
  6. 测试降级：构建失败时回退到旁观者模板
  7. 测试兼容性：未启用自主性架构时行为不变
- **验证**：所有测试通过

---

## 阶段二：多智能体协作

> 验收标准：银狼和三月七同时活跃，各自独立思考，主发言权可切换。

### Task 2.1: ExpressionOrgan 表达器官 + 发言标记

- **文件**：`src/maisaka/agent_autonomy/expression_organ.py`
- **内容**：
  1. 新建 `ExpressionOrgan` 类
  2. `build_speaker_tag()` 方法：根据 `speaker_tag_format` 配置构建发言标记（如"【银狼】"）
  3. `should_show_speaker_tag(is_multi_agent_active)` 方法：仅在多智能体活跃时显示
  4. `agent_id` 属性
- **验证**：`ExpressionOrgan(agent, "【{agent_name}】").build_speaker_tag()` 返回 `"【银狼】"`

### Task 2.2: ReplyToolContextExtender reply 工具上下文扩展

- **文件**：`src/maisaka/agent_autonomy/bridge/reply_context_extender.py`
- **内容**：
  1. 在 `BuiltinToolRuntimeContext` 中增加 `current_agent_id: str` 字段
  2. reply 工具发送消息时，根据 `current_agent_id` 注入发言标记前缀
  3. 仅在多智能体活跃时添加发言标记
- **验证**：多智能体活跃时，银狼的回复消息前缀为"【银狼】"

### Task 2.3: AgentActivity 数据模型 + AgentActivityStore

- **文件**：`src/common/database/database_model.py`、`src/maisaka/agent_autonomy/activity_store.py`
- **内容**：
  1. 新增 `AgentActivity` SQLModel（表名 `agent_autonomy_activities`），字段与 spec §6.3 一致
  2. 新增 `AgentActivityStore` 类，实现 `save_activity`, `get_active_agents`, `get_primary_agent`, `update_last_spoke`, `deactivate` 方法
  3. 唯一约束：`(session_id, agent_id, exited_at IS NULL)` — 同一会话同一智能体仅一条活跃记录
  4. 索引：`(session_id)`, `(agent_id)`, `(activated_at)`
- **验证**：持久化活跃状态后，`get_active_agents(session_id)` 返回正确列表

### Task 2.4: SpeakerChangeRecord 数据模型

- **文件**：`src/common/database/database_model.py`
- **内容**：
  1. 新增 `SpeakerChangeRecord` SQLModel（表名 `agent_autonomy_speaker_change_records`），字段与 spec §6.4 一致
  2. 索引：`(session_id, created_at)`, `(created_at)`
- **验证**：持久化发言权变更记录后可查询

### Task 2.5: AgentOrchestrator 编排器

- **文件**：`src/maisaka/agent_autonomy/orchestrator.py`
- **内容**：
  1. 新建 `AgentOrchestrator` 类
  2. `__init__`：接收 `session_id`, `session_name`, `chat_loop_adapter`, `config`；初始化活跃智能体字典、主发言智能体 ID、`AgentActivityStore`
  3. `activate_agent(agent_id, reason)` 方法：创建 `AutonomousAgent`，加入活跃列表，持久化活跃状态
  4. `deactivate_agent(agent_id, reason)` 方法：从活跃列表移除，持久化退场状态
  5. `get_active_agents()` / `get_primary_agent()` 方法
  6. `switch_primary_speaker(target_agent_id, reason, change_type)` 方法：切换主发言权，持久化 `SpeakerChangeRecord`，输出日志
  7. `handle_message(message)` 方法：编排主发言智能体回复（阶段二仅主发言，插话在阶段三）
  8. `is_degraded` 属性
  9. 降级处理：异常时降级为仅主发言智能体模式
  10. 活跃智能体数上限检查（max_active_agents）
  11. 超时退场检查（auto_exit_timeout_minutes）
- **验证**：银狼和三月七同时活跃，主发言权可从银狼切换到三月七

### Task 2.6: Orchestrator 与运行时集成

- **文件**：`src/maisaka/runtime.py`
- **内容**：
  1. 在 `MaisakaHeartFlowChatting.__init__()` 中创建 `AgentOrchestrator` 实例（当自主性架构启用时）
  2. `register_message()` 接收消息后调用 `orchestrator.handle_message()`
  3. 主发言智能体通过 `ChatLoopServiceAdapter` 切换上下文
  4. 未启用自主性架构时行为与当前完全一致
- **验证**：启用自主性架构后，用户消息由 Orchestrator 编排主发言智能体回复

### Task 2.7: 阶段二集成测试

- **文件**：`tests/test_agent_autonomy/test_phase2.py`
- **内容**：
  1. 测试 `ExpressionOrgan` 发言标记构建
  2. 测试 `AgentActivityStore` CRUD
  3. 测试 `AgentOrchestrator` 活跃智能体管理
  4. 测试主发言权切换
  5. 测试活跃智能体数上限
  6. 测试超时退场
  7. 测试降级处理
  8. 测试兼容性：未启用自主性架构时行为不变
- **验证**：所有测试通过

---

## 阶段三：自主行为

> 验收标准：三月七基于内在需求自主产生"想要插话"的行为意图，Orchestrator 调度执行。

### Task 3.1: InnerNeed 内在需求数据模型

- **文件**：`src/maisaka/agent_autonomy/inner_need.py`
- **内容**：
  1. 新建 `InnerNeed` dataclass：`need_type`, `strength`, `source`, `description`
  2. 新建 `BaseNeedCalculator` ABC：`calculate()` 抽象方法
  3. 新建 `EmotionNeedCalculator`：基于情绪类型和强度计算内在需求（lonely→需要陪伴, excited→想分享, calm持续→无聊）
  4. 新建 `MemoryNeedCalculator`：基于交互记忆计算内在需求（与B最近3次交互正面→想念B, 与B超24h无交互→想念B）
  5. 新建 `TimeNeedCalculator`：基于时间画像计算内在需求（深夜+night_active→找人聊天）
- **验证**：`EmotionNeedCalculator.calculate(agent_id, lonely_state)` 返回 `InnerNeed(need_type="companionship", ...)`

### Task 3.2: InnerNeedEngine 内在需求引擎

- **文件**：`src/maisaka/agent_autonomy/inner_need_engine.py`
- **内容**：
  1. 新建 `InnerNeedEngine` 类
  2. `register_calculator(need_type, calculator)` 方法：注册内在需求计算器
  3. `evaluate(agent_id)` 方法：遍历已注册计算器，聚合内在需求列表
  4. 内部依赖：`AgentEmotionManagerRegistry`, `AgentMemoryAdapter`
- **验证**：注册3个计算器后，`evaluate("silver_wolf")` 返回聚合的内在需求列表

### Task 3.3: BehaviorIntent 行为意图数据模型

- **文件**：`src/maisaka/agent_autonomy/behavior_intent.py`
- **内容**：
  1. 新建 `BehaviorIntent` dataclass：`intent_type`, `intent_strength`, `intent_source`, `source_description`
  2. 新建 `BaseIntentSource` ABC：`produce()` 抽象方法
  3. 新建 `InnerNeedIntentSource`：内在需求→行为意图（"需要陪伴"+对话中有人→want_to_speak）
  4. 新建 `EmotionIntentSource`：情绪→行为意图（excited+话题相关→want_to_speak）
  5. 新建 `TopicRelevanceIntentSource`：话题相关性→行为意图（对话提到游戏+银狼关注游戏→want_to_interject）
  6. 新建 `RelationshipIntentSource`：关系→行为意图（对话提及布洛妮娅+银狼与布洛妮娅关系亲密→want_to_interject）
  7. 新建 `InteractionSignalIntentSource`：交互信号→行为意图（交互信号"银狼想念三月七"→want_to_interject）
- **验证**：各 IntentSource 独立测试通过

### Task 3.4: BehaviorIntentEngine 行为意图引擎

- **文件**：`src/maisaka/agent_autonomy/behavior_intent_engine.py`
- **内容**：
  1. 新建 `BehaviorIntentEngine` 类
  2. `register_source(source_type, source)` 方法：注册行为意图来源
  3. `produce_intents(agent_id, conversation_context, interaction_signals)` 方法：
     - 通过 `InnerNeedEngine` 评估内在需求
     - 遍历已注册的 `IntentSource`
     - 综合各来源产生行为意图
     - 过滤意图强度 < 阈值的意图
  4. 内部依赖：`InnerNeedEngine`, `AgentEmotionManagerRegistry`
- **验证**：注册5个来源后，`produce_intents("silver_wolf", context, signals)` 返回行为意图列表

### Task 3.5: AutonomousAgent 扩展内在需求和行为意图

- **文件**：`src/maisaka/agent_autonomy/agent.py`
- **内容**：
  1. 在 `AutonomousAgent` 构造函数中构建 `InnerNeedEngine` 和 `BehaviorIntentEngine`
  2. 注册默认的 NeedCalculator 和 IntentSource
  3. 新增 `evaluate_inner_needs()` 方法
  4. 新增 `produce_behavior_intents(conversation_context, interaction_signals)` 方法
  5. 新增 `inner_need_engine` 和 `behavior_intent_engine` 属性
- **验证**：`agent.produce_behavior_intents(context)` 返回行为意图列表

### Task 3.6: InterjectionCooldownManager 插话冷却管理器

- **文件**：`src/maisaka/agent_autonomy/interjection_cooldown.py`
- **内容**：
  1. 新建 `InterjectionCooldownManager` 类
  2. `can_interject(session_id, agent_id)` 方法：检查冷却和频率限制
  3. `record_interjection(session_id, agent_id)` 方法：记录插话
  4. `get_cooldown_remaining(session_id, agent_id)` 方法
  5. `get_session_interjection_count(session_id, hours)` 方法
  6. 配置参数：`interjection_cooldown_minutes`, `max_interjections_per_hour`, `max_interjections_per_session_per_hour`
- **验证**：插话后5分钟内 `can_interject()` 返回 `False`

### Task 3.7: InterjectionScheduler 插话调度器

- **文件**：`src/maisaka/agent_autonomy/interjection_scheduler.py`
- **内容**：
  1. 新建 `InterjectionScheduler` 类
  2. 新建 `ScheduledInterjection` dataclass：`agent_id`, `intent`, `scheduled`, `skip_reason`
  3. `schedule(pending_intents, active_agents, primary_agent_id)` 方法：
     - 按意图强度降序排序
     - 遍历意图强度 ≥ 阈值的智能体
     - 检查冷却和频率限制
     - 返回调度决策列表
  4. 核心约束：不计算插话意愿，只基于智能体报告的意图强度排序
- **验证**：两个智能体同时报告行为意图，按强度排序调度

### Task 3.8: InterjectionEvent 数据模型

- **文件**：`src/common/database/database_model.py`
- **内容**：
  1. 新增 `InterjectionEvent` SQLModel（表名 `agent_autonomy_interjection_events`），字段与 spec §6.2 一致
  2. 索引：`(agent_id, created_at)`, `(session_id, created_at)`, `(interjection_type)`, `(created_at)`
- **验证**：持久化插话事件后可查询

### Task 3.9: Orchestrator 扩展插话调度

- **文件**：`src/maisaka/agent_autonomy/orchestrator.py`
- **内容**：
  1. `handle_message()` 扩展：主发言完成后，收集活跃智能体的行为意图，调度插话
  2. `report_intent(agent_id, intent)` 方法：接收智能体自主报告的行为意图
  3. `handle_interaction_signal(event)` 方法：处理交互信号（阶段三为占位实现，阶段四完善）
  4. 插话执行流程：切换到插话智能体上下文 → 激活思维器官 → 生成插话 → 附带发言标记 → 记录插话事件
  5. 插话不阻断主发言：使用 `asyncio.Semaphore` 控制并发
  6. 结构化日志输出
- **验证**：三月七自主产生行为意图后，Orchestrator 调度执行插话

### Task 3.10: 阶段三集成测试

- **文件**：`tests/test_agent_autonomy/test_phase3.py`
- **内容**：
  1. 测试 `InnerNeedEngine` 各计算器
  2. 测试 `BehaviorIntentEngine` 各来源
  3. 测试 `InterjectionCooldownManager` 冷却和频率限制
  4. 测试 `InterjectionScheduler` 调度排序
  5. 测试 Orchestrator 插话调度流程
  6. 测试插话不阻断主发言
  7. 测试行为意图强度阈值过滤
  8. 测试插话事件持久化
- **验证**：所有测试通过

---

## 阶段四：交互联动与可观测性

> 验收标准：交互信号触发智能体行为意图，插话反哺交互系统，WebUI 可观测。

### Task 4.1: 交互信号→行为意图联动

- **文件**：`src/maisaka/agent_autonomy/orchestrator.py`、`src/maisaka/agent_interaction/engine.py`
- **内容**：
  1. `InteractionEngine.execute()` 完成后通过事件机制发布交互事件通知
  2. `AgentOrchestrator` 注册为交互事件监听器
  3. 收到交互信号后：检查目标智能体是否活跃 → 必要时激活 → 通知智能体的 `BehaviorIntentEngine`
  4. 智能体自主决定是否产生行为意图
  5. 交互信号作为 `InteractionSignalIntentSource` 的输入
- **验证**：交互信号"银狼想念三月七"触发三月七产生行为意图

### Task 4.2: 插话反哺交互系统

- **文件**：`src/maisaka/agent_autonomy/orchestrator.py`
- **内容**：
  1. 智能体插话内容如果提及其他智能体，产生提及传递信号写入交互系统
  2. 插话后更新智能体情绪状态（写入 EmotionManager）
  3. 信号传导闭环：后台交互信号 → 前台行为意图 → 新交互信号
- **验证**：三月七插话提及银狼后，产生提及传递信号

### Task 4.3: BehaviorIntentRecord 数据模型 + 持久化

- **文件**：`src/common/database/database_model.py`、`src/maisaka/agent_autonomy/activity_store.py`
- **内容**：
  1. 新增 `BehaviorIntentRecord` SQLModel（表名 `agent_autonomy_behavior_intents`），字段与 spec §6.1 一致
  2. 在 `AgentActivityStore` 中新增 `save_behavior_intent()` 方法
  3. 索引：`(agent_id, created_at)`, `(session_id, created_at)`, `(intent_type)`, `(status)`, `(created_at)`
- **验证**：行为意图持久化后可查询

### Task 4.4: 结构化日志

- **文件**：`src/maisaka/agent_autonomy/orchestrator.py`、`src/maisaka/agent_autonomy/agent.py`
- **内容**：
  1. 回复日志：`[agent_autonomy] agent=X type=primary/interjection/switch reason=XX session=XX`
  2. 发言权变更日志：`[agent_autonomy] speaker_change from=A to=B reason=XX`
  3. 活跃状态变更日志：`[agent_autonomy] agent=X action=activate/deactivate session=XX reason=XX`
  4. 行为意图日志：`[agent_autonomy] agent=X intent=XX strength=XX source=XX`（DEBUG 级别）
  5. Orchestrator 调度日志（DEBUG 级别）
- **验证**：各事件触发后日志格式正确

### Task 4.5: WebUI API — 智能体自主性端点

- **文件**：`src/webui/routers/agent.py`
- **内容**：
  1. `GET /agent/autonomy/active/{session_id}` — 获取会话的活跃智能体列表
  2. `GET /agent/autonomy/primary/{session_id}` — 获取会话的主发言智能体
  3. `POST /agent/autonomy/switch-speaker` — 切换主发言智能体
  4. `POST /agent/autonomy/trigger-interjection` — 手动触发插话
  5. `GET /agent/autonomy/intents/{session_id}` — 获取会话的待处理行为意图
  6. `GET /agent/autonomy/interjection-events/{session_id}` — 获取会话的插话事件列表
  7. `GET /agent/autonomy/speaker-changes/{session_id}` — 获取会话的发言权变更记录
- **验证**：各端点返回正确数据

### Task 4.6: WebUI 前端 — 自主性面板

- **文件**：`dashboard/src/routes/agent/components/`、`dashboard/src/lib/agent-api.ts`、`dashboard/src/i18n/locales/`
- **内容**：
  1. 活跃智能体列表组件（显示当前会话的活跃智能体、主发言标识）
  2. 主发言权切换操作
  3. 手动触发插话操作
  4. 行为意图查看面板
  5. 插话事件历史
  6. 发言权变更历史
  7. API 函数：`dashboard/src/lib/agent-api.ts` 新增自主性 API 调用
  8. i18n 三语同步
- **验证**：WebUI 可查看活跃智能体、切换主发言、触发插话

### Task 4.7: 阶段四集成测试

- **文件**：`tests/test_agent_autonomy/test_phase4.py`
- **内容**：
  1. 测试交互信号→行为意图联动
  2. 测试插话反哺交互系统
  3. 测试行为意图持久化
  4. 测试结构化日志格式
  5. 测试 WebUI API 端点
  6. 测试信号传导闭环
  7. 测试交互信号与插话的循环打破（冷却机制）
- **验证**：所有测试通过

---

## 阶段五：优化与扩展

> 验收标准：性能达标，调度策略可配置，行为意图类型可注册。

### Task 5.1: 性能优化

- **文件**：`src/maisaka/agent_autonomy/` 各模块
- **内容**：
  1. 异步并行行为意图计算：多个智能体的 `produce_behavior_intents()` 并行执行
  2. 上下文切换缓存：`ChatLoopServiceAdapter.switch_agent_context()` 缓存已构建的提示词
  3. 并发控制：`asyncio.Semaphore(2)` 限制同一会话同时执行的回复轮次
  4. 行为意图过期清理：定时清理 `expired_at < now` 的行为意图
- **验证**：行为意图产生延迟 < 300ms（不含 LLM 调用），上下文切换延迟 < 100ms

### Task 5.2: Orchestrator 策略可配置

- **文件**：`src/maisaka/agent_autonomy/orchestrator.py`
- **内容**：
  1. 新建 `BaseOrchestratorStrategy` ABC
  2. 新建 `DefaultOrchestratorStrategy`（当前默认行为）
  3. `AgentOrchestrator` 根据配置选择策略
  4. 策略注册机制
- **验证**：配置不同策略后，Orchestrator 调度行为不同

### Task 5.3: 行为意图类型可注册

- **文件**：`src/maisaka/agent_autonomy/behavior_intent.py`
- **内容**：
  1. `BehaviorIntentEngine` 支持动态注册新的意图类型
  2. 新增意图类型无需修改核心逻辑
  3. 意图类型通过字符串定义，而非硬编码枚举
- **验证**：注册自定义意图类型后可正常产生行为意图

### Task 5.4: 动态性格预留

- **文件**：`src/maisaka/agent_autonomy/prompt_builder.py`
- **内容**：
  1. `EmbodiedPlannerPromptBuilder` 支持从动态数据源加载人设信息
  2. 人设注入点 `{identity}` 支持动态替换
  3. 为未来的动态性格引擎预留接口
- **验证**：人设注入点可被动态数据源替换

### Task 5.5: 阶段五集成测试 + 性能测试

- **文件**：`tests/test_agent_autonomy/test_phase5.py`
- **内容**：
  1. 测试并行行为意图计算
  2. 测试上下文切换缓存
  3. 测试并发控制（Semaphore）
  4. 测试行为意图过期清理
  5. 测试 Orchestrator 策略切换
  6. 测试行为意图类型注册
  7. 性能基准测试：行为意图产生延迟、上下文切换延迟
- **验证**：所有测试通过，性能指标达标

---

## 跨阶段任务

### Task X.1: `__init__.py` 模块导出

- **文件**：`src/maisaka/agent_autonomy/__init__.py`、`src/maisaka/agent_autonomy/bridge/__init__.py`、`src/maisaka/agent_autonomy/models/__init__.py`、`src/maisaka/agent_autonomy/config/__init__.py`
- **内容**：各阶段完成后更新模块导出

### Task X.2: 配置文件模板更新

- **文件**：`bot_config.toml` 模板
- **内容**：各阶段完成后更新配置模板和版本号

### Task X.3: i18n 三语同步

- **文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`
- **内容**：各阶段完成后同步翻译键