# 智能体交互活化 — 编码任务规划

> 核心理念：理想的角色不应是一具等待结局的标本，而应是一场永恒的进行时。
> 让智能体从"等待用户触发的标本"变为"拥有记忆、因记忆而行动的持续互动生命体"。

---

## Phase 1：基础设施（交互事件+冷却+数据模型）

> 目标：建立交互活化的数据基础，实现交互事件的持久化和冷却控制。
> 交付后可独立验证：交互事件可持久化、冷却控制生效、WebUI 可查看交互事件。

### 1.1 创建 InteractionEvent 数据模型

- [ ] 在 `src/common/database/database_model.py` 中新增 `InteractionEvent` SQLModel 模型，表名 `agent_interaction_events`。字段：`event_id`（String 主键，格式 `ie:{agent_id}:{timestamp_hex}:{random_hex}`）、`initiator_agent_id`（String，索引）、`target_agent_id`（String，索引）、`interaction_type`（String，索引，枚举值：emotion_driven/time_awareness/mention_propagation/event_ripple/inner_need/memory_driven/manual_trigger/inner_monologue）、`trigger_reason`（String，非空）、`content_summary`（String，最大500字符）、`emotion_effects`（String，JSON）、`relationship_effect`（Float）、`memory_write_status`（String，枚举值：success/failed/policy_rejected/skipped）、`echo_depth`（Integer，默认0）、`echo_parent_event_id`（String，默认空串）、`created_at`（DateTime，索引）、`metadata`（String，JSON）。索引：`(initiator_agent_id, created_at)`、`(target_agent_id, created_at)`、`(interaction_type)`、`(created_at)`。
- **验收标准**：模型可被 SQLModel 识别，`create_all` 后数据库中存在 `agent_interaction_events` 表，字段和索引正确。
- **涉及文件**：`src/common/database/database_model.py`（修改）
- **依赖**：无

### 1.2 创建 InteractionCooldown 数据模型

- [ ] 在 `src/common/database/database_model.py` 中新增 `InteractionCooldown` SQLModel 模型，表名 `agent_interaction_cooldowns`。字段：`agent_pair_key`（String 主键，格式 `{smaller_id}:{larger_id}`）、`last_interaction_at`（DateTime）、`interaction_count_hourly`（Integer，默认0）、`interaction_count_daily`（Integer，默认0）、`hourly_reset_at`（DateTime）、`daily_reset_at`（DateTime）。索引：`(agent_pair_key)`。
- **验收标准**：模型可被 SQLModel 识别，`create_all` 后数据库中存在 `agent_interaction_cooldowns` 表。
- **涉及文件**：`src/common/database/database_model.py`（修改）
- **依赖**：无

### 1.3 创建 InnerMonologueEvent 数据模型

- [ ] 在 `src/common/database/database_model.py` 中新增 `InnerMonologueEvent` SQLModel 模型，表名 `agent_inner_monologue_events`。字段：`monologue_id`（String 主键，格式 `im:{agent_id}:{timestamp_hex}`）、`agent_id`（String，索引）、`emotion_snapshot`（String，JSON）、`content`（String，最大1000字符）、`self_emotion_effect`（String，JSON）、`memory_references`（String，JSON数组）、`created_at`（DateTime，索引）。索引：`(agent_id, created_at)`、`(created_at)`。
- **验收标准**：模型可被 SQLModel 识别，`create_all` 后数据库中存在 `agent_inner_monologue_events` 表。
- **涉及文件**：`src/common/database/database_model.py`（修改）
- **依赖**：无

### 1.4 创建 AgentInteractionRelationship 数据模型

- [ ] 在 `src/common/database/database_model.py` 中新增 `AgentInteractionRelationship` SQLModel 模型，表名 `agent_interaction_relationships`。字段：`id`（Integer 自增主键）、`agent_id`（String，索引）、`target_agent_id`（String，索引）、`score`（Float，默认0）、`relationship_type`（String）、`attitude`（String）、`interaction_count`（Integer，默认0）、`last_interaction_at`（DateTime，可空）、`created_at`（DateTime）、`updated_at`（DateTime）。唯一约束：`(agent_id, target_agent_id)`。
- **验收标准**：模型可被 SQLModel 识别，`create_all` 后数据库中存在 `agent_interaction_relationships` 表，唯一约束生效。
- **涉及文件**：`src/common/database/database_model.py`（修改）
- **依赖**：无

### 1.5 创建交互活化模块目录结构

- [ ] 创建 `src/maisaka/agent_interaction/` 包目录，包含 `__init__.py`。创建子包：`models/`（`__init__.py`）、`config/`（`__init__.py`）、`memory/`（`__init__.py`）。在 `models/__init__.py` 中从 `database_model` 导出数据模型的 Pydantic 版本（非 table 版本），用于服务层内部传递。Pydantic 版本包含：`InteractionEventCreate`（创建用，不含 event_id/created_at）、`InteractionEventRead`（读取用，含全部字段）、`InteractionCooldownRead`、`InnerMonologueEventRead`、`AgentInteractionRelationshipCreate`、`AgentInteractionRelationshipRead`。
- **验收标准**：目录结构完整，Pydantic 模型可正常实例化，与 SQLModel 字段对齐。
- **涉及文件**：`src/maisaka/agent_interaction/__init__.py`（新建）、`src/maisaka/agent_interaction/models/__init__.py`（新建）、`src/maisaka/agent_interaction/config/__init__.py`（新建）、`src/maisaka/agent_interaction/memory/__init__.py`（新建）
- **依赖**：1.1 ~ 1.4

### 1.6 实现 InteractionEventStore 交互事件存储

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `event_store.py`，实现 `InteractionEventStore` 类。方法：`async save_event(event_data: InteractionEventCreate) -> str`（持久化交互事件，生成 event_id，返回事件ID）、`async get_event(event_id: str) -> InteractionEventRead | None`（按 event_id 查询）、`async query_events(*, agent_id="", target_agent_id="", interaction_type="", time_start=None, time_end=None, limit=50, offset=0) -> list[InteractionEventRead]`（按条件查询，支持多条件组合）、`async get_recent_events(limit=20) -> list[InteractionEventRead]`（获取最近交互事件）。所有数据库操作通过 `get_db_session()` 获取会话。`save_event` 同时输出结构化日志 `[agent_interaction] A→B type=XX reason=XX`。
- **验收标准**：事件可持久化到数据库，系统重启后可查询；查询支持按智能体、类型、时间范围过滤；日志格式正确。
- **涉及文件**：`src/maisaka/agent_interaction/event_store.py`（新建）
- **依赖**：1.5

