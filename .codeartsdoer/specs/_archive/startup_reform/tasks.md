# 启动流程改革 — 实施任务清单

## 概述

本任务清单将 `spec.md` 的 9 项核心能力（5.1-5.9）和 `design.md` 的 5 批次迁移策略转化为可执行、可验收的编码任务。

**缺陷覆盖**：缺陷 1（模块级副作用）、缺陷 2（隐式初始化顺序）、缺陷 3（sleep 轮询）、缺陷 4（getattr 私有属性）、缺陷 5（asyncio.gather 全有或全无）、缺陷 6（无分项计时）、缺陷 7（消息处理器注册时序窗口）。

**批次验证**：每批次完成后需容器重启验证，确保系统功能不退化。

---

## 1. 启动框架核心

**目标**：创建 `src/core/startup/` 包，实现 StartupOrchestrator + 数据模型 + 阶段枚举，为后续批次提供骨架。

**覆盖需求**：5.1（启动阶段划分）、5.2（显式初始化顺序）

### 1.1 创建启动框架目录和枚举/数据类

- [ ] 新建 `src/core/startup/__init__.py`，导出公共 API
- [ ] 新建 `src/core/startup/types.py`，实现以下类型：
  - `StartupPhase` 枚举：CONFIG_LOAD(0) / INFRASTRUCTURE(1) / CORE_SERVICES(2) / SUBSYSTEMS(3) / SESSION_RESTORE(4) / READY(5)
  - `ComponentStatus` 枚举：PENDING / IN_PROGRESS / SUCCESS / FAILED / SKIPPED
  - `StartupComponent` 数据类：name, phase, order, critical, init_fn, status, start_time, end_time, duration_ms, error
  - `PhaseResult` 数据类：phase, status, start_time, end_time, duration_ms, components
  - `StartupResult` 数据类：total_duration_ms, phases, failed_components, degraded_components, ready, core_ready, core_ready_time_ms, subsystem_status
  - `CoreReadiness` 数据类：message_pipeline_ready, agent_thinking_ready, reply_capability_ready, core_ready(property)

  **CoreReadiness 三条件组件映射**（由 StartupOrchestrator 在阶段 2 完成后自动判定）：
  - `message_pipeline_ready` ← `session_port_registry`（阶段 2 序号 2）完成后设为 True
  - `agent_thinking_ready` ← `agent_registry`（阶段 2 序号 6）完成后设为 True
  - `reply_capability_ready` ← `replyer_port`（阶段 2 序号 3）完成后设为 True

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/core/startup/__init__.py`（新建）, `src/core/startup/types.py`（新建） |
| 验证标准 | `from src.core.startup import StartupPhase, StartupComponent, StartupResult, CoreReadiness` 导入成功；`StartupPhase.CONFIG_LOAD.value == 0`；`CoreReadiness(True, True, True).core_ready == True` |
| 依赖 | 无 |

### 1.2 实现 StartupOrchestrator 核心逻辑

- [ ] 新建 `src/core/startup/orchestrator.py`，实现 `StartupOrchestrator` 类：
  - `__init__()`：初始化 `_components: list[StartupComponent]`、`_phase_results: dict[StartupPhase, PhaseResult]`、`_core_readiness: CoreReadiness`、`_subsystem_status: dict[str, ComponentStatus]`
  - `register(component: StartupComponent)`：注册组件，校验 name 唯一性和 phase+order 不冲突
  - `run() -> StartupResult`：按 StartupPhase 枚举顺序执行 6 个阶段，返回 StartupResult
  - `_run_phase(phase: StartupPhase) -> PhaseResult`：执行单个阶段——记录开始时间 → 检查准入条件 → 执行组件 → 记录结束时间
  - `_run_component(component: StartupComponent)`：执行单个组件——关键组件直接 await，异常向上传播；非关键组件 try/except 包裹，失败标记降级
  - `_check_phase_entry(phase: StartupPhase) -> bool`：检查前一阶段所有关键组件是否 SUCCESS
  - 阶段 3（SUBSYSTEMS）的组件使用 `asyncio.create_task()` 并行启动，其余阶段按 order 顺序执行

| 属性　　 | 值　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |
| ----------| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 负责人　 | CC　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |
| 涉及文件 | `src/core/startup/orchestrator.py`（新建）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |
| 验证标准 | 注册 3 个 mock 组件（分属不同阶段），调用 `run()` 后返回 `StartupResult`，阶段按枚举顺序执行，组件按 order 排序执行；关键组件异常时 `run()` 抛出异常；非关键组件异常时标记 FAILED 继续执行 |
| 依赖　　 | T1.1　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |

### 1.3 实现 StartupValidator 配置前置校验

- [ ] 新建 `src/core/startup/validator.py`，实现 `StartupValidator` 类：
  - `validate(global_config: Config, model_config: ModelConfig) -> list[str]` 静态方法
  - 校验项：
    1. model_config 中至少配置一个 API Provider
    2. model_config 中至少配置一个模型
    3. 每个模型的 api_provider 字段指向已定义的 Provider
    4. 智能体配置目录（`agents/`）存在且至少有一个智能体配置
  - 不重复 ConfigManager.model_post_init 已有的校验
  - 返回校验失败项列表，空列表表示通过

| 属性 | 值 |
|------|-----|
| 负责人 | Codex |
| 涉及文件 | `src/core/startup/validator.py`（新建） |
| 验证标准 | 无 API Provider 时返回非空列表；配置完整时返回空列表；模型引用不存在的 Provider 时返回对应错误信息 |
| 依赖 | T1.1 |

**批次 1 验证点**：启动框架代码可导入，类型检查通过，单元测试覆盖核心逻辑。此批次为纯新增代码，不影响现有功能。

---

## 2. main.py 重构——阶段化启动

**目标**：将 `_init_components()` 200 行线性函数拆分为 6 个阶段方法，接入 StartupOrchestrator，解决缺陷 2（隐式初始化顺序）和缺陷 7（消息处理器注册时序窗口）。

**覆盖需求**：5.1（启动阶段划分）、5.2（显式初始化顺序）、5.8（微内核启动理念）

### 2.1 拆分 _init_components 为 6 个阶段初始化方法

- [ ] 修改 `src/main.py`，在 `MainSystem` 类中新增 6 个阶段方法，将现有 `_init_components()` 逻辑按阶段分配：
  - `_init_phase0_config()` → 配置监听器启动（`config_manager.start_file_watcher()`）
  - `_init_phase1_infra()` → 工具记录清理（`run_startup_tool_record_vacuum_if_needed()`）
  - `_init_phase2_core_services()` → SessionStore/MessageRegistry/SessionNameCache/SessionResolver/BindingRestorer/SessionLifecycle 构造 + ChatManagerAdapter + Protocol 端口注册 + ReplyerServicePort + ImageDescriptionPort + RuntimeRegistry + AgentConfigRegistry + ModelConfigPort + prompt_manager
  - `_init_phase3_subsystems()` → plugin_runtime_manager.start() + a_memorix_host_service.start() + emoji_manager.load_emojis_from_db() + ModelConfigPort 注入 4 个消费者（详见下方消费者列表）
  - `_init_phase4_session_restore()` → lifecycle_port.initialize() + regularly_save_sessions() + memory_automation_service.start()
  - `_init_phase5_ready()` → ON_START 事件 + WebUI + 定时任务 + 交互调度器

  **ModelConfigPort 4 个消费者**（阶段 3 model_config_port_inject 组件注入）：
  1. `a_memorix_host_service` — EmbeddingAPIAdapter 依赖 ModelConfigPort 获取 embedding 模型配置
  2. `replyer_manager` — LLM 调用依赖 ModelConfigPort 获取回复模型配置
  3. `image_manager` — 图片描述依赖 ModelConfigPort 获取视觉模型配置
  4. `emotion_manager` — 情绪分析依赖 ModelConfigPort 获取情感模型配置

  **注意**：ModelConfigPort 在阶段 2（序号 7）构造，在阶段 3（序号 3）注入消费者。构造和注入分属不同阶段是因为消费者在阶段 2 尚未构造完成。
- [ ] 保留旧 `_init_components()` 暂时调用 6 个阶段方法（保持功能不变），供后续 T2.2 替换

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/main.py` |
| 验证标准 | 容器重启后功能与拆分前完全一致；6 个阶段方法可独立调用 |
| 依赖 | T1.1 |

