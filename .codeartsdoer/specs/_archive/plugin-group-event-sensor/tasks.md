# 群行为感知插件 — 编码任务列表

> 基于需求规格文档（spec.md）和实现方案文档（design.md）生成
> 覆盖需求：FR-01 ~ FR-08, NFR-01 ~ NFR-04, IF-01 ~ IF-03

---

## 1. 项目骨架与清单文件

- [ ] **T1-01** 创建插件目录结构 `plugins/group_event_sensor/`，包含所有子包（handlers/、reaction/、memory/、infra/、templates/zh-CN/、_locales/zh-CN/）及 `__init__.py` 文件
  - 依赖：无
  - 涉及文件：`plugins/group_event_sensor/` 全部目录及 `__init__.py`
  - 验收标准：目录结构与 design.md §1.3.1 一致，所有 `__init__.py` 存在
  - 复杂度：S

- [ ] **T1-02** 编写 `_manifest.json` 插件元信息文件
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/_manifest.json`
  - 验收标准：manifest_version=2，sdk版本范围 2.4.0~2.99.99，host_application min_version=1.0.0，capabilities 包含 send.text / config.get / llm.generate / api.call，id 为 "maibot-team.group-event-sensor"
  - 复杂度：S

- [ ] **T1-03** 编写 `config.py` 配置模型（Pydantic v2 + PluginConfigBase）
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/config.py`
  - 验收标准：包含 PluginSectionConfig、RedPacketConfig、PokeConfig、GroupBanConfig、GroupIncreaseConfig、GroupDecreaseConfig、ReactionConfig、MemoryConfig、LLMConfig、GroupOverrideConfig、GroupEventSensorConfig 全部模型；每个配置组设置 `__ui_label__`/`__ui_icon__`/`__ui_order__`；字段约束（cooldown_seconds≥1、reaction_mode 枚举、query_timeout_seconds 0.5~10.0、max_tokens 50~500、temperature 0.1~1.0）；所有字段有 description 和 default
  - 复杂度：M

- [ ] **T1-04** 编写 `plugin.py` 插件入口（GroupEventSensorPlugin 类 + create_plugin 工厂函数）
  - 依赖：T1-02, T1-03
  - 涉及文件：`plugins/group_event_sensor/plugin.py`
  - 验收标准：声明 config_model=GroupEventSensorConfig；实现 on_load()（初始化各层组件、注册 EventHandler、记录启动日志）；实现 on_unload()（清理资源、记录关闭日志）；实现 on_config_update()（热重载回调）；定义 create_plugin() 工厂函数
  - 复杂度：M

---

## 2. 基础设施层

- [ ] **T2-01** 编写 `infra/rate_limiter.py` 频率控制器
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/infra/rate_limiter.py`
  - 验收标准：实现 RateLimiter 类，check(user_id, event_type, cooldown) → bool；基于内存滑动窗口；使用 dict[str, float] 记录最后反应时间戳；定期清理过期记录防止内存泄漏
  - 复杂度：S

- [ ] **T2-02** 编写 `infra/safe_hash.py` 安全哈希工具
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/infra/safe_hash.py`
  - 验收标准：实现 hash_user_id(user_id) → str，对 QQ 号进行 SHA-256 截断哈希脱敏
  - 复杂度：S

- [ ] **T2-03** 编写 `infra/degradation.py` 降级策略管理器
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/infra/degradation.py`
  - 验收标准：实现 DegradationManager 类，mark_unavailable(service)、mark_available(service)、is_available(service) → bool、get_fallback_mode() → str；维护各外部服务可用性状态（a_memorix、llm）
  - 复杂度：S

> **T2-01、T2-02、T2-03 可并行执行**

---

## 3. 数据模型定义

- [ ] **T3-01** 编写事件数据模型（EventData、EventPerson、EventGroup、GroupEventType 枚举）
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/handlers/base.py`（或独立 models.py）
  - 验收标准：GroupEventType 枚举包含 RED_PACKET/POKE/GROUP_BAN/GROUP_INCREASE/GROUP_DECREASE；EventData 包含 event_type/sub_type/operator/target/group/duration/timestamp/raw_data；EventPerson 包含 user_id/nickname/is_bot；EventGroup 包含 group_id/group_name/stream_id
  - 复杂度：S