### 1.7 实现 InteractionCooldownManager 交互冷却管理器

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `cooldown.py`，实现 `InteractionCooldownManager` 类。方法：`can_trigger(agent_pair_key: str, cooldown_minutes: int = 30, max_per_hour: int = 2, max_per_day: int = 8) -> bool`（检查是否可触发，同时检查冷却时间和频率限制）、`record_interaction(agent_pair_key: str) -> None`（记录一次交互触发，更新 last_interaction_at 和计数器）、`get_cooldown_remaining(agent_pair_key: str, cooldown_minutes: int = 30) -> float`（获取剩余冷却时间秒数）。内部逻辑：`agent_pair_key` 由两个 agent_id 按字典序排列拼接；小时/天计数器在 `hourly_reset_at`/`daily_reset_at` 过期时自动重置。参考 `ProactiveFrequencyController` 的设计模式但按 agent_pair_key 管理。
- **验收标准**：同一对智能体交互后 30 分钟内不可再次触发；每小时最多 2 次，每天最多 8 次；计数器在小时/天切换时自动重置。
- **涉及文件**：`src/maisaka/agent_interaction/cooldown.py`（新建）
- **依赖**：1.2, 1.5

### 1.8 创建交互触发配置模型

- [ ] 在 `src/maisaka/agent_interaction/config/` 下创建 `trigger_config.py`，实现 `InteractionTriggerConfig` Pydantic 模型。字段：`enabled`（bool，默认True）、`cooldown_minutes`（int，≥5，默认30）、`max_interactions_per_hour`（int，1-10，默认2）、`max_interactions_per_day`（int，1-20，默认8）、`echo_enabled`（bool，默认True）、`echo_max_depth`（int，1-5，默认3）、`echo_decay_ratio`（float，0.1-1.0，默认0.5）、`monologue_enabled`（bool，默认True）、`monologue_min_interval_minutes`（int，≥5，默认15）、`monologue_idle_threshold_minutes`（int，≥10，默认30）、`monologue_emotion_intensity_threshold`（int，0-100，默认40）。实现 `MemoryDrivenTriggerConfig` Pydantic 模型。字段：`enabled`（bool，默认True）、`positive_memory_trigger_bonus`（float，0.0-0.5，默认0.2）、`negative_memory_trigger_penalty`（float，0.0-0.5，默认0.3）、`reunion_trigger_probability`（float，0.0-1.0，默认0.15）、`reunion_threshold_hours`（int，≥6，默认24）、`memory_weight_in_trigger`（float，0.0-1.0，默认0.3）、`propagated_memory_weight_ratio`（float，0.0-1.0，默认0.5）、`memory_decay_days`（int，≥3，默认7）、`memory_decay_ratio`（float，0.0-1.0，默认0.3）、`frequent_interaction_threshold`（int，≥2，默认3）、`frequent_interaction_reinforce_ratio`（float，0.0-0.5，默认0.2）。
- **验收标准**：两个配置模型可正常实例化，默认值符合 spec 定义，字段约束生效。
- **涉及文件**：`src/maisaka/agent_interaction/config/trigger_config.py`（新建）
- **依赖**：1.5

### 1.9 在配置模板中新增交互活化配置节

- [ ] 在 bot_config 模板中新增 `[agent_interaction]` 配置节，包含 `InteractionTriggerConfig` 的所有字段（使用默认值）。新增 `[agent_interaction.memory_driven]` 子节，包含 `MemoryDrivenTriggerConfig` 的所有字段。新增版本号。不修改 `legacy_migration`。
- **验收标准**：配置模板包含完整的交互活化配置节，字段和默认值与 `InteractionTriggerConfig`/`MemoryDrivenTriggerConfig` 一致。
- **涉及文件**：配置模板文件（修改）
- **依赖**：1.8

### 1.10 实现 WebUI 交互事件 API

- [ ] 在 `src/webui/routers/agent.py` 中新增以下 API 端点：`GET /api/webui/agent/interactions/recent`（获取最近交互事件列表，参数 `limit` 默认20，调用 `InteractionEventStore.get_recent_events`）、`GET /api/webui/agent/interactions/{event_id}`（获取交互事件详情，调用 `InteractionEventStore.get_event`）、`GET /api/webui/agent/interactions/history`（按条件查询交互历史，参数 `agent_id`/`target_agent_id`/`interaction_type`/`time_start`/`time_end`/`limit`/`offset`，调用 `InteractionEventStore.query_events`）。新增对应的 Pydantic 响应模型。
- **验收标准**：3个 API 端点可正常调用，返回正确的 JSON 数据；查询支持多条件过滤。
- **涉及文件**：`src/webui/routers/agent.py`（修改）
- **依赖**：1.6

---

## Phase 2：交互触发+影响落实

> 目标：实现6种触发类型和交互影响的原子写入，让智能体间交互从"数据骨架"变为"可触发的生命活动"。
> 交付后可独立验证：情绪驱动触发生效、交互影响原子写入、冷却控制正确。

### 2.1 实现 AgentEmotionManagerRegistry 全局情绪管理

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `emotion_registry.py`，实现 `AgentEmotionManagerRegistry` 类。为每个智能体维护一个全局 `EmotionManager` 实例，初始化时从 `AgentConfig.emotion_baseline` 构建。方法：`get_emotion_manager(agent_id: str) -> EmotionManager`（获取或创建智能体的全局 EmotionManager）、`get_emotion_state(agent_id: str) -> EmotionState`（获取智能体当前情绪状态）、`apply_trigger(agent_id: str, emotion_type: str, delta: float) -> None`（写入情绪变化）。内部使用 `AgentConfigRegistry` 获取智能体配置。全局实例与 `ChatLoopService` 中的会话实例独立，后续由会话创建时从全局实例读取基线来同步。
- **验收标准**：每个智能体有独立的全局 EmotionManager，情绪变化可通过 `apply_trigger` 写入，`get_emotion_state` 返回正确的衰减后状态。
- **涉及文件**：`src/maisaka/agent_interaction/emotion_registry.py`（新建）
- **依赖**：1.5

### 2.2 实现 AgentInteractionRelationship 初始化与更新

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `relationship_manager.py`，实现 `AgentRelationshipManager` 类。方法：`async initialize_from_config()`（从 `AgentConfig.internal_relationships` 导入基线数据到 `AgentInteractionRelationship` 表，仅插入不存在的记录）、`async get_relationship(agent_id: str, target_agent_id: str) -> AgentInteractionRelationshipRead | None`（查询智能体间关系）、`async update_relationship(agent_id: str, target_agent_id: str, delta: float) -> AgentInteractionRelationshipRead`（更新关系分数，截断到0-1000范围，更新 interaction_count 和 last_interaction_at）。初始化时从 `InternalRelationship` 导入基线：`score` 从 `mention_tendency` 映射（0-1 → 0-300），`relationship_type` 和 `attitude` 直接复制。
- **验收标准**：初始化后数据库中存在所有智能体间关系记录；关系分数更新后截断到0-1000；interaction_count 正确递增。
- **涉及文件**：`src/maisaka/agent_interaction/relationship_manager.py`（新建）
- **依赖**：1.4, 1.5