### 2.2 MainSystem.initialize() 接入 StartupOrchestrator

- [ ] 修改 `src/main.py`，重构 `MainSystem.initialize()`：
  - 创建 `StartupOrchestrator` 实例
  - 将 6 个阶段方法注册为 `StartupComponent`（声明 phase + order + critical）
  - 调用 `orchestrator.run()` 替代旧的 `_init_components()`
  - 删除旧 `_init_components()` 方法
  - 保存 `self._startup_result = result` 供后续查询
- [ ] 组件注册清单（与 design.md 2.4 节对齐）：
  - 阶段 0：config_manager(critical=True, order=0), config_validator(critical=True, order=1)
  - 阶段 1：file_watcher(critical=True, order=0), tool_record_vacuum(critical=False, order=1)
  - 阶段 2：session_submodules(critical=True, order=0), chat_manager_adapter(critical=True, order=1), session_port_registry(critical=True, order=2), replyer_port(critical=True, order=3), image_port(critical=True, order=4), runtime_port(critical=True, order=5), agent_registry(critical=True, order=6), model_config_port(critical=True, order=7), prompt_manager(critical=True, order=8)
  - 阶段 3：plugin_runtime(critical=False, order=0), a_memorix(critical=False, order=1), emoji_manager(critical=False, order=2), model_config_port_inject(critical=False, order=3)
  - 阶段 4：session_lifecycle(critical=True, order=0), memory_automation(critical=False, order=1)
  - 阶段 5：message_handlers(critical=True, order=0), on_start_event(critical=True, order=1), webui_server(critical=False, order=2), online_time_task(critical=False, order=3), statistic_task(critical=False, order=4), telemetry_tasks(critical=False, order=5), interaction_scheduler(critical=False, order=6)

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/main.py` |
| 验证标准 | 容器重启后启动日志可见 6 个阶段依次执行；所有 Protocol 端口注册时机不变；功能与改革前一致 |
| 依赖 | T1.2, T2.1 |

### 2.3 消息处理器注册移到阶段 5——就绪屏障

- [ ] 修改 `src/main.py`：
  - 将 `_register_message_handlers()` 从 `schedule_tasks()` 移到阶段 5 的 `message_handlers` 组件（order=0）
  - `schedule_tasks()` 只负责启动消息服务（`self.app.run()`, `self.server.run()`）和定时清理任务
  - 确保消息处理器注册（阶段 5 order=0）在消息服务启动（`schedule_tasks()`）之前完成
- [ ] 新增 i18n key `startup.message_handlers_registered`（zh-CN/en-US/ja-JP 三语同步）

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/main.py` |
| 验证标准 | 启动日志中消息处理器注册在消息服务启动之前；`schedule_tasks()` 中不再调用 `_register_message_handlers()`；容器重启后消息处理正常 |
| 依赖 | T2.2 |

