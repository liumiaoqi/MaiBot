# 智能体指挥中心 — 编码任务规划

> 核心理念：不做故事的结局，只做生命的序章。
> 角色不应是一具等待结局的标本，而应是一场永恒的进行时。

---

## Phase 1：基础框架 + 生命体征仪表盘

> 目标：替换现有智能体管理页为指挥中心框架，实现生命体征仪表盘。进入 `/agents` 后看到生命体征仪表盘，每张卡片展示情绪脉动、活跃节奏、关系温度和内在活动，点击卡片进入内心世界占位视图。

### 1.1 后端批量情绪 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/batch/emotion` 端点，一次性获取所有智能体的情绪状态。遍历 `registry.list_agents()`，对每个智能体调用 `EmotionManager(config).state`，捕获单个失败（该智能体不出现在返回结果中）。响应格式：`{ success: bool, data: Record<string, EmotionStateResponse> }`。新增 Pydantic 响应模型 `BatchEmotionResponse`。
- **验收标准**：调用 `GET /api/webui/agent/batch/emotion` 返回所有可用智能体的情绪状态字典，部分智能体失败不阻塞整体请求。
- **依赖**：无

### 1.2 后端批量关系 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/batch/relationships` 端点，一次性获取所有智能体的关系概要。遍历所有智能体，查询 `AgentRelationship` 表，捕获单个失败。响应格式：`{ success: bool, data: Record<string, List[RelationshipInfo]] }`。新增 Pydantic 响应模型 `BatchRelationshipResponse`。
- **验收标准**：调用 `GET /api/webui/agent/batch/relationships` 返回所有可用智能体的关系列表字典。
- **依赖**：无

### 1.3 后端批量会话数 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/batch/sessions` 端点，批量获取各智能体的已绑定会话数量。按 `agent_id` 分组统计 `ChatSession` 表。响应格式：`{ success: bool, data: Record<string, int> }`。新增 Pydantic 响应模型 `BatchSessionCountResponse`。
- **验收标准**：调用 `GET /api/webui/agent/batch/sessions` 返回各智能体的会话绑定数。
- **依赖**：无

### 1.4 后端批量子智能体最近记录 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/batch/subagent-latest` 端点，批量获取各智能体最近一条子智能体执行记录。对每个智能体查询 `SubAgentExecutionRecord` 最新一条（按 `completed_at` 降序），无记录则值为 `null`。响应格式：`{ success: bool, data: Record<string, SubAgentRecordResponse | null> }`。新增 Pydantic 响应模型 `BatchLatestSubAgentResponse`。
- **验收标准**：调用 `GET /api/webui/agent/batch/subagent-latest` 返回各智能体最近一条子智能体记录。
- **依赖**：无

### 1.5 前端批量 API 函数

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增4个批量 API 函数：`getBatchEmotions()`、`getBatchRelationships()`、`getBatchSessionCounts()`、`getBatchLatestSubAgentRecords()`。遵循已有的 `backendApi.get` + `requireSuccess` 模式。新增对应的 TypeScript 类型：`EmotionBehaviorRule`、批量响应类型。
- **验收标准**：4个函数可正确调用后端批量 API 并返回类型安全的数据。
- **依赖**：T1.1 ~ T1.4

### 1.6 提取共享情绪雷达图组件

- [ ] 将 `dashboard/src/routes/agent/index.tsx` 中的 `EmotionRadar` 和 `dashboard/src/routes/emotion-monitor/index.tsx` 中的 `EmotionRadarChart` 合并为统一的共享组件 `EmotionRadarChart`，放入 `dashboard/src/components/agent/EmotionRadarChart.tsx`。统一接口：`{ emotions: Record<string, number>; emotionLabels: Record<string, string>; size?: number; color?: string }`。更新 `agent/index.tsx` 和 `emotion-monitor/index.tsx` 的引用。
- **验收标准**：两个页面均使用共享组件，渲染效果与原来一致。
- **依赖**：无

### 1.7 提取共享情绪柱状图组件

- [ ] 将 `dashboard/src/routes/agent/index.tsx` 中的 `EmotionBars` 和 `dashboard/src/routes/emotion-monitor/index.tsx` 中的 `EmotionBarChart` 合并为统一的共享组件 `EmotionBarChart`，放入 `dashboard/src/components/agent/EmotionBarChart.tsx`。统一接口：`{ emotions: Record<string, number>; emotionLabels: Record<string, string>; showValues?: boolean }`。更新两个页面的引用。
- **验收标准**：两个页面均使用共享组件，渲染效果与原来一致。
- **依赖**：无

### 1.8 创建 useBatchAgentData Hook

- [ ] 在 `dashboard/src/routes/agent/hooks/` 目录下创建 `useBatchAgentData.ts`，实现 `useBatchAgentData` hook。使用 `useQuery` 的 `Promise.all` 组合，4个批量请求并行发起（agents + batchEmotions + batchRelationships + batchSessionCounts + batchLatestSubAgentRecords）。部分失败时可用数据正常返回，不可用部分以空值占位。`queryKey: ['agents', 'batch', 'overview']`。返回类型包含 `agents`、`emotions`、`relationships`、`sessionCounts`、`latestSubAgentRecords`、`isLoading`、`error`、`refetch`。
- **验收标准**：hook 并行加载所有批量数据，部分 API 失败时可用数据正常返回，loading 状态正确。
- **依赖**：T1.5