- [ ] **T3-02** 编写反应数据模型（HandleResult、ReactionContext、ReactionResult）
  - 依赖：T3-01
  - 涉及文件：同 T3-01
  - 验收标准：HandleResult 包含 should_continue/intercept/summary/reaction_sent；ReactionContext 包含 event_type/event_data/memory_context/config；ReactionResult 包含 text/mode/degraded
  - 复杂度：S

- [ ] **T3-03** 编写记忆上下文数据模型（MemoryContext、PersonProfile、InteractionRecord）
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/memory/service.py`（或独立 models.py）
  - 验收标准：MemoryContext 包含 person_profile/interaction_records/has_history/is_available；PersonProfile 包含 person_id/traits/preferences/summary；InteractionRecord 包含 timestamp/content/tags
  - 复杂度：S

> **T3-01 和 T3-03 可并行执行；T3-02 依赖 T3-01**

---

## 4. 事件监听与分发

- [ ] **T4-01** 编写 `handlers/base.py` BaseEventHandler 抽象基类
  - 依赖：T3-01, T3-02, T2-02
  - 涉及文件：`plugins/group_event_sensor/handlers/base.py`
  - 验收标准：定义抽象方法 handle(event_data, ctx) → HandleResult；提供公共事件信息提取方法（操作者信息、群信息、被操作者信息）；提供配置开关检查前置逻辑；提供异常捕获兜底确保单次失败不影响后续
  - 复杂度：M

- [ ] **T4-02** 编写 EventHandler 入口函数（plugin.py 中的 handle_group_event）
  - 依赖：T4-01, T1-04
  - 涉及文件：`plugins/group_event_sensor/plugin.py`
  - 验收标准：使用 @EventHandler 装饰器注册 ON_MESSAGE 事件处理器；检查 is_notify 字段筛选 notify 消息；提取 sub_type 并路由到对应处理器；未识别 sub_type 安全忽略并记录 debug 日志；插件总开关 enabled 检查；返回 (continue=True, intercept=False) 元组
  - 复杂度：M

- [ ] **T4-03** 建立 sub_type → 处理器映射注册表
  - 依赖：T4-01
  - 涉及文件：`plugins/group_event_sensor/handlers/__init__.py`
  - 验收标准：映射表包含 lucky_kong→RedPacketHandler、hongbao→RedPacketHandler、poke→PokeHandler、group_ban→GroupBanHandler、group_increase→GroupIncreaseHandler、group_decrease→GroupDecreaseHandler；支持动态注册新处理器（NFR-03-04 可扩展性）
  - 复杂度：S

---

## 5. 事件处理器实现

- [ ] **T5-01** 编写红包事件处理器 `handlers/red_packet.py`
  - 依赖：T4-01, T4-03
  - 涉及文件：`plugins/group_event_sensor/handlers/red_packet.py`
  - 验收标准：识别 sub_type="lucky_king"/"hongbao"；提取发红包者信息（user_id、nickname）和群信息；user_info 缺失时使用默认称呼"有人"；检查 red_packet.enabled 开关；调用 MemoryService 检索记忆上下文；调用 ReactionEngine 生成反应；通过 ctx.send.text() 发送；可选写入事件记忆（FR-01-01~FR-01-05）
  - 复杂度：M

- [ ] **T5-02** 编写戳一戳事件处理器 `handlers/poke.py`
  - 依赖：T4-01, T4-03, T2-01
  - 涉及文件：`plugins/group_event_sensor/handlers/poke.py`
  - 验收标准：识别 sub_type="poke"；区分"戳机器人"和"戳其他人"（比较 target_id 与 bot_info.user_id）；bot_info 不存在时默认假设被戳者为机器人；调用 RateLimiter.check() 频率控制（cooldown_seconds）；检查 poke.enabled 开关；非机器人被戳时根据 react_to_others 配置决定旁观反应（FR-02-01~FR-02-06）
  - 复杂度：M

- [ ] **T5-03** 编写禁言事件处理器 `handlers/group_ban.py`
  - 依赖：T4-01, T4-03
  - 涉及文件：`plugins/group_event_sensor/handlers/group_ban.py`
  - 验收标准：识别 sub_type="group_ban"；区分禁言（duration>0）和解禁（duration=0）；duration 缺失时默认按禁言处理；机器人自身被禁言时仅记录 warning 日志不发送消息；检查 group_ban.enabled 开关；基于禁言时长生成差异化反应（FR-03-01~FR-03-06）
  - 复杂度：M

- [ ] **T5-04** 编写入群事件处理器 `handlers/group_increase.py`
  - 依赖：T4-01, T4-03
  - 涉及文件：`plugins/group_event_sensor/handlers/group_increase.py`
  - 验收标准：识别 sub_type="group_increase"；提取入群者信息和群信息；user_info 缺失时使用默认称呼"新朋友"；根据记忆上下文 has_history 判断回归成员/新成员；检查 group_increase.enabled 开关（FR-04-01~FR-04-05）
  - 复杂度：M

- [ ] **T5-05** 编写退群事件处理器 `handlers/group_decrease.py`
  - 依赖：T4-01, T4-03
  - 涉及文件：`plugins/group_event_sensor/handlers/group_decrease.py`
  - 验收标准：识别 sub_type="group_decrease"；区分主动退群（operator_id==user_id）和被踢出（operator_id!=user_id）；无法区分时默认按主动退群处理；检查 group_decrease.enabled 开关；反应消息仅概括性提及不暴露具体记忆内容（FR-05-01~FR-05-06）
  - 复杂度：M

> **T5-01 ~ T5-05 可并行执行（各处理器之间无交叉依赖，NFR-03-03）**

---

## 6. 智能反应引擎

- [ ] **T6-01** 编写 `reaction/engine.py` ReactionEngine 反应决策引擎
  - 依赖：T3-02, T2-03
  - 涉及文件：`plugins/group_event_sensor/reaction/engine.py`
  - 验收标准：根据 reaction_mode 配置选择 TemplateReactor 或 LLMReactor；组装 ReactionContext；调用选定生成器生成反应文本；LLM 生成失败时降级为模板反应；返回 ReactionResult（含 text/mode/degraded）
  - 复杂度：M

- [ ] **T6-02** 编写 `reaction/template.py` TemplateReactor 模板反应生成器
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/reaction/template.py`
  - 验收标准：从 templates/zh-CN/ 目录加载对应事件类型的 TOML 模板文件；根据事件上下文变量填充模板占位符（{nickname}、{group_name} 等）；支持多条模板随机选择增加多样性；模板文件加载失败时使用硬编码默认模板
  - 复杂度：M