**批次 2 验证点**：容器重启后，启动日志可见 6 个阶段依次执行，每个阶段有开始/完成标记。所有 Protocol 端口注册时机不变，消息处理器在消息服务启动前注册。功能与改革前一致。

---

## 3. 错误处理与降级

**目标**：消除缺陷 3（sleep 轮询）、缺陷 4（getattr 私有属性）、缺陷 5（asyncio.gather 全有或全无），实现非关键组件独立异常边界和降级运行。

**覆盖需求**：5.4（启动错误处理与降级）、5.6（时序同步与接口规范）、5.9（插件实现无关性约束）

### 3.1 阶段 3 子系统独立异常边界

- [ ] 修改 `src/core/startup/orchestrator.py` 的 `_run_phase()` 方法，对阶段 3（SUBSYSTEMS）的组件使用 `asyncio.create_task()` 并行启动，每个 task 独立 try/except：
  - 不使用 `asyncio.gather()`，避免全有或全无行为
  - 每个 task 失败仅标记该组件为 FAILED + 记录降级警告
  - 等待所有 task 完成后继续下一阶段
  - 超时保护：`asyncio.wait_for(task, timeout=60.0)`，超时标记降级继续
- [ ] 修改 `src/main.py` 的 `_init_phase3_subsystems()`，移除现有的 `asyncio.gather(plugin_runtime_task, a_memorix_task)` + `await emoji_load_task` 逻辑，改为由 orchestrator 管理并行

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/core/startup/orchestrator.py`, `src/main.py` |
| 验证标准 | 模拟 A_memorix start() 抛出异常，插件运行时和表情管理器不受影响继续启动；启动摘要中 A_memorix 标记为 FAILED/降级 |
| 依赖 | T2.2 |

### 3.2 PluginRuntimeManager 暴露 ready_event

- [ ] 修改 `src/plugin_runtime/integration.py`：
  - 在 `PluginRuntimeManager.__init__()` 中新增 `self._ready_event: asyncio.Event = asyncio.Event()`
  - 新增 `@property ready_event -> asyncio.Event`
  - 在 `start()` 方法的成功路径末尾（`self._started = True` 之后）添加 `self._ready_event.set()`
  - 在 `start()` 方法的异常路径（except 块中）不 set event（保持 unset 表示未就绪）

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/plugin_runtime/integration.py` |

