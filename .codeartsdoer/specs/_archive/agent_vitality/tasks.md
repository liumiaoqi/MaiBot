# 智能体活跃状态机制完善 — 编码任务清单

> 理想的角色不应是一具等待结局的标本，而应是一场永恒的进行时。

## 1. 数据基础层：模型扩展与配置参数

### 1.1 扩展 AgentAutonomyActivity 数据库模型

- [ ] 在 `src/common/database/database_model.py` 的 `AgentAutonomyActivity` 类中新增 6 个字段：
  - `vitality_value: float`（默认 0.0，范围 [0.0, 100.0]）——生命力值
  - `state: str`（默认 "active"，max_length=16）——状态枚举：active / standby / dormant
  - `last_stimulus_at: Optional[datetime]`（默认 None）——最近一次环境刺激时间
  - `activated_to_active_at: Optional[datetime]`（默认 None）——最近一次从待命跃迁为活跃的时间
  - `fallback_to_standby_at: Optional[datetime]`（默认 None）——最近一次从活跃回落为待命的时间
  - `inner_need_summary: str`（默认 ""，max_length=500）——最近一次内在需求评估摘要
- [ ] 为 `state` 字段添加索引 `ix_agent_autonomy_activities_state`，用于按状态查询待命记录
- [ ] 验收：Alembic 迁移脚本可正常生成并执行，新增字段在数据库中正确创建

### 1.2 新增生命力配置参数

- [ ] 在 `src/config/official_configs.py` 的 `AgentAutonomySectionConfig` 类中新增以下字段（均含三语 label）：
  - `vitality_base_value: float`（默认 30.0，ge=0.0, le=100.0）——待命初始化生命力基准值
  - `vitality_activation_threshold: float`（默认 70.0，ge=30.0, le=100.0）——待命→活跃激活阈值
  - `vitality_decay_per_minute: float`（默认 2.0，ge=0.0, le=10.0）——每分钟生命力衰减值
  - `vitality_stimulus_message: float`（默认 5.0，ge=0.0, le=30.0）——消息感知生命力增长值
  - `vitality_stimulus_mention: float`（默认 20.0，ge=0.0, le=50.0）——提及感知生命力增长值
  - `vitality_stimulus_topic: float`（默认 10.0，ge=0.0, le=30.0）——话题相关生命力增长值
  - `vitality_tick_interval_seconds: int`（默认 60，ge=30, le=300）——心跳间隔秒数
  - `fallback_exit_timeout_minutes: int`（默认 120，ge=30, le=1440）——回落退场时间
  - `cohabitation_threshold_reduction: float`（默认 10.0，ge=0.0, le=30.0）——共居插话阈值降低基础值
  - `cohabitation_cooldown_reduction_minutes: float`（默认 1.0，ge=0.0, le=3.0）——共居冷却缩短基础值
  - `interjection_threshold_minimum: float`（默认 20.0，ge=10.0, le=40.0）——插话阈值最低限制
  - `interjection_cooldown_minimum_minutes: float`（默认 1.0，ge=0.5, le=3.0）——冷却时间最低限制
- [ ] 更新配置文件模板 `bot_config.toml`，新增版本号
- [ ] 验收：所有参数均可通过 `global_config.agent_autonomy` 正确读取，三语 label 在 WebUI 配置页面正确显示

### 1.3 扩展 AgentActivityStore 持久化方法

