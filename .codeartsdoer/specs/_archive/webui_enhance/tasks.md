# MaiBot WebUI 功能增强（SSD3）— 任务列表

## 阶段 1：配置编辑增强 — 基础组件（高价值低风险）

> 依赖：无（SSD1/SSD2 已完成）
> 目标：补齐配置编辑的核心缺失能力——分组导航、脏状态守卫、保存后重启提示

### 任务 1.1：实现配置分组导航组件 ConfigSectionNav
- **文件**：`dashboard/src/components/dynamic-form/ConfigSectionNav.tsx`（新建）
- **内容**：
  1. 定义 `ConfigSection` 接口（key/label/order/advanced/dirty）
  2. 从 Schema 的 `nested`、`uiOrder`、`uiLabel`、`uiAdvanced` 提取分组列表
  3. 渲染左侧导航列表：当前激活分组高亮、高级分组折叠、脏状态标记（小圆点）
  4. 点击分组触发 `onSectionChange(key)` 回调
- **验收条件**：[加载 bot 配置页面] → [左侧展示所有分组，点击切换右侧表单内容，有未保存修改的分组显示脏标记]
- **风险**：低，纯新增组件，不影响现有 DynamicConfigForm

### 任务 1.2：将 ConfigSectionNav 集成到 bot 配置页面
- **文件**：`dashboard/src/routes/config/bot.tsx`
- **内容**：
  1. 在 `BotConfigPageContent` 中引入 `ConfigSectionNav`，替换现有的 `DashboardTabBar` 横向 Tab 布局
  2. 布局调整为左右分栏：左侧 `ConfigSectionNav`（固定宽度 200px），右侧 `DynamicConfigForm`
  3. 分组切换时更新当前激活分组，右侧表单只渲染当前分组内容
  4. 分组的脏状态从 `hasUnsavedChanges` 按分组维度计算
- **验收条件**：[打开 bot 配置页] → [左侧分组导航，右侧表单，点击分组切换内容]
- **风险**：中，需重构 bot.tsx 的 Tab 渲染逻辑（当前 1189 行），但功能不变

### 任务 1.3：实现脏状态路由守卫 useUnsavedChangesGuard
- **文件**：`dashboard/src/hooks/useUnsavedChangesGuard.ts`（新建）
- **内容**：
  1. 拦截浏览器 `beforeunload` 事件（有未保存修改时弹出浏览器原生确认框）
  2. 拦截 TanStack Router 的路由跳转（通过 `router.subscribe` 监听 `onBeforeNavigate`）
  3. 弹出确认对话框（保存/放弃/取消），用户取消时阻止跳转
  4. 接受 `isDirty`/`onSave`/`onDiscard` 参数，与 `useConfigForm.isDirty` 对接
- **验收条件**：[修改配置后尝试离开页面] → [弹出确认对话框；取消则留在当前页面]
- **风险**：低，纯新增 hook

### 任务 1.4：将脏状态守卫集成到配置页面
- **文件**：`dashboard/src/routes/config/bot.tsx`、`dashboard/src/routes/config/model.tsx`
- **内容**：
  1. 在 bot 配置页和 model 配置页中调用 `useUnsavedChangesGuard({ isDirty: hasUnsavedChanges, ... })`
  2. 替换现有的 `beforeunload` 事件监听（如有）
  3. 路由跳转拦截与保存/放弃逻辑对接
- **验收条件**：[修改 bot 配置后点击侧边栏导航] → [弹出确认对话框]
- **风险**：低

### 任务 1.5：后端配置保存响应增加 needs_restart 字段
- **文件**：`src/webui/schemas/config.py`、`src/webui/routers/config.py`
- **内容**：
  1. 在 `schemas/config.py` 中新增 `ConfigSaveResponse` 模型（success/message/needs_restart/restart_required_sections）
  2. 在 `config.py` 的 bot section 保存和 model section 保存端点中，写入成功后判断修改的配置节是否需要重启
  3. 需要重启的配置节列表硬编码为：`BotConfig`（基础）、`DatabaseConfig`、`LogConfig`、`WebUIConfig`（运行时不可热加载的配置）
  4. 保存响应从直接返回 dict 改为返回 `ApiResponse[ConfigSaveResponse]`
- **验收条件**：[保存 BotConfig 分组] → [响应中 needs_restart=true，restart_required_sections=["BotConfig"]]
- **风险**：低，新增字段向后兼容（默认 false）

