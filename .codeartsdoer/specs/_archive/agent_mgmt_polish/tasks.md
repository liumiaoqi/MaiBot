# 智能体指挥中心 — 后续打磨编码任务

> 基于已完成的全量开发（Phase 1~4），对智能体管理页进行功能补全、交互修复和体验打磨。
> 任务优先级：功能缺失 > 交互缺陷 > 体验瑕疵

---

## 1. ActiveSessions 绑定/解绑逻辑补全

> 当前状态：`ActiveSessions` 组件的 `onUnbind` 和 `onBindClick` 回调均为空函数 `() => {}`，绑定/解绑按钮无法工作。

### 1.1 创建 UnbindConfirmDialog 解绑确认对话框

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `UnbindConfirmDialog.tsx`，实现解绑二次确认对话框。使用 Radix `AlertDialog` 组件，展示即将解绑的会话名称（`sessionName`）。Props：`{ open: boolean; onOpenChange: (open: boolean) => void; onConfirm: () => void; sessionName: string }`。确认按钮使用 `destructive` 变体。使用 i18n 翻译键 `agent.activeSessions.unbindConfirm`。
- **验收标准**：点击解绑按钮后弹出确认对话框，展示会话名称，确认后触发 `onConfirm`，取消后关闭对话框。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/UnbindConfirmDialog.tsx`（新建）
- **依赖**：无

### 1.2 创建 BindSessionDialog 绑定会话选择对话框

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `BindSessionDialog.tsx`，实现绑定会话选择对话框。使用 Radix `Dialog` 组件。内部使用 `useQuery` 调用 `getChatStreams()` 获取所有可用聊天流，以 `display_name` 展示（群名称或"xxx的私聊"），而非 `session_id`。加载中显示骨架屏，加载失败显示"加载失败"提示和重试按钮。已绑定当前智能体的会话在列表中标注"已绑定"。Props：`{ open: boolean; onOpenChange: (open: boolean) => void; onSelect: (sessionId: string) => void; agentId: string; boundSessionIds: string[] }`。使用 i18n 翻译键 `agent.activeSessions.bindSession`、`agent.activeSessions.loadFailed`、`agent.activeSessions.currentStatus`。
- **验收标准**：打开对话框后展示聊天流实际名称列表，加载失败显示错误提示+重试，已绑定会话有标注，选择后触发 `onSelect`。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/BindSessionDialog.tsx`（新建），`dashboard/src/lib/chat-management-api.ts`（已有 `getChatStreams`）
- **依赖**：无

### 1.3 在 InnerWorldView 中实现绑定/解绑状态机

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`，实现完整的绑定/解绑状态机。新增内部状态：`unbindConfirmOpen`、`pendingUnbindSessionId`、`bindDialogOpen`。新增 `useMutation` 调用 `unbindSessionAgent`，`onSuccess` 时 `invalidateQueries(['agents', 'sessions', agentId])` 刷新会话列表。新增 `useMutation` 调用 `bindSessionAgent`，`onSuccess` 时同样刷新。`isUnbinding` 在任一 mutation 执行时为 true。错误通过 `toast.error()` 反馈，使用 i18n 翻译键 `agent.activeSessions.unbindFailed` / `agent.activeSessions.bindFailed`。将 `ActiveSessions` 的 `onUnbind` 改为打开确认对话框，`onBindClick` 改为打开绑定对话框。渲染 `UnbindConfirmDialog` 和 `BindSessionDialog`。
- **验收标准**：点击解绑按钮→弹出确认对话框→确认后调用解绑 API→成功后刷新列表，失败显示 toast；点击绑定按钮→弹出会话选择对话框→选择后调用绑定 API→成功后刷新列表，失败显示 toast；操作执行中所有按钮禁用。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`（修改），`dashboard/src/lib/agent-api.ts`（已有 `bindSessionAgent`/`unbindSessionAgent`）
- **依赖**：1.1, 1.2