- [ ] **T6-03** 编写 `reaction/llm.py` LLMReactor LLM 反应生成器
  - 依赖：T3-03, T2-03
  - 涉及文件：`plugins/group_event_sensor/reaction/llm.py`
  - 验收标准：构建包含事件信息和记忆上下文的 LLM 提示词；调用 ctx.llm.generate(prompt=..., model="utils", max_tokens=300, temperature=0.7)；处理 LLM 返回值类型兼容（dict/list/str）；生成文本为空时返回 None 触发降级；生成文本超过 500 字符时截断
  - 复杂度：M

> **T6-02 和 T6-03 可并行执行；T6-01 依赖 T6-02 和 T6-03**

---

## 7. 记忆协同模块

- [ ] **T7-01** 编写 `memory/service.py` MemoryService 记忆服务
  - 依赖：T3-03, T2-03, T2-02
  - 涉及文件：`plugins/group_event_sensor/memory/service.py`
  - 验收标准：实现 search_context(person_id, group_id) → MemoryContext：调用 ctx.api.call("a_memorix", "search_memory", ...) 和 get_person_profile；实现 inject_context(memory_context, prompt) → str：将记忆检索结果格式化注入 LLM 提示词；实现 write_event_summary(event_data) → bool：调用 ingest_text 写入事件摘要；实现 check_availability() → bool：探测 A_Memorix 可用性；使用 asyncio.wait_for 实现超时控制；检索失败/超时时返回空 MemoryContext + 降级标记；维护 A_Memorix 可用性状态标记
  - 复杂度：L

---

## 8. 反应模板与提示词

- [ ] **T8-01** 编写红包反应模板 `templates/zh-CN/red_packet.toml`
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/templates/zh-CN/red_packet.toml`
  - 验收标准：包含多条模板文本（≥4条），支持 {nickname}、{group_name} 变量占位符，内容为简体中文
  - 复杂度：S

- [ ] **T8-02** 编写戳一戳反应模板 `templates/zh-CN/poke.toml`
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/templates/zh-CN/poke.toml`
  - 验收标准：包含多条模板文本（≥4条），支持 {nickname} 变量占位符，内容为简体中文
  - 复杂度：S

