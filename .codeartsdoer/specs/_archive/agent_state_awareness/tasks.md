# 智能体状态互知机制 — 编码任务清单

> 理想的角色不应是一具等待结局的标本，而应是一场永恒的进行时。

## 新增文件清单

| 文件路径 | 职责 |
|---------|------|
| `src/maisaka/agent_autonomy/state_awareness/__init__.py` | 包初始化，导出核心类 |
| `src/maisaka/agent_autonomy/state_awareness/summary_generator.py` | 共居状态摘要生成器 |
| `src/maisaka/agent_autonomy/state_awareness/rule_engine.py` | 状态感知规则引擎 |
| `src/maisaka/agent_autonomy/state_awareness/visibility_rule.py` | 状态可见性规则 |
| `src/maisaka/agent_autonomy/state_awareness/mapping.py` | 数值→自然语言映射（生命力等级、情绪倾向） |

## 修改文件清单

| 文件路径 | 修改内容 |
|---------|---------|
| `src/maisaka/agent_autonomy/event_bus.py` | 新增 `AgentStateChangeEvent` 数据类 |
| `src/maisaka/agent_autonomy/vitality_manager.py` | 在状态跃迁点发布 `agent_state_change` 事件 |
| `src/maisaka/agent_autonomy/ambient_awareness.py` | 扩展 `on_agent_speak()` 和 `on_session_message()` 调用规则引擎 |
| `src/maisaka/agent_autonomy/prompt_builder.py` | 扩展 `_build_embodied_context()` 新增 `cohabitant_states` 键 |
| `src/maisaka/agent_autonomy/orchestrator.py` | 扩展构造函数持有新组件，扩展 `_collect_behavior_intents()` 调用规则引擎 |
| `src/config/official_configs.py` | 新增 16 个状态感知和可见性规则配置字段 |
| `prompts/zh-CN/maisaka_chat_embodied.prompt` | 新增 `{cohabitant_states}` 占位符 |
| `prompts/en-US/maisaka_chat_embodied.prompt` | 新增 `{cohabitant_states}` 占位符（英文版） |
| `prompts/ja-JP/maisaka_chat_embodied.prompt` | 新增 `{cohabitant_states}` 占位符（日文版） |
| `src/webui/routers/agent.py` | 新增状态互知查询 API 端点 |

---

## 1. 配置参数扩展

**依赖**：无前置依赖，是所有后续任务的基础

### 1.1 新增状态感知规则配置参数

- [ ] 在 `src/config/official_configs.py` 的 `AgentAutonomySectionConfig` 类末尾新增以下字段（均含三语 label，均标记 `advanced: True`）：
  - `companion_vitality_threshold_adjustment: float`（默认 5.0，ge=0.0, le=20.0）——同伴生命力影响规则的插话阈值调整幅度
  - `companion_vitality_trigger_threshold: float`（默认 60.0，ge=30.0, le=100.0）——同伴生命力影响规则的触发阈值
  - `companion_emotion_infection_bonus: float`（默认 2.0，ge=0.0, le=10.0）——同伴情绪感染增强规则的强度增加
  - `companion_emotion_infection_trigger: float`（默认 80.0，ge=50.0, le=100.0）——同伴情绪感染增强规则的触发阈值
  - `companion_sad_response_threshold_adjustment: float`（默认 5.0，ge=0.0, le=20.0）——同伴低落响应规则的插话阈值调整幅度
  - `companion_sad_trigger_threshold: float`（默认 50.0，ge=20.0, le=80.0）——同伴低落响应规则的触发阈值
  - `companion_mention_vitality_bonus: float`（默认 5.0，ge=0.0, le=20.0）——同伴提及加成规则的生命力额外加成
- [ ] 更新配置文件模板 `bot_config.toml`，新增版本号
- [ ] 验收：所有参数可通过 `global_config.agent_autonomy` 正确读取，三语 label 在 WebUI 配置页面正确显示

### 1.2 新增状态可见性规则配置参数