### 2.3 实现 BaseTrigger 基类和 TriggerEvaluation 数据类

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `trigger_base.py`，实现 `BaseTrigger` 抽象基类和 `TriggerEvaluation` 数据类。`BaseTrigger` 定义 `async evaluate(agent_id, emotion_state, relationships, memory_context, time_context) -> TriggerEvaluation` 抽象方法。`TriggerEvaluation` 包含：`should_trigger`（bool）、`trigger_probability`（float）、`target_agent_id`（str）、`interaction_type`（str）、`trigger_reason`（str）、`metadata`（dict）。实现 `TriggerRegistry` 触发器注册表，支持 `register(trigger_type: str, trigger: BaseTrigger)` 和 `get(trigger_type: str) -> BaseTrigger | None`。
- **验收标准**：`BaseTrigger` 可被子类继承，`TriggerEvaluation` 可正常实例化，`TriggerRegistry` 支持注册和获取触发器。
- **涉及文件**：`src/maisaka/agent_interaction/trigger_base.py`（新建）
- **依赖**：1.5

### 2.4 实现 EmotionDrivenTrigger 情绪驱动触发器

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `triggers/emotion_driven.py`，实现 `EmotionDrivenTrigger` 类（继承 `BaseTrigger`）。触发逻辑：遍历智能体的 `internal_relationships`，对每个关系计算触发概率 = 主导情绪强度/100 × mention_tendency × 情绪-关系匹配系数。情绪-关系匹配规则：lonely → family/romantic 系数1.5、friend 系数1.0；happy → friend 系数1.2；excited → friend/rival 系数1.0；anxious → family/mentor 系数1.3。选择触发概率最高的目标智能体。当主导情绪强度 ≥ 阈值（默认60）且触发概率 ≥ 0.3 时 `should_trigger=True`。`interaction_type` 为 `emotion_driven`，`trigger_reason` 格式为 `"情绪驱动：{agent_id}的{emotion}强度{intensity}，向{target_id}发起{interaction_desc}"`。
- **验收标准**：智能体 lonely 强度 ≥ 60 且 mention_tendency ≥ 0.3 时触发交互；触发目标为关系最亲密的智能体；trigger_reason 包含完整的触发描述。
- **涉及文件**：`src/maisaka/agent_interaction/triggers/emotion_driven.py`（新建）、`src/maisaka/agent_interaction/triggers/__init__.py`（新建）
- **依赖**：2.3

### 2.5 实现 TimeAwarenessTrigger 时间感知触发器

- [ ] 在 `src/maisaka/agent_interaction/triggers/` 下创建 `time_awareness.py`，实现 `TimeAwarenessTrigger` 类（继承 `BaseTrigger`）。触发逻辑：调用 `TimeAwarenessService.get_time_context()` 获取当前时段，调用 `AgentConfig.time_behavior_profile` 获取对应时段的活跃系数。当活跃系数 ≥ 0.8 且关系类型为 family/romantic 时，触发概率 = 活跃系数 × mention_tendency × 0.8。深夜时段（22:00-06:00）仅对 family/romantic 关系触发。`interaction_type` 为 `time_awareness`，`trigger_reason` 格式为 `"时间感知：{agent_id}在{time_period}的活跃系数{coefficient}，向{target_id}发起{interaction_desc}"`。
- **验收标准**：深夜时段且 night_active_coefficient ≥ 0.8 且关系类型为 family/romantic 时触发；其他时段活跃系数 ≥ 0.8 时对亲密关系触发。
- **涉及文件**：`src/maisaka/agent_interaction/triggers/time_awareness.py`（新建）
- **依赖**：2.3

### 2.6 实现 MentionPropagationTrigger 提及传递触发器

- [ ] 在 `src/maisaka/agent_interaction/triggers/` 下创建 `mention_propagation.py`，实现 `MentionPropagationTrigger` 类（继承 `BaseTrigger`）。触发逻辑：当智能体在对话中被自然提及（非@）时，检查被提及智能体与提及方的 mention_tendency ≥ 0.3，触发概率 = mention_tendency × 0.6。被提及智能体产生"被提及反应"，情绪和关系可能变化。`interaction_type` 为 `mention_propagation`，`trigger_reason` 格式为 `"提及传递：{target_id}被{agent_id}提及，mention_tendency={value}"`。此触发器需要外部信号驱动（由对话运行时调用），不自行轮询。
- **验收标准**：被提及智能体与提及方的 mention_tendency ≥ 0.3 时产生反应；触发概率与 mention_tendency 正相关。
- **涉及文件**：`src/maisaka/agent_interaction/triggers/mention_propagation.py`（新建）
- **依赖**：2.3

### 2.7 实现 EventRippleTrigger 事件涟漪触发器

- [ ] 在 `src/maisaka/agent_interaction/triggers/` 下创建 `event_ripple.py`，实现 `EventRippleTrigger` 类（继承 `BaseTrigger`）。触发逻辑：当智能体与用户发生重要交互（关系升级、情绪剧烈变化等）时，向关联智能体传播信号。遍历该智能体的 internal_relationships 中关系类型为 family/romantic 的智能体，触发概率 = 事件影响强度 × mention_tendency × 0.5。`interaction_type` 为 `event_ripple`，`trigger_reason` 格式为 `"事件涟漪：{agent_id}与用户发生{event_desc}，向{target_id}传播信号"`。此触发器需要外部事件信号驱动。
- **验收标准**：智能体与用户关系升级时，family/romantic 关系的智能体收到涟漪信号；触发概率与事件影响强度和 mention_tendency 正相关。
- **涉及文件**：`src/maisaka/agent_interaction/triggers/event_ripple.py`（新建）
- **依赖**：2.3

### 2.8 实现 InnerNeedTrigger 内部需求触发器

- [ ] 在 `src/maisaka/agent_interaction/triggers/` 下创建 `inner_need.py`，实现 `InnerNeedTrigger` 类（继承 `BaseTrigger`）。触发逻辑：当智能体情绪状态连续一段时间（默认2小时）为 calm 且 intensity < 20 时，产生"无聊"内部需求。遍历 internal_relationships，触发概率 = (1 - calm_intensity/20) × mention_tendency × 0.4。选择触发概率最高的目标智能体。`interaction_type` 为 `inner_need`，`trigger_reason` 格式为 `"内部需求：{agent_id}感到{need_desc}，向{target_id}寻求{interaction_desc}"`。
- **验收标准**：智能体 calm 情绪强度 < 20 持续2小时后产生"无聊"需求；触发概率与 calm 强度负相关、与 mention_tendency 正相关。
- **涉及文件**：`src/maisaka/agent_interaction/triggers/inner_need.py`（新建）
- **依赖**：2.3