### 1.4 新增 ActiveSessions 相关 i18n 翻译键

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.activeSessions` 命名空间下新增翻译键：`unbindConfirm`（确认解绑？）、`unbindFailed`（解除绑定失败）、`bindFailed`（绑定失败）、`loadFailed`（加载失败）、`currentStatus`（当前状态：已绑定）、`confirm`（确认）、`cancel`（取消）。同步至 `en.json`、`ja.json`、`ko.json`。
- **验收标准**：所有新增翻译键在4种语言中完整对齐，切换语言后文案正确显示。
- **涉及文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`、`ko.json`
- **依赖**：无

---

## 2. DeepMonitorLink SPA 导航修复

> 当前状态：`DeepMonitorLink` 使用 `<a href>` 导致整页刷新，违反 SPA 导航原则。

### 2.1 替换 DeepMonitorLink 为 SPA 路由导航

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/DeepMonitorLink.tsx`，将 `<a href={url}>` 替换为 `@tanstack/react-router` 的 `Link` 组件。导入 `Link` from `@tanstack/react-router`，替换 `<a>` 为 `<Link to={route} search={{ agent: agentId }}>`。保持现有样式和图标不变。删除 `TARGET_ROUTES` 常量中的 URL 拼接逻辑，改为直接使用路由路径。
- **验收标准**：点击"深入观测"链接后，浏览器 Network 面板不出现 HTML 文档请求，仅发生 SPA 路由切换，URL 包含 `?agent=xxx` 参数。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/DeepMonitorLink.tsx`（修改）
- **依赖**：无

---

## 3. GroupStatsBar i18n 修复

> 当前状态：`GroupStatsBar` 中 `"个生命体"`、`"个活跃"`、`"条纽带"`、`"均温"` 均为硬编码中文，不通过 i18n。

### 3.1 将 GroupStatsBar 文案迁移至 i18n

- [ ] 修改 `dashboard/src/routes/agent/components/global-situation/GroupStatsBar.tsx`，引入 `useTranslation`，将4项硬编码文案替换为 i18n 翻译键：`agent.globalSituation.stats.totalAgents`（`{{count}} 个生命体`）、`agent.globalSituation.stats.activeAgents`（`{{count}} 个活跃`）、`agent.globalSituation.stats.totalRelationships`（`{{count}} 条纽带`）、`agent.globalSituation.stats.avgScore`（`均温 {{score}}`）。使用 `t()` 的插值功能传入 `count` 和 `score`。
- **验收标准**：统计条文案通过 i18n 翻译键渲染，切换至英文后文案正确显示英文。
- **涉及文件**：`dashboard/src/routes/agent/components/global-situation/GroupStatsBar.tsx`（修改）
- **依赖**：3.2

### 3.2 新增 GroupStatsBar i18n 翻译键

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.globalSituation.stats` 命名空间下新增翻译键：`totalAgents`、`activeAgents`、`totalRelationships`、`avgScore`。同步至 `en.json`、`ja.json`、`ko.json`。
- **验收标准**：4种语言翻译键完整对齐，统计条切换语言后文案正确。
- **涉及文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`、`ko.json`
- **依赖**：无

---

## 4. 星图交互浮层接入

> 当前状态：`NodeDetailPopover` 和 `RelationshipTooltip` 组件已创建但未在 `AgentConstellation` 中使用，节点点击和连线悬停无浮层显示。

### 4.1 在 AgentConstellation 中增加选中/悬停状态管理

- [ ] 修改 `dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`，新增内部状态 `selectedNodeId: string | null` 和 `hoveredEdgeId: string | null`。实现 `onNodeClick` 时设置 `selectedNodeId`，`onPaneClick` 时清除 `selectedNodeId` 和 `hoveredEdgeId`。实现边的 `onMouseEnter` 时设置 `hoveredEdgeId`，`onMouseLeave` 时清除 `hoveredEdgeId`。扩展 Props 接口，新增 `emotions`、`sessionCounts`、`agents` 三个属性，用于浮层数据获取。
- **验收标准**：单击节点时 `selectedNodeId` 更新，点击空白区域时清除，悬停连线时 `hoveredEdgeId` 更新，鼠标移出时清除。
- **涉及文件**：`dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`（修改）
- **依赖**：无

### 4.2 实现节点选中高亮逻辑