### 任务 1.6：前端展示配置保存后重启提示
- **文件**：`dashboard/src/routes/config/bot.tsx`、`dashboard/src/routes/config/model.tsx`
- **内容**：
  1. 配置保存成功后，检查响应中的 `needs_restart` 字段
  2. 如果 `needs_restart=true`，展示"部分配置需要重启生效"提示（使用已有的 `RestartOverlay` 组件或 toast）
  3. 提供快捷重启按钮
- **验收条件**：[保存需要重启的配置] → [页面显示"部分配置需要重启生效"提示，可一键重启]
- **风险**：低

## 阶段 2：配置编辑增强 — 模式切换与字段增强（高价值中风险）

> 依赖：阶段 1
> 目标：实现表单/源码模式切换、敏感字段掩码、前端校验增强

### 任务 2.1：实现配置模式切换 hook useConfigMode
- **文件**：`dashboard/src/hooks/useConfigMode.ts`（新建）
- **内容**：
  1. 管理 `mode` 状态（form/source），偏好存入 localStorage
  2. `switchMode(target)` 方法：切换前检查当前模式是否有未保存修改
  3. 表单→源码：将表单草稿序列化为 TOML 填充源码编辑器
  4. 源码→表单：解析 TOML 为配置对象同步到表单草稿；TOML 语法错误时阻止切换并高亮错误
  5. 管理 `sourceDraft`/`sourceError` 状态
- **验收条件**：[在表单模式修改配置 → 切换到源码模式] → [源码中包含表单修改的内容]；[源码有语法错误 → 切换被阻止]
- **风险**：中，TOML 序列化/反序列化需处理边界情况（特殊字符、嵌套对象）

### 任务 2.2：实现配置模式切换 UI ConfigModeSwitcher
- **文件**：`dashboard/src/components/dynamic-form/ConfigModeSwitcher.tsx`（新建）
- **内容**：
  1. 渲染模式切换按钮组（表单/源码），当前模式高亮
  2. 调用 `useConfigMode.switchMode()` 处理切换逻辑
  3. 源码模式下渲染 `CodeEditor` 组件（复用已有的 `@/components/CodeEditor`）
  4. 源码模式下展示 TOML 语法错误提示
- **验收条件**：[点击"源码模式"按钮] → [切换到源码编辑器视图]；[点击"表单模式"按钮] → [切换回表单视图]
- **风险**：低

### 任务 2.3：将模式切换集成到 bot 配置页面
- **文件**：`dashboard/src/routes/config/bot.tsx`
- **内容**：
  1. 引入 `ConfigModeSwitcher` 和 `useConfigMode`，替换现有的 `editMode`/`sourceCode`/`hasTomlError` 手动状态管理
  2. 删除 `loadSourceCode`/`translateTomlError` 等手动逻辑，由 `useConfigMode` 统一管理
  3. 源码模式保存时调用 `updateBotConfigRaw`，表单模式保存时调用 `updateBotConfigSection`
  4. 模式切换时保留未保存修改（表单草稿↔源码草稿双向同步）
- **验收条件**：[表单模式修改 → 切换源码 → 源码包含修改]；[源码修改 → 切换表单 → 表单包含修改]
- **风险**：中，需重构 bot.tsx 中的模式切换逻辑（约 200 行），需确保双向同步不丢数据

### 任务 2.4：增强敏感字段掩码展示
- **文件**：`dashboard/src/components/dynamic-form/DynamicField.tsx`
- **内容**：
  1. 扩展 `password` widget 渲染：在密码框右侧增加"查看明文"按钮（Eye/EyeOff 图标）
  2. 默认掩码显示，点击切换明文/掩码
  3. 保存时过滤未修改的敏感字段：如果字段值仍为掩码占位符（如 `••••••••`），不提交该字段
  4. 在 `DynamicFieldProps` 中新增 `originalValue` 可选属性，用于判断字段是否被修改
- **验收条件**：[查看包含 API Key 的配置] → [Key 以掩码显示；点击可查看明文；未修改 Key 时保存不覆盖原始值]
- **风险**：低，扩展现有 password 渲染，不影响其他 widget

### 任务 2.5：增强前端校验逻辑
- **文件**：`dashboard/src/components/dynamic-form/DynamicField.tsx`、`dashboard/src/components/dynamic-form/DynamicConfigForm.tsx`
- **内容**：
  1. 在 `DynamicField` 中增加前端校验：required（必填检查）、pattern（正则校验）、enum（枚举校验）、min/max（数值范围，已有部分实现）
  2. 校验失败时高亮字段边框并展示红色错误信息
  3. 在 `DynamicConfigForm` 层面增加整体验证：提交前遍历所有字段校验，任一失败阻止提交
  4. 后端校验失败时（`PARAM_CONFIG_INVALID`），高亮对应字段并展示后端返回的错误信息