### 2.9 实现 EffectCalculator 影响计算器

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `effect_calculator.py`，实现 `EffectCalculator` 类和 `InteractionEffect` 数据类。`InteractionEffect` 包含：`initiator_emotion_deltas`（dict[str, float]）、`target_emotion_deltas`（dict[str, float]）、`relationship_delta`（float）、`memory_content`（str）、`emotion_tag`（str，枚举 positive/negative/neutral/mixed）。`calculate(interaction_type, relationship_type, initiator_emotion, target_emotion, echo_depth=0) -> InteractionEffect` 方法基于规则引擎计算影响。规则示例：emotion_driven + lonely + family → initiator: {lonely: -15, happy: +10}, target: {happy: +5, calm: -5}, relationship: +3.0, tag: positive；emotion_driven + rival → initiator: {excited: +3}, target: {angry: +5, happy: +3}, relationship: +1.0, tag: mixed。回声深度 > 0 时影响量 × echo_decay_ratio^echo_depth。所有影响量为0时返回空结果（禁止零影响交互）。
- **验收标准**：不同交互类型和关系类型产生不同的情绪/关系影响；回声影响量按衰减比例递减；所有影响量为0时返回空结果。
- **涉及文件**：`src/maisaka/agent_interaction/effect_calculator.py`（新建）
- **依赖**：1.5

### 2.10 实现 InteractionEngine 交互引擎

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `engine.py`，实现 `InteractionEngine` 类和 `InteractionResult` 数据类。`InteractionResult` 包含：`success`（bool）、`event_id`（str）、`emotion_effects`（dict）、`relationship_effect`（float）、`memory_write_status`（str）、`echo_triggered`（bool）、`error`（str）。核心方法 `async execute(evaluation: TriggerEvaluation) -> InteractionResult`：1) 调用 `EffectCalculator.calculate` 计算影响；2) 若影响为空则返回失败；3) 开启事务：写入双方情绪变化（`AgentEmotionManagerRegistry.apply_trigger`）、更新关系分数（`AgentRelationshipManager.update_relationship`）、写入交互记忆（`AgentMemoryAdapter.write_interaction_memory`，Phase 3 实现，此处先跳过并标记 `memory_write_status=skipped`）；4) 全部成功则提交事务并持久化交互事件（`InteractionEventStore.save_event`）；5) 部分失败则回滚已写入的影响并标记事件为"影响写入失败"。方法 `async execute_manual(initiator_id, target_id, interaction_type, reason) -> InteractionResult`：管理员手动触发，记录审计日志。
- **验收标准**：交互触发后双方情绪和关系正确变化；情绪+关系+记忆三者原子写入（全部成功或全部回滚）；交互事件持久化到数据库；管理员手动触发记录审计日志。
- **涉及文件**：`src/maisaka/agent_interaction/engine.py`（新建）
- **依赖**：2.1, 2.2, 2.9, 1.6, 1.7

### 2.11 实现 InteractionTrigger 触发器调度器

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `trigger_scheduler.py`，实现 `InteractionTrigger` 调度器类。核心方法 `async evaluate_all(agent_id: str) -> TriggerEvaluation | None`：1) 从 `AgentEmotionManagerRegistry` 获取情绪状态；2) 从 `AgentConfigRegistry` 获取关系网；3) 遍历所有已注册的触发器（通过 `TriggerRegistry`），调用各触发器的 `evaluate` 方法；4) 综合触发概率 = 情绪权重(0.4)×情绪概率 + 时间权重(0.3)×时间概率 + 关系权重(0.3)×关系概率（Phase 3 增加记忆权重）；5) 选择综合概率最高的触发结果；6) 若综合概率 ≥ 触发阈值（默认0.5），检查冷却状态（`InteractionCooldownManager.can_trigger`）；7) 冷却通过则返回触发决策，否则返回 None。方法 `async try_trigger(agent_id: str) -> InteractionResult | None`：调用 `evaluate_all` 获取触发决策，若非空则调用 `InteractionEngine.execute`。
- **验收标准**：综合多种触发信号计算触发概率；冷却控制正确阻止重复触发；触发后调用 InteractionEngine 执行交互。
- **涉及文件**：`src/maisaka/agent_interaction/trigger_scheduler.py`（新建）
- **依赖**：2.3 ~ 2.8, 2.10, 1.7

### 2.12 实现交互引擎定时调度

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `scheduler.py`，实现 `InteractionScheduler` 类。使用 `asyncio` 定时任务，每隔 `evaluation_interval_seconds`（默认300秒/5分钟）遍历所有已注册智能体，调用 `InteractionTrigger.try_trigger(agent_id)`。调度器可通过 `start()`/`stop()` 控制生命周期。调度器异常时降级为静默模式（不触发交互），不影响主对话流程。在应用启动时（`src/main.py` 或相关入口）注册调度器启动。
- **验收标准**：调度器每5分钟遍历所有智能体评估交互触发；异常时不影响主对话流程；可正常启动和停止。
- **涉及文件**：`src/maisaka/agent_interaction/scheduler.py`（新建）
- **依赖**：2.11

---

## Phase 3：记忆深度配合

> 目标：实现智能体交互记忆的语义映射、画像生成和提示词注入，让交互留痕真正影响智能体的行为。
> 交付后可独立验证：交互记忆通过语义映射写入、画像由记忆聚合生成、交互记忆可注入提示词。

### 3.1 实现 AgentMemoryAdapter 智能体记忆适配器

- [ ] 在 `src/maisaka/agent_interaction/memory/` 下创建 `adapter.py`，实现 `AgentMemoryAdapter` 类。静态方法 `build_chat_id(agent_a_id, agent_b_id) -> str`：返回 `agent_interaction:{smaller_id}:{larger_id}`（按字典序排列保证方向无关）。静态方法 `build_person_id(agent_id) -> str`：返回 `agent:{agent_id}`。方法 `async write_interaction_memory(event: InteractionEventRead, effect: InteractionEffect) -> MemoryWriteResult`：为双方分别调用 `MemoryService.ingest_text()` 写入交互记忆，参数：`external_id=event.event_id`、`source_type="agent_interaction"`、`chat_id=build_chat_id(A, B)`、`person_ids=[build_person_id(agent_id)]`、`tags=["agent_interaction", effect.emotion_tag, event.interaction_type]`、`metadata={interaction_event_id, emotion_snapshot, relationship_delta}`。方法 `async search_interaction_memory(agent_id, target_agent_id, query="", limit=5) -> MemorySearchResult`：调用 `MemoryService.search()` 检索交互记忆，参数：`chat_id=build_chat_id(agent_id, target_agent_id)`、`person_id=build_person_id(agent_id)`。
- **验收标准**：交互记忆通过 `agent_interaction:{A}:{B}` chat_id 写入，不污染用户记忆；检索通过相同的 chat_id/person_id 命名空间隔离；写入前校验 chat_id 前缀格式。
- **涉及文件**：`src/maisaka/agent_interaction/memory/adapter.py`（新建）
- **依赖**：1.5, 1.6

