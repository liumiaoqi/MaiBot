# 编码任务列表

> 基于 `.codeartsdoer/specs/agent_log/spec.md` 和 `design.md` 生成

## 阶段一：AutonomyLogger 核心模块

### 任务 1.1：创建 AutonomyLogger 模块

**文件**: `src/maisaka/agent_autonomy/autonomy_logger.py`（新建）

**内容**:
- `AutonomyEventType` 枚举类：thinking / expression / inner_need / behavior_intent / interjection / orchestration
- `AutonomyLogger` 类：
  - `__init__()`: 使用 `get_logger("agent_autonomy")` 初始化
  - `log(agent_id, event_type, detail, *, level="info", session_id="")`: 统一日志输出
  - 日志格式: `[Autonomy:{agent_id}] {event_type}: {detail}`
  - `get()` 类方法：获取单例
- `AutonomyEventSubscriber` 类：
  - `subscribe_all()`: 订阅 EventBus 的 interaction_signal 和 interjection_mention
  - `_on_interaction_signal()`: 转发交互信号日志
  - `_on_interjection_mention()`: 转发插话提及日志

**验收**: `AutonomyLogger.get().log("himeko", "thinking", "测试日志")` 输出 `[Autonomy:himeko] thinking: 测试日志`

### 任务 1.2：为 ThinkingOrgan 添加日志

**文件**: `src/maisaka/agent_autonomy/thinking_organ.py`（修改）

**内容**:
- 在 `think()` 方法完成时调用 `AutonomyLogger.log()` 记录思考结果
- INFO 级别：思考完成（包含决策摘要）
- DEBUG 级别：中间推理过程

**验收**: 智能体完成思考 → `docker logs` 中出现 `[Autonomy:{agent_id}] thinking: ...`

### 任务 1.3：为 ExpressionOrgan 添加日志

**文件**: `src/maisaka/agent_autonomy/expression_organ.py`（修改）

**内容**:
- 在表达意图产生时调用 `AutonomyLogger.log()` 记录
- INFO 级别：表达意图（想说话/想行动）

**验收**: 智能体产生表达意图 → 日志中出现 `[Autonomy:{agent_id}] expression: ...`

### 任务 1.4：为 InterjectionScheduler 添加日志

**文件**: `src/maisaka/agent_autonomy/interjection_scheduler.py`（修改）

**内容**:
- 在插话决策点调用 `AutonomyLogger.log()` 记录
- INFO 级别：决定插话 / 决定跳过（含原因）
- WARNING 级别：冷却中无法插话

**验收**: 插话决策 → 日志中出现 `[Autonomy:{agent_id}] interjection: 决定插话...` 或 `interjection: 跳过(冷却中)`

### 任务 1.5：为 AgentOrchestrator 添加日志

**文件**: `src/maisaka/agent_autonomy/orchestrator.py`（修改）

**内容**:
- 在关键协调决策点调用 `AutonomyLogger.log()` 记录
- INFO 级别：发言权变更、智能体加入/退出、插话执行
- DEBUG 级别：优先级排序细节

**验收**: 协调决策 → 日志中出现 `[Autonomy:{agent_id}] orchestration: ...`

### 任务 1.6：为 InnerNeedEngine 和 BehaviorIntentEngine 添加日志

**文件**: `src/maisaka/agent_autonomy/inner_need.py`、`behavior_intent.py`（修改）

**内容**:
- InnerNeedEngine：DEBUG 级别记录需求计算结果
- BehaviorIntentEngine：INFO 级别记录意图产生，DEBUG 级别记录意图计算过程

**验收**: 需求/意图计算 → 日志中出现对应 event_type

### 任务 1.7：在 Orchestrator 初始化时启动 EventBus 订阅

**文件**: `src/maisaka/agent_autonomy/orchestrator.py`（修改）

**内容**:
- 在 `__init__` 中创建 `AutonomyEventSubscriber` 并调用 `subscribe_all()`
- 确保 EventBus 事件也通过日志记录

**验收**: 交互信号发布 → 日志中出现 orchestration 类型日志

---

## 阶段二：会话持久化恢复

### 任务 2.1：ActivityStore 新增查询方法

**文件**: `src/maisaka/agent_autonomy/activity_store.py`（修改）

**内容**:
- 新增 `get_all_active_sessions() -> list[AgentAutonomyActivity]`
- 查询条件: `exited_at IS NULL`
- 返回所有未退出的活跃记录

**验收**: 调用方法 → 返回所有活跃的智能体会话关联

### 任务 2.2：AgentOrchestrator 新增 restore_agent 方法