### 1.9 创建 useAgentNavigation Hook

- [ ] 在 `dashboard/src/routes/agent/hooks/` 目录下创建 `useAgentNavigation.ts`，实现 `useAgentNavigation` hook。使用 `@tanstack/react-router` 的 `useSearch()` 读取 URL 参数 `agent`，自动进入内心世界。监听键盘 `ArrowUp`/`ArrowDown` 事件，在智能体列表中切换。选中状态同步至 URL，支持浏览器前进/后退。返回 `selectedAgentId`、`setSelectedAgentId`、`navigateToAgent`、`navigateToNext`、`navigateToPrev`、`isInnerWorldOpen`、`exitInnerWorld`。
- **验收标准**：访问 `/agents?agent=silver_wolf` 自动选中该智能体并进入内心世界；键盘↑↓可切换智能体；URL 同步更新。
- **依赖**：无

### 1.10 创建 useViewSwitch Hook

- [ ] 在 `dashboard/src/routes/agent/hooks/` 目录下创建 `useViewSwitch.ts`，实现 `useViewSwitch` hook。管理 `currentView: TopView`（dashboard/constellation/global）状态。切换视图时保持 `selectedAgentId` 不变。从内心世界返回时恢复之前的 `currentView`。返回 `currentView`、`switchView`。
- **验收标准**：视图切换正常，从内心世界返回后恢复之前的顶层视图。
- **依赖**：无

### 1.11 创建生命体征派生工具函数

- [ ] 在 `dashboard/src/routes/agent/utils/` 目录下创建 `vital-signs.ts`，实现生命体征派生计算函数。包含：`deriveEmotionPulseData(emotion, agent)` → `EmotionPulseData`；`deriveActivityRhythmData(agent, sessionCount)` → `ActivityRhythmData`（判定规则：session_count > 0 && talk_value_modifier > 1.0 → active；session_count > 0 && talk_value_modifier >= 0.5 → quiet；否则 → dormant）；`deriveRelationshipWarmthData(relationships)` → `RelationshipWarmthData`（highest_level >= 3 → warm；>= 2 → moderate；>= 1 → cold；无数据 → unavailable）；`deriveInnerActivityData(latestRecord)` → `InnerActivityData`（最近1小时内有完成记录 → introspecting；否则 → quiet；无数据 → unavailable）；`deriveVitalSignsData(agent, emotion, relationships, sessionCount, latestRecord)` → `VitalSignsData`。定义所有派生模型的 TypeScript 类型。
- **验收标准**：各派生函数根据输入数据正确计算生命体征指标，语义化描述替代原始参数值。
- **依赖**：无

### 1.12 创建 EmotionPulse 动画组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `EmotionPulse.tsx`，实现情绪脉动动画组件。使用 `@react-spring/web` 的 `useSpring` 实现脉动效果，`scale` 在 `1.0 ~ 1.0 + intensity/200` 之间循环，周期 `2s - intensity/100` 秒。展示主导情绪图标和颜色。情绪数据不可用时显示"脉动暂不可感知"占位符。使用 i18n 翻译键 `agent.vitalSigns.emotionPulse.unavailable`。
- **验收标准**：有情绪数据时显示脉动动画和情绪图标；无数据时显示占位文案。
- **依赖**：T1.11

### 1.13 创建 ActivityRhythmIndicator 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `ActivityRhythmIndicator.tsx`，实现活跃节奏指示器。活跃状态呼吸灯 `opacity: 0.4 ~ 1.0`，周期 3s；安静状态 `opacity: 0.2 ~ 0.5`，周期 5s；沉睡无动画。展示语义化状态标签（活跃/安静/沉睡）和会话数。使用 i18n 翻译键 `agent.vitalSigns.activity.*`。
- **验收标准**：三种状态显示正确的动画效果和语义化标签。
- **依赖**：T1.11

### 1.14 创建 RelationshipWarmthIndicator 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `RelationshipWarmthIndicator.tsx`，实现关系温度指示器。以温度色彩展示关系温度——warm 暖色（橙红）、moderate 中间色、cold 冷色（蓝色）、unavailable 灰色。展示关系数和语义化标签。使用 i18n 翻译键 `agent.vitalSigns.warmth.*`。
- **验收标准**：四种温度等级显示正确的色彩和语义化标签。
- **依赖**：T1.11

### 1.15 创建 InnerActivityIndicator 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `InnerActivityIndicator.tsx`，实现内在活动指示器。微光效果 `opacity: 0.1 ~ 0.3`，周期 4s。展示"内省中"或"安静"标签和最近活动类型。使用 i18n 翻译键 `agent.vitalSigns.innerActivity.*`。
- **验收标准**：内省状态显示微光动画和"内省中"标签；安静状态无动画。
- **依赖**：T1.11

### 1.16 创建 CoreBadge 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `CoreBadge.tsx`，实现核心智能体徽章。当 `is_default` 为 true 时显示"核心"徽章。使用 i18n 翻译键 `agent.vitalSigns.coreBadge`。
- **验收标准**：默认智能体显示"核心"徽章，非默认智能体不显示。
- **依赖**：无