### 3.2 在 InteractionEngine 中接入记忆写入

- [ ] 修改 `src/maisaka/agent_interaction/engine.py`，在 `execute` 方法中将 Phase 2 的 `memory_write_status=skipped` 替换为实际调用 `AgentMemoryAdapter.write_interaction_memory`。记忆写入失败时标记 `memory_write_status=failed`，但不回滚情绪和关系影响（记忆写入降级为非阻塞）。A_Memorix 不可用时降级为本地日志记录，标记 `memory_write_status=failed`。写入成功后调用 `AgentProfileService.mark_stale` 标记画像待刷新（Phase 3.3 实现后接入）。
- **验收标准**：交互后双方交互记忆正确写入 A_Memorix；记忆写入失败不阻塞情绪和关系影响；A_Memorix 不可用时降级为日志记录。
- **涉及文件**：`src/maisaka/agent_interaction/engine.py`（修改）
- **依赖**：3.1, 2.10

### 3.3 实现 AgentProfileService 智能体画像服务

- [ ] 在 `src/maisaka/agent_interaction/memory/` 下创建 `profile.py`，实现 `AgentProfileService` 类和 `AgentProfileResult` 数据类。`AgentProfileResult` 包含：`observer_agent_id`、`target_agent_id`、`summary`（str，最大500字符）、`traits`（list[str]，最多10项）、`evidence`（list[dict]）、`interaction_count`（int）、`last_interaction_at`（float）、`emotion_tendency`（str）、`refresh_status`（str：fresh/stale/pending）。方法 `async get_profile(observer_agent_id, target_agent_id) -> AgentProfileResult`：检查缓存（内存 TTL 缓存），若 fresh 则返回缓存；若 stale/pending 则调用 `refresh_profile`。方法 `async refresh_profile(observer_agent_id, target_agent_id) -> AgentProfileResult`：1) 调用 `AgentMemoryAdapter.search_interaction_memory` 获取交互记忆；2) 调用 `InteractionEventStore.query_events` 获取交互事件；3) 聚合生成画像：summary 从最近5次交互内容摘要拼接，traits 从交互记忆中提取高频特征，evidence 从交互事件中提取关键事实；4) 更新缓存，标记 fresh。方法 `async mark_stale(observer_agent_id, target_agent_id) -> None`：标记画像为 stale。当累计交互次数 < 3 时返回空画像。
- **验收标准**：累计交互 ≥ 3 次后自动生成画像，包含交互风格总结、关系演变轨迹、情感倾向；画像由交互记忆聚合生成，结构兼容 `PersonProfileResult`；交互记忆更新后画像标记为 stale，下次检索时重新聚合。
- **涉及文件**：`src/maisaka/agent_interaction/memory/profile.py`（新建）
- **依赖**：3.1, 1.6

### 3.4 扩展 HeuristicMemoryInjector 识别智能体交互记忆

- [ ] 修改 `src/maisaka/memory/heuristic_injector.py`，在 `_is_hit_allowed()` 方法中增加对 `agent_interaction:` 前缀 chat_id 的识别逻辑。当命中的 chat_id 以 `agent_interaction:` 开头时，检查当前智能体（通过 `agent_id` 参数）是否为该交互记忆的参与方（从 chat_id 中解析两个 agent_id），若是则允许该命中，否则拒绝。确保不会将其他智能体对的私密交互记忆注入到不相关的智能体提示词中。遵守 CrossChatContextService 的共享规则。
- **验收标准**：`agent_interaction:` 前缀的交互记忆可被 HeuristicMemoryInjector 检索到（当智能体是参与方时）；非参与方的交互记忆不被注入；不违反跨聊共享规则。
- **涉及文件**：`src/maisaka/memory/heuristic_injector.py`（修改）
- **依赖**：3.1

### 3.5 在 build_prompt_template_context 中新增 agent_interaction_memory slot

- [ ] 修改 `src/maisaka/chat_loop_service.py` 的 `build_prompt_template_context` 方法，新增 `agent_interaction_memory` slot。当 `self._agent_id` 存在时，调用 `AgentProfileService.get_profile` 获取该智能体对所有关系智能体的画像，格式化为"最近的交互动态"段落。格式示例：`"## 最近的交互动态\n- 与布洛妮娅：最近有过争执，语气可能更激烈\n- 与希儿：上次聊得很开心，关系更近了"`。该 slot 位于 `agent_internal_relationships` 之后，与静态关系描述合并注入（不替换）。交互记忆为空时（新部署）该 slot 为空字符串，静态 `internal_relationships_prompt` 作为兜底。
- **验收标准**：`build_prompt_template_context` 返回的字典包含 `agent_interaction_memory` key；有交互记忆时注入动态内容，无交互记忆时为空字符串；动态内容与静态关系描述合并注入。
- **涉及文件**：`src/maisaka/chat_loop_service.py`（修改）
- **依赖**：3.3

### 3.6 更新 prompt 模板三语同步

- [ ] 在 `prompts/zh-CN/maisaka_chat.prompt`、`prompts/en-US/maisaka_chat.prompt`、`prompts/ja-JP/maisaka_chat.prompt` 中，在 `{agent_internal_relationships}` 之后新增 `{agent_interaction_memory}` 占位符。确保三语模板结构一致。同步更新 `maisaka_replyer.prompt` 三语模板（如适用）。
- **验收标准**：三语 prompt 模板均包含 `{agent_interaction_memory}` 占位符，位于 `{agent_internal_relationships}` 之后；渲染后交互动态内容正确出现在提示词中。
- **涉及文件**：`prompts/zh-CN/maisaka_chat.prompt`（修改）、`prompts/en-US/maisaka_chat.prompt`（修改）、`prompts/ja-JP/maisaka_chat.prompt`（修改）
- **依赖**：3.5

### 3.7 在 DeepSeek 优化配置中注册交互记忆注入优先级

- [ ] 修改 `src/maisaka/agent/config.py` 中 `DeepSeekOptimizationConfig` 的 `injection_priority` 默认值，在 `anti_mechanization` 和 `profile` 之间插入 `interaction_memory`。修改 `prefix_cache_priority` 默认值，在 `internal_relationships` 之后插入 `interaction_memory`。确保交互记忆注入的优先级低于身份提示词和反机械化规则，高于一般启发式记忆。
- **验收标准**：`injection_priority` 和 `prefix_cache_priority` 包含 `interaction_memory` 项，位置正确。
- **涉及文件**：`src/maisaka/agent/config.py`（修改）
- **依赖**：3.5

---

## Phase 4：内心独白+交互回声

> 目标：实现内心独白和交互回声传播，让智能体拥有"内在生命"和"连锁反应"。
> 交付后可独立验证：内心独白在空闲时产生、交互回声链最大深度3层、记忆驱动触发生效。