- [ ] **T8-03** 编写禁言反应模板 `templates/zh-CN/group_ban.toml`
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/templates/zh-CN/group_ban.toml`
  - 验收标准：包含禁言和解禁两类模板，支持 {nickname}、{duration} 变量占位符，内容为简体中文
  - 复杂度：S

- [ ] **T8-04** 编写入群反应模板 `templates/zh-CN/group_increase.toml`
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/templates/zh-CN/group_increase.toml`
  - 验收标准：包含新成员欢迎和回归成员欢迎两类模板，支持 {nickname} 变量占位符，内容为简体中文
  - 复杂度：S

- [ ] **T8-05** 编写退群反应模板 `templates/zh-CN/group_decrease.toml`
  - 依赖：T1-01
  - 涉及文件：`plugins/group_event_sensor/templates/zh-CN/group_decrease.toml`
  - 验收标准：包含主动退群和被踢出两类模板，支持 {nickname} 变量占位符，内容为简体中文，不暴露具体记忆内容
  - 复杂度：S

- [ ] **T8-06** 编写各事件类型的 LLM 提示词模板（在 llm.py 中内联或独立文件）
  - 依赖：T6-03
  - 涉及文件：`plugins/group_event_sensor/reaction/llm.py`（或 `templates/zh-CN/prompts/`）
  - 验收标准：每种事件类型有独立的系统提示词和用户提示词模板；提示词包含事件信息占位和记忆上下文注入位置；提示词引导 LLM 生成简体中文、个性化、不超过 300 token 的反应文本
  - 复杂度：M

> **T8-01 ~ T8-05 可并行执行**

---

## 9. 组件集成与装配

- [ ] **T9-01** 在 plugin.py on_load() 中装配所有组件并注入依赖
  - 依赖：T1-04, T4-02, T5-01~T5-05, T6-01, T7-01, T2-01~T2-03
  - 涉及文件：`plugins/group_event_sensor/plugin.py`
  - 验收标准：on_load() 实例化 MemoryService、ReactionEngine（含 TemplateReactor + LLMReactor）、RateLimiter、DegradationManager；将组件注入到各事件处理器；注册 EventHandler；调用 MemoryService.check_availability() 探测 A_Memorix 可用性；记录中文启动日志
  - 复杂度：M

- [ ] **T9-02** 实现 on_config_update() 配置热重载逻辑
  - 依赖：T9-01, T1-03
  - 涉及文件：`plugins/group_event_sensor/plugin.py`
  - 验收标准：Pydantic 模型校验 config_data；校验失败时保持原配置并记录 warning 日志；校验通过后更新 self.config；通知 ReactionEngine、各事件处理器、MemoryService 刷新配置；记录 info 日志"配置已热重载"（FR-07-04）
  - 复杂度：M

- [ ] **T9-03** 实现群级配置覆盖逻辑
  - 依赖：T9-01, T1-03
  - 涉及文件：`plugins/group_event_sensor/plugin.py` 或 `handlers/base.py`
  - 验收标准：获取事件 group_id → 查找 group_overrides 中是否存在覆盖 → 用非 None 覆盖值替换全局值 → 无覆盖时使用全局配置（FR-07-05）
  - 复杂度：S

---

## 10. Docker 适配与部署验证

- [ ] **T10-01** 验证插件目录结构与 Docker 卷挂载兼容
  - 依赖：T9-01
  - 涉及文件：`plugins/group_event_sensor/` 全部
  - 验收标准：所有文件操作使用相对于插件目录的路径（通过 __file__ 获取基准路径）；模板文件路径使用 Path(__file__).parent / "templates" / "zh-CN" / f"{event_type}.toml"；不依赖宿主机绝对路径
  - 复杂度：S

- [ ] **T10-02** 验证容器重启状态恢复行为
  - 依赖：T9-01
  - 涉及文件：`plugins/group_event_sensor/plugin.py`、`infra/rate_limiter.py`、`infra/degradation.py`
  - 验收标准：确认 RateLimiter 和 DegradationManager 为内存态（重启自动重置）；确认配置通过 config.toml 持久化；确认 on_load() 重新探测 A_Memorix 可用性；核心业务逻辑无状态依赖
  - 复杂度：S

