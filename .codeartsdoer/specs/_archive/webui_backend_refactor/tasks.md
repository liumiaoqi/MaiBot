# WebUI 后端架构重构 — 任务列表

## 阶段 1：基础设施（零风险引入）

### 任务 1.1：创建统一响应体和错误码体系
- **文件**：`src/webui/schemas/base.py`（新建）、`src/webui/errors/__init__.py`（新建）、`src/webui/errors/codes.py`（新建）、`src/webui/errors/app_error.py`（新建）
- **内容**：
  1. 定义 `ApiResponse[T]` 泛型模型（code/data/message）
  2. 定义 `ErrorResponse` 模型（error_code/error_message/details）
  3. 定义 `ErrorCode` 枚举（AUTH_*/PARAM_*/BIZ_*/SYS_* 共 11 个错误码）
  4. 定义 `AppError` 异常类（封装 error_code + http_status + details）
  5. 定义 `ERROR_CODE_HTTP_STATUS` 映射表（ErrorCode → HTTP 状态码）
- **验收条件**：`from src.webui.schemas.base import ApiResponse, ErrorResponse` 和 `from src.webui.errors import AppError, ErrorCode` 无报错
- **风险**：无，纯新增文件，不影响现有代码

### 任务 1.2：注册全局异常处理器
- **文件**：`src/webui/app.py`
- **内容**：
  1. 在 `create_app()` 中注册 `AppError` 异常处理器：AppError → ErrorResponse + 对应 HTTP 状态码
  2. 注册通用异常处理器：未捕获异常 → ErrorResponse(error_code=SYS_INTERNAL_ERROR, http_status=500)
  3. 异常处理器中记录完整堆栈到日志，ErrorResponse 不泄露内部细节
- **验收条件**：路由中抛出 `AppError(ErrorCode.BIZ_NOT_FOUND, "资源不存在", http_status=404)` 时，前端收到 `{"error_code": "BIZ_NOT_FOUND", "error_message": "资源不存在"}` + HTTP 404
- **风险**：低，异常处理器只在异常时触发，不影响正常流程

### 任务 1.3：创建 WebSocket 域注册表
- **文件**：`src/webui/routers/websocket/domains.py`（新建）
- **内容**：
  1. 定义 `WSDomain` 数据类（name, event_types, subscribe_handler, unsubscribe_handler）
  2. 定义 `WSDomainRegistry` 类（register/get/list_domains）
  3. 定义事件类型枚举：LogsEventType / PluginProgressEventType / MaisakaMonitorEventType / ChatEventType
  4. 创建模块级 `ws_domain_registry` 单例
- **验收条件**：`from src.webui.routers.websocket.domains import ws_domain_registry, LogsEventType` 无报错
- **风险**：无，纯新增文件

## 阶段 2：Schema 外迁与规范化

### 任务 2.1：迁移 routes.py 内联 Schema 到 schemas/auth.py
- **文件**：`src/webui/routes.py`、`src/webui/schemas/auth.py`
- **内容**：
  1. routes.py 中的 TokenVerifyRequest / TokenVerifyResponse / TokenUpdateRequest / TokenUpdateResponse / TokenRegenerateResponse / FirstSetupStatusResponse / CompleteSetupResponse / ResetSetupResponse 已在 schemas/auth.py 中有副本
  2. 修改 routes.py：删除内联 Schema 定义，改为 `from src.webui.schemas.auth import ...`
  3. 验证所有端点的 response_model 引用仍然正确
- **验收条件**：routes.py 中无 BaseModel 子类定义；`pytest` 或手动验证 auth 端点功能不变
- **风险**：低，纯代码搬迁，Schema 定义已存在

### 任务 2.2：迁移 config.py 内联 Schema 到 schemas/config.py
- **文件**：`src/webui/routers/config.py`、`src/webui/schemas/config.py`（新建）
- **内容**：
  1. 将 config.py 中的 PromptFileInfo / PromptValidationResult / PromptVersionInfo / PromptCatalogResponse / PromptFileResponse / PromptVersionFileResponse / PromptVersionListResponse / PromptUpdateRequest / PromptGeneratorChatPrompt / PromptGeneratorParsedResult / PromptGeneratorConfigBlock / PromptGeneratorRequest / PromptGeneratorResponse / PromptGeneratorApplyRequest / PromptGeneratorApplyResponse 迁移到 schemas/config.py
  2. 修改 config.py：删除内联 Schema 定义，改为 `from src.webui.schemas.config import ...`
  3. 保留 _SingleModelPromptOrchestrator 在 config.py（它是业务逻辑类，不是 Schema）