### 4.1 实现 MonologueTrigger 内心独白触发器

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `monologue_trigger.py`，实现 `MonologueTrigger` 类。触发逻辑：当智能体空闲超过 `monologue_idle_threshold_minutes`（默认30分钟）且主导情绪强度 > `monologue_emotion_intensity_threshold`（默认40）时，触发内心独白。冷却期：同一智能体的内心独白至少间隔 `monologue_min_interval_minutes`（默认15分钟）。方法 `should_trigger(agent_id: str, idle_minutes: float, emotion_state: EmotionState) -> bool`。空闲时间追踪：记录每个智能体最后一次对话/交互的时间戳，`idle_minutes = now - last_active_at`。
- **验收标准**：智能体空闲 ≥ 30 分钟且情绪强度 > 40 时触发内心独白；同一智能体 15 分钟内不重复触发。
- **涉及文件**：`src/maisaka/agent_interaction/monologue_trigger.py`（新建）
- **依赖**：2.1

### 4.2 实现 MonologueEngine 内心独白引擎

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `monologue_engine.py`，实现 `MonologueEngine` 类。核心方法 `async execute(agent_id: str) -> InnerMonologueEvent`：1) 从 `AgentEmotionManagerRegistry` 获取情绪状态；2) 从 `AgentConfigRegistry` 获取智能体配置（性格特征）；3) 从 `AgentMemoryAdapter` 检索最近记忆（可选，A_Memorix 不可用时跳过）；4) 基于性格+情绪+记忆生成内心独白内容（优先使用 LLM 生成，LLM 不可用时降级为模板：`"{agent_name}默默地想着……{emotion_desc}"`）；5) 计算自我情绪影响（微小变化，+2~5），调用 `AgentEmotionManagerRegistry.apply_trigger` 写入；6) 持久化内心独白事件到 `InteractionEventStore`（interaction_type=inner_monologue）；7) 内心独白不触发任何外部行为（不产生对话或交互）。内容必须体现智能体性格特征（如银狼包含游戏/黑客元素，符华体现沉稳/守护者特征）。
- **验收标准**：内心独白内容体现智能体性格特征；产生微小自我情绪影响（+2~5）；内心独白事件持久化到数据库；不触发任何外部行为。
- **涉及文件**：`src/maisaka/agent_interaction/monologue_engine.py`（新建）
- **依赖**：4.1, 3.1, 1.6

### 4.3 实现 EchoDetector 回声检测器

- [ ] 在 `src/maisaka/agent_interaction/` 下创建 `echo_detector.py`，实现 `EchoDetector` 类。核心方法 `async check_and_propagate(result: InteractionResult, evaluation: TriggerEvaluation) -> None`：1) 检查交互结果中是否有单一情绪变化量 > 20（回声阈值）；2) 若超过阈值，检查回声深度 < `echo_max_depth`（默认3）；3) 检查传播链中无重复智能体（环路检测）；4) 通过检查后，构建回声触发决策（深度+1，影响量×echo_decay_ratio），递归调用 `InteractionTrigger.try_trigger`；5) 传播时间超过 30 秒强制截断。方法 `_detect_loop(chain: list[str], new_agent_id: str) -> bool`：检查传播链中是否已存在新智能体。
- **验收标准**：交互导致情绪剧烈变化（>20）时触发回声；回声链最大深度3层；每层影响量衰减50%；环路检测正确截断；30秒超时强制截断。
- **涉及文件**：`src/maisaka/agent_interaction/echo_detector.py`（新建）
- **依赖**：2.10, 2.11

### 4.4 在 InteractionEngine 中接入回声检测

- [ ] 修改 `src/maisaka/agent_interaction/engine.py`，在 `execute` 方法末尾，交互成功后调用 `EchoDetector.check_and_propagate(result, evaluation)`。回声检测异常时不影响已完成的交互（静默截断）。
- **验收标准**：交互完成后自动检查是否产生回声；回声检测异常不影响原交互结果。
- **涉及文件**：`src/maisaka/agent_interaction/engine.py`（修改）
- **依赖**：4.3, 2.10

### 4.5 实现 MemoryDrivenTrigger 记忆驱动触发器

- [ ] 在 `src/maisaka/agent_interaction/triggers/` 下创建 `memory_driven.py`，实现 `MemoryDrivenTrigger` 类（继承 `BaseTrigger`）。触发逻辑：1) 调用 `AgentMemoryAdapter.search_interaction_memory` 检索与各智能体的交互记忆；2) 正面交互记忆（emotion_tag=positive）对触发概率加成 `positive_memory_trigger_bonus`（默认+20%）；3) 负面交互记忆（emotion_tag=negative）对触发概率惩罚 `negative_memory_trigger_penalty`（默认-30%），但"想和好"类型交互概率 +15%；4) 检索到"上次约定再聊"类型记忆时，在合适时段主动发起"续聊"类型交互；5) 超过 `reunion_threshold_hours`（默认24小时）无交互时产生"想念"内部需求，触发概率 = `reunion_trigger_probability` × mention_tendency。`interaction_type` 为 `memory_driven`，`trigger_reason` 格式为 `"记忆驱动：{agent_id}基于与{target_id}的{memory_desc}发起交互"`。
- **验收标准**：正面交互记忆 +20% 触发概率，负面 -30%；"想和好"类型 +15%；24小时无交互产生"想念"需求；"续聊"类型引用上次交互内容。
- **涉及文件**：`src/maisaka/agent_interaction/triggers/memory_driven.py`（新建）
- **依赖**：2.3, 3.1

### 4.6 实现记忆传播机制

- [ ] 在 `src/maisaka/agent_interaction/memory/adapter.py` 中新增 `async propagate_memory(source_agent_id, target_agent_id, about_agent_id) -> None` 方法。逻辑：1) 检索 source_agent 关于 about_agent 的交互记忆；2) 筛选可传播的记忆（排除标记为"私密"的间接记忆——`metadata.propagated_from` 存在的记忆不可再传播）；3) 将筛选后的记忆以 `propagated_from=source_agent_id` 标记写入 target_agent 的记忆中；4) 间接记忆在提示词注入和触发决策中的权重为直接记忆的 50%（通过 `propagated_memory_weight_ratio` 配置）。在 `InteractionEngine.execute` 中，当交互双方存在共同关系人时调用记忆传播。
- **验收标准**：智能体 A 可在交互中向 B 传播关于 C 的记忆；间接记忆标记 `propagated_from`；间接记忆不可再传播（防止链式传播）；间接记忆权重为直接记忆的50%。
- **涉及文件**：`src/maisaka/agent_interaction/memory/adapter.py`（修改）
- **依赖**：3.1, 2.10

### 4.7 实现记忆衰减与强化机制

