# 一、需求与存量功能关系分析

## 1.1 需求功能与存量功能对比

### 1.1.1 已实现功能

| 需求功能 | 存量功能 | 代码位置 | 匹配度 |
|---------|---------|---------|--------|
| 智能体配置列表展示 | AgentConfigResponse 返回智能体配置 | 后端 `src/webui/schemas/agent.py:17` → 前端 `dashboard/src/lib/agent-api.ts:20` | 75% |
| 情绪状态监控 | EmotionStateResponse 返回情绪数据 | 后端 `src/webui/routers/agent.py:157` → 前端 `dashboard/src/routes/emotion-monitor/index.tsx` | 100% |
| 关系概览监控 | RelationshipSummaryResponse 返回关系数据 | 后端 `src/webui/routers/agent.py:186` → 前端 `dashboard/src/routes/relationship-monitor/` | 100% |
| 推理过程浏览 | ReasoningPromptFile 列表+详情+重放 | 后端 `src/webui/routers/reasoning_process.py` → 前端 `dashboard/src/lib/reasoning-process-api.ts` + `dashboard/src/routes/reasoning-process.tsx` | 75% |
| MaiSaka 实时监控 | WebSocket 订阅 maisaka_monitor 主题 | 后端 `src/maisaka/monitor/events.py` → 前端 `dashboard/src/lib/maisaka-monitor-client.ts` + `dashboard/src/routes/monitor/maisaka-monitor.tsx` | 50% |
| 智能体自主性 API | 活跃智能体/插话/发言权切换/生命力/状态互知 | 后端 `src/webui/routers/agent.py:580+` → 前端 `dashboard/src/lib/agent-api.ts:521+` | 100% |
| 记忆迁移状态 API | MigrationStateResponse + advance 接口 | 后端 `src/webui/routers/agent.py:827` → 前端 **未接入** | 50% |
| 消息发送 source_kind | MessageSentEvent 携带 source_kind 字段 | 后端 `src/maisaka/monitor/events.py:392` → 前端 `dashboard/src/lib/maisaka-monitor-client.ts:81` | 100% |
| 会话绑定管理 | SessionBinding CRUD + 批量绑定 | 后端 `src/webui/routers/agent.py:218+` → 前端 `dashboard/src/lib/agent-api.ts:142+` | 100% |
| 子智能体监控 | SubAgentRecordResponse + 统计 | 后端 `src/webui/routers/agent.py` → 前端 `dashboard/src/lib/agent-api.ts:216+` | 100% |

### 1.1.2 需要扩展的功能