- **验收条件**：config.py 中无 BaseModel 子类定义（除 _SingleModelPromptOrchestrator 不是 BaseModel）；OpenAPI 文档中 config 端点 Schema 完整
- **风险**：中，config.py 有 15+ 个 Schema，需逐一验证引用正确

### 任务 2.3：迁移 agent.py 内联 Schema 到 schemas/agent.py
- **文件**：`src/webui/routers/agent.py`、`src/webui/schemas/agent.py`（新建）
- **内容**：
  1. 将 agent.py 中的 EmotionBaselineResponse / InternalRelationshipResponse / AgentConfigResponse / AgentListResponse / AgentDetailResponse / SessionBindingResponse / BindSessionRequest / BatchBindItem / BatchBindRequest / BatchBindError / BatchBindResponse / BindGroupRequest / GroupBindingResponse / GroupBindingsListResponse / CohabitantInfo / SessionAgentInfo / SessionsByAgentResponse / ReloadResponse / EmotionStateResponse / RelationshipSummaryResponse 迁移到 schemas/agent.py
  2. 修改 agent.py：删除内联 Schema 定义，改为 `from src.webui.schemas.agent import ...`
- **验收条件**：agent.py 中无 BaseModel 子类定义；agent 端点功能不变
- **风险**：低，Schema 较多但结构简单

### 任务 2.4：迁移 memory.py 内联 Schema 到 schemas/memory.py
- **文件**：`src/webui/routers/memory.py`、`src/webui/schemas/memory.py`（新建）
- **内容**：
  1. 将 memory.py 中的所有 BaseModel 子类（NodeRequest / EdgeCreateRequest / EdgeDeleteRequest / ImportChatTarget / MemoryTimelineEvent / MemoryTimelineResponse 等 20+ 个）迁移到 schemas/memory.py
  2. 修改 memory.py：删除内联 Schema 定义，改为 `from src.webui.schemas.memory import ...`
- **验收条件**：memory.py 中无 BaseModel 子类定义；memory 端点功能不变
- **风险**：中，Schema 数量多，需仔细处理类型引用

### 任务 2.5：迁移 system.py 内联 Schema 到 schemas/system.py
- **文件**：`src/webui/routers/system.py`、`src/webui/schemas/system.py`（新建）
- **内容**：
  1. 将 system.py 中的 RestartResponse / StatusResponse / CacheDirectoryStats / DatabaseFileStats / DatabaseTableStats / DatabaseStorageStats / LocalCacheStatsResponse / LocalCacheImageItem / LocalCacheImageDateGroup / LocalCacheImageListResponse / LocalCacheLogDirectoryItem / LocalCacheLogDirectoryListResponse / LocalCacheDataEntry / LocalCacheDataEntriesResponse / LocalCacheCleanupRequest / LocalCacheCleanupResponse / LocalCacheDatabaseVacuumResponse / LocalCacheImageDeleteRequest / LocalCacheImageBulkDeleteRequest / LocalCacheLogDirectoryDeleteRequest / LocalCacheDataEntryDeleteRequest 迁移到 schemas/system.py
  2. 修改 system.py：删除内联 Schema 定义，改为 `from src.webui.schemas.system import ...`
- **验收条件**：system.py 中无 BaseModel 子类定义；system 端点功能不变
- **风险**：低

### 任务 2.6：补全 response_model 声明
- **文件**：`src/webui/routes.py`、各路由文件
- **内容**：
  1. 为 health_check 端点添加 response_model
  2. 为 logout / check_auth 端点添加 response_model
  3. 检查所有路由端点，确保均有 response_model 声明
- **验收条件**：`/openapi.json` 中所有端点均有响应 Schema 定义
- **风险**：低

## 阶段 3：统一响应体迁移

### 任务 3.1：创建响应包装依赖
- **文件**：`src/webui/schemas/base.py`
- **内容**：
  1. 创建 `wrap_response` 辅助函数：将业务数据包装为 `ApiResponse(data=..., message=...)`
  2. 不使用中间件自动包装（中间件会破坏 response_model 的 OpenAPI 生成），而是在路由处理函数中显式调用
  3. 设计决策理由：FastAPI 的 response_model 机制与中间件自动包装冲突，中间件包装后 OpenAPI 文档无法展示实际响应结构。显式包装虽然多一行代码，但 OpenAPI 文档准确
- **验收条件**：`wrap_response(data={"key": "value"}, message="操作成功")` 返回 `ApiResponse(code=0, data={"key": "value"}, message="操作成功")`
- **风险**：无