- [ ] 在 `src/config/official_configs.py` 的 `AgentAutonomySectionConfig` 类中新增以下字段（均含三语 label，均标记 `advanced: True`）：
  - `active_visible_to_active: bool`（默认 True）——活跃智能体对活跃智能体是否可见
  - `standby_visible_to_active: bool`（默认 True）——待命智能体对活跃智能体是否可见
  - `standby_emotion_visible_to_active: bool`（默认 False）——待命智能体的情绪是否对活跃智能体可见
  - `dormant_visible_to_any: bool`（默认 False）——沉睡智能体是否对任何智能体可见
  - `vitality_level_high_threshold: float`（默认 60.0，ge=30.0, le=100.0）——生命力"高"等级阈值
  - `vitality_level_low_threshold: float`（默认 30.0，ge=0.0, le=60.0）——生命力"低"等级阈值
  - `emotion_tendency_threshold: float`（默认 50.0，ge=20.0, le=80.0）——情绪倾向描述的强度阈值
  - `max_summary_length: int`（默认 500，ge=100, le=1000）——共居状态摘要最大长度
  - `state_awareness_enabled: bool`（默认 True）——是否启用状态互知功能（总开关）
- [ ] 验收：所有参数可通过 `global_config.agent_autonomy` 正确读取

---

## 2. 事件类型扩展

**依赖**：1.1（配置参数）

### 2.1 新增 AgentStateChangeEvent 数据类

- [ ] 在 `src/maisaka/agent_autonomy/event_bus.py` 文件末尾新增 `AgentStateChangeEvent` 数据类：
  - `agent_id: str = ""` ——发生跃迁的智能体 ID
  - `session_id: str = ""` ——所属会话 ID
  - `from_state: str = ""` ——跃迁前状态（"dormant" / "standby" / "active"）
  - `to_state: str = ""` ——跃迁后状态
  - `trigger_reason: str = ""` ——触发原因
  - `vitality_at_change: float = 0.0` ——跃迁时的生命力值
  - `timestamp: str = ""` ——跃迁时间（ISO 8601）
- [ ] 验收：新事件类型可通过 `bus.emit()` / `bus.emit_sync()` 正确发布和接收

### 2.2 在 VitalityManager 状态跃迁点发布事件

- [ ] 在 `src/maisaka/agent_autonomy/vitality_manager.py` 中修改以下方法，在状态跃迁后发布 `agent_state_change` 事件：
  - `add_to_standby()` 方法末尾：发布事件（from_state="dormant", to_state="standby"），使用 `AutonomyEventBus.get_instance().emit_sync("agent_state_change", event)`
  - `remove_from_standby()` 方法末尾：发布事件（from_state="standby", to_state="dormant"）
  - `check_instant_activation()` 方法中跃迁成功后：发布事件（from_state="standby", to_state="active"）
  - `_evaluate_single_agent()` 方法中生命力激活后：发布事件（from_state="standby", to_state="active"）
- [ ] 事件发布失败时记录 WARNING 日志，不阻塞跃迁流程
- [ ] 验收：智能体状态跃迁时 `agent_state_change` 事件正确发布，包含完整字段

---

## 3. 数值映射模块

**依赖**：1.2（可见性规则配置参数）

### 3.1 实现生命力等级映射

- [ ] 新建 `src/maisaka/agent_autonomy/state_awareness/mapping.py`，实现以下内容：
  - `VitalityLevel` 枚举类：`HIGH`、`MEDIUM`、`LOW`
  - `VitalityLevelMapping` 类：
    - `__init__(self, config: AgentAutonomySectionConfig)` ——从配置读取阈值
    - `map_to_level(vitality: float) -> VitalityLevel` ——生命力值映射为等级（≥high_threshold→HIGH，<low_threshold→LOW，其余→MEDIUM）
    - `map_to_description(level: VitalityLevel, state: str) -> str` ——等级+状态映射为自然语言描述
  - 描述映射规则（zh-CN）：
    - 活跃+HIGH："也在场，精神饱满"
    - 活跃+MEDIUM："也在场"
    - 活跃+LOW："也在场，似乎有些疲倦"
    - 待命+HIGH："在旁边听着，跃跃欲试"
    - 待命+MEDIUM："在旁边安静地听着"
    - 待命+LOW："在旁边待着，有些困倦"