**文件**: `src/maisaka/agent_autonomy/orchestrator.py`（修改）

**内容**:
- 新增 `restore_agent(agent_id: str, is_primary: bool = False) -> None`
- 重建 AutonomousAgent 实例，加入 `_active_agents`
- 恢复 `_primary_agent_id` 标记
- **不触发事件**，不记录 activity（数据库中已有）

**验收**: 调用 `restore_agent("himeko", True)` → `_active_agents` 包含 himeko，`_primary_agent_id` 为 himeko

### 任务 2.3：创建 SessionRecoveryService

**文件**: `src/maisaka/agent_autonomy/session_recovery.py`（新建）

**内容**:
- `SessionRecoveryService` 类：
  - `recover_all(chat_manager) -> dict[str, list[str]]`
  - 查询所有活跃记录，按 session_id 分组
  - 验证 ChatSession 存在性（不存在则标记 exited）
  - 为每个会话获取/创建 Orchestrator，调用 `restore_agent()`
  - 日志记录恢复结果
- 纯状态重建，不触发任何智能体行为

**验收**: 重启后调用 `recover_all()` → 活跃会话的智能体关联被恢复

### 任务 2.4：Runtime 启动时集成恢复

**文件**: `src/maisaka/runtime.py`（修改）

**内容**:
- 在 `_init_agent_autonomy()` 末尾调用 `SessionRecoveryService.recover_all()`
- 使用 `asyncio.create_task()` 异步执行，不阻塞启动
- 传入 `self._chat_manager` 用于验证 ChatSession 存在性

**验收**: MaiBot 重启 → 日志中出现 `会话恢复完成: N 个会话, M 个智能体`

---

## 阶段三：日志查询 API

### 任务 3.1：后端日志查询 API

**文件**: `src/webui/routers/agent.py`（修改）

**内容**:
- 新增 `GET /api/webui/agent/autonomy-logs` 端点
- 请求参数: agent_id, event_type, start_time, end_time, page, page_size
- 实现方式: 读取日志文件，按 `[Autonomy:` 前缀过滤，解析为结构化数据
- 限制最大读取行数（5000 行）
- 响应格式: `{ items: [...], total, page, page_size }`

**验收**: `curl /api/webui/agent/autonomy-logs?agent_id=himeko` → 返回姬子的自主性日志

### 任务 3.2：前端 API 层

**文件**: `dashboard/src/lib/agent-api.ts`（修改）

**内容**:
- 新增 `getAutonomyLogs(params)` 函数
- 调用 `GET /api/webui/agent/autonomy-logs`
- 支持筛选参数

**验收**: 前端调用 `getAutonomyLogs({ agent_id: "himeko" })` → 返回数据

---

## 阶段四：WebUI 日志面板

### 任务 4.1：创建 AutonomyLogPanel 组件

**文件**: `dashboard/src/routes/agent/components/AutonomyLogPanel.tsx`（新建）

**内容**:
- 使用 `useDataList` hook 管理分页/筛选
- 智能体筛选下拉框
- 事件类型筛选标签
- 日志列表（带颜色标记：thinking=蓝、expression=绿、interjection=橙、orchestration=紫）
- 时间戳显示
- 空状态提示

**验收**: 打开面板 → 显示智能体活动日志，可按智能体/事件类型筛选

### 任务 4.2：集成到智能体页面

**文件**: `dashboard/src/routes/agent/` 相关路由文件（修改）

**内容**:
- 在智能体管理页面添加"活动日志"标签页
- 引入 AutonomyLogPanel 组件

**验收**: 智能体页面 → 切换到"活动日志"标签 → 显示日志面板

### 任务 4.3：i18n 三语

**文件**: `dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`（修改）

**内容**:
- 添加日志面板相关 i18n 键
- 中文/英文/日文三语同步

**验收**: 切换语言 → 日志面板标题、筛选标签等跟随切换

---

## 阶段五：__init__.py 导出与验证

### 任务 5.1：更新模块导出

**文件**: `src/maisaka/agent_autonomy/__init__.py`（修改）

**内容**:
- 导出 `AutonomyLogger`、`AutonomyEventType`、`AutonomyEventSubscriber`
- 导出 `SessionRecoveryService`

**验收**: `from src.maisaka.agent_autonomy import AutonomyLogger` 不报错

### 任务 5.2：端到端验证

**内容**:
- Docker 环境启动 MaiBot
- `docker logs maim-bot-core 2>&1 | grep "\[Autonomy:"` → 能看到智能体活动
- 重启容器 → 日志中出现"会话恢复完成"
- WebUI 日志面板能正常展示和筛选

**验收**: 以上三项均通过