### 任务 3.2：迁移 auth 路由到统一响应体
- **文件**：`src/webui/routes.py`
- **内容**：
  1. 修改 verify_token / logout / check_auth / update_token / regenerate_token / get_setup_status / complete_setup / reset_setup 端点
  2. 将返回值从裸 Pydantic model 或 dict 改为 `ApiResponse(data=..., message=...)`
  3. 将 HTTPException 改为 `raise AppError(ErrorCode.AUTH_FAILED, ...)`
  4. 更新 response_model 为 `ApiResponse[OriginalResponse]`
- **验收条件**：auth 端点返回 `{"code": 0, "data": {...}, "message": "..."}` 格式
- **风险**：中，前端适配在 SSD2 中处理，需保留兼容路由

### 任务 3.3：迁移 agent 路由到统一响应体
- **文件**：`src/webui/routers/agent.py`
- **内容**：
  1. 修改 list_agents / get_agent_detail / get_agent_emotion / get_agent_relationships / get_session_binding / bind_session_agent / unbind_session_agent 等端点
  2. 将 `AgentListResponse(success=True, ...)` 改为 `ApiResponse(data=AgentListData(...), message="...")`
  3. 将 HTTPException 改为 AppError
- **验收条件**：agent 端点返回统一响应体格式
- **风险**：中

### 任务 3.4：迁移 system 路由到统一响应体
- **文件**：`src/webui/routers/system.py`
- **内容**：
  1. 修改 restart / status / local_cache_stats 等端点
  2. 将 `RestartResponse(success=True, ...)` 改为 `ApiResponse(data=..., message="...")`
  3. 将 HTTPException 改为 AppError
- **验收条件**：system 端点返回统一响应体格式
- **风险**：低

### 任务 3.5：迁移 config 路由到统一响应体
- **文件**：`src/webui/routers/config.py`
- **内容**：
  1. 修改所有 config 端点的返回值为 ApiResponse 格式
  2. 将 HTTPException 改为 AppError（配置校验失败 → PARAM_CONFIG_INVALID，配置写入失败 → BIZ_CONFIG_WRITE_FAILED）
  3. 统一配置写入路径：所有写入操作通过 config_manager 入口，写入后触发 reload
- **验收条件**：config 端点返回统一响应体格式；配置写入后运行时配置已更新
- **风险**：中，config 路由数量多，需逐一迁移

### 任务 3.6：迁移 memory 路由到统一响应体
- **文件**：`src/webui/routers/memory.py`
- **内容**：
  1. 修改所有 memory 端点的返回值为 ApiResponse 格式
  2. 将 HTTPException 改为 AppError
- **验收条件**：memory 端点返回统一响应体格式
- **风险**：中

## 阶段 4：路由规范化与兼容层

### 任务 4.1：创建 agent 路由别名（复数名词）
- **文件**：`src/webui/routers/agent.py`
- **内容**：
  1. 新增 `/agents` 前缀的路由器，端点路径与 `/agent` 相同
  2. 两个路由器指向同一处理函数，无代码重复
  3. 旧 `/agent` 路由标记为 deprecated（日志记录）
- **验收条件**：`GET /api/webui/agents` 和 `GET /api/webui/agent/list` 返回相同数据
- **风险**：低

### 任务 4.2：创建 chat 兼容路由
- **文件**：`src/webui/routers/chat/routes.py`、`src/webui/routers/__init__.py`
- **内容**：
  1. 在 chat/routes.py 中新增 compat_router，prefix 为 `/api/chat`
  2. compat_router 的端点调用主路由的处理函数
  3. 在 `get_all_routers()` 中注册 compat_router
- **验收条件**：`/api/chat/sessions` 和 `/api/webui/chat/sessions` 返回相同数据
- **风险**：低

### 任务 4.3：标记旧 WebSocket 端点为 deprecated
- **文件**：`src/webui/logs_ws.py`
- **内容**：
  1. 在 `/ws/logs` 端点添加 deprecation 日志
  2. 不删除旧端点，保持功能不变
- **验收条件**：连接 `/ws/logs` 时日志输出 deprecation 警告
- **风险**：无

## 阶段 5：WebSocket 域注册表集成

### 任务 5.1：注册四个域到 WSDomainRegistry
- **文件**：`src/webui/routers/websocket/domains.py`、`src/webui/routers/websocket/unified.py`
- **内容**：
  1. 在 domains.py 中创建四个域实例：LogsDomain / PluginProgressDomain / MaisakaMonitorDomain / ChatDomain
  2. 每个域定义 event_types 集合和 subscribe_handler
  3. 在应用启动时调用 `ws_domain_registry.register(...)` 注册四个域
  4. 修改 unified.py 的 `_handle_subscribe`：从 if-elif 链改为查询 `ws_domain_registry.get(domain)`