- [ ] 验收：生命力值 75.0 → HIGH + "精神饱满"；生命力值 15.0 → LOW + "有些困倦"

### 3.2 实现情绪倾向映射

- [ ] 在 `src/maisaka/agent_autonomy/state_awareness/mapping.py` 中新增 `EmotionTendencyMapping` 类：
  - `__init__(self, config: AgentAutonomySectionConfig)` ——从配置读取强度阈值
  - `map_to_tendency(emotion_type: str, intensity: float) -> str` ——情绪类型+强度映射为自然语言倾向描述
  - 映射规则：
    - happy/excited 且强度≥阈值："心情不错" / "很兴奋"
    - sad/lonely 且强度≥阈值："有些低落" / "似乎有点孤单"
    - angry/anxious 且强度≥阈值："似乎有些烦躁" / "看起来有些不安"
    - 所有强度<阈值：返回空字符串（不特别描述）
- [ ] 验收：情绪 happy(80) → "心情不错"；情绪中性（所有<50）→ 空字符串

---

## 4. 状态可见性规则

**依赖**：1.2（可见性规则配置参数）

### 4.1 实现 StateVisibilityRule

- [ ] 新建 `src/maisaka/agent_autonomy/state_awareness/visibility_rule.py`，实现以下内容：
  - `VisibilityInfo` 数据类：`visible: bool`、`show_emotion: bool`、`show_vitality_level: bool`
  - `StateVisibilityRule` 类：
    - `__init__(self, config: AgentAutonomySectionConfig)` ——从配置读取可见性规则
    - `evaluate(observer_state: str, target_state: str) -> VisibilityInfo` ——判定目标对观察者的可见信息粒度
  - 可见性判定逻辑：
    - target_state="dormant" → 不可见（`visible=False`）
    - observer_state="active" 且 target_state="active" → 可见状态+生命力等级+情绪倾向
    - observer_state="active" 且 target_state="standby" → 可见状态+生命力等级，不展示情绪（`show_emotion=False`）
    - 其他组合 → 不可见
  - 自我不可见规则：调用方负责过滤自身，`evaluate()` 不处理
- [ ] 验收：活跃观察待命 → 可见但无情绪；沉睡目标 → 不可见

---

## 5. 共居状态摘要生成器

**依赖**：3（数值映射）、4（可见性规则）

### 5.1 实现摘要条目数据结构

- [ ] 新建 `src/maisaka/agent_autonomy/state_awareness/summary_generator.py`，实现 `CohabitantStateEntry` 数据类：
  - `agent_id: str` ——共居智能体 ID
  - `display_name: str` ——显示名称
  - `state: str` ——当前状态（"active" / "standby"）
  - `vitality_level: VitalityLevel` ——生命力等级
  - `emotion_tendency: str` ——情绪倾向描述（待命智能体为空字符串）

### 5.2 实现 CohabitantStateSummaryGenerator 核心

- [ ] 在 `src/maisaka/agent_autonomy/state_awareness/summary_generator.py` 中实现 `CohabitantStateSummaryGenerator` 类：
  - `__init__(self, vitality_manager: VitalityManager, orchestrator: AgentOrchestrator, visibility_rule: StateVisibilityRule)` ——持有各依赖引用
  - `generate(session_id: str, observer_agent_id: str) -> str` ——生成共居状态摘要文本
    1. 查询待命智能体列表（`vitality_manager.get_standby_agents()`）
    2. 查询活跃智能体列表（`orchestrator.get_active_agents()`）
    3. 过滤掉自身（observer_agent_id）和沉睡智能体
    4. 对每个共居智能体调用 `visibility_rule.evaluate()` 判定可见性
    5. 对可见的智能体：获取情绪快照（`agent.get_emotion_state()`）、获取显示名（`AgentConfigRegistry`）、生命力值映射为等级、情绪映射为倾向描述
    6. 按优先级排序：活跃优先于待命，高生命力优先于低生命力
    7. 组装摘要文本：前缀 `"\n你身边的同伴状态："`，多条以分号连接
    8. 若摘要长度超过 `max_summary_length`，按优先级截断
  - `generate_preview(session_id: str) -> dict[str, Any]` ——生成感知关系预览数据（供 WebUI 使用），返回包含 `observer_agents`、`cohabitant_entries`、`summary_text` 的字典