| 需求功能 | 存量功能 | 差异说明 | 扩展方向 |
|---------|---------|---------|---------|
| AgentConfigInfo 前端类型对齐 | 前端 `AgentConfigInfo` 含 `idle_backoff_modifier`，后端 `AgentConfigResponse` 已无此字段 | 前端多一个已废弃字段，渲染时 `.toFixed(1)` 会抛 undefined 异常 | 前端类型移除 `idle_backoff_modifier`；后端无需改动 |
| CollapsedParameters 展示退避系数 | `CollapsedParameters.tsx` 接收 `idleBackoffModifier` 并展示 | 旧概念已不存在，展示无意义 | 移除 `idleBackoffModifier` prop，替换为生命力相关参数或直接移除该行 |
| 情绪监控展示退避系数 | `emotion-monitor/index.tsx:491` 展示 `×{selectedAgent.idle_backoff_modifier.toFixed(1)}` | 同上，渲染 undefined | 移除退避系数展示，替换为生命力值或移除该列 |
| TimingGate 事件处理 | 前端定义 `TimingGateResultEvent`/`MaisakaTimingGateBlock`，`maisaka-monitor.tsx` 渲染 `TimingGateCard` | 后端已不再发射 `timing_gate.result` 事件，前端代码为死代码 | 前端移除 `TimingGateResultEvent`/`MaisakaTimingGateBlock` 类型定义，移除 `TimingGateCard` 组件和渲染分支 |
| planner.finalized 事件中 timing_gate 字段 | 前端 `PlannerFinalizedEvent` 含 `timing_gate: MaisakaTimingGateBlock \| null` | 后端 `emit_planner_finalized` 不再填充 timing_gate 数据，该字段始终为 null | 前端将 `timing_gate` 标记为可选/废弃，PlannerFinalizedCard 中不再检查 timing_gate |
| planner.request / planner.response 事件 | 前端定义了 `PlannerRequestEvent`/`PlannerResponseEvent` 类型 | 后端 `events.py` 仅发射 `planner.finalized`，不再单独发射 `planner.request`/`planner.response` | 前端移除这两个事件类型定义，TimelineEventRenderer 移除对应分支 |
| replier.request / replier.response 事件 | 前端定义了 `ReplierRequestEvent`/`ReplierResponseEvent` | 后端不再单独发射这些事件（replyer 管道仍在，但监控事件已合并到 planner.finalized 的 tools 中） | 前端移除这两个事件类型定义，TimelineEventRenderer 移除对应分支 |
| tool.execution 事件 | 前端定义了 `ToolExecutionEvent` 类型和渲染分支 | 后端 `events.py` 无 `emit_tool_execution` 函数，该事件不再发射 | 前端移除 `ToolExecutionEvent` 类型定义和渲染分支 |
| 推理过程 stage 默认值 | `reasoning-process-api.ts:133` 默认 stage='planner' | ThinkingOrgan 产生的日志目录名需确认是否仍为 'planner' | 确认 ThinkingOrgan 日志目录名，如已变更则更新默认值 |
| STAGE_LABELS 适配 | `reasoning-process.tsx:82-98` 定义了 planner/replier/timing_gate 标签 | ThinkingOrgan 可能产生新的 stage 名称，需补充标签 | 新增 ThinkingOrgan 相关 stage 标签，保留旧标签用于历史数据 |
| CohabitantInfo/SessionAgentInfo 的 vitality_value | 前端定义为可选 `vitality_value?: number`，后端 `CohabitantInfo`/`SessionAgentInfo` 无此字段 | 前端多定义了后端不返回的字段 | 后端 CohabitantInfo 新增 vitality_value 字段（从 VitalityManager 获取），或前端移除该可选字段 |
| /api/planner 和 /api/replier 路由 | 前端 `planner-api.ts` 调用 `/api/planner/*` 和 `/api/replier/*` | 后端 `routes.py` 未注册这些路由（仅有 `/api/webui/reasoning-process/*`），调用必定 404 | 确认旧路由是否存在于其他注册点；若不存在，planner-monitor.tsx 和 replier-monitor.tsx 为死页面，需移除或重定向 |

### 1.1.3 需要新增的功能或接口

**记忆迁移状态前端面板**（后端 API 已存在）
- 输入：无（获取所有插件迁移状态）
- 输出：各插件迁移阶段、推进操作
- 核心逻辑：调用已有 `GET /agents/migration/states` 和 `POST /agents/migration/{plugin_id}/advance` API
- 依赖：后端 API 已存在（`src/webui/routers/agent.py:827`），仅需前端接入

**ThinkingOrgan 思考状态监控**（后端需新增）
- 输入：session_id（可选）
- 输出：ThinkingOrgan 当前思考状态（思考中/等待/空闲）、工具循环轮次、上下文注入信息
- 核心逻辑：从 Orchestrator 查询 ThinkingOrgan 状态
- 依赖：Orchestrator 实例、ThinkingOrgan 状态暴露接口

**Orchestrator 调度状态监控**（后端需新增）
- 输入：session_id
- 输出：当前调度决策（谁在思考、触发原因、调度路径：主回复/插话/提醒）
- 核心逻辑：从 Orchestrator 查询调度状态
- 依赖：Orchestrator 实例

**管家系统（Butler）插话决策监控**（后端需新增）
- 输入：session_id（可选）、时间范围
- 输出：管家三层过滤决策记录（规则过滤结果、管家LLM选择结果、角色LLM决策结果）
- 核心逻辑：从 Butler 查询最近的插话决策日志
- 依赖：Butler 决策日志持久化或内存查询接口

## 1.2 存量功能详细分析

### AgentConfigResponse（后端 schema）

**接口契约**：
- 入参：agent_id（路径参数）
- 出参：agent_id, display_name, personality, reply_style, is_default, color, emotion_baseline, emotion_decay_rate, relationship_growth_rate, talk_value_modifier, memory_focus_areas, internal_relationships, anti_mechanization_rules
- 注意：**不含** `idle_backoff_modifier`，后端 `_config_to_response()` 映射时也未写入此字段

**业务规则**：从 AgentConfig 字段映射，字段集合由 AgentConfig 数据类决定

**扩展点**：无，纯数据映射

**约束**：后端不返回 `idle_backoff_modifier`，前端访问此字段必得 undefined