- [ ] 在 `src/maisaka/agent_autonomy/activity_store.py` 中新增以下方法：
  - `save_standby_activity(session_id, agent_id, vitality_value, activation_reason)` —— 保存待命状态记录（state="standby", exited_at=None）
  - `update_vitality(session_id, agent_id, vitality_value, inner_need_summary)` —— 更新生命力和内在需求摘要
  - `update_stimulus_time(session_id, agent_id)` —— 更新 last_stimulus_at
  - `fallback_to_standby(session_id, agent_id, vitality_value)` —— 活跃→待命回落（设置 state="standby", fallback_to_standby_at=now, 不设置 exited_at）
  - `activate_from_standby(session_id, agent_id)` —— 待命→活跃跃迁（设置 state="active", activated_to_active_at=now）
  - `get_standby_agents(session_id)` —— 获取会话的待命智能体列表（state="standby" 且 exited_at=None）
  - `get_all_standby_sessions()` —— 获取所有未退出的待命记录（用于重启恢复）
  - `exit_standby(session_id, agent_id, reason)` —— 待命→沉睡退场（设置 exited_at=now, exit_reason=reason）
- [ ] 修改现有 `deactivate()` 方法：当 reason 为 "fallback_to_standby" 时，调用 `fallback_to_standby()` 而非设置 exited_at
- [ ] 验收：所有新方法可正确读写数据库，待命/活跃/退场状态转换逻辑正确

## 2. 待命智能体注册表

### 2.1 实现 StandbyAgentRegistry

- [ ] 新建 `src/maisaka/agent_autonomy/standby_registry.py`，实现以下内容：
  - `StandbyAgentInfo` 数据类：agent_id, session_id, vitality_value, last_stimulus_at, activated_to_active_at, fallback_to_standby_at, inner_need_summary
  - `StandbyAgentRegistry` 类：内存注册表，使用 `_agents: dict[tuple[str, str], StandbyAgentInfo]` 存储
  - `add(info: StandbyAgentInfo)` —— 幂等添加，已存在时更新
  - `remove(agent_id, session_id) -> StandbyAgentInfo | None` —— 移除并返回
  - `get(agent_id, session_id) -> StandbyAgentInfo | None` —— 查询单个
  - `get_by_session(session_id) -> list[StandbyAgentInfo]` —— 查询会话所有待命智能体
  - `update_vitality(agent_id, session_id, new_value)` —— 更新生命力值
  - `contains(agent_id, session_id) -> bool` —— 检查是否在待命列表中
- [ ] 验收：注册表的增删改查操作正确，幂等性保证，内存占用合理

## 3. 生命力管理器

### 3.1 实现 VitalityManager 核心

- [ ] 新建 `src/maisaka/agent_autonomy/vitality_manager.py`，实现 `VitalityManager` 类：
  - `__init__(self, orchestrator: AgentOrchestrator)` —— 持有 StandbyAgentRegistry、AmbientAwarenessProcessor、VitalityTickScheduler 的引用
  - `sync_standby_agents(session_id)` —— 同步待命列表：查询 AgentRouter 绑定关系，将绑定但非活跃且非待命的智能体加入待命，初始化生命力为 vitality_base_value
  - `add_to_standby(agent_id, session_id, reason, initial_vitality=None)` —— 将智能体加入待命列表并持久化到数据库
  - `remove_from_standby(agent_id, session_id, reason)` —— 从待命列表移除并持久化退场记录
  - `update_vitality(agent_id, session_id, delta, reason) -> float` —— 更新生命力值，范围限制 [0.0, 100.0]，返回更新后值
  - `check_instant_activation(agent_id, session_id) -> bool` —— 检查即时跃迁条件（被直接提及），满足时调用 orchestrator.activate_agent("vitality_activation")
  - `evaluate_vitality_tick()` —— 执行一次心跳评估（遍历所有待命智能体，计算生命力，判定跃迁）
  - `get_standby_agents(session_id) -> list[StandbyAgentInfo]` —— 获取待命智能体列表
  - `get_agent_vitality(agent_id, session_id) -> float` —— 获取生命力值
  - `get_cohabitation_params(session_id) -> CohabitationParams` —— 计算共居插话动态参数