- [ ] 修改 `dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`，当 `selectedNodeId` 存在时，根据选中节点计算高亮效果：选中节点及其关联边的 `style.opacity` 设为 1，其余边设为 0.2；选中节点及其关联节点的 `style.opacity` 设为 1，其余节点设为 0.4。在 `useMemo` 中根据 `selectedNodeId` 派生 `highlightedNodes` 和 `highlightedEdges`。
- **验收标准**：选中节点后，该节点及其关系连线高亮，其余节点和连线变暗；取消选中后恢复。
- **涉及文件**：`dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`（修改）
- **依赖**：4.1

### 4.3 接入 NodeDetailPopover 节点详情浮层

- [ ] 修改 `dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`，当 `selectedNodeId` 存在时渲染 `NodeDetailPopover` 组件。浮层定位基于选中节点的 ReactFlow 坐标（使用 `useReactFlow().flowToScreenPosition` 或节点 `position` + `viewport` 计算）。传入该节点的 `ConstellationNodeData`、对应的 `emotion` 和 `sessionCount` 数据。点击星图空白区域时关闭浮层。节点浮层数据不完整时，缺失部分显示 i18n 翻译键 `agent.constellation.dataIncomplete`（"暂不可感知"）。
- **验收标准**：单击节点时在节点旁显示浮层，展示情绪脉动和活跃节奏；点击空白区域关闭浮层；数据不完整时显示"暂不可感知"。
- **涉及文件**：`dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`（修改），`dashboard/src/routes/agent/components/constellation/NodeDetailPopover.tsx`（已有）
- **依赖**：4.1, 4.2

### 4.4 接入 RelationshipTooltip 关系悬停浮层

- [ ] 修改 `dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`，当 `hoveredEdgeId` 存在时渲染 `RelationshipTooltip` 组件。浮层跟随鼠标位置定位（使用 `onMouseMove` 事件获取坐标）。传入该边的 `ConstellationEdgeData`。鼠标移出连线时关闭浮层。浮层展示关系类型、态度描述和互动风格，使用语义化描述（禁止原始 `mention_tendency` 数值）。
- **验收标准**：悬停连线时在鼠标旁显示关系浮层，展示关系类型、态度、互动风格和紧密程度描述；鼠标移出时关闭。
- **涉及文件**：`dashboard/src/routes/agent/components/constellation/AgentConstellation.tsx`（修改），`dashboard/src/routes/agent/components/constellation/RelationshipTooltip.tsx`（已有）
- **依赖**：4.1

### 4.5 更新 CommandCenterLayout 传递浮层所需数据

- [ ] 修改 `dashboard/src/routes/agent/components/CommandCenterLayout.tsx`，在渲染 `AgentConstellation` 时传入新增的 `emotions`、`sessionCounts`、`agents` props，使星图浮层能获取所需数据。
- **验收标准**：`AgentConstellation` 接收到完整的 `emotions`、`sessionCounts`、`agents` 数据，浮层正常展示。
- **涉及文件**：`dashboard/src/routes/agent/components/CommandCenterLayout.tsx`（修改）
- **依赖**：4.1

### 4.6 新增星图交互相关 i18n 翻译键

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.constellation` 命名空间下新增翻译键：`dataIncomplete`（暂不可感知）、`legend.active`（活跃）、`legend.quiet`（安静）、`legend.dormant`（沉睡）。同步至 `en.json`、`ja.json`、`ko.json`。
- **验收标准**：4种语言翻译键完整对齐。
- **涉及文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`、`ko.json`
- **依赖**：无

---

## 5. 关系网络内部关系可视化升级

> 当前状态：`RelationshipNetwork` 中内部关系以纯文本列表展示（颜色圆点 + 目标ID + 关系类型 + 态度），需求要求以小型力导向图展示。