### 1.17 创建 VitalSignsCard 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `VitalSignsCard.tsx`，组合 EmotionPulse、ActivityRhythmIndicator、RelationshipWarmthIndicator、InnerActivityIndicator、CoreBadge 为完整的生命体征卡片。Props：`{ data: VitalSignsData; isSelected: boolean; onClick: () => void }`。卡片包含：头像（主题色圆形+首字）+ 显示名称 + agent_id + 核心徽章 + 情绪脉动 + 活跃节奏 + 关系温度 + 内在活动。选中时 `ring-2 ring-primary`。禁止展示原始技术参数值。
- **验收标准**：卡片展示6项信息（头像/名称、情绪脉动、活跃节奏、关系温度、内在活动、核心徽章），不出现原始参数值。
- **依赖**：T1.12 ~ T1.16

### 1.18 创建 ViewSwitcher 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `ViewSwitcher.tsx`，实现顶层视图切换器。展示三个选项：仪表盘、星图、全局态势。使用 Radix `Tabs` 或自定义按钮组实现。Props：`{ currentView: TopView; onSwitch: (view: TopView) => void }`。使用 i18n 翻译键。
- **验收标准**：三个视图选项可切换，当前选中项高亮。
- **依赖**：无

### 1.19 创建 CommandCenterLayout 组件

- [ ] 在 `dashboard/src/routes/agent/components/` 目录下创建 `CommandCenterLayout.tsx`，实现指挥中心页面根组件。管理顶层视图切换和内心世界叠加。布局：顶部 ViewSwitcher → 当前顶层视图内容（Dashboard/Constellation/GlobalSituation）→ InnerWorldView 叠加层。使用 `useBatchAgentData`、`useAgentNavigation`、`useViewSwitch` hooks。Dashboard 视图展示 VitalSignsCard 响应式网格 + 搜索过滤 + 刷新按钮。InnerWorldView 仅在 `selectedAgentId` 存在时显示（Phase 2 实现完整内心世界，Phase 1 仅展示占位视图）。
- **验收标准**：进入 `/agents` 后看到生命体征仪表盘，卡片展示生命感指标，点击卡片进入内心世界占位视图。
- **依赖**：T1.8 ~ T1.10, T1.17, T1.18

### 1.20 替换路由页面组件

- [ ] 修改 `dashboard/src/routes/agent/index.tsx`，将 `AgentManagementPage` 替换为 `CommandCenterLayout`。保留原有的 `EMOTION_COLORS` 和 `EMOTION_ICONS` 常量（移至 `utils/emotion-constants.ts` 共享）。删除旧的 `AgentCard`、`EmotionRadar`、`EmotionBars`、`RelationshipTable` 组件（已被 VitalSignsCard 和共享组件替代）。确保路由文件仅导出 `CommandCenterLayout`。
- **验收标准**：`/agents` 路由渲染新的指挥中心页面，旧的左右分栏布局不再出现。
- **依赖**：T1.6, T1.7, T1.19