- [ ] 在 `src/maisaka/agent_interaction/memory/adapter.py` 中新增记忆衰减与强化逻辑。衰减：交互记忆超过 `memory_decay_days`（默认7天）未被引用时，检索权重衰减 `memory_decay_ratio`（默认30%）。强化：再次交互且引用旧记忆时，被引用的旧记忆权重恢复至原始值；频繁交互（24小时内 ≥ `frequent_interaction_threshold` 次）时，最近交互记忆权重强化 `frequent_interaction_reinforce_ratio`（默认+20%）。衰减和强化通过 `MemoryService.search()` 的权重参数和 `metadata` 标记实现。
- **验收标准**：7天未被引用的交互记忆检索权重衰减30%；被引用后权重恢复；频繁交互时最近记忆权重+20%。
- **涉及文件**：`src/maisaka/agent_interaction/memory/adapter.py`（修改）
- **依赖**：3.1

### 4.8 WebUI 内心世界面板 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/monologue/{agent_id}` 端点，获取智能体内心独白列表。参数 `limit` 默认10。从 `InnerMonologueEvent` 表查询，按 `created_at` 降序。新增 `GET /api/webui/agent/profile/{observer_id}/{target_id}` 端点，获取智能体画像。调用 `AgentProfileService.get_profile`。新增对应的 Pydantic 响应模型。
- **验收标准**：两个 API 端点可正常调用，返回正确的 JSON 数据。
- **涉及文件**：`src/webui/routers/agent.py`（修改）
- **依赖**：4.2, 3.3

---

## Phase 5：WebUI 可视化+配置化

> 目标：完善 WebUI 交互可见性和配置管理，让管理员能直观感知和调控智能体的"生命活动"。
> 交付后可独立验证：WebUI 可查看交互流和内心世界、交互参数可配置、管理员可手动触发交互。

### 5.1 前端交互记忆 API 函数

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增 API 函数：`getRecentInteractions(limit?: number)`、`getInteractionDetail(eventId: string)`、`getInteractionHistory(params: InteractionHistoryParams)`、`getAgentMonologues(agentId: string, limit?: number)`、`getAgentProfile(observerId: string, targetId: string)`。新增对应的 TypeScript 类型定义：`InteractionEventResponse`、`InnerMonologueEventResponse`、`AgentProfileResponse`、`InteractionHistoryParams`。遵循已有的 `backendApi.get` + `requireSuccess` 模式。
- **验收标准**：5个函数可正确调用后端 API 并返回类型安全的数据。
- **涉及文件**：`dashboard/src/lib/agent-api.ts`（修改）
- **依赖**：1.10, 4.8

### 5.2 创建交互流面板组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `InteractionStream.tsx`，实现交互流面板组件。展示最近的智能体间交互事件列表，每条事件显示：发起方头像+名称 → 接收方头像+名称、交互类型标签（颜色映射）、触发原因摘要、时间戳。点击事件展开详情：完整的触发原因、交互内容摘要、情绪影响详情、关系影响、记忆写入状态。使用 `useQuery` 调用 `getRecentInteractions`，自动刷新间隔 30 秒。空状态显示"暂无交互活动"占位符。使用 i18n 翻译键。
- **验收标准**：交互流面板展示最近交互事件，点击展开详情；30秒自动刷新；空状态有占位符。
- **涉及文件**：`dashboard/src/routes/agent/components/InteractionStream.tsx`（新建）
- **依赖**：5.1

### 5.3 创建内心世界面板组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `MonologuePanel.tsx`，实现内心世界面板组件。展示智能体的内心独白列表，每条独白显示：独白内容、情绪快照（简化展示主导情绪图标+强度）、自我情绪影响、时间戳。独白内容默认折叠，点击展开。使用 `useQuery` 调用 `getAgentMonologues`。空状态显示"内心世界暂无涟漪"占位符。使用 i18n 翻译键。
- **验收标准**：内心世界面板展示智能体内心独白列表，点击展开详情；空状态有占位符。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/MonologuePanel.tsx`（新建）
- **依赖**：5.1

### 5.4 创建交互配置管理组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `InteractionConfigPanel.tsx`，实现交互触发配置管理面板。展示 `InteractionTriggerConfig` 和 `MemoryDrivenTriggerConfig` 的所有字段，使用表单控件（开关、滑块、数字输入框）。保存时调用 `PUT /api/webui/agent/interactions/config` API。使用 `useMutation` + `invalidateQueries` 实现乐观更新。配置项分组展示：基础配置（启用/冷却/频率）、回声配置（启用/深度/衰减）、内心独白配置（启用/间隔/阈值）、记忆驱动配置（启用/加成/惩罚/想念阈值）。使用 i18n 翻译键。
- **验收标准**：配置面板展示所有交互触发配置项；修改后保存成功；分组展示清晰。
- **涉及文件**：`dashboard/src/routes/agent/components/InteractionConfigPanel.tsx`（新建）
- **依赖**：5.1

### 5.5 实现管理员手动触发交互 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `POST /api/webui/agent/interactions/trigger` 端点，管理员手动触发交互。请求体：`{ initiator_id: str, target_id: str, interaction_type: str, reason: str }`。调用 `InteractionEngine.execute_manual`，记录审计日志。新增 `GET /api/webui/agent/interactions/config` 端点获取交互触发配置，`PUT /api/webui/agent/interactions/config` 端点更新交互触发配置。新增对应的 Pydantic 请求/响应模型。
- **验收标准**：手动触发 API 可正常调用，交互事件持久化，审计日志记录；配置读写 API 正常工作。
- **涉及文件**：`src/webui/routers/agent.py`（修改）
- **依赖**：2.10, 1.8

### 5.6 前端手动触发交互组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `ManualTriggerDialog.tsx`，实现手动触发交互对话框。使用 Radix `Dialog` 组件。表单包含：发起方智能体选择（下拉列表）、接收方智能体选择（下拉列表）、交互类型选择（下拉列表）、触发原因输入（文本框）。提交时调用 `POST /api/webui/agent/interactions/trigger`。成功后刷新交互流面板。使用 i18n 翻译键。
- **验收标准**：对话框可选择智能体和交互类型，提交后交互事件出现在交互流中。
- **涉及文件**：`dashboard/src/routes/agent/components/ManualTriggerDialog.tsx`（新建）
- **依赖**：5.5

### 5.7 实现交互热点和关系网络动态

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/interactions/hotspots` 端点，返回交互热点对（24小时内交互超过5次的智能体对）。在 `InteractionStream` 组件中，热点对的事件以高亮样式展示。在星图（`AgentConstellation`）中，热点对的连线加粗或变色显示。关系分数变化时，星图中对应连线的粗细或颜色动态更新。
- **验收标准**：交互热点对在交互流中高亮显示；星图中热点对连线加粗/变色；关系分数变化反映在星图连线样式上。
- **涉及文件**：`src/webui/routers/agent.py`（修改）、`dashboard/src/routes/agent/components/InteractionStream.tsx`（修改）、`dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`（修改）
- **依赖**：5.2

### 5.8 集成交互流和内心世界到指挥中心布局

