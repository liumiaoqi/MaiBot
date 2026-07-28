# WebUI 前端架构重构 — 任务列表

## 阶段 1：请求客户端层适配统一响应体（零风险引入）

### 任务 1.1：扩展 envelope.ts 支持 ApiResponse/ErrorResponse 格式
- **文件**：`dashboard/src/lib/http/envelope.ts`
- **内容**：
  1. 新增 `ApiResponseEnvelope<T>` 接口（code/data/message）
  2. 新增 `ErrorResponseEnvelope` 接口（error_code/error_message/details）
  3. 新增 `isApiResponseEnvelope()` 类型守卫
  4. 新增 `isErrorResponseEnvelope()` 类型守卫
  5. 新增 `unwrapApiResponse<T>()` 解包函数：code === 0 提取 data，code !== 0 抛出 ApiError
  6. 保留现有 `SuccessEnvelope` 和 `requireSuccess`（过渡期兼容）
- **验收条件**：`isApiResponseEnvelope({code: 0, data: {a: 1}, message: ""})` 返回 true；`unwrapApiResponse({code: 0, data: {a: 1}, message: ""}, "失败")` 返回 `{a: 1}`
- **风险**：无，纯新增类型和函数，不影响现有代码

### 任务 1.2：扩展 ApiError 支持 errorCode 字段和错误码分类
- **文件**：`dashboard/src/lib/http/errors.ts`
- **内容**：
  1. 在 `ApiError` 类中新增 `errorCode?: string` 字段
  2. 构造函数 options 中新增 `errorCode` 参数
  3. 新增 `isAuthError(error)` / `isParamError(error)` / `isBizError(error)` / `isSysError(error)` 分类判断函数
- **验收条件**：`new ApiError('test', {errorCode: 'AUTH_FAILED'})` 可正常创建；`isAuthError(err)` 返回 true
- **风险**：无，新增可选字段和函数，不影响现有 ApiError 使用

### 任务 1.3：修改请求客户端响应解析流程支持 ApiResponse 自动解包
- **文件**：`dashboard/src/lib/http/client.ts`
- **内容**：
  1. 在 HTTP 200 且 `parse === 'json'` 的分支中，`JSON.parse` 后增加格式检测：
     - 如果 `isApiResponseEnvelope(parsed)`，调用 `unwrapApiResponse(parsed, errorMessage)` 提取 data
     - 否则直接返回 parsed（兼容旧格式）
  2. 在 HTTP 非 200 的分支中，`JSON.parse` 后增加格式检测：
     - 如果 `isErrorResponseEnvelope(parsed)`，构造 `ApiError(message=error_message, errorCode=error_code, detail=details)`
     - 否则走现有的 `formatApiError` 逻辑
  3. 确保类型安全：`request<T>` 返回的 T 是 data 字段的类型
- **验收条件**：后端返回 `{code: 0, data: {agents: [...]}, message: ""}` 时，调用方直接拿到 `{agents: [...]}`；后端返回 `{error_code: "BIZ_NOT_FOUND", error_message: "资源不存在"}` + HTTP 404 时，ApiError.message 为 "资源不存在"，ApiError.errorCode 为 "BIZ_NOT_FOUND"
- **风险**：中，需确保旧格式响应不受影响；需仔细处理类型推断

### 任务 1.4：更新 http/index.ts 导出
- **文件**：`dashboard/src/lib/http/index.ts`
- **内容**：
  1. 新增导出 `ApiResponseEnvelope` / `ErrorResponseEnvelope` / `isApiResponseEnvelope` / `isErrorResponseEnvelope` / `unwrapApiResponse`
  2. 新增导出 `isAuthError` / `isParamError` / `isBizError` / `isSysError`
- **验收条件**：`import { isApiResponseEnvelope, isAuthError } from '@/lib/http'` 无报错
- **风险**：无

## 阶段 2：API 模块迁移（逐模块进行）