- [ ] 生命力计算公式：`vitality = current + inner_need_bonus + emotion_bonus - decay_per_minute * elapsed_minutes`
  - inner_need_bonus：InnerNeedEngine 评估出的需求强度之和（归一化到 [0, 20]）
  - emotion_bonus：EmotionManager 当前情绪强度（归一化到 [0, 10]）
  - 时间衰减：`decay_per_minute * (now - last_stimulus_at).total_seconds() / 60`
- [ ] 心跳评估中的跃迁判定：vitality ≥ activation_threshold 且活跃数 < max_active_agents → 调用 activate_agent("vitality_activation")
- [ ] 待命退场判定：待命时间 ≥ fallback_exit_timeout_minutes 且 vitality = 0 → 从待命列表移除（退场为 Dormant）
- [ ] 并发控制：使用 `asyncio.Lock` 保证同一时刻仅一个心跳任务执行
- [ ] 异常处理：AgentRouter 不可用时跳过同步；InnerNeedEngine 异常时跳过内在需求加成；单个智能体评估超时时跳过继续下一个
- [ ] 验收：生命力计算正确，状态跃迁逻辑符合三态状态机，并发控制有效

### 3.2 实现 CohabitationParams 数据类

- [ ] 在 `vitality_manager.py` 中定义 `CohabitationParams` 数据类：intent_threshold, cooldown_minutes, max_interjections_per_hour
- [ ] `get_cohabitation_params()` 方法逻辑：
  - 查询 AgentRouter 获取会话绑定智能体数量 bound_count
  - 若 bound_count < 3，返回默认配置值
  - 若 bound_count ≥ 3，计算 adjustment_factor = min(bound_count / 3, 2.0)
  - 动态阈值 = interjection_intent_threshold - cohabitation_threshold_reduction * adjustment_factor，不低于 interjection_threshold_minimum
  - 动态冷却 = interjection_cooldown_minutes - cohabitation_cooldown_reduction_minutes * adjustment_factor，不低于 interjection_cooldown_minimum_minutes
  - 动态频率上限 = max_interjections_per_hour + 2
- [ ] 验收：绑定 13 个智能体时阈值降至 40.0、冷却缩至 3 分钟；绑定 2 个智能体时参数不变

## 4. 环境感知处理器

### 4.1 扩展 AutonomyEventBus 事件类型

- [ ] 在 `src/maisaka/agent_autonomy/event_bus.py` 中新增两个事件数据类：
  - `SessionMessageEvent`：session_id, sender_type("user"|"agent"), sender_id, content, timestamp
  - `AgentSpeakEvent`：session_id, agent_id, content_summary, emotion_type, emotion_intensity
- [ ] 验收：新事件类型可通过 `bus.emit()` / `bus.emit_sync()` 正确发布和接收

### 4.2 实现 AmbientAwarenessProcessor

- [ ] 新建 `src/maisaka/agent_autonomy/ambient_awareness.py`，实现 `AmbientAwarenessProcessor` 类：
  - `__init__(self, vitality_manager: VitalityManager)` —— 持有 VitalityManager 引用
  - `on_session_message(event: SessionMessageEvent)` —— 处理会话消息事件：
    1. 获取该会话的所有待命智能体
    2. 每个待命智能体生命力 += vitality_stimulus_message
    3. 检查是否提及待命智能体（调用 check_mention），提及则生命力 += vitality_stimulus_mention，并检查即时跃迁
    4. 检查话题相关性（调用 check_topic_relevance），匹配则生命力 += vitality_stimulus_topic
    5. 更新所有待命智能体的 last_stimulus_at
  - `on_agent_speak(event: AgentSpeakEvent)` —— 处理智能体发言事件（情绪感染）：
    1. 获取该会话的所有待命智能体
    2. 若发言智能体情绪强烈（intensity ≥ 60），对待命智能体调用 emotion_manager.apply_trigger() 小幅偏移
  - `extract_message_summary(content, max_length=200) -> str` —— 提取消息摘要（截取 + 关键词，不调用 LLM）
  - `check_mention(content, agent_id) -> bool` —— 检查消息是否提及指定智能体（复用 AgentConfigRegistry 的 display_name 匹配逻辑）
  - `check_topic_relevance(content, agent_id) -> list[str]` —— 检查消息与智能体 attention_keywords 的匹配