- [ ] 异常处理：
  - VitalityManager 不可用 → 仅展示活跃智能体状态
  - EmotionManager 不可用 → 跳过情绪描述
  - 任何异常 → 返回空字符串，不阻塞提示词构建
- [ ] 性能约束：13 个共居智能体场景下总耗时 ≤ 50ms
- [ ] 验收：银狼（活跃）的摘要中包含其他 12 个智能体的自然语言状态描述；无共居智能体时返回空字符串

### 5.3 创建 state_awareness 包

- [ ] 新建 `src/maisaka/agent_autonomy/state_awareness/__init__.py`，导出核心类：
  - `CohabitantStateSummaryGenerator`、`StateAwareRuleEngine`、`StateVisibilityRule`、`AgentStateChangeEvent`
- [ ] 验收：`from src.maisaka.agent_autonomy.state_awareness import CohabitantStateSummaryGenerator` 可正常导入

---

## 6. 状态感知规则引擎

**依赖**：1.1（感知规则配置参数）、4（可见性规则）

### 6.1 实现 RuleEvaluationResult 数据类

- [ ] 新建 `src/maisaka/agent_autonomy/state_awareness/rule_engine.py`，实现 `RuleEvaluationResult` 数据类：
  - `intent_threshold_adjustment: float` ——插话意图阈值偏移量
  - `infection_bonus: float` ——情绪感染强度偏移量
  - `mention_bonus: float` ——提及生命力加成偏移量
  - `triggered_rules: list[str]` ——触发的规则名称列表

### 6.2 实现 StateAwareRuleEngine 核心

- [ ] 在 `src/maisaka/agent_autonomy/state_awareness/rule_engine.py` 中实现 `StateAwareRuleEngine` 类：
  - `__init__(self, vitality_manager: VitalityManager, visibility_rule: StateVisibilityRule)` ——持有各依赖引用
  - `evaluate_for_interjection(session_id: str) -> RuleEvaluationResult` ——评估插话相关的感知规则（规则1+规则3）
    1. 规则1（同伴生命力影响）：查询待命智能体生命力分布，若有待命生命力≥`companion_vitality_trigger_threshold`，则 `intent_threshold_adjustment += companion_vitality_threshold_adjustment`
    2. 规则3（同伴低落响应）：查询活跃智能体情绪状态，若有活跃智能体情绪为 sad/lonely 且强度≥`companion_sad_trigger_threshold`，则 `intent_threshold_adjustment -= companion_sad_response_threshold_adjustment`
    3. 返回 `RuleEvaluationResult`，包含叠加后的阈值调整量
  - `evaluate_for_infection(session_id: str, speaker_emotion_intensity: float) -> float` ——评估情绪感染增强规则（规则2）
    1. 若发言智能体情绪强度≥`companion_emotion_infection_trigger`，返回 `companion_emotion_infection_bonus`
    2. 否则返回 0.0
  - `evaluate_for_mention(session_id: str, mention_source_type: str) -> float` ——评估同伴提及加成规则（规则4）
    1. 若提及来源为活跃智能体（`mention_source_type == "agent"`），返回 `companion_mention_vitality_bonus`
    2. 否则返回 0.0
- [ ] 异常处理：评估超时或异常 → 返回零偏移结果，记录 WARNING 日志
- [ ] 性能约束：单次评估 ≤ 10ms，纯规则计算
- [ ] 验收：3 个待命智能体生命力≥60 → 阈值+5.0；活跃智能体低落 → 阈值-5.0；两者同时触发可抵消

---

## 7. 提示词模板扩展

**依赖**：5（摘要生成器），但模板修改可与代码并行

### 7.1 修改 zh-CN 提示词模板