### 1.21 Phase 1 i18n 翻译键（中文基准）

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent` 命名空间下新增 Phase 1 所需翻译键：`agent.commandCenter.*`（title、subtitle）、`agent.vitalSigns.*`（emotionPulse.unavailable、activity.active/quiet/dormant、warmth.warm/moderate/cold/unavailable、innerActivity.introspecting/quiet/unavailable、coreBadge、sessionCount、relationshipCount）、`agent.constellation.title`、`agent.globalSituation.title`。
- **验收标准**：新增翻译键完整，页面中文文案正常显示。
- **依赖**：无

---

## Phase 2：内心世界

> 目标：实现内心世界的5个子视图。点击生命体征卡片后进入内心世界，可在5个子视图间切换，每个子视图展示对应数据，"深入观测"链接跳转至监控页。

### 2.1 后端情绪-行为映射 API

- [ ] 在 `src/webui/routers/agent.py` 中新增 `GET /api/webui/agent/{agent_id}/emotion-behavior-rules` 端点，获取智能体的情绪-行为映射规则。从 `AgentConfig.emotion_behavior_map` 读取。新增 Pydantic 模型 `EmotionBehaviorRuleResponse`（emotion_type、intensity_threshold、behavior_tendency、reply_style_modifier）和 `EmotionBehaviorRulesResponse`。注意：`AgentConfig.emotion_behavior_map` 字段当前未在 `_config_to_response` 中暴露，需确认该字段的数据结构。
- **验收标准**：调用 `GET /api/webui/agent/{agent_id}/emotion-behavior-rules` 返回该智能体的情绪-行为映射规则列表。
- **依赖**：无

### 2.2 前端情绪-行为映射 API 函数

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增 `getEmotionBehaviorRules(agentId: string)` 函数和 `EmotionBehaviorRule` 类型定义。遵循已有的 `backendApi.get` + `requireSuccess` 模式。
- **验收标准**：函数可正确调用后端 API 并返回类型安全的数据。
- **依赖**：T2.1

### 2.3 创建 useInnerWorldData Hook

- [ ] 在 `dashboard/src/routes/agent/hooks/` 目录下创建 `useInnerWorldData.ts`，实现 `useInnerWorldData` hook。管理单个智能体的所有数据请求：agent detail、emotion、relationships、subAgentRecords、emotionBehaviorRules、sessions。使用多个 `useQuery`，通过 `enabled: !!agentId` 控制请求触发。切换智能体时自动重新请求，但切换子视图不重新请求（利用 TanStack Query 缓存）。`queryKey` 遵循 `['agents', 'detail', agentId]`、`['agents', 'emotion', agentId]` 等现有约定。
- **验收标准**：hook 正确加载单个智能体的所有数据，切换子视图不重新请求，切换智能体时重新请求。
- **依赖**：T2.2

### 2.4 创建 IdentityHeader 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `IdentityHeader.tsx`，实现身份标识区域。展示大尺寸头像（主题色圆形+首字）、显示名称、情绪脉动徽章（主导情绪图标+标签+颜色）、人格摘要（从 `personality` 字段截断至50字）。包含返回按钮。使用 i18n 翻译键 `agent.innerWorld.*`。
- **验收标准**：身份标识区域展示完整的智能体身份信息。
- **依赖**：无

### 2.5 创建 EmotionBaselineShift 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `EmotionBaselineShift.tsx`，实现基线偏移可视化。每个情绪维度一行：图标 + 标签 + 偏移条 + 差值 + 方向箭头。正向偏移（delta > 5）：绿色条 + "↑"；负向偏移（delta < -5）：红色条 + "↓"；稳定（|delta| <= 5）：灰色条 + "→"。从 `emotions` 和 `emotion_baseline` 计算偏移数据。
- **验收标准**：基线偏移图正确显示各情绪维度的偏移方向和幅度。
- **依赖**：无

### 2.6 创建 EmotionBehaviorMap 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `EmotionBehaviorMap.tsx`，实现情绪-行为映射展示。以语义化方式展示情绪对行为的影响，如"焦虑时倾向回避""开心时更主动互动"。从 `EmotionBehaviorRule[]` 数据派生展示内容。使用 i18n 翻译键 `agent.emotionLandscape.behaviorTendency`。
- **验收标准**：有行为规则时展示语义化描述；无规则时不显示该区域。
- **依赖**：T2.2

### 2.7 创建 EmotionLandscape 子视图

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `EmotionLandscape.tsx`，实现情绪景观子视图。布局：上方左右分栏（情绪雷达图 + 情绪强度柱图），下方基线偏移对比 + 行为倾向。复用共享组件 `EmotionRadarChart` 和 `EmotionBarChart`。包含"深入观测 → 情绪监控页"链接。情绪数据不可用时显示"情绪景观暂不可感知"占位符。使用 i18n 翻译键 `agent.emotionLandscape.*`。
- **验收标准**：情绪景观展示雷达图、柱图、基线偏移和行为倾向，"深入观测"链接正确跳转。
- **依赖**：T1.6, T1.7, T2.5, T2.6

### 2.8 创建 RelationshipNetwork 子视图

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `RelationshipNetwork.tsx`，实现关系网络子视图。展示：关系等级分布图（复用 `RelationshipDistributionChart` 逻辑）、关系排行（复用 `RelationshipScoreChart` 逻辑）、内部关系小型网络图（基于 reactflow + dagre 的简化版力导向图，节点为智能体头像，连线颜色映射关系类型）。包含"深入观测 → 关系监控页"链接。关系数据不可用时显示"关系网络暂不可感知"占位符。使用 i18n 翻译键 `agent.relationshipNetwork.*`。
- **验收标准**：关系网络展示等级分布、排行和内部关系图，"深入观测"链接正确跳转。
- **依赖**：无

### 2.9 创建 MemoryGarden 子视图

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `MemoryGarden.tsx`，实现记忆花园子视图。展示：记忆焦点区域（以花园标签形式展示 `memory_focus_areas`，每个标签带有植物/花园图标）、内在活动记录（Dream/Compaction/Checkpoint 的近期执行情况，语义化描述如"刚刚完成了一次内省"）。包含"深入观测 → 子智能体监控页"链接。活动记录不可用时显示"活动记录暂不可用"占位符。使用 i18n 翻译键 `agent.memoryGarden.*`。
- **验收标准**：记忆花园展示焦点标签和内在活动记录，"深入观测"链接正确跳转。
- **依赖**：无

### 2.10 创建 LifeTimeline 子视图

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `LifeTimeline.tsx`，实现生命时间线子视图。从关系变化（`RelationshipInfo` 中 `score` 接近等级阈值推断"即将突破"）、情绪变化（`dominant_emotion` 变化）、子智能体记录（`SubAgentRecord` 完成事件）聚合时间线事件。按时间降序排列，最多展示20条。每个事件包含：图标 + 时间戳 + 描述。事件类型：emotion_shift（情绪转折）、relationship_breakthrough（关系突破）、memory_milestone（记忆里程碑）。无事件时显示"暂无近期事件"。使用 i18n 翻译键 `agent.lifeTimeline.*`。
- **验收标准**：时间线展示聚合的近期事件，事件按时间降序排列。
- **依赖**：无

### 2.11 创建 ActiveSessions 子视图

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `ActiveSessions.tsx`，实现活跃会话子视图。复用现有 `agent/index.tsx` 中的会话绑定/解绑逻辑。展示已绑定会话列表（每条显示会话名称 + 解绑按钮），新增绑定按钮弹出会话选择对话框。会话选择对话框复用现有的 `getChatStreams` 查询。解绑操作需二次确认。使用 i18n 翻译键 `agent.activeSessions.*`。
- **验收标准**：会话列表正确展示，绑定/解绑操作正常工作，解绑需二次确认。
- **依赖**：无

### 2.12 创建 LifeDefensePanel 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `LifeDefensePanel.tsx`，实现生命防线（反机械化规则语义化展示）。以折叠面板形式展示，标题"生命防线"带有盾牌图标和描述文案"这些规则守护着角色的独特性，防止回应陷入机械化重复"。每条规则以语义化描述展示，而非编号列表。使用 i18n 翻译键 `agent.lifeDefense.*`。
- **验收标准**：反机械化规则以语义化方式展示，折叠面板可展开/收起。
- **依赖**：无

### 2.13 创建 CollapsedParameters 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `CollapsedParameters.tsx`，实现底层参数折叠区。以折叠面板形式展示原始技术参数：`talk_value_modifier`（活跃度修正）、`idle_backoff_modifier`（空闲退避修正）、`relationship_growth_rate`（关系进展速率）、`emotion_decay_rate`（情绪衰减率）。每个参数以语义化标签+数值展示。使用 i18n 翻译键 `agent.collapsedParameters.*`。
- **验收标准**：底层参数收纳在折叠区，默认收起，展开后显示4个参数。
- **依赖**：无

### 2.14 创建 DeepMonitorLink 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `DeepMonitorLink.tsx`，实现深入观测导航链接。展示跳转至对应独立监控页的链接（情绪监控、关系监控、子智能体监控）。使用 `@tanstack/react-router` 的 `navigate`，携带 `?agent=xxx` 参数。使用 i18n 翻译键。
- **验收标准**：点击链接正确跳转至对应监控页，URL 携带 agent 参数。
- **依赖**：无

### 2.15 创建 InnerWorldView 容器组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/` 目录下创建 `InnerWorldView.tsx`，实现内心世界沉浸式视图容器。布局：顶部 IdentityHeader → 子视图切换 Tabs（情绪景观/关系网络/记忆花园/生命时间线/活跃会话）→ 当前子视图内容 → 底部 LifeDefensePanel（折叠）+ CollapsedParameters（折叠）+ DeepMonitorLink。使用 Radix `Tabs` 组件。切换子视图时利用 TanStack Query 缓存不重新请求数据。使用 `useInnerWorldData` hook 加载数据。使用 i18n 翻译键 `agent.innerWorld.*`。
- **验收标准**：5个子视图可正常切换，数据正确展示，底部折叠区和导航链接正常。
- **依赖**：T2.3, T2.4, T2.7 ~ T2.14