---

## 11. 单元测试

- [ ] **T11-01** 编写配置模型单元测试
  - 依赖：T1-03
  - 涉及文件：`tests/test_config.py`
  - 验收标准：验证 GroupEventSensorConfig 默认值正确；验证字段约束（cooldown_seconds≥1、reaction_mode 枚举、query_timeout_seconds 范围、max_tokens 范围、temperature 范围）；验证 Pydantic 校验拒绝非法值；验证群级覆盖逻辑
  - 复杂度：M

- [ ] **T11-02** 编写基础设施层单元测试
  - 依赖：T2-01, T2-02, T2-03
  - 涉及文件：`tests/test_rate_limiter.py`、`tests/test_safe_hash.py`、`tests/test_degradation.py`
  - 验收标准：RateLimiter：验证冷却期内拒绝、冷却期后允许、定期清理过期记录；SafeHash：验证哈希输出为字符串、不同输入产生不同输出、原始 QQ 号不出现在输出中；DegradationManager：验证标记/查询可用性、降级模式返回
  - 复杂度：M

- [ ] **T11-03** 编写事件处理器单元测试（Mock 依赖）
  - 依赖：T5-01~T5-05
  - 涉及文件：`tests/test_handlers.py`
  - 验收标准：红包：模拟 sub_type="lucky_king" 验证事件识别和信息提取；戳一戳：模拟 poke 事件验证方向判断和频率控制；禁言：模拟 group_ban 验证禁言/解禁区分和机器人自身被禁言处理；入群：模拟 group_increase 验证新成员/回归成员判断；退群：模拟 group_decrease 验证主动退群/被踢出区分；未识别 sub_type 安全忽略
  - 复杂度：L

- [ ] **T11-04** 编写智能反应引擎单元测试
  - 依赖：T6-01, T6-02, T6-03
  - 涉及文件：`tests/test_reaction.py`
  - 验收标准：TemplateReactor：验证模板加载、变量填充、随机选择、加载失败降级到硬编码默认模板；LLMReactor：验证提示词构建、LLM 返回值类型兼容（dict/list/str）、空返回降级、超长截断；ReactionEngine：验证模式选择、LLM 失败降级到模板
  - 复杂度：M

- [ ] **T11-05** 编写记忆服务单元测试（Mock A_Memorix）
  - 依赖：T7-01
  - 涉及文件：`tests/test_memory_service.py`
  - 验收标准：search_context：验证正常检索返回 MemoryContext、超时降级返回空上下文、异常降级；inject_context：验证记忆注入格式；write_event_summary：验证写入调用；check_availability：验证可用性探测；验证不直接操作存储层
  - 复杂度：M

> **T11-01 ~ T11-05 可并行执行**

---

## 12. 集成测试

- [ ] **T12-01** 编写事件端到端集成测试
  - 依赖：T9-01, T11-01~T11-05
  - 涉及文件：`tests/test_integration.py`
  - 验收标准：模拟完整事件流（notify消息 → EventHandler → 处理器 → 反应引擎 → 消息发送）；验证各事件类型在 template 模式和 llm 模式下的端到端行为；验证事件开关关闭时无反应；验证 A_Memorix 不可用时降级为模板模式；验证单次异常不影响后续事件处理
  - 复杂度：L

- [ ] **T12-02** 编写配置热重载集成测试
  - 依赖：T9-02
  - 涉及文件：`tests/test_config_reload.py`
  - 验收标准：修改配置后验证插件立即使用新配置；验证事件开关变更立即生效；验证反应模式切换立即生效
  - 复杂度：M

- [ ] **T12-03** 编写 A_Memorix 协同集成测试
  - 依赖：T7-01, T9-01
  - 涉及文件：`tests/test_memory_integration.py`
  - 验收标准：验证记忆检索结果注入 LLM 提示词；验证记忆写入调用参数正确；验证 A_Memorix 超时后降级；验证 A_Memorix 返回异常数据后降级
  - 复杂度：M

---

## 13. 安全与合规验证