### MaisakaMonitorClient（前端 WebSocket 客户端）

**接口契约**：
- 订阅 maisaka_monitor 主题，接收 14 种事件类型
- 当前定义了 `timing_gate.result`、`planner.request`、`planner.response`、`replier.request`、`replier.response`、`tool.execution` 六种后端不再发射的事件

**业务规则**：事件类型由后端 `events.py` 的 `emit_*` 函数决定

**扩展点**：新增事件类型只需在 `MaisakaMonitorEvent` 联合类型中添加

**约束**：
- 后端当前仅发射 7 种事件：`session.start`、`stage.status`、`stage.removed`、`message.ingested`、`message.sent`、`message.updated`、`planner.finalized`
- `planner.request`/`planner.response`/`replier.request`/`replier.response`/`timing_gate.result`/`tool.execution` 均不再发射

### planner-api.ts（前端 Planner/Replier 监控 API）

**接口契约**：
- 调用 `/api/planner/overview`、`/api/planner/stats`、`/api/planner/chats`、`/api/planner/chat/{id}/logs`、`/api/planner/log/{id}/{filename}`、`/api/planner/all-logs`
- 调用 `/api/replier/overview`、`/api/replier/chat/{id}/logs`、`/api/replier/log/{id}/{filename}`

**业务规则**：这些路由不在 `src/webui/routes.py` 中注册

**约束**：后端 WebUI 路由前缀为 `/api/webui`，这些 `/api/planner` 和 `/api/replier` 路由不在 WebUI 路由树中。需要确认是否有其他路由注册点（如独立 API 服务）。若不存在，planner-monitor.tsx 和 replier-monitor.tsx 为完全不可用的死页面。

### 推理过程页面（reasoning-process.tsx）

**接口契约**：
- 通过 `reasoning-process-api.ts` 调用 `/api/webui/reasoning-process/*` 系列接口
- 默认 stage='planner'，CORE_STAGE_NAMES=['planner', 'replyer']，REMOVED_STAGE_NAMES=['timing_gate']

**业务规则**：stage 名称与 ThinkingOrgan 日志目录名对应

**扩展点**：STAGE_LABELS 可扩展新 stage 标签

**约束**：ThinkingOrgan 迁移后日志目录名可能已变更，需确认

### 记忆迁移 API（后端已实现，前端未接入）

**接口契约**：
- `GET /agents/migration/states` → `List[MigrationStateResponse]`
- `POST /agents/migration/{plugin_id}/advance` → `MigrationAdvanceResponse`

**业务规则**：MigrationCoordinator 管理 5 阶段状态机

**扩展点**：前端可新增迁移状态面板

**约束**：前端无任何组件调用此 API

# 二、增量设计方案

## 2.1 实现模型

### 2.1.1 上下文视图

```
                    ┌──────────────────────────────────────────┐
                    │           WebUI 前端（React 19）          │
                    │                                          │
                    │  ┌─────────────┐  ┌──────────────────┐   │
                    │  │ 智能体管理   │  │ MaiSaka 监控     │   │
                    │  │ InnerWorld  │  │ maisaka-monitor  │   │
                    │  │ EmotionMon  │  │ planner-monitor  │   │
                    │  └──────┬──────┘  │ replier-monitor  │   │
                    │         │         └────────┬─────────┘   │
                    │  ┌──────┴──────┐  ┌────────┴─────────┐   │
                    │  │ agent-api   │  │ maisaka-monitor-  │   │
                    │  │ planner-api │  │ client (WS)       │   │
                    │  └──────┬──────┘  └────────┬─────────┘   │
                    └─────────┼─────────────────┼─────────────┘
                              │ HTTP            │ WebSocket
                              ▼                 ▼
                    ┌──────────────────────────────────────────┐
                    │        WebUI 后端（FastAPI）              │
                    │                                          │
                    │  /api/webui/agents/*                     │
                    │  /api/webui/reasoning-process/*          │
                    │  /api/planner/*  ← 未注册，404           │
                    │  /api/replier/*  ← 未注册，404           │
                    │  WebSocket: maisaka_monitor              │
                    └──────────────────────────────────────────┘
```

### 2.1.2 服务/组件总体架构

**设计决策 1：清算分三批执行，按严重程度排序**

理由：失效引用（idle_backoff_modifier、/api/planner 404）会导致运行时报错，优先级最高；过时展示（TimingGate 死代码）不影响运行但增加维护负担，优先级次之；缺失界面（迁移面板、管家监控）是功能增强，优先级最低。