### 2.16 实现内心世界过渡动画

- [ ] 在 `InnerWorldView` 中集成 `motion` 库的 `AnimatePresence` + `fade` 过渡动画。切换智能体时整个内心世界淡入淡出，duration 200ms。在 `CommandCenterLayout` 中集成内心世界叠加层的进入/退出动画。
- **验收标准**：切换智能体时有平滑的淡入淡出过渡，内心世界打开/关闭有动画。
- **依赖**：T2.15, T1.19

### 2.17 Phase 2 i18n 翻译键（中文基准）

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent` 命名空间下新增 Phase 2 所需翻译键：`agent.innerWorld.*`（back、personalitySummary、subView.*）、`agent.emotionLandscape.*`（radarTitle、barTitle、baselineShift、behaviorTendency、shiftUp、shiftDown、shiftStable、unavailable、deepMonitor）、`agent.relationshipNetwork.*`（title、distribution、ranking、internalGraph、unavailable、deepMonitor）、`agent.memoryGarden.*`（title、focusAreas、innerActivity、noFocusAreas、dreamComplete、unavailable、deepMonitor）、`agent.lifeTimeline.*`（title、emotionShift、relationshipBreakthrough、memoryMilestone、noEvents、relationshipWarmUp）、`agent.lifeDefense.*`（title、description）、`agent.collapsedParameters.*`（title、talkValueModifier、idleBackoffModifier、relationshipGrowthRate、emotionDecayRate）、`agent.activeSessions.*`（title、bindSession、unbind、unbindConfirm、noSessions）。
- **验收标准**：新增翻译键完整，内心世界各子视图中文文案正常显示。
- **依赖**：无

---

## Phase 3：智能体星图 + 全局态势

> 目标：实现力导向图星图和全局态势大屏。切换至星图视图可看到力导向布局的智能体关系网，切换至全局态势可看到群体情绪分布和活跃度热力图。

### 3.1 创建星图数据派生工具函数

- [ ] 在 `dashboard/src/routes/agent/utils/` 目录下创建 `constellation.ts`，实现星图数据派生计算函数。`deriveConstellationData(agents, emotions, sessionCounts)` → `ConstellationData`。包含：`ConstellationNode`（从 AgentConfigInfo + EmotionStateInfo + ActivityRhythmData 派生，节点大小映射 activity_status）、`ConstellationEdge`（从 AgentConfigInfo.internal_relationships 派生，mention_label 映射：>= 0.7 → "紧密"、>= 0.4 → "一般"、< 0.4 → "疏远"；连线颜色映射 relationship_type；连线粗细映射 mention_tendency × 4 + 1）。定义 TypeScript 类型。
- **验收标准**：派生函数正确计算星图节点和连线数据，语义化描述替代原始数值。
- **依赖**：T1.11

### 3.2 创建 ConstellationNode 自定义渲染

- [ ] 在 `dashboard/src/routes/agent/components/constellation/` 目录下创建 `ConstellationNode.tsx`，实现星图节点的自定义渲染。圆形节点，背景色为 `color`，中心显示情绪图标，外围脉动光环（使用 `@react-spring/web` 实现脉动效果，同 EmotionPulse 参数）。节点大小映射 activity_status（active > quiet > dormant）。显示名称标签在节点下方。`is_default` 节点有特殊边框标识。
- **验收标准**：节点展示正确的颜色、图标和脉动动画，大小反映活跃状态。
- **依赖**：T3.1

### 3.3 创建 ConstellationEdge 自定义渲染

- [ ] 在 `dashboard/src/routes/agent/components/constellation/` 目录下创建 `ConstellationEdge.tsx`，实现星图关系连线的自定义渲染。连线颜色映射 relationship_type（romantic → #ef4444、family → #f97316、mentor → #3b82f6、friend → #22c55e、rival → #94a3b8）。连线粗细映射 mention_tendency × 4 + 1（范围 1px ~ 5px）。禁止展示原始 mention_tendency 数值。
- **验收标准**：连线展示正确的颜色和粗细，不出现原始数值。
- **依赖**：T3.1

### 3.4 创建 RelationshipTooltip 组件

- [ ] 在 `dashboard/src/routes/agent/components/constellation/` 目录下创建 `RelationshipTooltip.tsx`，实现关系悬停浮层。展示关系类型、态度描述和互动风格，使用语义化描述（如"紧密""一般""疏远"替代 mention_tendency 数值）。使用 i18n 翻译键 `agent.constellation.tooltip.*`。
- **验收标准**：悬停连线时显示关系浮层，内容语义化。
- **依赖**：无

### 3.5 创建 NodeDetailPopover 组件

- [ ] 在 `dashboard/src/routes/agent/components/constellation/` 目录下创建 `NodeDetailPopover.tsx`，实现节点点击浮层。展示该智能体的简要生命体征（情绪脉动、活跃节奏、关系温度）。点击节点时高亮该节点及其所有关系连线。
- **验收标准**：点击节点时显示浮层，节点和连线高亮。
- **依赖**：T3.2, T3.3

### 3.6 创建 AgentConstellation 主组件

- [ ] 在 `dashboard/src/routes/agent/components/constellation/` 目录下创建 `AgentConstellation.tsx`，实现力导向图主组件。基于 `reactflow` + `dagre` 实现。`dagre` 负责初始布局计算，`reactflow` 负责渲染和交互。集成 ConstellationNode、ConstellationEdge、RelationshipTooltip、NodeDetailPopover。Props：`{ data: ConstellationData; selectedAgentId: string | null; onNodeClick: (agentId: string) => void; onNodeDoubleClick: (agentId: string) => void }`。无内部关系数据时仅展示散落节点并显示"暂无内部关系数据"提示。使用 i18n 翻译键 `agent.constellation.*`。
- **验收标准**：星图以力导向布局展示智能体节点和关系连线，交互正常（悬停、单击、双击）。
- **依赖**：T3.1 ~ T3.5

### 3.7 创建 EmotionDonutChart 组件

- [ ] 在 `dashboard/src/routes/agent/components/global-situation/` 目录下创建 `EmotionDonutChart.tsx`，实现群体情绪环形图。基于 `recharts` 的 `PieChart`，`innerRadius` 设为外径的 60%。每个扇区颜色使用 `EMOTION_COLORS`。展示所有智能体的主导情绪分布。点击扇区高亮对应智能体。使用 i18n 翻译键 `agent.globalSituation.emotionDistribution`。
- **验收标准**：环形图正确展示主导情绪分布，点击扇区可高亮对应智能体。
- **依赖**：无

### 3.8 创建 ActivityHeatmap 组件

- [ ] 在 `dashboard/src/routes/agent/components/global-situation/` 目录下创建 `ActivityHeatmap.tsx`，实现活跃度热力图。使用 CSS Grid 渲染色块网格。每个智能体一个色块，颜色从冷色（#3b82f6，沉睡）到暖色（#ef4444，活跃）渐变。色块内显示智能体首字。色块大小一致，排列为响应式网格。使用 i18n 翻译键 `agent.globalSituation.activityHeatmap`。
- **验收标准**：热力图正确展示各智能体的活跃状态，颜色映射正确。
- **依赖**：无

### 3.9 创建 RelationshipDynamicsFlow 组件

- [ ] 在 `dashboard/src/routes/agent/components/global-situation/` 目录下创建 `RelationshipDynamicsFlow.tsx`，实现关系动态流。纯文本列表，展示近期关系变化事件。数据来源：前端从批量关系数据中，比对关系分数与等级阈值来推断"接近突破"的关系，标注为"即将突破"。无变化时显示"近期关系平稳，无显著变化"。使用 i18n 翻译键 `agent.globalSituation.relationshipDynamics.*`。
- **验收标准**：关系动态流展示接近阈值的关系事件，无变化时显示占位文案。
- **依赖**：无

### 3.10 创建 GroupStatsBar 组件

- [ ] 在 `dashboard/src/routes/agent/components/global-situation/` 目录下创建 `GroupStatsBar.tsx`，实现群体概览统计条。展示：智能体总数、活跃智能体数、总关系数、平均关系分数。格式：`13 个生命体 · 5 个活跃 · 120 条纽带 · 均温 450`。使用 i18n 翻译键 `agent.globalSituation.stats`。
- **验收标准**：统计条正确展示4项关键指标。
- **依赖**：无

### 3.11 创建 GlobalSituationView 主组件

- [ ] 在 `dashboard/src/routes/agent/components/global-situation/` 目录下创建 `GlobalSituationView.tsx`，实现全局态势感知大屏。布局：顶部 GroupStatsBar → 中间左右分栏（EmotionDonutChart + ActivityHeatmap）→ 底部 RelationshipDynamicsFlow。使用 `useBatchAgentData` hook 加载数据。数据部分不可用时基于可用数据渲染，缺失区域显示"数据暂不可用"。使用 i18n 翻译键 `agent.globalSituation.*`。
- **验收标准**：全局态势视图展示群体情绪分布、活跃度热力图和关系动态流。
- **依赖**：T3.7 ~ T3.10

### 3.12 集成星图和全局态势到 CommandCenterLayout

- [ ] 在 `CommandCenterLayout` 中集成 `AgentConstellation` 和 `GlobalSituationView`。当 `currentView` 为 `constellation` 时渲染星图，为 `global` 时渲染全局态势。星图双击节点进入内心世界。全局态势数据使用 `useBatchAgentData` hook。
- **验收标准**：切换至星图视图可看到力导向布局的智能体关系网，切换至全局态势可看到群体情绪分布和活跃度热力图。
- **依赖**：T1.19, T3.6, T3.11

### 3.13 Phase 3 i18n 翻译键（中文基准）

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent` 命名空间下新增 Phase 3 所需翻译键：`agent.constellation.*`（title、noRelationships、mention.close/moderate/distant、tooltip.relationshipType/attitude/interactionStyle）、`agent.globalSituation.*`（title、stats、emotionDistribution、activityHeatmap、relationshipDynamics、noChanges、nearBreakthrough）。
- **验收标准**：新增翻译键完整，星图和全局态势中文文案正常显示。
- **依赖**：无

