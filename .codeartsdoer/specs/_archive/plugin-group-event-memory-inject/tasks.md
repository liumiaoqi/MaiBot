# 事件记忆注入功能 — 编码任务列表

> 基于需求规格(spec.md)和实现方案(design.md)生成，覆盖 FR-01~FR-20 及 NFR-01~NFR-07

---

## 1. 配置模型扩展

- [ ] **T1-1** 新增 `EventMemoryInjectConfig` 配置节
  - 在 `config.py` 中新增 `EventMemoryInjectConfig(PluginConfigBase)` 类
  - 字段：`enabled`(bool, 默认False)、`red_packet_enabled`(bool, 默认True)、`poke_enabled`(bool, 默认True)、`group_ban_enabled`(bool, 默认True)、`group_increase_enabled`(bool, 默认True)、`group_decrease_enabled`(bool, 默认True)、`cooldown_seconds`(int, 默认30, ge=0, le=3600)、`inject_timeout`(float, 默认5.0, ge=1.0, le=30.0)、`target_plugin_id`(str, 默认"qq_user_memory_plugin")
  - UI元数据：`__ui_label__="事件记忆注入"`, `__ui_icon__="syringe"`, `__ui_order__=10`
  - 涉及文件：`config.py`
  - 验收标准：类定义完整，Pydantic约束生效，非法值校验通过
  - 复杂度：S

- [ ] **T1-2** 将 `EventMemoryInjectConfig` 挂载到顶层配置
  - 在 `GroupEventSensorConfig` 中新增字段 `event_memory_inject: EventMemoryInjectConfig = Field(default_factory=EventMemoryInjectConfig)`
  - 涉及文件：`config.py`
  - 验收标准：`GroupEventSensorConfig` 实例包含 `event_memory_inject` 属性，默认值正确
  - 复杂度：S

- [ ] **T1-3** 更新 `config.toml` 模板和配置版本号
  - 在 `config.toml` 中新增 `[event_memory_inject]` 节及所有默认值
  - 将 `config_version` 从 `"1.0.0"` 升级至 `"1.1.0"`
  - 涉及文件：`config.toml`
  - 验收标准：配置文件包含完整的新配置节，版本号正确
  - 复杂度：S

---

## 2. 注入冷却管理器

- [ ] **T2-1** 实现 `InjectCooldownManager` 类
  - 在 `memory/cooldown.py` 中创建 `InjectCooldownManager`
  - `__init__`：初始化 `_timers: dict[str, float]`（群ID→上次注入时间戳）和 `_last_cleanup: float`
  - `is_cooled_down(group_id, cooldown_seconds) -> tuple[bool, float]`：冷却判定逻辑，cooldown_seconds==0始终允许，检测异常时间戳（未来时间/负数）时重置并记录warn
  - `mark_injected(group_id)`：标记注入成功，更新时间戳
  - `reset(group_id)`：重置指定群计时器
  - `_cleanup_expired()`：清理超过3600秒未更新的记录，每300秒执行一次
  - 涉及文件：`memory/cooldown.py`（新建）
  - 验收标准：冷却判定逻辑正确，异常时间戳自动重置，过期清理生效
  - 复杂度：M

---

## 3. 事件记忆注入器

- [ ] **T3-1** 实现 `EventMemoryInjector` 骨架与配置/可用性管理
  - 在 `memory/injector.py` 中创建 `EventMemoryInjector`
  - `__init__(degradation_manager, cooldown_manager)`：注入依赖，初始化 `_config`、`_ctx`、`_consecutive_failures`（连续失败计数）
  - `update_config(config, ctx)`：更新配置和上下文引用
  - `is_available` 属性：查询 `qq_user_memory_plugin` 可用性
  - `check_availability(ctx)` 异步方法：调用 `ctx.api.call("qq_user_memory_plugin", "retrieve_user_memory", limit=1, user_id="probe")` 探测，超时3秒，成功标记可用，失败标记不可用
  - 涉及文件：`memory/injector.py`（新建）
  - 验收标准：可用性探测逻辑正确，降级标记正确
  - 复杂度：M