| 依赖 | 无（可与批次 2 并行） |

### 3.3 AMemorixHostService 暴露 ready_event

- [ ] 修改 `src/A_memorix/host_service.py`：
  - 在 `AMemorixHostService.__init__()` 中新增 `self._ready_event: asyncio.Event = asyncio.Event()`
  - 新增 `@property ready_event -> asyncio.Event`
  - 在 `start()` 方法的成功路径末尾（`await self._ensure_kernel()` 之后）添加 `self._ready_event.set()`
  - 在 `start()` 方法的"未启用"路径也 set event（表示"已就绪——只是未启用"）
  - 在 `start()` 方法的异常路径不 set event

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/A_memorix/host_service.py` |
| 验证标准 | `AMemorixHostService().ready_event` 属性可访问，类型为 `asyncio.Event`；`start()` 成功后 `ready_event.is_set() == True` |
| 依赖 | 无（可与批次 2 并行） |

### 3.4 删除 _wait_for_plugin_runners_spawned() + 替换为 Event 等待

- [ ] 修改 `src/main.py`：
  - 删除 `_wait_for_plugin_runners_spawned()` 函数（第 32-46 行）
  - 删除 `_init_components()` 中对该函数的调用（第 201 行）
  - 在阶段 3 的 plugin_runtime 组件初始化中，改为 `await asyncio.wait_for(plugin_runtime_manager.ready_event.wait(), timeout=30.0)`，超时标记降级
  - 删除 `await asyncio.sleep(0)` 调度让步（第 225 行）
  - 删除注释掉的 `await asyncio.sleep(0.5)`（第 277 行）

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/main.py` |
| 验证标准 | `src/main.py` 中不存在 `_wait_for_plugin_runners_spawned` 函数定义和调用；不存在 `asyncio.sleep(0)` 和 `asyncio.sleep(0.02)` 调用（测试/调试除外）；容器重启后插件运行时正常启动 |
| 依赖 | T2.2, T3.2 |

**批次 3 验证点**：启动代码中不存在 `asyncio.sleep()` hack 和 `getattr` 私有属性访问；非关键组件失败时系统降级运行而非终止；关键组件失败时系统终止。

---

## 4. 可观测性与校验

**目标**：实现缺陷 6（无分项计时）的修复，集成 StartupValidator 到阶段 0，添加启动摘要和阶段状态日志。

**覆盖需求**：5.3（启动可观测性）、5.7（配置前置校验）

### 4.1 阶段/组件计时逻辑

- [ ] 修改 `src/core/startup/orchestrator.py`：
  - 在 `_run_phase()` 中添加 `time.monotonic()` 计时：开始时记录 `phase.start_time`，结束时记录 `phase.end_time`，计算 `phase.duration_ms`
  - 在 `_run_component()` 中添加 `time.monotonic()` 计时：开始时记录 `component.start_time`，结束时记录 `component.end_time`，计算 `component.duration_ms`
  - 在 `run()` 中计算 `StartupResult.total_duration_ms` 和 `StartupResult.core_ready_time_ms`（核心就绪时刻 - 启动开始时刻）