### 任务 2.1：迁移 agent-api.ts 路径和解包方式
- **文件**：`dashboard/src/lib/agent-api.ts`
- **内容**：
  1. 修改 `API_BASE` 从 `'/api/webui/agent'` 到 `'/api/webui/agents'`
  2. 删除所有 `requireSuccess()` 调用（解包已由请求客户端自动处理）
  3. 删除响应类型中的 `success` 字段（如 `AgentListResponse.success` → 直接定义 data 层级类型）
  4. 调整函数返回值：直接返回请求客户端解包后的 data
  5. 迁移子路径：`/list` → 根路径、`/emotion/{id}` → `/{id}/emotion`、`/relationship/{id}` → `/{id}/relationships`、`/binding/session/{id}` → `/bindings/sessions/{id}`、`/binding/group` → `/bindings/groups`、`/sessions/{id}` → `/{id}/sessions`
- **验收条件**：智能体管理页面功能正常（列表、详情、情绪、关系、绑定、重载）
- **风险**：中，路径变更需与后端兼容路由同步验证

### 任务 2.2：迁移 chat-management-api.ts 路径和解包方式
- **文件**：`dashboard/src/lib/chat-management-api.ts`
- **内容**：
  1. 新增 `API_BASE = '/api/webui/chat'` 常量
  2. 将所有硬编码的 `/api/chat/...` 路径改为 `${API_BASE}/...`
  3. 删除手动 `success` 检查（如 `result.sessions ?? []` 改为直接使用 data）
  4. 删除响应类型中的 `success` 字段
- **验收条件**：聊天管理页面功能正常（列表、详情、学习配置、发言频率、Prompt）
- **风险**：中，chat 路径前缀变更需与后端兼容路由同步验证

### 任务 2.3：迁移 system-api.ts 解包方式
- **文件**：`dashboard/src/lib/system-api.ts`
- **内容**：
  1. 删除响应类型中的 `success` 字段（如 `LocalCacheImageListResponse.success`）
  2. 调整函数返回值：直接返回请求客户端解包后的 data
- **验收条件**：设置页面中的本地缓存管理功能正常
- **风险**：低，路径无变化，只调整解包方式

### 任务 2.4：迁移 memory-api.ts 解包方式
- **文件**：`dashboard/src/lib/memory-api.ts`
- **内容**：
  1. 删除响应类型中的 `success` 字段（如 `MemoryGraphPayload.success`）
  2. 调整函数返回值：直接返回请求客户端解包后的 data
- **验收条件**：知识库/图谱页面功能正常
- **风险**：中，memory-api.ts 文件较大（1834 行），需仔细处理类型

### 任务 2.5：迁移 config-api.ts 解包方式
- **文件**：`dashboard/src/lib/config-api.ts`
- **内容**：
  1. 简化 `unwrapConfigResponse()` 逻辑：请求客户端已自动解包 ApiResponse，`unwrapConfigResponse` 只需处理 config 字段的提取
  2. 删除 `FetchModelsResponse` 中的 `success` 字段
  3. 调整 `fetchProviderModels()` 和 `fetchModelClientTypes()` 的响应解析
- **验收条件**：配置页面（bot/model/prompt）功能正常
- **风险**：低，config-api.ts 已有较完善的缓存机制，只需调整解包逻辑

### 任务 2.6：迁移 unified-ws.ts WS token 获取
- **文件**：`dashboard/src/lib/unified-ws.ts`
- **内容**：
  1. 修改 `getWsToken()` 函数：后端返回 `ApiResponse<{token: string}>` 格式，请求客户端自动解包后直接拿到 `{token: string}`
  2. 删除 `data.success && data.token` 的手动检查
- **验收条件**：WebSocket 连接正常建立，日志/聊天/监控功能正常
- **风险**：低

### 任务 2.7：迁移其他 API 模块
- **文件**：`dashboard/src/lib/emoji-api.ts`、`expression-api.ts`、`person-api.ts`、`jargon-api.ts`、`behavior-api.ts`、`deepseek-api.ts`、`planner-api.ts`、`reasoning-process-api.ts`、`prompt-api.ts`、`prompt-generator-api.ts`、`pack-api.ts`、`survey-api.ts`
- **内容**：
  1. 逐个检查各 API 模块中的 `success` 字段和手动解包逻辑
  2. 删除 `requireSuccess()` 调用和手动 `success` 检查
  3. 删除响应类型中的 `success` 字段