- [ ] **T3-2** 实现摘要文本生成 `_generate_summary`
  - 按事件类型生成简体中文摘要文本：
    - `red_packet`：`{operator}在群{group}发了红包`
    - `poke`：`{operator}戳了戳{target}`
    - `group_ban`（禁言）：`{operator}禁言了{target}，时长{duration}秒`
    - `group_ban`（解禁，duration==0）：`{operator}解禁了{target}`
    - `group_increase`：`{operator}加入了群{group}`
    - `group_decrease`：`{operator}退出了群{group}`
  - 昵称缺失时使用"有人"兜底
  - 涉及文件：`memory/injector.py`
  - 验收标准：5种事件类型摘要格式正确，包含参与者标识和时间信息
  - 复杂度：M

- [ ] **T3-3** 实现标签构建与重要性映射
  - `_build_tags(event_type) -> str`：返回 `"group_event,{event_type}"` 格式
  - `_determine_importance(event_type) -> int`：red_packet=1, poke=1, group_ban=3, group_increase=2, group_decrease=2
  - 涉及文件：`memory/injector.py`
  - 验收标准：标签格式正确，重要性映射覆盖5种事件类型
  - 复杂度：S

- [ ] **T3-4** 实现 API 参数映射与多参与者注入策略
  - `_map_to_api_params(event_data, summary) -> list[dict]`：返回参数字典列表（多参与者场景需多条）
  - 单参与者事件（红包/入群/退群）：`target_user_id=operator.user_id`
  - 多参与者事件（戳一戳）：为被戳者注入，`target_user_id=target.user_id`
  - 多参与者事件（禁言）：为被禁言者注入，`target_user_id=target.user_id`
  - 每条参数包含：`target_user_id`, `content`, `category="relation"`, `importance`, `group_id`, `tags`
  - 涉及文件：`memory/injector.py`
  - 验收标准：参数映射完整，多参与者场景生成多条参数
  - 复杂度：M

- [ ] **T3-5** 实现注入主流程 `inject` 方法
  - 检查总开关 `enabled`，关闭则跳过
  - 检查事件类型开关（如 `red_packet_enabled`），关闭则跳过
  - 检查目标插件可用性，不可用则跳过并记录warn
  - 查询冷却状态 `cooldown_manager.is_cooled_down`，冷却期内跳过并记录debug
  - 校验事件数据完整性（`operator.user_id` 非空、`group.group_id` 非空），不完整跳过并记录warn
  - 调用 `_generate_summary`、`_build_tags`、`_determine_importance`、`_map_to_api_params`
  - 对每条参数调用 `_call_inject_api`
  - 注入成功：更新冷却计时器，记录info日志，重置连续失败计数
  - 注入失败：不更新冷却，记录warn/error日志，递增连续失败计数
  - 连续失败超过10次：输出warn告警
  - 涉及文件：`memory/injector.py`
  - 验收标准：完整注入流程正确，所有前置检查生效，异常不外泄
  - 复杂度：L

- [ ] **T3-6** 实现 API 调用与超时控制 `_call_inject_api`
  - 使用 `asyncio.wait_for` 包装 `ctx.api.call()`，超时时间取自配置 `inject_timeout`
  - 捕获 `asyncio.TimeoutError`：记录warn日志，返回失败
  - 捕获其他异常：记录error日志（含异常类型和消息），返回失败
  - API返回 `success=True`：返回成功
  - API返回 `success=False`：白名单拒绝用debug级别，其他用warn级别，返回失败
  - 涉及文件：`memory/injector.py`
  - 验收标准：超时控制生效，异常全部捕获，返回值处理正确
  - 复杂度：M

---

## 4. 处理器基类扩展

- [ ] **T4-1** `BaseEventHandler` 新增注入器属性与公共方法
  - 新增类属性 `event_memory_injector: Any = None`
  - 新增 `async inject_event_memory(event_data, ctx) -> None` 方法：
    - 检查 `event_memory_injector` 是否存在
    - 检查配置中 `event_memory_inject.enabled` 是否启用
    - 检查该事件类型开关是否启用（根据 `event_data.event_type` 映射到对应配置字段）
    - 调用 `await self.event_memory_injector.inject(event_data, ctx)`
    - 全程异常捕获，注入失败不影响处理器
  - 涉及文件：`handlers/base.py`
  - 验收标准：注入器属性可赋值，公共方法逻辑完整，异常不外泄
  - 复杂度：M

---

## 5. 各处理器集成注入调用