- [ ] **T13-01** 安全审查：QQ 号脱敏与敏感信息防护
  - 依赖：T2-02, T5-01~T5-05, T7-01
  - 涉及文件：全部处理器、memory/service.py、infra/safe_hash.py
  - 验收标准：日志中不出现明文 QQ 号；退群反应不泄露具体记忆内容（FR-05-06）；反应消息不包含完整 QQ 号或 IP 地址；记忆操作仅通过 ctx.api.call() 公开接口（FR-06-05）
  - 复杂度：M

- [ ] **T13-02** 代码规范审查
  - 依赖：T9-01
  - 涉及文件：全部 Python 文件
  - 验收标准：导入顺序符合 AGENTS.md 规范（标准库/第三方库在前，本地模块在后，同包相对导入）；日志使用简体中文；不使用 getattr/setattr 替代已有类属性访问；不修改根目录 .gitignore；不自行计算 session_id fallback hash
  - 复杂度：M

---

## 14. 最终验收与文档

- [ ] **T14-01** 运行全部测试并确认通过
  - 依赖：T11-01~T11-05, T12-01~T12-03, T13-01, T13-02
  - 涉及文件：`tests/`
  - 验收标准：所有单元测试和集成测试通过；无跳过的测试（除明确标记 skip 的）
  - 复杂度：S

- [ ] **T14-02** 编写插件使用文档（README）
  - 依赖：T14-01
  - 涉及文件：`plugins/group_event_sensor/README.md`
  - 验收标准：包含插件功能介绍、配置说明（各事件开关、反应模式、记忆配置）、安装部署步骤（Docker 环境）、模板自定义说明、常见问题
  - 复杂度：M

---

## 任务依赖关系与执行策略

### 关键路径（不可并行，决定最短完成时间）

```
T1-01 → T1-02 → T1-04 → T4-02 → T9-01 → T10-01 → T12-01 → T14-01 → T14-02
T1-01 → T1-03 → T1-04
T3-01 → T4-01 → T5-01~T5-05 → T9-01
T6-01 → T9-01
T7-01 → T9-01
```

### 可并行执行分组

| 阶段 | 可并行任务 |
|------|-----------|
| 基础设施层 | T2-01 ∥ T2-02 ∥ T2-03 |
| 数据模型 | T3-01 ∥ T3-03，然后 T3-02 |
| 事件处理器 | T5-01 ∥ T5-02 ∥ T5-03 ∥ T5-04 ∥ T5-05 |
| 反应生成器 | T6-02 ∥ T6-03，然后 T6-01 |
| 模板文件 | T8-01 ∥ T8-02 ∥ T8-03 ∥ T8-04 ∥ T8-05 |
| 单元测试 | T11-01 ∥ T11-02 ∥ T11-03 ∥ T11-04 ∥ T11-05 |

### 复杂度汇总

| 复杂度 | 数量 | 说明 |
|--------|------|------|
| S | 17 | 简单任务，≤1小时 |
| M | 22 | 中等任务，1~3小时 |
| L | 4 | 复杂任务，3~5小时 |
| **合计** | **43** | |

### 需求覆盖追踪

| 需求组 | 覆盖任务 |
|--------|---------|
| FR-01 红包事件 | T5-01, T8-01, T11-03, T12-01 |
| FR-02 戳一戳事件 | T5-02, T8-02, T11-03, T12-01 |
| FR-03 禁言事件 | T5-03, T8-03, T11-03, T12-01 |
| FR-04 入群事件 | T5-04, T8-04, T11-03, T12-01 |
| FR-05 退群事件 | T5-05, T8-05, T11-03, T12-01 |
| FR-06 记忆上下文 | T7-01, T11-05, T12-03 |
| FR-07 配置管理 | T1-03, T9-02, T9-03, T11-01, T12-02 |
| FR-08 异常降级 | T2-03, T4-01, T6-01, T7-01, T11-02~T11-05, T12-01 |
| NFR-01 性能 | T2-01, T7-01, T6-03 |
| NFR-02 可靠性 | T4-01, T2-03, T7-01, T12-01 |
| NFR-03 可维护性 | T4-03, T9-02, T13-02 |
| NFR-04 兼容性 | T1-02, T4-02, T13-02 |
| IF-01 主程序接口 | T4-02, T6-03, T9-01 |
| IF-02 A_Memorix接口 | T7-01, T13-01 |
| IF-03 协议端接口 | T4-02 |