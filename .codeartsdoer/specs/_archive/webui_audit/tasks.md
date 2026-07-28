# WebUI 清算审计 — 编码任务列表

## 1. 失效引用清除（P1：运行时报错修复）

### 1.1 移除 idle_backoff_modifier 前端引用

- [ ] 从 `dashboard/src/lib/agent-api.ts:31` 的 `AgentConfigInfo` 接口删除 `idle_backoff_modifier: number` 字段
- [ ] 从 `dashboard/src/routes/agent/components/inner-world/CollapsedParameters.tsx:8` 的 props 删除 `idleBackoffModifier: number`，删除 L15 解构，删除 L34-35 退避系数展示行
- [ ] 从 `dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx:205` 删除 `idleBackoffModifier={agent.idle_backoff_modifier}` 传参
- [ ] 从 `dashboard/src/routes/emotion-monitor/index.tsx:489-492` 删除退避系数展示列，将 `grid-cols-3` 改为 `grid-cols-2`
- [ ] 从 4 个 i18n 文件中移除 `idleBackoffModifier` 和 `backoffModifier` 翻译键：`zh.json`、`en.json`、`ja.json`、`ko.json`
- [ ] 验收：全局搜索 `idle_backoff_modifier` / `idleBackoffModifier` / `backoffModifier` 无残留；智能体管理页面和情绪监控页面正常渲染，无 undefined/NaN

### 1.2 移除 TimingGate 和死事件类型定义

- [ ] 从 `dashboard/src/lib/maisaka-monitor-client.ts` 删除 6 个死事件接口：`TimingGateResultEvent`（L118）、`PlannerRequestEvent`（L131）、`PlannerResponseEvent`（L140）、`ToolExecutionEvent`（L152）、`ReplierRequestEvent`（L223）、`ReplierResponseEvent`（L232）
- [ ] 从 `dashboard/src/lib/maisaka-monitor-client.ts` 删除 `MaisakaTimingGateBlock` 接口（L179）
- [ ] 将 `PlannerFinalizedEvent.timing_gate` 标记为可选（`timing_gate?: MaisakaTimingGateBlock | null`），保留用于历史数据兼容
- [ ] 从 `MaisakaMonitorEvent` 联合类型删除 6 个死事件分支：`timing_gate.result`、`planner.request`、`planner.response`、`tool.execution`、`replier.request`、`replier.response`
- [ ] 验收：`MaisakaMonitorEvent` 仅包含活跃事件（session.start / stage.status / stage.removed / stage.snapshot / message.ingested / message.sent / message.updated / planner.finalized）；TypeScript 编译无错误

### 1.3 清理 maisaka-monitor.tsx 死事件渲染

- [ ] 删除 `TimingGateCard` 组件（L557 起）
- [ ] 删除 `PlannerResponseCard` 组件（L681 起）
- [ ] 删除 `ToolExecutionCard` 组件（L996 起）
- [ ] 删除 `ReplierResponseCard` 组件（L1085 起）
- [ ] 从 `TimelineEventRenderer` switch 删除 4 个死分支：`timing_gate.result`、`planner.response`、`tool.execution`、`replier.response`
- [ ] 从 `PlannerFinalizedCard` 删除 `timing_gate?.result?.action === 'no_action'` 检查（L1152-1153）
- [ ] 删除时间线渲染中的 `noReplyTimingGateCycles` 逻辑（L1325-1331、L1355-1357）
- [ ] 清理 import 中已删除类型的引用（`PlannerResponseEvent`、`ReplierResponseEvent`、`TimingGateResultEvent`、`ToolExecutionEvent`）
- [ ] 验收：MaiSaka 监控页面正常渲染；时间线仅展示活跃事件；无 TypeScript 编译错误

## 2. 过时展示更新（P2：概念适配与死页面清理）

### 2.1 推理过程页面 STAGE_LABELS 适配

- [ ] 确认 ThinkingOrgan 产生的日志目录名（检查 `src/core/agent_autonomy/` 中 ThinkingOrgan 日志输出路径），确定默认 stage 参数是否需从 `'planner'` 变更
- [ ] 在 `dashboard/src/routes/reasoning-process.tsx:82-98` 的 `STAGE_LABELS` 中新增 ThinkingOrgan 相关 stage 标签：`thinking_organ: '思维管道'`、`tool_loop: '工具循环'`，及其他根据实际日志目录名补充的标签
- [ ] 保留 `timing_gate: '时机判断'` 用于历史数据查看
- [ ] 评估 `CORE_STAGE_NAMES`（L76）是否需新增 `'thinking_organ'`
- [ ] 验收：新架构产生的推理日志在推理过程页面正确展示中文标签；旧日志仍可查看

### 2.2 移除 planner-monitor / replier-monitor 死页面和 planner-api.ts