- [ ] **T5-1** `RedPacketHandler` 集成注入调用
  - 在 `handle` 方法的 return 之前，使用 `asyncio.create_task(self.inject_event_memory(event_data, ctx))` 异步调用
  - 涉及文件：`handlers/red_packet.py`
  - 验收标准：红包事件触发后异步执行注入，不阻塞核心反应
  - 复杂度：S

- [ ] **T5-2** `PokeHandler` 集成注入调用
  - 在 `handle` 方法的 return 之前，使用 `asyncio.create_task` 异步调用注入
  - 涉及文件：`handlers/poke.py`
  - 验收标准：戳一戳事件触发后异步执行注入
  - 复杂度：S

- [ ] **T5-3** `GroupBanHandler` 集成注入调用
  - 在 `handle` 方法的 return 之前，使用 `asyncio.create_task` 异步调用注入
  - 涉及文件：`handlers/group_ban.py`
  - 验收标准：禁言事件触发后异步执行注入
  - 复杂度：S

- [ ] **T5-4** `GroupIncreaseHandler` 集成注入调用
  - 在 `handle` 方法的 return 之前，使用 `asyncio.create_task` 异步调用注入
  - 涉及文件：`handlers/group_increase.py`
  - 验收标准：入群事件触发后异步执行注入
  - 复杂度：S

- [ ] **T5-5** `GroupDecreaseHandler` 集成注入调用
  - 在 `handle` 方法的 return 之前，使用 `asyncio.create_task` 异步调用注入
  - 涉及文件：`handlers/group_decrease.py`
  - 验收标准：退群事件触发后异步执行注入
  - 复杂度：S

---

## 6. 插件入口集成

- [ ] **T6-1** `plugin.py` 初始化注入器并装配到处理器
  - `__init__` 中新增 `self._event_memory_injector: EventMemoryInjector | None = None` 和 `self._cooldown_manager: InjectCooldownManager | None = None`
  - `on_load` 中：创建 `InjectCooldownManager` 实例 → 创建 `EventMemoryInjector` 实例 → `update_config` → `check_availability` → 在 `_init_handlers` 中装配注入器
  - `_init_handlers` 中：为每个处理器设置 `handler.event_memory_injector = self._event_memory_injector`
  - `on_config_update` 中：调用 `injector.update_config(new_config, self.ctx)`
  - 涉及文件：`plugin.py`
  - 验收标准：插件加载时注入器初始化完成，各处理器持有注入器引用，配置热更新传递到注入器
  - 复杂度：M

---

## 7. 降级管理器扩展

- [ ] **T7-1** `DegradationManager` 新增 `qq_user_memory_plugin` 服务标识支持
  - 现有 `DegradationManager` 已支持通用服务标识的可用性管理（`mark_available`/`mark_unavailable`/`is_available`），无需修改类结构
  - 确认 `EventMemoryInjector` 使用 `"qq_user_memory_plugin"` 作为服务标识调用降级管理器
  - 涉及文件：`infra/degradation.py`（确认无需修改）
  - 验收标准：降级管理器可正确管理 `qq_user_memory_plugin` 的可用性状态
  - 复杂度：S

---

## 8. memory 包导出更新

- [ ] **T8-1** 更新 `memory/__init__.py` 导出
  - 在 `memory/__init__.py` 中导入并导出 `EventMemoryInjector` 和 `InjectCooldownManager`
  - 涉及文件：`memory/__init__.py`
  - 验收标准：`from .memory import EventMemoryInjector, InjectCooldownManager` 可正常工作
  - 复杂度：S

---

## 9. 集成验证

- [ ] **T9-1** 配置模型端到端验证
  - 验证 `GroupEventSensorConfig.model_validate()` 可正确解析包含 `event_memory_inject` 节的配置
  - 验证非法配置值（如 `cooldown_seconds=-5`）使用默认值并输出告警
  - 验证默认配置下 `enabled=False`
  - 涉及文件：`config.py`
  - 验收标准：配置解析、校验、默认值全部正确
  - 复杂度：S

- [ ] **T9-2** 冷却管理器逻辑验证
  - 验证冷却期内拒绝注入、冷却过期允许注入
  - 验证 `cooldown_seconds=0` 禁用频率控制
  - 验证同群不同事件类型共享冷却
  - 验证注入失败不更新冷却计时器
  - 验证异常时间戳自动重置
  - 涉及文件：`memory/cooldown.py`
  - 验收标准：所有冷却逻辑符合 spec 5.2.1 规则1-4
  - 复杂度：M