- [ ] 在 VitalityManager 初始化时创建 AmbientAwarenessProcessor 实例，并订阅 EventBus 的 "session_message" 和 "agent_speak" 事件
- [ ] 性能约束：单条消息的环境感知处理延迟 < 200ms（13 个待命智能体），不调用 LLM
- [ ] 异常处理：消息为空时跳过；EmotionManager 不可用时跳过情绪更新；AgentConfigRegistry 不可用时跳过提及检测
- [ ] 验收：待命智能体能感知消息/提及/话题并更新生命力，情绪感染正确触发，不产生任何可见回复

### 4.3 在 ChatLoopAdapter 中注入环境感知事件

- [ ] 在 `src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py` 中，当用户消息到达时，通过 `AutonomyEventBus.emit_sync()` 发布 `SessionMessageEvent`
- [ ] 在 Orchestrator 的插话执行完成后，发布 `AgentSpeakEvent`（包含发言智能体 ID、内容摘要、情绪状态）
- [ ] 验收：用户消息和智能体发言均能触发环境感知事件

## 5. 心跳调度器

### 5.1 实现 VitalityTickScheduler

- [ ] 新建 `src/maisaka/agent_autonomy/vitality_tick.py`，实现 `VitalityTickScheduler` 类：
  - `__init__(self, vitality_manager: VitalityManager, interval_seconds: int = 60)` —— 持有 VitalityManager 引用
  - `start()` —— 启动 asyncio 周期任务，每隔 interval_seconds 调用 `vitality_manager.evaluate_vitality_tick()`
  - `stop()` —— 停止周期任务，等待当前心跳完成
  - `is_running -> bool` —— 查询运行状态
- [ ] 使用 `asyncio.create_task()` 创建周期任务，在 `_tick_loop()` 中使用 `asyncio.sleep()` 控制间隔
- [ ] 在 VitalityManager 初始化时创建 VitalityTickScheduler 实例，并在 Orchestrator 启动时调用 `start()`
- [ ] 在 Orchestrator 销毁或降级时调用 `stop()`
- [ ] 验收：心跳以配置间隔周期触发，无待命智能体时跳过评估，并发锁防止重复执行

## 6. Orchestrator 集成

### 6.1 扩展 Orchestrator 初始化

- [ ] 在 `src/maisaka/agent_autonomy/orchestrator.py` 的 `__init__()` 中：
  - 新增 `self._vitality_manager = VitalityManager(self)` 
  - 在 `_subscribe_events()` 中新增订阅 `"session_message"` 和 `"agent_speak"` 事件（转发给 AmbientAwarenessProcessor）
  - 启动 VitalityTickScheduler
- [ ] 验收：VitalityManager 和心跳调度器随 Orchestrator 生命周期正确启停

### 6.2 扩展 handle_message 待命同步

- [ ] 在 `handle_message()` 中，激活主发言智能体后，调用 `self._vitality_manager.sync_standby_agents(session_id)` 同步待命列表
- [ ] 同步逻辑：查询 AgentRouter 获取绑定智能体集合，对比活跃列表和待命列表，将绑定但非活跃且非待命的智能体加入待命
- [ ] 验收：用户消息到达后，所有绑定但非活跃的智能体自动进入待命状态

### 6.3 修改超时退场为回落逻辑

- [ ] 修改 `_check_timeout_exit()` 方法：
  - 非主发言智能体超时后，调用 `self._vitality_manager.add_to_standby(agent_id, session_id, "timeout_fallback")` 加入待命
  - 然后调用 `deactivate_agent(agent_id, "fallback_to_standby")` 从活跃列表移除（但不设置 exited_at）
  - 主发言智能体仍不执行超时退场