- **验收条件**：各对应页面功能正常
- **风险**：低，逐个迁移，影响范围可控

## 阶段 3：领域 Hook 抽取（与阶段 2 可并行）

### 任务 3.1：抽取 useAgentManagement 领域 hook
- **文件**：`dashboard/src/hooks/useAgentManagement.ts`（新建）
- **内容**：
  1. 从 `routes/agent/index.tsx` 页面中提取智能体管理状态逻辑
  2. hook 承载：智能体列表查询、详情查询、情绪/关系查询、会话绑定 CRUD、批量绑定、重载
  3. 使用 TanStack Query 的 useQuery/useMutation 管理服务端状态
  4. 对外暴露 `UseAgentManagementReturn` 接口
- **验收条件**：智能体管理页面功能不变，页面组件行数显著减少
- **风险**：中，需确保状态迁移后无功能丢失

### 任务 3.2：抽取 useChatManagement 领域 hook
- **文件**：`dashboard/src/hooks/useChatManagement.ts`（新建）
- **内容**：
  1. 从 `routes/chat-management.tsx` 页面中提取聊天管理状态逻辑
  2. hook 承载：聊天流列表查询、详情查询、学习配置更新、发言频率更新、Prompt 更新、删除
  3. 使用 TanStack Query 的 useQuery/useMutation 管理服务端状态
  4. 对外暴露 `UseChatManagementReturn` 接口
- **验收条件**：聊天管理页面功能不变，页面组件行数显著减少
- **风险**：中

### 任务 3.3：抽取 useEmotionMonitor 领域 hook
- **文件**：`dashboard/src/hooks/useEmotionMonitor.ts`（新建）
- **内容**：
  1. 从 `routes/emotion-monitor/index.tsx` 页面中提取情绪监控状态逻辑
  2. hook 承载：批量情绪查询、情绪-行为规则查询、WebSocket 事件监听
  3. 对外暴露 `UseEmotionMonitorReturn` 接口
- **验收条件**：情绪监控页面功能不变
- **风险**：低

### 任务 3.4：抽取 useRelationshipMonitor 领域 hook
- **文件**：`dashboard/src/hooks/useRelationshipMonitor.ts`（新建）
- **内容**：
  1. 从 `routes/relationship-monitor/index.tsx` 页面中提取关系监控状态逻辑
  2. hook 承载：批量关系查询、交互事件查询、交互配置查询
  3. 对外暴露 `UseRelationshipMonitorReturn` 接口
- **验收条件**：关系监控页面功能不变
- **风险**：低

### 任务 3.5：重构对应页面组件消费领域 hook
- **文件**：`dashboard/src/routes/agent/index.tsx`、`routes/chat-management.tsx`、`routes/emotion-monitor/index.tsx`、`routes/relationship-monitor/index.tsx`
- **内容**：
  1. 将页面组件中的状态逻辑替换为领域 hook 调用
  2. 页面组件只负责渲染 UI 和传递事件处理函数
  3. 删除页面组件中的 useState/useEffect + API 调用组合
- **验收条件**：页面功能不变，页面组件行数 < 150 行（不含样式）
- **风险**：中，需逐一验证功能完整性

## 阶段 4：旧格式兼容代码清理

### 任务 4.1：删除 SuccessEnvelope 和 requireSuccess
- **文件**：`dashboard/src/lib/http/envelope.ts`
- **内容**：
  1. 删除 `SuccessEnvelope` 接口
  2. 删除 `requireSuccess()` 函数
  3. 更新 `http/index.ts` 中的导出
- **前置条件**：所有 API 模块已迁移完成，不再有 `requireSuccess` 调用
- **验收条件**：`grep -r "requireSuccess" dashboard/src/` 无结果；应用功能正常
- **风险**：低，需确认所有调用方已迁移