**设计决策 2：planner-monitor 和 replier-monitor 直接移除**

理由：这两个页面调用的 `/api/planner/*` 和 `/api/replier/*` 路由在后端未注册，必定 404。标记"历史"后用户打开仍是报错页面，体验差。历史日志查看功能已由 `/api/webui/reasoning-process/*` 覆盖，无需保留死页面。移除方式：删除对应路由注册和导航入口，保留源文件供参考。

**设计决策 3：记忆迁移面板接入已有 API，不新增后端接口**

理由：后端 `GET /agents/migration/states` 和 `POST /agents/migration/{plugin_id}/advance` 已完整实现，前端仅需新增 API 客户端函数和面板组件。

**设计决策 4：ThinkingOrgan/Orchestrator/Butler 监控暂不新增后端接口**

理由：这些组件的内部状态目前没有暴露查询接口，新增需要修改核心模块代码，超出"清算"范围（spec 明确"不负责后端架构变更本身"）。当前通过已有的自主性 API（活跃智能体、插话事件、发言权变更、生命力、状态互知）间接覆盖部分监控需求。待后续专项迭代时再新增专属监控接口。

**组件关系**：

```
清算修复范围：

第1批（失效引用清除）
├── agent-api.ts: 移除 idle_backoff_modifier 字段
├── CollapsedParameters.tsx: 移除 idleBackoffModifier prop
├── InnerWorldView.tsx: 移除 idleBackoffModifier 传参
├── emotion-monitor/index.tsx: 移除退避系数展示
└── maisaka-monitor-client.ts: 移除 6 种死事件类型

第2批（过时展示更新）
├── maisaka-monitor.tsx: 移除 TimingGateCard 和 6 个死事件渲染分支
├── reasoning-process.tsx: STAGE_LABELS 新增 thinking_organ 标签
├── 移除 planner-monitor.tsx 和 replier-monitor.tsx 路由和导航入口
└── 移除 planner-api.ts（全部 API 调用 404）

第3批（缺失界面补充）
├── 新增 migration-api.ts: 迁移状态 API 客户端
├── 新增 MigrationPanel 组件: 迁移状态面板
└── agent-api.ts: 后端 CohabitantInfo 补充 vitality_value
```

### 2.1.3 实现设计文档

#### 第1批：失效引用清除

**1. 移除 idle_backoff_modifier**

修改清单：
- `dashboard/src/lib/agent-api.ts:31` — 从 `AgentConfigInfo` 接口删除 `idle_backoff_modifier: number`
- `dashboard/src/routes/agent/components/inner-world/CollapsedParameters.tsx:8` — 从 props 删除 `idleBackoffModifier: number`
- `dashboard/src/routes/agent/components/inner-world/CollapsedParameters.tsx:34-36` — 删除退避系数展示行
- `dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx:205` — 删除 `idleBackoffModifier={agent.idle_backoff_modifier}` 传参
- `dashboard/src/routes/emotion-monitor/index.tsx:489-492` — 删除退避系数展示列，将 3 列 grid 改为 2 列

**2. 移除 TimingGate 和死事件类型**

修改清单：
- `dashboard/src/lib/maisaka-monitor-client.ts:118-129` — 删除 `TimingGateResultEvent` 接口
- `dashboard/src/lib/maisaka-monitor-client.ts:131-138` — 删除 `PlannerRequestEvent` 接口
- `dashboard/src/lib/maisaka-monitor-client.ts:140-150` — 删除 `PlannerResponseEvent` 接口
- `dashboard/src/lib/maisaka-monitor-client.ts:152-161` — 删除 `ToolExecutionEvent` 接口
- `dashboard/src/lib/maisaka-monitor-client.ts:223-241` — 删除 `ReplierRequestEvent` 和 `ReplierResponseEvent` 接口
- `dashboard/src/lib/maisaka-monitor-client.ts:179-191` — 删除 `MaisakaTimingGateBlock` 接口
- `dashboard/src/lib/maisaka-monitor-client.ts:253` — 从 `MaisakaMonitorEvent` 联合类型删除 `timing_gate.result` 分支
- `dashboard/src/lib/maisaka-monitor-client.ts:254-255` — 删除 `planner.request` 和 `planner.response` 分支
- `dashboard/src/lib/maisaka-monitor-client.ts:257` — 删除 `tool.execution` 分支
- `dashboard/src/lib/maisaka-monitor-client.ts:258-259` — 删除 `replier.request` 和 `replier.response` 分支
- `dashboard/src/lib/maisaka-monitor-client.ts:210` — `PlannerFinalizedEvent.timing_gate` 标记为可选（保留用于历史数据兼容）