| 属性 | 值 |
|------|-----|
| 负责人 | Codex |
| 涉及文件 | `src/core/startup/orchestrator.py` |
| 验证标准 | 启动完成后 `StartupResult.total_duration_ms > 0`；每个 `PhaseResult.duration_ms > 0`；每个 `StartupComponent.duration_ms > 0` |
| 依赖 | T1.2 |

### 4.2 启动摘要输出

- [ ] 修改 `src/core/startup/orchestrator.py`，实现 `_emit_startup_summary(result: StartupResult)` 方法：
  - 输出格式与 design.md 2.8.2 节对齐：
    ```
    [启动摘要] 总耗时=15234ms | 核心就绪=3210ms
      阶段0 配置加载: 234ms ✓
        config_manager: 198ms ✓
        config_validator: 36ms ✓
      ...
      降级组件: 无 / 组件名列表
    ```
  - 在 `run()` 末尾调用 `_emit_startup_summary()`
  - 使用 `logger.info()` 输出

| 属性 | 值 |
|------|-----|
| 负责人 | Codex |
| 涉及文件 | `src/core/startup/orchestrator.py` |
| 验证标准 | 容器启动后日志包含 `[启动摘要]` 行；摘要中可见总耗时、核心就绪耗时、各阶段耗时、降级组件列表 |
| 依赖 | T4.1 |

### 4.3 阶段状态日志

- [ ] 修改 `src/core/startup/orchestrator.py`：
  - 在 `_run_phase()` 开始时输出 `[启动] 阶段N: 名称 状态=进行中`
  - 在 `_run_phase()` 成功完成时输出 `[启动] 阶段N: 名称 状态=成功 耗时=Xms`
  - 在 `_run_phase()` 失败时输出 `[启动] 阶段N: 名称 状态=失败 耗时=Xms`
  - 在 `_run_component()` 失败时输出 `[启动] 组件X 初始化失败: [异常信息]`（关键组件）或 `[启动] 非关键组件X 初始化失败，降级运行: [异常信息]`（非关键组件）
- [ ] 新增 i18n keys：`startup.phase_in_progress`, `startup.phase_success`, `startup.phase_failed`, `startup.component_critical_failed`, `startup.component_degraded`（三语同步）

| 属性 | 值 |
|------|-----|
| 负责人 | Codex |
| 涉及文件 | `src/core/startup/orchestrator.py` |
| 验证标准 | 启动日志中可见每个阶段的"进行中"和"成功/失败"状态行；非关键组件失败时可见降级警告 |
| 依赖 | T1.2 |

### 4.4 StartupValidator 集成到阶段 0

- [ ] 修改 `src/main.py`：
  - 在阶段 0 的 `config_validator` 组件（order=1）中调用 `StartupValidator.validate(global_config, model_config)`
  - 校验失败时（返回非空列表）抛出 `ValueError`，终止启动
  - 校验失败日志输出所有失败项
- [ ] 新增 i18n keys：`startup.config_validation_failed`, `startup.validation_item`（三语同步）

| 属性 | 值 |
|------|-----|
| 负责人 | Codex |
| 涉及文件 | `src/main.py` |
| 验证标准 | model_config.toml 中 API Provider 缺失时，启动在阶段 0 终止，日志输出具体校验失败项；配置完整时正常启动 |
| 依赖 | T1.3, T2.2 |

**批次 4 验证点**：启动日志包含结构化启动摘要（总耗时、各阶段耗时、核心就绪时间、降级组件）；每个阶段有状态日志；配置不完整时阶段 0 终止。

---

## 5. 模块级单例迁移——config_manager 延迟初始化

**目标**：消除缺陷 1（模块级副作用）的核心根源——`config.py` 第 753-755 行的模块级 `ConfigManager()` + `initialize()` 执行。渐进迁移，本次只处理 config_manager + global_config，其余 46 个单例后续处理。

**覆盖需求**：5.5（模块级副作用消除）

**风险提示**：此批次影响全项目 100+ 处导入，是整个改革中风险最高的任务。_ConfigProxy 代理机制是兼容性保证的关键——迁移后 `from src.config.config import global_config` 仍可使用，因为 _ConfigProxy 在属性访问时才调用 getter。

### 5.1 config_manager / global_config 模块级初始化消除