- [ ] 修改 `deactivate_agent()` 方法：当 reason 为 "fallback_to_standby" 时，调用 `_activity_store.fallback_to_standby()` 而非 `_activity_store.deactivate()`
- [ ] 验收：活跃智能体超时后回落为待命而非直接退场，主发言不受影响

### 6.4 扩展行为意图收集使用动态插话参数

- [ ] 修改 `_collect_behavior_intents()` 方法：
  - 调用 `self._vitality_manager.get_cohabitation_params(session_id)` 获取动态插话参数
  - 将动态的 `intent_threshold` 传递给 `agent.produce_behavior_intents()` 替代固定配置值
- [ ] 修改 `_schedule_interjections()` 中的冷却检查：
  - 将动态的 `cooldown_minutes` 和 `max_interjections_per_hour` 传递给 `InterjectionCooldownManager`
- [ ] 验收：绑定 ≥3 个智能体时插话阈值降低、冷却缩短；绑定 <3 时参数不变

### 6.5 扩展交互信号处理支持待命唤醒

- [ ] 修改 `handle_interaction_signal()` 方法：
  - 若目标智能体不在活跃列表也不在待命列表，先调用 `self._vitality_manager.add_to_standby(target_agent_id, session_id, "interaction_signal")` 唤醒为待命
  - 然后尝试激活（若活跃数未满）
- [ ] 验收：交互信号可将沉睡智能体唤醒为待命

## 7. 会话恢复扩展

### 7.1 扩展 SessionRecoveryService 恢复待命状态

- [ ] 在 `src/maisaka/agent_autonomy/session_recovery.py` 的 `recover_all()` 方法中：
  - 除恢复活跃智能体外，还需查询 `AgentActivityStore.get_all_standby_sessions()` 获取待命记录
  - 对每个待命记录，调用 `orch._vitality_manager.add_to_standby(agent_id, session_id, "session_recovery", initial_vitality=record.vitality_value)` 恢复待命状态
  - 验证 ChatSession 仍存在，不存在则清理待命记录
- [ ] 在 `AgentOrchestrator.restore_agent()` 中增加对 `state="standby"` 记录的处理：
  - 若记录 state 为 "standby"，调用 `_vitality_manager.add_to_standby()` 而非 `restore_agent()`
- [ ] 验收：系统重启后，待命智能体列表从数据库正确恢复，生命力值保留

## 8. 插话冷却动态参数支持

### 8.1 扩展 InterjectionCooldownManager

- [ ] 在 `src/maisaka/agent_autonomy/interjection_cooldown.py` 中：
  - 修改 `can_interject()` 方法签名，新增可选参数 `override_cooldown: float | None = None` 和 `override_max_per_hour: int | None = None`
  - 当传入 override 参数时使用覆盖值，否则使用全局配置值
  - 保持向后兼容：不传参数时行为不变
- [ ] 验收：Orchestrator 可传入动态参数覆盖默认冷却时间和频率限制

## 9. WebUI 后端 API

### 9.1 新增生命力状态查询 API

- [ ] 在 `src/webui/routers/agent.py` 中新增端点：
  - `GET /agent/vitality?session_id={session_id}` —— 查询会话智能体生命力状态
  - 返回 `SessionVitalityResponse`：success, session_id, active_agents, standby_agents, dormant_agents
  - `VitalityAgentItem`：agent_id, display_name, state("active"|"standby"|"dormant"), vitality_value, last_stimulus_at
- [ ] 实现逻辑：
  1. 从 AgentOrchestrator 获取活跃智能体列表
  2. 从 VitalityManager 获取待命智能体列表及生命力值
  3. 从 AgentRouter 获取绑定智能体集合，减去活跃和待命的，剩余为沉睡
  4. 组装并返回分类后的列表
- [ ] 验收：API 正确返回三态分类的智能体列表，待命智能体包含生命力值