- [ ] 修改 `dashboard/src/routes/agent/components/CommandCenterLayout.tsx`，在指挥中心布局中集成交互流面板和内心世界面板。交互流面板作为全局视图的一个 Tab 或侧边栏面板。内心世界面板作为 InnerWorldView 的一个子视图。手动触发交互按钮放置在交互流面板的头部。配置管理入口放置在交互流面板的头部（齿轮图标）。
- **验收标准**：指挥中心可查看交互流和内心世界；手动触发和配置管理入口可达。
- **涉及文件**：`dashboard/src/routes/agent/components/CommandCenterLayout.tsx`（修改）
- **依赖**：5.2, 5.3, 5.4, 5.6

### 5.9 Phase 5 i18n 翻译键

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent` 命名空间下新增 Phase 5 所需翻译键：`agent.interaction.*`（stream.title、stream.empty、detail.triggerReason、detail.emotionEffect、detail.relationshipEffect、detail.memoryStatus、hotspot.label）、`agent.monologue.*`（panel.title、panel.empty、content.label、emotionSnapshot.label、selfEffect.label）、`agent.interactionConfig.*`（title、basic.*、echo.*、monologue.*、memoryDriven.*）、`agent.interaction.manualTrigger.*`（title、initiator、target、type、reason、submit）。同步至 `en.json`、`ja.json`、`ko.json`。
- **验收标准**：4种语言翻译键完整对齐，页面切换语言后文案正确。
- **涉及文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`、`ko.json`
- **依赖**：无

---

## Phase 6：集成验证与收尾

> 目标：端到端验证所有功能，确保交互活化系统作为整体可正常运行。

### 6.1 端到端交互触发验证

- [ ] 编写集成测试验证完整交互流程：1) 设置两个智能体（如 silver_wolf 和 bronya）的配置和关系；2) 将 silver_wolf 的 lonely 情绪强度设为 70；3) 运行交互调度器一轮；4) 验证 silver_wolf 向 bronya 发起了情绪驱动交互；5) 验证双方情绪变化正确；6) 验证关系分数更新；7) 验证交互记忆写入 A_Memorix；8) 验证交互事件持久化到数据库；9) 验证冷却控制阻止 30 分钟内重复触发。
- **验收标准**：完整交互流程端到端通过，所有验证点通过。
- **涉及文件**：`tests/` 目录下新建测试文件
- **依赖**：Phase 1 ~ 3 全部完成

### 6.2 内心独白端到端验证

- [ ] 编写集成测试验证内心独白流程：1) 设置智能体空闲时间 > 30 分钟且情绪强度 > 40；2) 运行内心独白触发检查；3) 验证内心独白内容生成（包含性格特征）；4) 验证自我情绪影响写入；5) 验证内心独白事件持久化；6) 验证内心独白不触发外部行为；7) 验证冷却期阻止 15 分钟内重复触发。
- **验收标准**：内心独白流程端到端通过，所有验证点通过。
- **涉及文件**：`tests/` 目录下新建测试文件
- **依赖**：Phase 4 全部完成

### 6.3 交互回声端到端验证

- [ ] 编写集成测试验证交互回声流程：1) 设置三个智能体 A、B、C 的关系链；2) 触发 A→B 交互，使 B 的情绪剧烈变化（>20）；3) 验证回声触发 B→C 交互；4) 验证回声影响量衰减50%；5) 验证回声深度不超过3层；6) 验证环路检测截断 A→B→C→A 的传播链。
- **验收标准**：交互回声流程端到端通过，深度限制和环路检测正确。
- **涉及文件**：`tests/` 目录下新建测试文件
- **依赖**：Phase 4 全部完成

### 6.4 记忆驱动触发端到端验证

- [ ] 编写集成测试验证记忆驱动触发：1) 创建 A↔B 的正面交互记忆；2) 验证 A 对 B 的触发概率 +20%；3) 创建 A↔B 的负面交互记忆；4) 验证 A 对 B 的触发概率 -30%，但"想和好"类型 +15%；5) 设置 A↔B 超过 24 小时无交互；6) 验证 A 产生"想念"内部需求；7) 验证记忆传播：A 向 C 传播关于 B 的记忆，C 获得间接记忆。
- **验收标准**：记忆驱动触发流程端到端通过，所有验证点通过。
- **涉及文件**：`tests/` 目录下新建测试文件
- **依赖**：Phase 3 ~ 4 全部完成

### 6.5 提示词注入验证

- [ ] 编写测试验证交互记忆提示词注入：1) 创建 A↔B 的交互记忆（正面/负面）；2) 构建包含 A 的对话提示词；3) 验证 `agent_interaction_memory` slot 包含正确的交互动态内容；4) 验证交互记忆注入优先级正确（低于身份和反机械化，高于一般启发式记忆）；5) 验证 HeuristicMemoryInjector 可检索到 `agent_interaction:` 前缀的记忆。
- **验收标准**：交互记忆正确注入到提示词中，优先级正确，HeuristicMemoryInjector 可检索。
- **涉及文件**：`tests/` 目录下新建测试文件
- **依赖**：Phase 3 全部完成

### 6.6 WebUI 交互可见性验证

- [ ] 手动验证 WebUI 交互可见性：1) 打开指挥中心，查看交互流面板是否展示交互事件；2) 点击交互事件查看详情；3) 打开内心世界面板查看内心独白；4) 修改交互触发配置并保存；5) 手动触发一次交互并验证出现在交互流中；6) 验证交互热点对高亮显示。
- **验收标准**：WebUI 所有交互可见性功能正常工作。
- **涉及文件**：手动验证
- **依赖**：Phase 5 全部完成

### 6.7 性能与可靠性验证

- [ ] 验证性能指标：1) 交互触发决策延迟 < 500ms（不含 LLM 调用）；2) 交互影响计算（情绪+关系+记忆）< 1s；3) 单次交互事件持久化 < 200ms；4) 交互记忆检索 < 300ms。验证可靠性：1) 系统重启后交互事件不丢失；2) 交互影响写入部分失败时正确回滚；3) 交互触发器异常时不影响主对话流程；4) 交互回声链超时正确截断。
- **验收标准**：所有性能指标达标，可靠性场景验证通过。
- **涉及文件**：`tests/` 目录下新建测试文件 + 手动验证
- **依赖**：Phase 1 ~ 5 全部完成

### 6.8 与现有 ProactiveEngine 兼容性验证

- [ ] 验证交互活化系统与现有 ProactiveEngine 的兼容性：1) 启用交互活化后，"智能体→用户"主动对话功能正常；2) 交互触发不影响 ProactiveEngine 的决策延迟；3) 两者的频率控制互不干扰；4) 关闭交互活化（`enabled=false`）后，ProactiveEngine 正常工作。
- **验收标准**：交互活化与 ProactiveEngine 完全兼容，不破坏现有功能。
- **涉及文件**：手动验证 + 测试文件
- **依赖**：Phase 1 ~ 5 全部完成