- **验收条件**：WebSocket 订阅行为不变；新增域只需注册到 registry，无需修改 unified.py
- **风险**：中，需确保域处理逻辑迁移后行为一致

### 任务 5.2：将 chat 域的 call 分发改为注册表
- **文件**：`src/webui/routers/websocket/domains.py`
- **内容**：
  1. 为 ChatDomain 添加 call_handler 字段
  2. 修改 unified.py 的 `_handle_call`：从 if-elif 链改为查询 registry
- **验收条件**：chat 域的 call 操作行为不变
- **风险**：中

## 阶段 6：配置管理统一化

### 任务 6.1：统一配置写入入口
- **文件**：`src/webui/routers/config.py`
- **内容**：
  1. 审查 config.py 中所有配置写入路径
  2. 将直接调用 `save_toml_with_format` 的端点改为通过 config_manager 统一入口
  3. 写入后调用 `config_manager.reload()` 确保运行时配置更新
  4. 保留 `save_toml_with_format` 作为 config_manager 内部使用的工具函数
- **验收条件**：通过 API 修改配置后，`config_manager.global_config` 的值已更新
- **风险**：中，需确保 reload 逻辑正确

### 任务 6.2：配置写入错误处理统一
- **文件**：`src/webui/routers/config.py`
- **内容**：
  1. 配置写入失败 → `AppError(ErrorCode.BIZ_CONFIG_WRITE_FAILED, ...)`
  2. 配置校验失败 → `AppError(ErrorCode.PARAM_CONFIG_INVALID, details={"fields": [...]})`
  3. 删除裸 HTTPException，统一使用 AppError
- **验收条件**：配置错误返回 ErrorResponse 格式
- **风险**：低

## 阶段 7：测试基础设施

### 任务 7.1：创建 WebUI 测试框架
- **文件**：`tests/webui/conftest.py`（新建）、`tests/webui/__init__.py`（新建）
- **内容**：
  1. 创建 httpx AsyncClient fixture（基于 FastAPI TestClient）
  2. 创建认证 fixture：自动获取有效 token 并设置 Cookie
  3. 创建断言工具：`assert_api_success(response, expected_data)` / `assert_api_error(response, expected_error_code)`
- **验收条件**：`pytest tests/webui/` 可运行，fixture 正常工作
- **风险**：低

### 任务 7.2：编写 auth 路由集成测试
- **文件**：`tests/webui/test_auth.py`（新建）
- **内容**：
  1. 测试 verify_token 成功/失败
  2. 测试 check_auth 已认证/未认证
  3. 测试 update_token / regenerate_token
  4. 测试错误响应格式（ErrorResponse）
- **验收条件**：auth 路由测试通过
- **风险**：低

### 任务 7.3：编写 config 路由集成测试
- **文件**：`tests/webui/test_config.py`（新建）
- **内容**：
  1. 测试获取配置 Schema
  2. 测试读取/写入配置
  3. 测试配置校验失败错误响应
  4. 测试 Prompt 相关端点
- **验收条件**：config 核心路由测试通过
- **风险**：低

### 任务 7.4：编写 agent 路由集成测试
- **文件**：`tests/webui/test_agent.py`（新建）
- **内容**：
  1. 测试 list_agents / get_agent_detail
  2. 测试 get_agent_emotion / get_agent_relationships
  3. 测试 session binding CRUD
- **验收条件**：agent 核心路由测试通过
- **风险**：低

### 任务 7.5：编写 WebSocket 域注册表单元测试
- **文件**：`tests/webui/test_ws_domains.py`（新建）
- **内容**：
  1. 测试 WSDomainRegistry.register / get / list_domains
  2. 测试订阅不存在的域返回错误
  3. 测试事件类型枚举完整性
- **验收条件**：域注册表测试通过
- **风险**：低

## 阶段 8：OpenAPI 文档完善

### 任务 8.1：配置 FastAPI OpenAPI 元信息
- **文件**：`src/webui/app.py`
- **内容**：
  1. 设置 title="MaiBot WebUI API"、description="MaiBot WebUI 后端 API 文档"、version="2.0.0"
  2. 为所有端点补全 summary 和 description（中文）
- **验收条件**：`/docs` 页面展示完整的中文 API 文档
- **风险**：低

### 任务 8.2：保护 OpenAPI 文档端点
- **文件**：`src/webui/app.py`
- **内容**：
  1. 确保 `/docs` 和 `/openapi.json` 端点受认证保护
  2. 可通过 FastAPI 的 `docs_url` 和 `openapi_url` 配合依赖注入实现
- **验收条件**：未认证访问 `/docs` 返回 401
- **风险**：低