- [ ] 删除 `dashboard/src/lib/planner-api.ts`（全部 API 调用 `/api/planner/*` 和 `/api/replier/*` 返回 404，仅被两个死组件引用）
- [ ] 删除 `dashboard/src/routes/monitor/planner-monitor.tsx`（未被任何组件导入的死组件）
- [ ] 删除 `dashboard/src/routes/monitor/replier-monitor.tsx`（未被任何组件导入的死组件）
- [ ] 将 `dashboard/src/router.tsx:227-231` 的 `/planner-monitor` 路由重命名为 `/maisaka-monitor`，更新变量名 `plannerMonitorRoute` → `maisakaMonitorRoute`，同步更新 L418 路由树引用
- [ ] 将 `dashboard/src/components/layout/constants.ts:63` 的导航路径从 `/planner-monitor` 改为 `/maisaka-monitor`
- [ ] 更新 `dashboard/src/components/layout/Layout.tsx:50` 中 `/planner-monitor` 的硬编码路径为 `/maisaka-monitor`
- [ ] 验收：侧边栏"MaiSaka 监控"入口指向 `/maisaka-monitor`；旧路径 `/planner-monitor` 不再注册；MaiSaka 实时监控页面正常工作；`planner-api.ts` 和两个死组件文件已删除

## 3. 缺失界面补充（P3：功能增强）

### 3.1 记忆迁移状态面板

- [ ] 新增 `dashboard/src/lib/migration-api.ts`，实现迁移状态 API 客户端：
  - `getMigrationStates()` → `MigrationStateItem[]`，调用 `GET /api/webui/agents/migration/states`
  - `advanceMigration(pluginId: string)` → `MigrationAdvanceResult`，调用 `POST /api/webui/agents/migration/{plugin_id}/advance`
  - 定义 `MigrationStateItem` 和 `MigrationAdvanceResult` 接口，与后端 `MigrationStateResponse`/`MigrationAdvanceResponse` 对齐
- [ ] 新增 `dashboard/src/routes/agent/components/inner-world/MigrationPanel.tsx`，实现迁移状态面板组件：
  - 展示各插件的迁移阶段（5 阶段状态机可视化：LEGACY_ONLY → DUAL_WRITE → DUAL_READ → DATA_MIGRATION → NEW_INDEPENDENT）
  - 提供"推进阶段"按钮（调用 advanceMigration，带确认对话框）
  - 使用 TanStack Query 管理数据获取和缓存失效
- [ ] 将 MigrationPanel 嵌入智能体管理页面的自主性面板区域
- [ ] 验收：记忆迁移面板可查看当前阶段和推进操作；advance 操作后阶段正确更新

### 3.2 后端 CohabitantInfo 补充 vitality_value

- [ ] 在 `src/webui/schemas/agent.py:83-88` 的 `CohabitantInfo` 新增 `vitality_value: float = 0.0` 字段
- [ ] 在 `src/webui/routers/agent.py:533` 构建 `CohabitantInfo` 时从 VitalityManager 获取 vitality_value：
  - 获取路径：`AgentOrchestrator.get_by_session(session_id)` → `orchestrator._vitality_manager.get_agent_vitality(agent_id)`
  - 如果 Orchestrator 不存在（session 未激活），vitality_value 默认为 0.0
- [ ] 前端 `dashboard/src/lib/agent-api.ts:58` 的 `CohabitantInfo.vitality_value` 从可选改为必填（`vitality_value: number`）
- [ ] 前端 `dashboard/src/lib/agent-api.ts:70` 的 `SessionAgentInfo.vitality_value` 从可选改为必填（`vitality_value: number`）
- [ ] 验收：ActiveSessions 组件的 VitalityBar 正常渲染，不再需要 `!= null` 判断

### 3.3 source_kind 展示

- [ ] 在 `dashboard/src/routes/monitor/maisaka-monitor.tsx` 的 `MessageSentCard` 组件中展示 `source_kind` 字段
- [ ] 添加 source_kind 中文标签映射：主回复 → 主回复、interjection → 插话、reminder → 提醒、plugin → 插件
- [ ] 验收：MaiSaka 监控页面的已发送消息事件可区分消息来源类型

## 4. 验证与回归测试

### 4.1 前端编译验证

- [ ] 运行前端构建（`npm run build`），确认无 TypeScript 编译错误
- [ ] 验收：构建产物无错误

### 4.2 页面功能回归

- [ ] 智能体管理页面：配置列表、内心世界面板、会话绑定、自主性操作均正常
- [ ] 情绪监控页面：情绪状态、行为参数（无退避系数）正常展示
- [ ] 关系概览页面：关系数据正常展示
- [ ] MaiSaka 监控页面（`/maisaka-monitor`）：时间线仅展示活跃事件，无死事件残留；source_kind 标签正确
- [ ] 推理过程页面：新旧日志均可查看，stage 标签正确
- [ ] 记忆迁移面板：可查看状态和推进操作
- [ ] 验收：所有页面功能正常，无运行时报错

### 4.3 数据契约对齐验证

- [ ] 前端 `AgentConfigInfo` 字段集合 ⊆ 后端 `AgentConfigResponse` 字段集合
- [ ] 前端 `MaisakaMonitorEvent` 事件类型 ⊆ 后端 `emit_*` 函数发射的事件类型
- [ ] 前端 `CohabitantInfo` / `SessionAgentInfo` 字段与后端 schema 一致（含 vitality_value）
- [ ] 验收：无前端访问后端不返回字段的情况