- **验收条件**：[提交包含空必填字段的配置] → [对应字段高亮，错误信息清晰可读]；[输入不符合正则的值] → [字段高亮提示格式错误]
- **风险**：中，需确保校验逻辑不与现有 min/max 校验冲突

## 阶段 3：统一管理入口 — 首页概览卡片（高价值低风险）

> 依赖：无（可与阶段 1/2 并行）
> 目标：首页展示核心状态概览卡片，提供快捷操作入口

### 任务 3.1：实现系统状态卡片 SystemStatusCard
- **文件**：`dashboard/src/routes/home/cards/SystemStatusCard.tsx`（新建）
- **内容**：
  1. 展示系统运行状态：运行时间、MaiBot 版本
  2. 数据来源：复用已有的 `useBotStatus` hook 和 `useMaibotVersion` hook
  3. 卡片宽度：medium（3/10 列）
  4. 注册到 `HomeCardManager` 的内置卡片列表
- **验收条件**：[打开首页] → [展示系统状态卡片，显示运行时间和版本号]
- **风险**：低，复用已有 hook

### 任务 3.2：实现智能体状态卡片 AgentStatusCard
- **文件**：`dashboard/src/routes/home/cards/AgentStatusCard.tsx`（新建）
- **内容**：
  1. 展示智能体状态：活跃智能体数、绑定会话数
  2. 数据来源：复用已有的 `useDashboardData` hook 中的 `agent_stats` 字段
  3. 卡片宽度：medium（3/10 列）
  4. 点击卡片跳转到智能体管理页面
- **验收条件**：[打开首页] → [展示智能体状态卡片，显示活跃数和绑定会话数]
- **风险**：低

### 任务 3.3：实现 LLM 概览卡片 LLMOverviewCard
- **文件**：`dashboard/src/routes/home/cards/LLMOverviewCard.tsx`（新建）
- **内容**：
  1. 展示 LLM 调用概览：今日调用数、费用、Token 消耗
  2. 数据来源：复用已有的 `useDashboardData` hook 中的 `summary` 字段
  3. 卡片宽度：medium（3/10 列）
  4. 点击卡片跳转到 DeepSeek 监控页面
- **验收条件**：[打开首页] → [展示 LLM 概览卡片，显示今日调用数和费用]
- **风险**：低

### 任务 3.4：实现聊天流概览卡片 ChatStreamCard
- **文件**：`dashboard/src/routes/home/cards/ChatStreamCard.tsx`（新建）
- **内容**：
  1. 展示聊天流概览：活跃会话数、今日消息数
  2. 数据来源：复用已有的 `useDashboardData` hook 中的 `recent_activity` 字段
  3. 卡片宽度：medium（3/10 列）
  4. 点击卡片跳转到聊天管理页面
- **验收条件**：[打开首页] → [展示聊天流概览卡片，显示活跃会话数]
- **风险**：低

### 任务 3.5：将内置卡片注册到首页
- **文件**：`dashboard/src/routes/home/index.tsx`（或首页入口文件）
- **内容**：
  1. 将 SystemStatusCard/AgentStatusCard/LLMOverviewCard/ChatStreamCard 注册到 `HomeCardManager` 的 `cards` 属性
  2. 确保卡片数据并行加载（使用 TanStack Query 或 Promise.allSettled）
  3. 首屏渲染时间 < 2 秒
- **验收条件**：[打开首页] → [展示四类核心状态卡片，数据实时更新，首屏 < 2 秒]
- **风险**：低

### 任务 3.6：扩展快捷操作入口
- **文件**：`dashboard/src/routes/home/hooks/useQuickShortcuts.ts`
- **内容**：
  1. 在 `quickShortcutOptions` 中增加"编辑主配置"（`route:bot-config`，已有）、"编辑模型配置"（`route:model-providers`，已有）
  2. 确认"重启 MaiBot"快捷操作已有重启确认流程（复用 `useRestart`）
  3. 确认"查看日志"快捷操作已有（`route:logs`）
  4. 无需新增操作，只需确认现有快捷操作列表覆盖 spec 5.2.1 第 2 条要求