---

## Phase 4：监控页整合 + 打磨

> 目标：完善监控页导航、动画打磨、性能优化。从指挥中心跳转至监控页时自动选中对应智能体，动画流畅，4语言完整支持。

### 4.1 情绪监控页 URL 参数支持

- [ ] 修改 `dashboard/src/routes/emotion-monitor/index.tsx`，初始化时使用 `@tanstack/react-router` 的 `useSearch()` 读取 `?agent=xxx` 查询参数。若存在且该智能体在列表中，自动切换至 Detail 模式并选中该智能体。若智能体不存在，忽略该参数展示默认 Grid 模式。
- **验收标准**：从指挥中心跳转至情绪监控页时自动选中对应智能体并展示详情。
- **依赖**：无

### 4.2 关系监控页 URL 参数支持

- [ ] 修改 `dashboard/src/routes/relationship-monitor/index.tsx`，初始化时使用 `useSearch()` 读取 `?agent=xxx` 查询参数。若存在且该智能体在列表中，自动选中该智能体。若不存在，忽略该参数。
- **验收标准**：从指挥中心跳转至关系监控页时自动选中对应智能体。
- **依赖**：无

### 4.3 子智能体监控页 URL 参数支持

- [ ] 修改 `dashboard/src/routes/subagent-monitor/index.tsx`，初始化时使用 `useSearch()` 读取 `?agent=xxx` 查询参数。若存在且该智能体在列表中，自动设置 `filterAgent` 为该智能体。若不存在，忽略该参数。
- **验收标准**：从指挥中心跳转至子智能体监控页时自动筛选对应智能体。
- **依赖**：无