### 5.1 创建 InternalRelationshipGraph 内部关系网络图组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `InternalRelationshipGraph.tsx`，实现小型力导向图组件。基于 `reactflow` + `dagre` 实现，复用 `AgentConstellation` 的 dagre 布局逻辑。节点为智能体头像（主题色圆形+首字，统一 36px），连线颜色映射关系类型（复用 `REL_TYPE_COLORS`）。悬停浮层展示关系类型、态度、互动风格（语义化描述，禁止原始 `mention_tendency`）。使用 `ErrorBoundary` 包裹，渲染异常时降级为纯文本列表。Props：`{ agentId: string; internalRelationships: InternalRelationship[]; agents: AgentConfigInfo[] }`。
- **验收标准**：有内部关系数据时展示小型力导向图，节点为头像，连线颜色反映关系类型，悬停浮层语义化；渲染异常时降级为文本列表。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/InternalRelationshipGraph.tsx`（新建）
- **依赖**：无

### 5.2 在 RelationshipNetwork 中集成 InternalRelationshipGraph

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/RelationshipNetwork.tsx`，将内部关系区域从纯文本列表替换为 `InternalRelationshipGraph` 组件。当 `internalRelationships` 为空时不展示网络图区域（仅展示等级分布和排行）。需要从 `useBatchAgentData` 获取 `agents` 数据，通过 props 传递给 `InternalRelationshipGraph`。保留纯文本列表作为 `ErrorBoundary` 降级内容。
- **验收标准**：有内部关系时展示力导向图而非文本列表；无内部关系时不展示网络图区域；渲染异常时降级为文本列表。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/RelationshipNetwork.tsx`（修改），`dashboard/src/routes/agent/components/inner-world/InternalRelationshipGraph.tsx`（5.1 新建）
- **依赖**：5.1

### 5.3 更新 InnerWorldView 传递 agents 数据给 RelationshipNetwork

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`，在渲染 `RelationshipNetwork` 时传入 `agents` 数据（从 `useBatchAgentData` 获取），使内部关系网络图能获取目标智能体的配置信息（头像颜色、显示名称等）。
- **验收标准**：`RelationshipNetwork` 接收到 `agents` 数据，内部关系网络图节点展示正确的头像和名称。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`（修改）
- **依赖**：5.2

---

## 6. 动画与布局微调

> 当前状态：多个组件的动画参数和布局存在体验瑕疵。

### 6.1 EmotionPulse 脉动幅度上限约束

- [ ] 修改 `dashboard/src/routes/agent/components/EmotionPulse.tsx`，在 `scaleRange` 计算后添加 `Math.min(scaleRange, 1.2)` 上限约束。将 `const scaleRange = 1.0 + intensity / 200` 改为 `const scaleRange = Math.min(1.0 + intensity / 200, 1.2)`。
- **验收标准**：智能体主导情绪强度为 100 时，脉动 scale 不超过 1.2，动画自然不突兀。
- **涉及文件**：`dashboard/src/routes/agent/components/EmotionPulse.tsx`（修改）
- **依赖**：无

### 6.2 ActivityRhythmIndicator 沉睡状态修复

- [ ] 修改 `dashboard/src/routes/agent/components/ActivityRhythmIndicator.tsx`，将沉睡状态从 `opacity: 0.6` 固定值改为 `opacity: 1.0`、灰色、无动画。修改沉睡分支的 spring 配置：`from: { opacity: 1.0 }`、`to: { opacity: 1.0 }`、`immediate: true`。确保沉睡状态显示固定不透明的灰色圆点，无呼吸灯效果。
- **验收标准**：智能体处于"沉睡"状态时，活跃节奏指示器显示不透明的灰色圆点，无动画。
- **涉及文件**：`dashboard/src/routes/agent/components/ActivityRhythmIndicator.tsx`（修改）
- **依赖**：无

### 6.3 InnerWorldView 布局响应式调整

- [ ] 修改 `dashboard/src/routes/agent/components/CommandCenterLayout.tsx`，调整内心世界叠加层的响应式布局。将 `max-w-4xl` 改为 `max-w-5xl`，并添加响应式类：小屏（<768px）使用 `max-w-full`，大屏保持 `max-w-5xl`。可使用 Tailwind 的 `max-w-full md:max-w-5xl` 实现。
- **验收标准**：在 1366px 宽度屏幕上内心世界叠加层宽度合理，不出现左右大片空白；在 768px 宽度屏幕上接近全屏展示。
- **涉及文件**：`dashboard/src/routes/agent/components/CommandCenterLayout.tsx`（修改）
- **依赖**：无

### 6.4 EmotionBaselineShift 偏移条最小可见宽度

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/EmotionBaselineShift.tsx`，在偏移条宽度计算中添加最小可见宽度逻辑。将 `width: Math.min(Math.abs(delta), 100)%` 改为：当 `Math.abs(delta) >= 5` 时，宽度为 `Math.max(Math.min(Math.abs(delta), 100), 10)%`；当 `Math.abs(delta) < 5` 时，宽度保持 `Math.min(Math.abs(delta), 100)%`。
- **验收标准**：某情绪维度 delta=8 时，偏移条宽度不低于 10%，用户可清晰辨识偏移方向。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/EmotionBaselineShift.tsx`（修改）
- **依赖**：无

### 6.5 ViewSwitcher 替换 emoji 图标为 lucide-react 图标

- [ ] 修改 `dashboard/src/routes/agent/components/ViewSwitcher.tsx`，将 emoji 图标 `📊`、`🌌`、`🌍` 替换为 `lucide-react` SVG 图标。导入 `LayoutDashboard`、`Sparkles`、`Globe` from `lucide-react`。将 `VIEW_ICONS` 从 `Record<TopView, string>` 改为 `Record<TopView, React.ComponentType<{ className?: string }>>`，映射：`dashboard → LayoutDashboard`、`constellation → Sparkles`、`global → Globe`。渲染时使用 `<Icon className="h-4 w-4" />` 替代 `<span>{emoji}</span>`。
- **验收标准**：视图切换器图标使用 SVG 渲染而非 emoji，在 Windows/macOS/Linux 上显示一致。
- **涉及文件**：`dashboard/src/routes/agent/components/ViewSwitcher.tsx`（修改）
- **依赖**：无

### 6.6 EmotionDonutChart 添加图例

- [ ] 修改 `dashboard/src/routes/agent/components/global-situation/EmotionDonutChart.tsx`，在环形图下方添加自定义图例组件。图例展示各情绪类型的颜色色块和情绪标签，水平排列，自动换行。每个图例项包含：小色块（12×12px）+ 情绪标签 + 数量。使用 recharts 的 `Legend` 组件或自定义渲染。
- **验收标准**：查看群体情绪环形图时，图表下方展示图例，包含颜色色块和情绪标签，不依赖 Tooltip 即可辨识。
- **涉及文件**：`dashboard/src/routes/agent/components/global-situation/EmotionDonutChart.tsx`（修改）
- **依赖**：6.8

### 6.7 ActivityHeatmap 添加图例

- [ ] 修改 `dashboard/src/routes/agent/components/global-situation/ActivityHeatmap.tsx`，在热力图下方添加颜色-状态映射的图例说明。图例格式：红色色块 + "活跃" + 黄色色块 + "安静" + 蓝色色块 + "沉睡"。使用 i18n 翻译键 `agent.globalSituation.heatmapLegend.active`、`agent.globalSituation.heatmapLegend.quiet`、`agent.globalSituation.heatmapLegend.dormant`。
- **验收标准**：查看活跃度热力图时，图表下方展示图例：红色=活跃、黄色=安静、蓝色=沉睡。
- **涉及文件**：`dashboard/src/routes/agent/components/global-situation/ActivityHeatmap.tsx`（修改）
- **依赖**：6.9

### 6.8 EmotionDonutChart 标签取值修复

- [ ] 修改 `dashboard/src/routes/agent/components/global-situation/EmotionDonutChart.tsx`，修复标签取值逻辑。将 `emotions[Object.keys(emotions)[0]]?.emotion_labels[emotion]` 改为遍历所有智能体的 `emotion_labels`，优先取非空值：`Object.values(emotions).find(e => e.emotion_labels?.[emotion])?.emotion_labels[emotion] || emotion`。确保每个情绪类型的标签从该情绪类型对应的智能体数据中独立获取，而非仅取第一个智能体的标签映射。
- **验收标准**：5个智能体主导情绪为 happy，3个为 calm 时，环形图中 happy 和 calm 标签均正确显示，不依赖第一个智能体的标签映射。
- **涉及文件**：`dashboard/src/routes/agent/components/global-situation/EmotionDonutChart.tsx`（修改）
- **依赖**：无

### 6.9 新增动画与布局相关 i18n 翻译键

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 中新增翻译键：`agent.globalSituation.heatmapLegend.active`（活跃）、`agent.globalSituation.heatmapLegend.quiet`（安静）、`agent.globalSituation.heatmapLegend.dormant`（沉睡）。同步至 `en.json`、`ja.json`、`ko.json`。
- **验收标准**：4种语言翻译键完整对齐，热力图图例切换语言后文案正确。
- **涉及文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`、`ko.json`
- **依赖**：无