- [ ] **T9-3** 注入器核心流程验证
  - 验证总开关关闭时跳过注入
  - 验证事件类型开关关闭时跳过注入
  - 验证目标插件不可用时优雅降级
  - 验证事件数据不完整时跳过注入并记录warn
  - 验证注入成功后更新冷却计时器
  - 验证注入失败后不更新冷却计时器
  - 验证连续失败超过10次输出告警
  - 涉及文件：`memory/injector.py`
  - 验收标准：所有注入前置检查和后置处理符合 spec 5.1.1 和 5.1.3
  - 复杂度：M

- [ ] **T9-4** 处理器集成验证
  - 验证各处理器在核心反应完成后异步调用注入
  - 验证注入失败不影响处理器返回结果
  - 验证 `asyncio.create_task` 包装确保不阻塞
  - 涉及文件：`handlers/*.py`
  - 验收标准：注入调用不阻塞、不影响核心反应（FR-07, FR-20, NFR-02, NFR-03）
  - 复杂度：M

- [ ] **T9-5** 插件初始化与配置热更新验证
  - 验证 `on_load` 中注入器初始化顺序正确
  - 验证目标插件不可用时降级标记正确
  - 验证 `on_config_update` 传递配置更新到注入器
  - 涉及文件：`plugin.py`
  - 验收标准：插件生命周期中注入器状态正确
  - 复杂度：M

---

## 任务依赖关系

```
T1-1 → T1-2 → T1-3
T2-1 (独立)
T3-1 → T3-2 → T3-3 → T3-4 → T3-5 → T3-6
T4-1 (依赖 T3-1 骨架)
T5-1~T5-5 (依赖 T4-1)
T6-1 (依赖 T1-2, T2-1, T3-6, T4-1)
T7-1 (独立，确认性任务)
T8-1 (依赖 T3-6, T2-1)
T9-1 (依赖 T1-3)
T9-2 (依赖 T2-1)
T9-3 (依赖 T3-6, T2-1)
T9-4 (依赖 T5-1~T5-5)
T9-5 (依赖 T6-1)
```

## 需求覆盖追踪

| 需求 | 覆盖任务 |
|------|---------|
| FR-01 事件触发记忆注入 | T3-5, T4-1, T5-1~T5-5 |
| FR-02 五种事件类型覆盖 | T3-2, T3-4, T5-1~T5-5 |
| FR-03 摘要文本内容 | T3-2 |
| FR-04 参与者关联 | T3-4 |
| FR-05 标签分类 | T3-3 |
| FR-06 注入幂等性 | T3-4 (external_id由API保证) |
| FR-07 注入失败降级 | T3-5, T3-6, T4-1 |
| FR-08 冷却窗口控制 | T2-1, T3-5 |
| FR-09 冷却过期恢复 | T2-1 |
| FR-10 冷却维度为群 | T2-1 |
| FR-11 冷却窗口可配置 | T1-1, T2-1 |
| FR-12 注入成功更新冷却 | T2-1, T3-5 |
| FR-13 注入失败不更新冷却 | T2-1, T3-5 |
| FR-14 功能总开关 | T1-1, T3-5, T4-1 |
| FR-15 事件类型独立开关 | T1-1, T3-5, T4-1 |
| FR-16 配置校验与默认值 | T1-1, T9-1 |
| FR-17 目标插件不可用降级 | T3-1, T7-1 |
| FR-18 注入API超时 | T3-6 |
| FR-19 事件上下文不完整 | T3-5 |
| FR-20 注入操作异步执行 | T4-1, T5-1~T5-5 |
| NFR-01 注入耗时上限 | T3-6 |
| NFR-02 核心反应无延迟 | T4-1, T5-1~T5-5 |
| NFR-03 核心反应可靠性 | T3-5, T3-6, T4-1 |
| NFR-04 失败率告警 | T3-5 |
| NFR-05 SDK版本兼容 | T3-1, T3-6 |
| NFR-06 Docker适配 | T1-3 |
| NFR-07 不修改目标插件 | 全局约束 |