- [ ] 在 `prompts/zh-CN/maisaka_chat_embodied.prompt` 中，在 `{agent_emotion_state}` 和 `{agent_relationship}` 之后、`以上是你的人设` 之前，新增 `{cohabitant_states}` 占位符（独立一行）
- [ ] 验收：模板包含 `{cohabitant_states}` 占位符，位于正确位置

### 7.2 修改 en-US 提示词模板

- [ ] 在 `prompts/en-US/maisaka_chat_embodied.prompt` 中，在 `{agent_emotion_state}` 和 `{agent_relationship}` 之后、`The above is your persona` 之前，新增 `{cohabitant_states}` 占位符（独立一行）
- [ ] 验收：英文模板与中文模板占位符位置一致

### 7.3 修改 ja-JP 提示词模板

- [ ] 在 `prompts/ja-JP/maisaka_chat_embodied.prompt` 中，在 `{agent_emotion_state}` 和 `{agent_relationship}` 之后、`以上はあなたの人物設定` 之前，新增 `{cohabitant_states}` 占位符（独立一行）
- [ ] 验收：日文模板与中文模板占位符位置一致

---

## 8. 提示词构建器集成

**依赖**：5（摘要生成器）、7（提示词模板）

### 8.1 扩展 EmbodiedPlannerPromptBuilder 注入共居状态摘要

- [ ] 在 `src/maisaka/agent_autonomy/prompt_builder.py` 的 `_build_embodied_context()` 方法中：
  - 新增 `"cohabitant_states"` 键到返回的上下文字典
  - 实现逻辑：
    1. 获取当前智能体所属的 Orchestrator（通过 `AgentOrchestrator.get_by_session()` 或其他方式获取 session_id）
    2. 若 Orchestrator 存在且 `state_awareness_enabled` 为 True，调用 `summary_generator.generate(session_id, self._agent_id)` 获取摘要
    3. 若获取失败或无共居智能体，`cohabitant_states` 为空字符串
  - 在 `__init__()` 中新增可选参数或通过其他方式获取 `CohabitantStateSummaryGenerator` 引用
- [ ] 向后兼容：`{cohabitant_states}` 占位符缺失时 `load_prompt` 不报错，降级为空字符串
- [ ] 验收：活跃智能体的提示词中包含共居状态摘要文本；无共居智能体时占位符为空

---

## 9. Orchestrator 集成

**依赖**：5（摘要生成器）、6（规则引擎）

### 9.1 扩展 Orchestrator 构造函数持有新组件

- [ ] 在 `src/maisaka/agent_autonomy/orchestrator.py` 的 `__init__()` 中：
  - 新增 `self._visibility_rule = StateVisibilityRule(self._config)` 实例化
  - 新增 `self._summary_generator = CohabitantStateSummaryGenerator(self._vitality_manager, self, self._visibility_rule)` 实例化
  - 新增 `self._rule_engine = StateAwareRuleEngine(self._vitality_manager, self._visibility_rule)` 实例化
  - 将 `self._summary_generator` 传递给 `AmbientAwarenessProcessor`（或通过其他方式使 prompt_builder 可访问）
- [ ] 在 `_subscribe_events()` 中新增订阅 `"agent_state_change"` 事件（可选，供 Orchestrator 内部使用）
- [ ] 验收：新组件随 Orchestrator 生命周期正确初始化

### 9.2 扩展 _collect_behavior_intents 使用感知规则引擎

- [ ] 修改 `src/maisaka/agent_autonomy/orchestrator.py` 的 `_collect_behavior_intents()` 方法：
  - 在获取 `cohabitation_params` 后，调用 `self._rule_engine.evaluate_for_interjection(self._session_id)` 获取感知规则评估结果
  - 将 `rule_result.intent_threshold_adjustment` 叠加到 `dynamic_threshold`：`dynamic_threshold += rule_result.intent_threshold_adjustment`
  - 确保 `dynamic_threshold` 不低于 `interjection_threshold_minimum`
  - 记录 DEBUG 日志：触发的规则名称和调整量
- [ ] 验收：待命智能体生命力高时活跃智能体插话阈值提升；活跃智能体低落时阈值降低