---

## 7. 生命时间线时间戳修复

> 当前状态：情绪转折和关系突破事件使用 `new Date().toISOString()` 伪造当前时间，记忆里程碑已使用真实时间。

### 7.1 修复 LifeTimeline 时间戳逻辑

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/LifeTimeline.tsx`，将情绪转折事件和关系突破事件的时间戳从 `new Date().toISOString()` 改为特殊标记值（如 `"current"`）。在渲染时间戳时，判断若为 `"current"` 则显示 i18n 翻译键 `agent.lifeTimeline.currentStatus`（"当前状态"）而非 `new Date(timestamp).toLocaleString()`。记忆里程碑事件的时间戳 `record.completed_at` 保持不变（已是真实时间）。
- **验收标准**：智能体最近完成了一次 Dream 巩固，完成时间为 10:30 → 时间线中该事件显示 10:30；情绪转折事件无历史时间戳 → 标注为"当前状态"而非当前时间。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/LifeTimeline.tsx`（修改）
- **依赖**：7.2

### 7.2 新增 LifeTimeline 时间戳相关 i18n 翻译键

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.lifeTimeline` 命名空间下新增翻译键：`currentStatus`（当前状态）。同步至 `en.json`、`ja.json`、`ko.json`。
- **验收标准**：4种语言翻译键完整对齐，时间线中"当前状态"标注切换语言后文案正确。
- **涉及文件**：`dashboard/src/i18n/locales/zh.json`、`en.json`、`ja.json`、`ko.json`
- **依赖**：无

---

## 8. 内心世界 Tabs 状态保持

> 当前状态：`InnerWorldView` 使用 `<Tabs defaultValue="emotion">`，每次切换智能体时 Tabs 重置为"情绪景观"。

### 8.1 将 InnerWorldView Tabs 从非受控改为受控

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`，将 Tabs 从非受控改为受控模式。新增内部状态 `activeTab`，类型为 `"emotion" | "relationship" | "memory" | "timeline" | "sessions"`，默认值 `"emotion"`。将 `<Tabs defaultValue="emotion">` 改为 `<Tabs value={activeTab} onValueChange={setActiveTab}>`。切换智能体时 `activeTab` 保持不变（不重置）。
- **验收标准**：用户在"记忆花园"子视图按下↓方向键切换至下一个智能体后，仍停留在"记忆花园"子视图。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`（修改）
- **依赖**：无

---

## 9. useInnerWorldData 加载状态修复

> 当前状态：`isLoading` 仅检查 `agentQuery.isLoading || emotionQuery.isLoading`，忽略其余4个查询。

### 9.1 完善 useInnerWorldData 加载状态判断

- [ ] 修改 `dashboard/src/routes/agent/hooks/useInnerWorldData.ts`，将 `isLoading` 改为检查所有6个查询：`agentQuery.isLoading || emotionQuery.isLoading || relationshipQuery.isLoading || sessionsQuery.isLoading || subAgentQuery.isLoading || behaviorRulesQuery.isLoading`。新增 `isCoreLoading` 属性，仅检查 `agentQuery.isLoading`。新增 `isAuxLoading` 属性，检查其余5个查询的 `isLoading`。更新返回类型 `InnerWorldData`，增加 `isCoreLoading` 和 `isAuxLoading` 字段。
- **验收标准**：agent 和 emotion 已加载完成但 relationships 仍在加载中时，内心世界仍显示加载状态而非部分渲染。
- **涉及文件**：`dashboard/src/routes/agent/hooks/useInnerWorldData.ts`（修改）
- **依赖**：无

### 9.2 InnerWorldView 实现渐进加载

- [ ] 修改 `dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`，利用 `isCoreLoading` 和 `isAuxLoading` 实现渐进渲染。当 `isCoreLoading` 为 true 时显示全屏加载状态；当 `isCoreLoading` 为 false 但 `isAuxLoading` 为 true 时，先展示 `IdentityHeader`，辅助数据区域显示骨架屏；当两者均为 false 时正常渲染所有内容。
- **验收标准**：agent 已加载但 emotion 仍在加载时，身份标识区域正常展示，情绪景观区域显示骨架屏。
- **涉及文件**：`dashboard/src/routes/agent/components/inner-world/InnerWorldView.tsx`（修改）
- **依赖**：9.1

---

## 10. 集成验证

> 确保所有打磨项正确集成，无回归问题。

### 10.1 ActiveSessions 绑定/解绑端到端验证

- [ ] 验证 ActiveSessions 绑定/解绑的完整交互流程：1）点击解绑按钮→弹出确认对话框→确认后调用 API→成功后刷新列表→该会话从列表移除；2）解绑 API 失败→显示 toast 错误提示→列表不变；3）点击绑定按钮→弹出会话选择对话框→列表展示聊天流实际名称→选择后调用 API→成功后刷新列表→新会话出现；4）绑定 API 失败→显示 toast 错误提示→列表不变；5）操作执行中所有按钮禁用；6）会话选择对话框加载失败→显示错误提示+重试。
- **验收标准**：所有6个场景均按规格正确处理，无静默失败或异常。
- **依赖**：1.1 ~ 1.4

### 10.2 星图交互浮层端到端验证

- [ ] 验证星图交互浮层的完整交互流程：1）单击节点→节点高亮+关联连线高亮+浮层显示情绪脉动和活跃节奏；2）悬停连线→浮层显示关系类型、态度、互动风格和紧密程度；3）点击空白区域→关闭浮层+取消高亮；4）节点浮层数据不完整→缺失部分显示"暂不可感知"；5）切换选中节点→高亮和浮层正确切换。
- **验收标准**：所有5个场景均按规格正确处理。
- **依赖**：4.1 ~ 4.6

### 10.3 动画与布局验证

- [ ] 验证动画和布局打磨效果：1）EmotionPulse 高强度值时脉动幅度不超过 1.2；2）沉睡状态显示固定不透明灰色圆点；3）1366px 屏幕内心世界宽度合理；4）768px 屏幕内心世界接近全屏；5）EmotionBaselineShift delta=8 时偏移条宽度不低于 10%；6）ViewSwitcher 图标为 SVG 渲染；7）EmotionDonutChart 包含图例；8）ActivityHeatmap 包含图例；9）13个智能体同时展示脉动动画时帧率不低于 30fps。
- **验收标准**：所有9个验证项通过。
- **依赖**：6.1 ~ 6.9

### 10.4 i18n 完整性验证

- [ ] 验证所有新增 i18n 翻译键在4种语言中完整对齐：1）切换至英文→所有打磨相关文案正确显示英文；2）切换至日文→所有打磨相关文案正确显示日文；3）切换至韩文→所有打磨相关文案正确显示韩文；4）GroupStatsBar 统计条切换语言后文案正确；5）ActivityHeatmap 图例切换语言后文案正确；6）LifeTimeline "当前状态"标注切换语言后文案正确。
- **验收标准**：4种语言下所有文案正确显示，无遗漏翻译键。
- **依赖**：1.4, 3.2, 4.6, 6.9, 7.2

### 10.5 回归验证

- [ ] 验证打磨修改未引入回归问题：1）生命体征仪表盘正常加载，所有卡片展示生命感指标；2）内心世界5个子视图可切换，数据正确；3）星图视图正常渲染，力导向布局正确；4）全局态势视图正常展示群体数据；5）从内心世界"深入观测"跳转至监控页，URL 参数正确传递（SPA 路由切换，无整页刷新）；6）会话绑定/解绑功能正常；7）智能体配置重载功能正常；8）EmotionDonutChart 标签取值正确（多智能体场景）。
- **验收标准**：所有验证项通过，无回归问题。
- **依赖**：10.1 ~ 10.4