### 4.4 生命感动画参数微调

- [ ] 微调所有生命感动画参数：EmotionPulse 脉动频率和幅度、ActivityRhythmIndicator 呼吸灯节奏、InnerActivityIndicator 微光效果、ConstellationNode 脉动光环。确保动画在 Docker 环境下流畅运行，帧率不低于 30fps。在13个智能体节点 + 全部内部关系连线的场景下测试性能。
- **验收标准**：动画流畅自然，13个智能体场景下帧率不低于 30fps。
- **依赖**：T1.12 ~ T1.15, T3.2

### 4.5 批量 API 性能优化

- [ ] 优化4个批量 API 的响应性能：确保并行请求总耗时不超过单次 API 请求耗时的 1.5 倍。检查后端批量 API 是否有不必要的重复查询，优化数据库查询（如使用批量查询替代逐个查询）。前端确保 `useBatchAgentData` 的 `Promise.all` 并行发起所有请求。
- **验收标准**：指挥中心首页首次加载完成时间不超过 2 秒。
- **依赖**：T1.1 ~ T1.4, T1.8

### 4.6 星图渲染性能优化

- [ ] 优化 `AgentConstellation` 的渲染性能。实现：简化连线动画效果（当节点或连线数量较多时自动简化）、节点懒渲染（视口外的节点延迟渲染）、减少不必要的重绘。确保13个智能体节点 + 全部内部关系连线场景下帧率不低于 30fps。
- **验收标准**：星图在最大负载下帧率不低于 30fps，交互流畅。
- **依赖**：T3.6