### 9.3 将摘要生成器注入到 PromptBuilder

- [ ] 修改 `src/maisaka/agent_autonomy/orchestrator.py` 中智能体创建流程，使 `EmbodiedPlannerPromptBuilder` 可访问 `CohabitantStateSummaryGenerator`：
  - 方案：在 `AutonomousAgent` 创建后，通过 `agent.prompt_builder` 注册 identity_provider 或直接注入 summary_generator 引用
  - 或方案：在 `_build_embodied_context()` 中通过 `AgentOrchestrator.get_by_session()` 获取 Orchestrator 实例，再获取 summary_generator
- [ ] 验收：`EmbodiedPlannerPromptBuilder._build_embodied_context()` 能正确获取并调用摘要生成器

---

## 10. 环境感知处理器集成规则引擎

**依赖**：6（规则引擎）

### 10.1 扩展 AmbientAwarenessProcessor 构造函数

- [ ] 修改 `src/maisaka/agent_autonomy/ambient_awareness.py` 的 `AmbientAwarenessProcessor.__init__()`：
  - 新增 `rule_engine: StateAwareRuleEngine | None = None` 可选参数
  - 保存为 `self._rule_engine`
- [ ] 在 `src/maisaka/agent_autonomy/orchestrator.py` 的 `__init__()` 中，创建 `AmbientAwarenessProcessor` 时传入 `rule_engine` 参数
- [ ] 验收：`AmbientAwarenessProcessor` 持有规则引擎引用

### 10.2 扩展 on_agent_speak 使用动态感染强度

- [ ] 修改 `src/maisaka/agent_autonomy/ambient_awareness.py` 的 `on_agent_speak()` 方法：
  - 在情绪感染循环中，若 `self._rule_engine` 不为 None，调用 `self._rule_engine.evaluate_for_infection(session_id, event.emotion_intensity)` 获取感染强度偏移
  - 将固定值 `3.0` 替换为 `3.0 + infection_bonus`
  - 若 `self._rule_engine` 为 None，保持原有逻辑不变（向后兼容）
- [ ] 验收：发言智能体情绪强度≥80 时，待命智能体感染强度从 3.0 增加到 5.0

### 10.3 扩展 on_session_message 使用同伴提及加成

- [ ] 修改 `src/maisaka/agent_autonomy/ambient_awareness.py` 的 `on_session_message()` 方法：
  - 在提及检测后，若 `self._rule_engine` 不为 None 且提及来源为智能体（`event.sender_type == "agent"`），调用 `self._rule_engine.evaluate_for_mention(session_id, "agent")` 获取额外加成
  - 将 `mention_bonus` 叠加到 `delta`：`delta += mention_bonus`
  - 若 `self._rule_engine` 为 None，保持原有逻辑不变
- [ ] 验收：活跃智能体提及待命智能体时，待命智能体获得额外生命力加成（+5.0）

---

## 11. WebUI 状态互知 API

**依赖**：5（摘要生成器）、6（规则引擎）

### 11.1 新增状态互知查询 API

- [ ] 在 `src/webui/routers/agent.py` 中新增端点：
  - `GET /agent/state-awareness?session_id={session_id}` ——查询会话智能体感知关系和摘要预览
  - 返回 `StateAwarenessResponse`：success, session_id, cohabitant_entries, summary_preview, active_rules
  - `CohabitantEntry`：agent_id, display_name, state, vitality_level, emotion_tendency
  - `active_rules`：当前生效的感知规则名称及最近触发时间
- [ ] 实现逻辑：
  1. 获取会话对应的 `AgentOrchestrator` 实例
  2. 调用 `orchestrator._summary_generator.generate_preview(session_id)` 获取感知关系和摘要预览
  3. 调用 `orchestrator._rule_engine` 获取当前生效规则信息
  4. 组装并返回
- [ ] 验收：API 正确返回感知关系数据、摘要预览文本和感知规则状态

---

## 12. WebUI 前端展示

**依赖**：11（WebUI API）