- [ ] 修改 `src/config/config.py`：
  - 将第 753-755 行：
    ```python
    config_manager = ConfigManager()
    config_manager.initialize()
    global_config: Config = cast(Config, _ConfigProxy(config_manager.get_global_config))
    model_config: ModelConfig = cast(ModelConfig, _ConfigProxy(config_manager.get_model_config))
    ```
    改为：
    ```python
    config_manager: ConfigManager | None = None
    global_config: Config = cast(Config, _ConfigProxy(lambda: config_manager.get_global_config() if config_manager is not None else None))
    model_config: ModelConfig = cast(ModelConfig, _ConfigProxy(lambda: config_manager.get_model_config() if config_manager is not None else None))
    ```
  - 新增 `initialize_config() -> None` 函数：
    ```python
    def initialize_config() -> None:
        """显式初始化配置管理器，由 StartupOrchestrator 在阶段 0 调用。"""
        global config_manager
        config_manager = ConfigManager()
        config_manager.initialize()
    ```
  - `_ConfigProxy` 的 getter 改为 lambda 形式，在 `config_manager is None` 时访问属性会触发 `AttributeError`（不兜底，让错误完整暴露）
  - 保留 `_ConfigProxy` 类不变，保留 `model_config` 的 _ConfigProxy 代理

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | `src/config/config.py` |
| 验证标准 | `import src.config.config` 不触发 `ConfigManager()` 构造和 `initialize()` 调用；`initialize_config()` 调用后 `config_manager is not None`；`global_config.bot.nickname` 在 `initialize_config()` 后正常访问 |
| 依赖 | T2.2 |

### 5.2 initialize_config() 在阶段 0 调用

- [ ] 修改 `src/main.py`：
  - 在阶段 0 的 `config_manager` 组件（order=0）的 init_fn 中调用 `initialize_config()`
  - 确保 `initialize_config()` 在 `config_manager.start_file_watcher()` 之前调用
  - `main()` 函数入口处（`set_main_loop` 之后、`system.initialize()` 之前）调用 `initialize_config()`，确保 `global_config` 在 `MainSystem.__init__` 之前可用

| 属性　　 | 值　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |
| ----------| ------------------------------------------------------------------------------------------------|
| 负责人　 | CC　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |
| 涉及文件 | `src/main.py`　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| 验证标准 | 容器重启后功能与改革前一致；`MainSystem.initialize()` 中 `global_config.bot.nickname` 正常访问 |
| 依赖　　 | T5.1, T2.2　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 |

### 5.3 全项目 config_manager 导入兼容性验证

- [ ] 检查所有 `from src.config.config import config_manager` 和 `from src.config.config import global_config` 导入点（约 100+ 处），确认：
  - 函数/方法体内的 `global_config.xxx` 访问正常（_ConfigProxy 代理保证）
  - 模块级的 `global_config.xxx` 访问（如有）需改为函数内延迟访问
  - `config_manager` 的直接使用（如 `config_manager.get_global_config()`）需确保在 `initialize_config()` 之后
- [ ] 修复发现的兼容性问题（预计少量模块级访问需改为延迟访问）
- [ ] 验证配置热重载机制正常（`_ConfigProxy` + `config_manager.register_reload_callback()`）

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | 全项目涉及 `config_manager` / `global_config` 导入的文件 |
| 验证标准 | 容器重启后全项目无 `AttributeError: 'NoneType' object has no attribute...` 错误；配置热重载正常（修改 bot_config.toml 后自动生效） |
| 依赖 | T5.2 |

**批次 5 验证点**：`import src.config.config` 不触发配置加载；`initialize_config()` 调用后配置可用；全项目无导入错误；配置热重载正常；容器重启功能不退化。

---

## 6. 集成验证与回归测试

**目标**：端到端验证启动流程改革的完整性和正确性。

### 6.1 启动流程端到端验证

- [x] 容器重启，验证以下场景：
  - 正常启动：6 个阶段依次执行，启动摘要输出正确 ✅
  - 核心就绪时间：`core_ready_time_ms ≤ 5000ms` ✅ (4288ms)
  - 阶段 3 子系统异步启动不阻塞阶段 4/5 ✅
  - 消息处理器在消息服务启动前注册（就绪屏障） ✅
  - 配置热重载正常 ⬜（需手动验证）
  - WebUI 正常启动 ✅
  - 插件运行时正常启动 ✅
  - A_memorix 正常启动 ✅