**3. maisaka-monitor.tsx 清理**

修改清单：
- 删除 `TimingGateCard` 组件（约 30 行）
- 删除 `PlannerResponseCard` 组件（如存在）
- 删除 `ReplierResponseCard` 组件（如存在）
- 删除 `ToolExecutionCard` 组件（如存在）
- `TimelineEventRenderer` switch 中删除 `timing_gate.result`、`planner.response`、`tool.execution`、`replier.response` 分支
- `PlannerFinalizedCard` 中删除 `timing_gate?.result?.action === 'no_action'` 检查

#### 第2批：过时展示更新

**1. STAGE_LABELS 适配**

修改清单：
- `dashboard/src/routes/reasoning-process.tsx:82-98` — 新增 ThinkingOrgan 相关 stage 标签：
  - `thinking_organ: '思维管道'`
  - `tool_loop: '工具循环'`
  - 其他 ThinkingOrgan 产生的 stage 名称（需确认实际日志目录名）
- 保留 `timing_gate: '时机判断'` 用于历史数据查看
- `CORE_STAGE_NAMES` 考虑新增 `'thinking_organ'`（如 ThinkingOrgan 日志目录名已变更）

**2. planner-monitor 和 replier-monitor 标记**

修改清单：
- `dashboard/src/routes/monitor/planner-monitor.tsx` — 在页面顶部添加提示："此页面查看历史规划器日志，当前架构已切换为 ThinkingOrgan"
- `dashboard/src/routes/monitor/replier-monitor.tsx` — 在页面顶部添加提示："此页面查看历史回复器日志"
- 两个页面的加载失败状态已有 TanStack Query 的错误处理，无需额外修改

**3. 路由路径评估**

`/planner-monitor` 路径暂不重命名。理由：
- 用户可能已收藏此路径
- 重命名需同步修改 `router.tsx`、`Layout.tsx`、`constants.ts`
- 当前路径名不影响功能，低优先级

#### 第3批：缺失界面补充

**1. 记忆迁移状态面板**

新增文件：
- `dashboard/src/lib/migration-api.ts` — 迁移状态 API 客户端
- `dashboard/src/routes/agent/components/inner-world/MigrationPanel.tsx` — 迁移状态面板组件

API 客户端设计：
```
getMigrationStates() → MigrationStateItem[]
advanceMigration(pluginId: string) → MigrationAdvanceResult
```

面板设计：
- 展示各插件的迁移阶段（5 阶段状态机可视化）
- 提供"推进阶段"按钮（调用 advance API）
- 嵌入到智能体管理页面的自主性面板区域

**2. 后端 CohabitantInfo 补充 vitality_value**

修改清单：
- `src/webui/schemas/agent.py:83-88` — `CohabitantInfo` 新增 `vitality_value: float = 0.0`
- `src/webui/routers/agent.py` — 构建 `CohabitantInfo` 时从 VitalityManager 获取 vitality_value

VitalityManager 获取路径：
- VitalityManager 是 per-session 的，由 Orchestrator 持有
- router 层通过 `AgentOrchestrator.get_by_session(session_id)` 获取 Orchestrator 实例
- 再通过 `orchestrator._vitality_manager.get_agent_vitality(agent_id)` 获取具体智能体的 vitality_value
- 如果 Orchestrator 不存在（session 未激活），vitality_value 默认为 0.0

**3. source_kind 展示**

当前 `MessageSentEvent` 已携带 `source_kind` 字段，前端 `maisaka-monitor.tsx` 的 `MessageSentCard` 需确认是否展示此字段。如未展示，添加 source_kind 标签（主回复/插话/提醒/插件）。

## 2.2 接口设计

### 2.2.1 总体设计

本次清算的接口变更分为两类：
1. **前端类型清理**：移除后端不再返回的字段，不改变 API 调用方式
2. **新增 API 客户端**：为已有后端接口补充前端调用函数

接口稳定性等级：
- 已有接口（AgentConfigResponse 等）：**稳定**，不破坏性变更
- 新增迁移 API 客户端：**稳定**，后端接口已存在
- MaiSaka 监控事件类型：**实验性**，后端事件发射可能随架构演进继续变化

### 2.2.2 接口清单

#### 前端类型变更