- **验收条件**：[打开首页快捷操作] → [包含重启、编辑配置、管理智能体、查看日志等入口]
- **风险**：无，确认性任务

### 任务 3.7：微调侧边栏导航分组
- **文件**：`dashboard/src/components/layout/constants.ts`
- **内容**：
  1. 将 `sidebar.groups.overview` 分组标题改为"概览"
  2. 将 `sidebar.groups.botConfig` 分组标题改为"配置"
  3. 将 `sidebar.groups.botResources` 分组标题改为"资源"
  4. 将 `sidebar.groups.extensionsMonitor` 分组标题改为"扩展"
  5. 确认分组内导航项按使用频率排序
- **验收条件**：[检查侧边栏菜单] → [分组标题为概览/配置/资源/扩展，与 spec 5.2.1 第 4 条一致]
- **风险**：无，纯 i18n 文案调整

## 阶段 4：实时监控增强 — 后端 API（中价值中风险）

> 依赖：无（可与阶段 1/2/3 并行）
> 目标：新增系统资源采集、LLM 统计增强、CSV 导出等后端端点

### 任务 4.1：新增系统资源采集端点
- **文件**：`src/webui/routers/system.py`、`src/webui/schemas/system.py`
- **内容**：
  1. 在 `schemas/system.py` 中新增 `SystemResourcesResponse` 模型（cpu_percent/memory_percent/memory_used/memory_total/disk_percent/disk_used/disk_total/database_size/timestamp）
  2. 在 `system.py` 中新增 `GET /api/webui/system/resources` 端点
  3. 使用 `psutil` 采集 CPU/内存/磁盘数据
  4. 数据库大小复用已有的 `_get_database_size()` 逻辑
  5. psutil 不可用时返回 `AppError(ErrorCode.SYS_SERVICE_UNAVAILABLE)`
- **验收条件**：[GET /api/webui/system/resources] → [返回 CPU/内存/磁盘/数据库大小数据]
- **风险**：低，psutil 在 Docker 镜像中已包含

### 任务 4.2：新增智能体维度统计端点
- **文件**：`src/webui/routers/statistics.py`、`src/webui/schemas/statistics.py`
- **内容**：
  1. 在 `schemas/statistics.py` 中新增 `AgentStatisticsItem` 模型（agent_id/request_count/total_input_tokens/total_output_tokens/total_cost/avg_response_time）和 `AgentStatisticsResponse` 模型
  2. 在 `statistics.py` 中新增 `GET /api/webui/statistics/agents?hours=24` 端点
  3. 从 ModelUsage 表按 agent_id 分组查询统计数据
  4. 返回 `ApiResponse[AgentStatisticsResponse]`
- **验收条件**：[GET /api/webui/statistics/agents?hours=24] → [返回每个智能体的调用次数、Token、费用、延迟]
- **风险**：低，需确认 ModelUsage 表有 agent_id 字段

### 任务 4.3：新增 CSV 导出端点
- **文件**：`src/webui/routers/statistics.py`
- **内容**：
  1. 新增 `GET /api/webui/statistics/export?hours=24&format=csv` 端点
  2. 查询 ModelUsage 表获取原始调用记录
  3. 使用 `StreamingResponse` 返回 CSV 文件（Content-Type: text/csv）
  4. Content-Disposition: `attachment; filename=llm_stats_{timestamp}.csv`
  5. CSV 字段：时间、智能体、模型、输入Token、输出Token、费用、延迟
- **验收条件**：[GET /api/webui/statistics/export?hours=24&format=csv] → [浏览器下载 CSV 文件，内容包含完整统计数据]
- **风险**：低

### 任务 4.4：新增系统资源 WebSocket 域
- **文件**：`src/webui/routers/websocket/domains.py`
- **内容**：
  1. 新增 `SystemResourcesEventType` 枚举（UPDATE/SNAPSHOT）
  2. 新增 `subscribe_system_resources` handler：订阅后立即推送一次 snapshot，之后每 5 秒推送 update
  3. 新增 `unsubscribe_system_resources` handler：取消订阅时停止定时推送任务
  4. 创建 `system_resources_domain = WSDomain(...)` 实例
  5. 在应用启动时调用 `ws_domain_registry.register(system_resources_domain)`
- **验收条件**：[前端订阅 system_resources 域] → [收到 snapshot 事件，之后每 5 秒收到 update 事件]
- **风险**：中，需确保定时任务在取消订阅时正确清理