### 4.7 首页 AgentOverviewGrid 增加情绪脉动信号

- [ ] 修改 `dashboard/src/routes/index.tsx` 中的 `AgentOverviewGrid` 组件，为每个智能体头像增加情绪脉动视觉信号。在 `AgentIndicator` 旁边添加微弱的脉动色彩指示器，反映当前主导情绪。需要加载批量情绪数据（复用 `useBatchAgentData` 或单独调用 `getBatchEmotions`）。
- **验收标准**：首页智能体头像旁显示情绪脉动信号，无情绪数据时不显示。
- **依赖**：T1.5

### 4.8 全量 i18n 翻译（英文）

- [ ] 将 Phase 1 ~ Phase 3 新增的所有 `agent.*` 翻译键同步翻译至 `dashboard/src/i18n/locales/en.json`。以 `zh.json` 为基准，确保键完全对齐。情绪标签等已有翻译键复用 `emotion.*` 命名空间。
- **验收标准**：切换至英文语言后，指挥中心所有文案正确显示英文。
- **依赖**：T1.21, T2.17, T3.13

### 4.9 全量 i18n 翻译（日文）

- [ ] 将 Phase 1 ~ Phase 3 新增的所有 `agent.*` 翻译键同步翻译至 `dashboard/src/i18n/locales/ja.json`。以 `zh.json` 为基准，确保键完全对齐。
- **验收标准**：切换至日文语言后，指挥中心所有文案正确显示日文。
- **依赖**：T1.21, T2.17, T3.13

### 4.10 全量 i18n 翻译（韩文）

- [ ] 将 Phase 1 ~ Phase 3 新增的所有 `agent.*` 翻译键同步翻译至 `dashboard/src/i18n/locales/ko.json`。以 `zh.json` 为基准，确保键完全对齐。
- **验收标准**：切换至韩文语言后，指挥中心所有文案正确显示韩文。
- **依赖**：T1.21, T2.17, T3.13

---

## 5. 集成验证

### 5.1 Docker 环境端到端验证

- [ ] 在 Docker 环境下完成指挥中心的端到端验证。验证内容：1）进入 `/agents` 后生命体征仪表盘正常加载，所有卡片展示生命感指标；2）点击卡片进入内心世界，5个子视图可切换，数据正确；3）星图视图正常渲染，力导向布局正确，交互正常；4）全局态势视图正常展示群体数据；5）从内心世界"深入观测"跳转至监控页，URL 参数正确传递，监控页自动选中；6）从首页智能体头像跳转至指挥中心，自动进入内心世界；7）4种语言切换正常；8）动画流畅，帧率达标。
- **验收标准**：所有验证项通过，无阻塞性问题。
- **依赖**：T1.1 ~ T4.10 全部完成

### 5.2 异常场景验证

- [ ] 验证所有异常场景的处理：1）智能体列表加载失败 → 显示错误提示和重试按钮；2）部分智能体情绪数据不可用 → 卡片正常展示基础信息，情绪区域显示"脉动暂不可感知"；3）部分智能体关系数据不可用 → 卡片正常展示基础信息，关系区域显示"温度暂不可感知"；4）子智能体记录不可用 → 记忆花园部分可用，活动区域显示占位文案；5）会话绑定操作失败 → 显示 toast 错误提示；6）URL 指定的智能体不存在 → 忽略参数，展示默认状态；7）星图无内部关系数据 → 仅展示散落节点和提示文案。
- **验收标准**：所有异常场景均按规格正确处理，无白屏或静默失败。
- **依赖**：T5.1

### 5.3 代码审查与回归验证

- [ ] 完成代码审查：1）确认所有新增组件遵循项目代码规范（import 顺序、类型注解、注释）；2）确认所有用户可见文案通过 i18n 管理；3）确认现有功能（会话绑定/解绑、智能体重载、情绪监控页、关系监控页、子智能体监控页）未受影响；4）确认 `AgentConfigInfo`、`EmotionStateInfo`、`RelationshipInfo`、`SubAgentRecord` 数据结构向后兼容；5）确认首页 `AgentOverviewGrid` 导航链接指向新的指挥中心路由。
- **验收标准**：代码审查通过，现有功能无回归问题。
- **依赖**：T5.2