| 接口/类型 | 变更类型 | 说明 |
|----------|---------|------|
| `AgentConfigInfo` | 字段删除 | 移除 `idle_backoff_modifier` |
| `CollapsedParametersProps` | 字段删除 | 移除 `idleBackoffModifier` |
| `CohabitantInfo`（前端） | 字段对齐 | `vitality_value` 从可选改为必填（后端补充后） |
| `TimingGateResultEvent` | 类型删除 | 后端不再发射此事件 |
| `PlannerRequestEvent` | 类型删除 | 后端不再发射此事件 |
| `PlannerResponseEvent` | 类型删除 | 后端不再发射此事件 |
| `ToolExecutionEvent` | 类型删除 | 后端不再发射此事件 |
| `ReplierRequestEvent` | 类型删除 | 后端不再发射此事件 |
| `ReplierResponseEvent` | 类型删除 | 后端不再发射此事件 |
| `MaisakaTimingGateBlock` | 类型删除 | timing_gate 概念已移除 |
| `PlannerFinalizedEvent.timing_gate` | 字段标记可选 | 保留用于历史数据兼容 |
| `MaisakaMonitorEvent` | 联合类型缩减 | 移除 6 个死事件分支 |

#### 新增前端 API 客户端

**migration-api.ts**

```typescript
interface MigrationStateItem {
  plugin_id: string
  plugin_name: string
  current_phase: string
  previous_phase: string
  last_updated: number
  notes: string
}

interface MigrationAdvanceResult {
  success: boolean
  plugin_id: string
  current_phase: string
  previous_phase: string
}

function getMigrationStates(): Promise<MigrationStateItem[]>
function advanceMigration(pluginId: string): Promise<MigrationAdvanceResult>
```

- 业务说明：查询和推进记忆系统范式迁移的 5 阶段状态机
- 前置条件：用户已认证
- 后置条件：advance 调用后迁移阶段前进一步
- 异常映射：404 → "未找到插件"；500 → "推进迁移阶段失败"
- 调用示例：`const states = await getMigrationStates()`

#### 后端 Schema 变更

| Schema | 变更类型 | 说明 |
|--------|---------|------|
| `CohabitantInfo` | 字段新增 | 新增 `vitality_value: float = 0.0` |

## 2.3 数据模型

### 2.3.1 设计目标

- 前端类型定义与后端 schema 严格对齐，消除 undefined 渲染风险
- 保留历史数据兼容性（timing_gate 标签和 PlannerFinalizedEvent.timing_gate 可选字段）
- 新增迁移状态面板的数据模型

### 2.3.2 模型实现

#### AgentConfigInfo（前端，修正后）

```
AgentConfigInfo
  ├── agent_id: string
  ├── display_name: string
  ├── personality: string
  ├── reply_style: string
  ├── is_default: boolean
  ├── color: string
  ├── emotion_baseline: Record<string, number>
  ├── emotion_decay_rate: number
  ├── relationship_growth_rate: number
  ├── talk_value_modifier: number
  ├── memory_focus_areas: string[]
  ├── internal_relationships: InternalRelationship[]
  └── anti_mechanization_rules: string[]
  
  [已删除] idle_backoff_modifier: number
```

#### MaisakaMonitorEvent（前端，修正后）

```
MaisakaMonitorEvent（7 种活跃事件）
  ├── session.start → SessionStartEvent
  ├── stage.status → StageStatusEvent
  ├── stage.removed → StageRemovedEvent
  ├── stage.snapshot → StageSnapshotEvent
  ├── message.ingested → MessageIngestedEvent
  ├── message.sent → MessageSentEvent
  ├── message.updated → MessageUpdatedEvent
  └── planner.finalized → PlannerFinalizedEvent
  
  [已删除] timing_gate.result, planner.request, planner.response,
           tool.execution, replier.request, replier.response
```

#### MigrationStateItem（前端，新增）

```
MigrationStateItem
  ├── plugin_id: string
  ├── plugin_name: string
  ├── current_phase: string       ← LEGACY_ONLY/DUAL_WRITE/DUAL_READ/DATA_MIGRATION/NEW_INDEPENDENT
  ├── previous_phase: string
  ├── last_updated: number
  └── notes: string
```

#### CohabitantInfo（后端，扩展后）

```
CohabitantInfo
  ├── agent_id: string
  ├── display_name: string
  ├── is_primary: boolean
  ├── status: string
  └── vitality_value: float       ← 新增，从 VitalityManager 获取
```