### 任务 4.2：删除 types/api.ts 中的旧 ApiResponse 类型
- **文件**：`dashboard/src/types/api.ts`
- **内容**：
  1. 删除旧的 `ApiResponse<T>` 判别联合类型（`{success: true, data: T} | {success: false, error: string}`）
  2. 如果文件为空，删除整个文件
- **前置条件**：所有使用旧 `ApiResponse` 类型的代码已迁移
- **验收条件**：`grep -r "from.*types/api" dashboard/src/` 无结果或仅剩新类型引用
- **风险**：低

### 任务 4.3：清理 API 模块中残留的旧响应类型
- **文件**：各 `*-api.ts` 文件
- **内容**：
  1. 删除所有包含 `success: boolean` 字段的响应接口定义
  2. 将响应类型简化为 data 层级的类型（如 `AgentListResponse` → `AgentListData`）
- **前置条件**：所有 API 模块已迁移到新格式
- **验收条件**：`grep -r "success: boolean" dashboard/src/lib/` 无结果
- **风险**：低

## 阶段 5：导航结构微调与性能优化

### 任务 5.1：微调侧边栏导航分组和排序
- **文件**：`dashboard/src/components/layout/constants.ts`
- **内容**：
  1. 确认导航分组与 spec 5.4 规范一致（概览/配置/资源/扩展）
  2. 调整分组内导航项排序（高频项在前）
  3. 确认所有导航路径与 router.tsx 路由定义匹配
- **验收条件**：侧边栏菜单展示与设计规范一致
- **风险**：无，纯配置变更

### 任务 5.2：优化大数据量列表的虚拟化渲染
- **文件**：`dashboard/src/routes/chat-management.tsx`、`routes/logs.tsx` 等
- **内容**：
  1. 检查聊天流列表是否使用 `@tanstack/react-virtual` 虚拟化渲染
  2. 检查日志列表是否使用虚拟化渲染
  3. 对超过 100 条数据的列表添加虚拟化
- **验收条件**：加载 1000+ 条数据时页面滚动流畅
- **风险**：低

### 任务 5.3：优化领域 hook 的重渲染性能
- **文件**：`dashboard/src/hooks/useAgentManagement.ts` 等
- **内容**：
  1. 对 hook 返回的对象使用 `useMemo` 包裹
  2. 对 hook 返回的函数使用 `useCallback` 包裹
  3. 使用 React DevTools Profiler 验证无级联重渲染
- **验收条件**：React DevTools Profiler 显示无因 hook 返回值引用变化导致的级联重渲染
- **风险**：低

## 阶段 6：集成验证

### 任务 6.1：端到端功能验证
- **文件**：无代码改动
- **内容**：
  1. 验证所有页面功能正常（首页、智能体、情绪、关系、聊天管理、配置、资源、插件、设置）
  2. 验证错误处理正常（认证失败跳登录、参数错误高亮、业务错误提示、系统错误展示）
  3. 验证 WebSocket 连接正常（日志流、聊天流、监控流）
  4. 验证配置写入后自动 reload（修改配置 → 运行时配置已更新）
- **验收条件**：所有页面功能测试通过，无回归问题
- **风险**：低

### 任务 6.2：旧路径兼容性验证
- **文件**：无代码改动
- **内容**：
  1. 验证前端所有 API 调用均使用新路径
  2. 验证后端兼容路由仍可正常工作（作为安全网）
  3. 确认前端无硬编码旧路径
- **验收条件**：`grep -r "/api/webui/agent/" dashboard/src/` 无结果；`grep -r "/api/chat/" dashboard/src/` 无结果
- **风险**：无

### 任务 6.3：代码审查与设计回顾
- **文件**：无代码改动
- **内容**：
  1. 检查所有 API 模块是否已删除 `requireSuccess` 调用
  2. 检查所有 API 模块是否已删除 `success: boolean` 响应类型
  3. 检查领域 hook 是否与页面组件正确对接
  4. 检查请求客户端的 ApiResponse 解包逻辑是否正确处理所有边界情况
  5. 确认设计与实现的一致性
- **验收条件**：代码审查通过，无遗留问题
- **风险**：无