### 任务 4.5：新增 LLM 调用 WebSocket 域
- **文件**：`src/webui/routers/websocket/domains.py`
- **内容**：
  1. 新增 `LLMStatsEventType` 枚举（CALL_COMPLETED/SNAPSHOT）
  2. 新增 `subscribe_llm_stats` handler：订阅后推送一次 snapshot（最近 24 小时统计摘要）
  3. 新增 `unsubscribe_llm_stats` handler
  4. 创建 `llm_stats_domain = WSDomain(...)` 实例
  5. 在应用启动时调用 `ws_domain_registry.register(llm_stats_domain)`
- **验收条件**：[前端订阅 llm_stats 域] → [收到 snapshot 事件]
- **风险**：低，域注册机制已成熟

### 任务 4.6：在 LLM 调用链路中集成事件推送触发
- **文件**：`src/webui/routers/websocket/domains.py`（或 LLM 调用完成的位置）
- **内容**：
  1. 在 LLM 调用完成后的回调中，构造 `LLMCallEvent` 数据（agent_id/model_name/input_tokens/output_tokens/cost/response_time/timestamp）
  2. 通过 `ws_domain_registry.get("llm_stats")` 获取域实例，调用域的事件推送方法
  3. 仅在有订阅者时推送（避免无谓开销）
- **验收条件**：[LLM 调用完成] → [订阅 llm_stats 域的前端收到 call_completed 事件]
- **风险**：中，需找到 LLM 调用完成的准确位置，避免影响调用性能

## 阶段 5：实时监控增强 — 前端组件（中价值中风险）

> 依赖：阶段 4（后端 API 和 WebSocket 域）
> 目标：前端消费后端数据，渲染监控面板

### 任务 5.1：实现系统资源数据 hook useSystemResources
- **文件**：`dashboard/src/hooks/useSystemResources.ts`（新建）
- **内容**：
  1. 通过 WebSocket 订阅 `system_resources` 域获取实时数据
  2. 首次加载通过 `GET /api/webui/system/resources` 获取快照
  3. WebSocket 断线时回退到 API 轮询（30 秒间隔）
  4. 返回 `data/isConnected/error/refetch`
- **验收条件**：[打开监控页面] → [系统资源数据实时更新]；[WebSocket 断线] → [数据仍通过轮询更新]
- **风险**：低

### 任务 5.2：实现 LLM 统计数据 hook useLLMStats
- **文件**：`dashboard/src/hooks/useLLMStats.ts`（新建）
- **内容**：
  1. 整合 API 历史数据查询（`GET /api/webui/statistics/agents`、`/dashboard`、`/models`）
  2. WebSocket 实时增量更新（订阅 `llm_stats` 域，call_completed 事件增量累加）
  3. 时间范围切换（1h/6h/24h/7d/30d），切换时重新获取历史数据
  4. CSV 导出功能（调用 `GET /api/webui/statistics/export`）
  5. 返回 `agentStats/modelStats/timeSeriesData/isLoading/isConnected/hours/setHours/exportCSV`
- **验收条件**：[切换时间范围] → [统计图表和指标更新]；[点击导出] → [下载 CSV 文件]
- **风险**：中，增量累加逻辑需正确处理 WebSocket 事件与历史数据的合并

### 任务 5.3：实现时间范围选择器 TimeRangeSelector
- **文件**：`dashboard/src/components/monitor/TimeRangeSelector.tsx`（新建）
- **内容**：
  1. 渲染预设时间范围按钮组：1h/6h/24h/7d/30d
  2. 当前选中的时间范围高亮
  3. 默认选中 24h
  4. 点击切换时触发 `onTimeRangeChange(hours)` 回调
- **验收条件**：[点击"7天"按钮] → [按钮高亮，回调传入 168]
- **风险**：低

### 任务 5.4：实现系统资源监控组件 SystemResourceMonitor
- **文件**：`dashboard/src/routes/monitor/system-resource-monitor.tsx`（新建）
- **内容**：
  1. 展示 CPU/内存/磁盘占用率指标卡片（数值 + 进度条）
  2. 展示数据库大小
  3. 使用 `useSystemResources` hook 获取数据
  4. WebSocket 断线时展示"实时数据已断开"提示
- **验收条件**：[打开系统资源监控] → [展示 CPU/内存/磁盘/数据库指标，数据实时更新]
- **风险**：低