### 12.1 扩展前端 API 层

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增：
  - `CohabitantEntry` 接口：agent_id, display_name, state, vitality_level, emotion_tendency
  - `StateAwarenessResponse` 接口：success, session_id, cohabitant_entries, summary_preview, active_rules
  - `fetchStateAwareness(sessionId: string)` 函数，调用 `GET /api/webui/agent/state-awareness?session_id={sessionId}`
- [ ] 验收：前端可正确调用状态互知 API 并获取响应数据

### 12.2 新增状态互知展示组件

- [ ] 在智能体状态面板中新增"感知关系"区域：
  - 展示活跃智能体可感知的共居智能体列表（名称+状态+生命力等级）
  - 展示摘要预览文本
  - 展示当前生效的感知规则名称
- [ ] 验收：管理员可在 WebUI 中查看共居智能体间的感知关系

### 12.3 新增 i18n 三语翻译

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 中新增状态互知相关翻译键：
  - `agent.stateAwareness.title`：状态互知
  - `agent.stateAwareness.summaryPreview`：摘要预览
  - `agent.stateAwareness.activeRules`：生效规则
  - `agent.stateAwareness.vitalityLevel.high`：高
  - `agent.stateAwareness.vitalityLevel.medium`：中
  - `agent.stateAwareness.vitalityLevel.low`：低
- [ ] 在 `dashboard/src/i18n/locales/en.json` 中新增对应英文翻译
- [ ] 在 `dashboard/src/i18n/locales/ja.json` 中新增对应日文翻译
- [ ] 验收：切换语言时标签和提示文本正确跟随切换

---

## 13. 集成验证

**依赖**：所有前置任务完成

### 13.1 端到端功能验证

- [ ] 验证共居状态摘要生成：绑定 13 个智能体到会话，活跃智能体的提示词中包含其他 12 个智能体的自然语言状态描述
- [ ] 验证摘要内容正确性：待命智能体显示"在旁边安静地听着"类描述，不含生命力数值和情绪数值
- [ ] 验证可见性规则：活跃智能体可看到待命智能体的状态+生命力等级但无情绪；沉睡智能体不出现在摘要中
- [ ] 验证自我不可见：智能体的摘要中不包含自身状态
- [ ] 验证状态感知规则——同伴生命力影响：3 个待命智能体生命力≥60 时，活跃智能体插话阈值+5.0
- [ ] 验证状态感知规则——同伴低落响应：活跃智能体情绪 sad(60) 时，其他活跃智能体插话阈值-5.0
- [ ] 验证状态感知规则——情绪感染增强：发言智能体情绪强度≥80 时，待命智能体感染强度增加
- [ ] 验证状态感知规则——同伴提及加成：活跃智能体提及待命智能体时，待命智能体获得额外生命力加成
- [ ] 验证状态变更事件发布：智能体从待命跃迁为活跃时发布 `agent_state_change` 事件
- [ ] 验证提示词模板三语同步：zh-CN/en-US/ja-JP 三个模板均包含 `{cohabitant_states}` 占位符
- [ ] 验证降级安全：摘要生成失败时不影响智能体正常回复；规则引擎异常时静默降级
- [ ] 验证单智能体模式兼容：无共居智能体时不产生任何开销

### 13.2 性能验证

- [ ] 验证摘要生成性能：13 个共居智能体场景下摘要生成总耗时 ≤ 50ms
- [ ] 验证规则引擎性能：单次感知规则评估延迟 ≤ 10ms
- [ ] 验证事件发布性能：状态变更事件发布延迟 ≤ 20ms
- [ ] 验证摘要长度约束：摘要文本不超过 500 字符

### 13.3 兼容性验证

- [ ] 验证与 agent_vitality 机制兼容：状态互知是生命力机制的上层消费者，不修改 VitalityManager 核心逻辑
- [ ] 验证与现有插话机制兼容：状态感知规则调整的是参数而非逻辑
- [ ] 验证与现有提示词系统兼容：通过新增 `{cohabitant_states}` 占位符注入，不修改现有占位符
- [ ] 验证配置文件兼容：新增配置参数不影响现有配置读取