## 10. WebUI 前端展示

### 10.1 扩展前端 API 层

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增：
  - `VitalityAgentItem` 接口：agent_id, display_name, state, vitality_value, last_stimulus_at
  - `SessionVitalityResponse` 接口：success, session_id, active_agents, standby_agents, dormant_agents
  - `fetchSessionVitality(sessionId: string)` 函数，调用 `GET /api/webui/agent/vitality?session_id={sessionId}`
- [ ] 扩展 `CohabitantInfo` 接口：新增 `state: 'active' | 'standby' | 'dormant'` 和 `vitality_value: number` 字段
- [ ] 扩展 `SessionAgentInfo` 接口：新增 `vitality_value: number` 字段
- [ ] 验收：前端可正确调用生命力 API 并获取响应数据

### 10.2 更新 ActiveSessions 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/ActiveSessions.tsx` 中：
  - 将共居智能体的状态展示从二态（active / bound_inactive）扩展为三态（active / standby / dormant）
  - 待命智能体显示黄色"待命"标签和生命力值进度条
  - 沉睡智能体显示灰色"沉睡"标签
  - 活跃智能体显示绿色"活跃"标签（保持不变）
  - 生命力值以进度条形式展示：高生命力绿色，中等黄色，低灰色
- [ ] 验收：三态标签正确显示，生命力进度条颜色和长度与数值匹配

### 10.3 新增 i18n 三语翻译

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 中新增生命力相关翻译键：
  - `agent.vitality.standby`：待命
  - `agent.vitality.dormant`：沉睡
  - `agent.vitality.active`：活跃
  - `agent.vitality.value`：生命力
  - `agent.vitality.lastStimulus`：最近刺激
- [ ] 在 `dashboard/src/i18n/locales/en.json` 中新增对应英文翻译
- [ ] 在 `dashboard/src/i18n/locales/ja.json` 中新增对应日文翻译
- [ ] 验收：切换语言时标签和提示文本正确跟随切换

## 11. 集成验证

### 11.1 端到端功能验证

- [ ] 验证沉睡→待命自动激活：绑定 13 个智能体到会话，发送消息后 12 个非活跃智能体自动进入待命
- [ ] 验证环境感知：用户消息到达后，待命智能体生命力增长；提及名字时大幅增长
- [ ] 验证心跳评估：60 秒心跳触发后，待命智能体生命力正确更新（含内在需求加成和衰减）
- [ ] 验证待命→活跃跃迁：生命力达到阈值后自动跃迁，跃迁后立即产生行为意图
- [ ] 验证提及即时跃迁：直接提及待命智能体名字时绕过阈值立即跃迁
- [ ] 验证活跃→待命回落：非主发言智能体超时后回落为待命而非退场
- [ ] 验证回落退场：待命 120 分钟且生命力为 0 后真正退场
- [ ] 验证共居插话优化：绑定 ≥3 个智能体时插话阈值降低、冷却缩短
- [ ] 验证会话恢复：重启后待命智能体从数据库正确恢复
- [ ] 验证降级安全：VitalityManager 异常不导致 Orchestrator 降级

### 11.2 性能验证

- [ ] 验证心跳评估性能：13 个待命智能体单次心跳 < 2 秒
- [ ] 验证环境感知性能：单条消息处理延迟 < 200ms
- [ ] 验证无待命智能体时零开销：无待命智能体的会话心跳跳过
- [ ] 验证内存占用：13 个待命智能体内存增量 < 5 KB

### 11.3 兼容性验证

- [ ] 验证单智能体模式兼容：未启用多智能体共居时不产生生命力计算开销
- [ ] 验证现有插话机制兼容：活跃智能体的插话逻辑不受影响
- [ ] 验证现有交互信号兼容：agent-interaction-alive 系统正常工作
- [ ] 验证配置文件兼容：新增配置参数不影响现有配置读取