### 任务 5.5：实现 LLM 统计趋势图表 LLMStatsChart
- **文件**：`dashboard/src/components/monitor/LLMStatsChart.tsx`（新建）
- **内容**：
  1. 使用 recharts 渲染按时间维度的趋势折线图（调用次数、Token、费用）
  2. 支持按智能体/模型维度切换视图
  3. 数据来源：`useLLMStats` hook 的 `timeSeriesData`
  4. 图表支持 tooltip 展示详细数据
- **验收条件**：[打开 LLM 统计面板] → [展示趋势图表，可切换智能体/模型维度]
- **风险**：低，recharts 已在项目中使用

### 任务 5.6：实现聊天流状态监控页面 ChatStreamMonitor
- **文件**：`dashboard/src/routes/monitor/chat-stream-monitor.tsx`（新建）
- **内容**：
  1. 展示聊天流状态列表：会话名称（群名/私聊名）、绑定智能体、最后活跃时间、今日消息数、会话类型
  2. 列表支持按活跃时间、消息数排序
  3. 数据来源：复用已有的 `chat-management-api.ts` 的聊天流列表 API
  4. 超过 100 条数据时使用虚拟化渲染（`@tanstack/react-virtual`）
- **验收条件**：[打开聊天流监控] → [展示所有聊天流状态，支持排序，大数据量滚动流畅]
- **风险**：低，复用已有 API

### 任务 5.7：整合监控面板入口
- **文件**：`dashboard/src/routes/monitor/index.tsx`、`dashboard/src/components/layout/constants.ts`
- **内容**：
  1. 在监控页面 `index.tsx` 中整合 SystemResourceMonitor、LLMStatsPanel（含 TimeRangeSelector + LLMStatsChart + CSV 导出按钮）、ChatStreamMonitor
  2. 在侧边栏 `constants.ts` 中新增"系统监控"导航项（路径 `/monitor`）
  3. DeepSeek 监控保持独立页面，在统一监控面板中提供概览卡片和跳转入口
- **验收条件**：[点击侧边栏"系统监控"] → [展示系统资源、LLM 统计、聊天流状态三个面板]
- **风险**：低

## 阶段 6：集成验证与清理（收尾）

> 依赖：阶段 1-5 全部完成
> 目标：端到端验证、回归测试、代码清理

### 任务 6.1：配置编辑端到端验证
- **文件**：无代码改动
- **内容**：
  1. 验证 bot 配置页：分组导航切换、表单/源码模式切换、脏状态守卫、保存后重启提示、敏感字段掩码、前端校验
  2. 验证 model 配置页：脏状态守卫、保存后重启提示
  3. 验证配置 Schema 加载失败时的错误提示
  4. 验证配置保存失败时表单内容保留
  5. 验证源码模式 TOML 语法错误时阻止切换
- **验收条件**：所有配置编辑场景功能正常，无回归问题
- **风险**：无

### 任务 6.2：首页与监控端到端验证
- **文件**：无代码改动
- **内容**：
  1. 验证首页四类状态卡片数据展示和定时刷新
  2. 验证快捷操作入口跳转正确
  3. 验证系统资源监控数据实时更新
  4. 验证 LLM 统计面板：时间范围切换、趋势图表、CSV 导出
  5. 验证聊天流状态监控：列表展示、排序
  6. 验证 WebSocket 断线提示和自动重连
- **验收条件**：所有首页和监控场景功能正常，无回归问题
- **风险**：无

### 任务 6.3：性能与兼容性验证
- **文件**：无代码改动
- **内容**：
  1. 配置页面首次加载时间不超过基线 + 500ms
  2. 首页首屏渲染时间 < 2 秒
  3. 监控面板数据刷新不导致前端渲染卡顿
  4. 现有监控页面（情绪监控、关系监控、DeepSeek 监控、MaiSaka 监控）功能不受影响
  5. 旧路径通过 TanStack Router 重定向到新路径
- **验收条件**：性能指标满足 spec 4.1 要求，现有功能无回归
- **风险**：无

### 任务 6.4：代码审查与设计回顾
- **文件**：无代码改动
- **内容**：
  1. 检查所有新增组件是否遵循 SSD2 架构（backendApi 自动解包、领域 Hook 抽取）
  2. 检查所有新增后端端点是否遵循 SSD1 规范（ApiResponse 统一响应体、AppError 错误处理）
  3. 检查 WebSocket 新增域是否通过 WSDomainRegistry 注册
  4. 检查配置字段是否由 Schema 驱动，无硬编码字段列表
  5. 确认设计与实现的一致性
- **验收条件**：代码审查通过，无遗留问题
- **风险**：无