**集成验证修复**（T6.1 过程中发现并修复的 3 个 bug）：
1. `bot.py` 入口未调用 `initialize_config()` — 实际入口是 `bot.py` 而非 `main.py`，`initialize_config()` 只加在了 `main.py`
2. `StartupValidator._validate_agent_config()` 检查子目录而非 `.md` 文件 — 与 `AgentConfigLoader.load_all()` 的 `glob("*.md")` 不一致
3. `StartupOrchestrator._update_core_readiness()` 组件名映射错误 — `session_port_registry` 应为 `chat_manager_adapter`

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | 无代码修改，纯验证 |
| 验证标准 | 上述 8 项全部通过 |
| 依赖 | T5.3 |

### 6.2 降级场景验证

- [x] 模拟以下降级场景，验证系统行为：
  - A_memorix 启动失败 → 系统降级运行，智能体无记忆上下文但可回复
  - 插件运行时启动超时 → 系统降级运行，插件功能不可用
  - WebUI 启动失败 → 系统降级运行，消息处理不受影响
  - 智能体交互调度器启动失败 → 系统降级运行，日志记录降级警告

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | 无代码修改，纯验证 |
| 验证标准 | 4 个降级场景全部通过；降级组件在启动摘要中正确列出 |
| 依赖 | T6.1 |

### 6.3 关键组件失败终止验证

- [x] 模拟以下关键组件失败场景，验证系统终止行为：
  - ConfigManager 初始化失败 → 阶段 0 终止
  - SessionStore 构造失败 → 阶段 2 终止
  - Protocol 端口注册失败 → 阶段 2 终止
  - 消息处理器注册失败 → 阶段 5 终止

| 属性 | 值 |
|------|-----|
| 负责人 | CC |
| 涉及文件 | 无代码修改，纯验证 |
| 验证标准 | 4 个终止场景全部通过；终止日志包含失败组件名、异常类型、异常消息 |
| 依赖 | T6.1 |

---

## 任务依赖关系图

```
T1.1 ──→ T1.2 ──→ T2.2 ──→ T2.3 ──→ T3.1
  │        │        │                  │
  │        │        │                  └──→ T3.4 ←── T3.2
  │        │        │
  │        │        ├──→ T4.4 ←── T1.3
  │        │        │
  │        └──→ T4.1 ──→ T4.2
  │             │
  │             └──→ T4.3
  │
  ├──→ T2.1 ──→ T2.2
  │
  ├──→ T1.3 ──→ T4.4
  │
  ├──→ T3.2（独立，可与批次 2 并行）
  │
  └──→ T3.3（独立，可与批次 2 并行）

T2.2 ──→ T5.1 ──→ T5.2 ──→ T5.3 ──→ T6.1 ──→ T6.2
                                              └──→ T6.3
```

**关键路径**：T1.1 → T1.2 → T2.1 → T2.2 → T5.1 → T5.2 → T5.3 → T6.1

**可并行任务**：
- T3.2（PluginRuntimeManager ready_event）和 T3.3（AMemorixHostService ready_event）可与批次 2 并行
- T1.3（StartupValidator）和 T4.1-T4.3（可观测性）可在批次 2 期间并行开发
- T3.2 和 T3.3 修改不同文件，可由 CC 和 Codex 并行执行

---

## 文件锁分配

| 文件 | 批次 1 | 批次 2 | 批次 3 | 批次 4 | 批次 5 |
|------|--------|--------|--------|--------|--------|
| `src/core/startup/types.py` | CC | — | — | — | — |
| `src/core/startup/orchestrator.py` | CC | — | CC | Codex | — |
| `src/core/startup/validator.py` | Codex | — | — | — | — |
| `src/main.py` | — | CC | CC | CC | CC |
| `src/plugin_runtime/integration.py` | — | — | CC | — | — |
| `src/A_memorix/host_service.py` | — | — | CC | — | — |
| `src/config/config.py` | — | — | — | — | CC |

**注意**：同一文件在同一批次内只能由一个智能体修改。跨批次时文件可切换负责人。