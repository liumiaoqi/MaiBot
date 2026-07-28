# SDKMemoryKernel 完全隔离 — 编码任务

## 1. MemoryService 顶层导入消除 + getattr 链消除（第1批）

**目标**：消除 `memory_service.py` 对 A_memorix 的顶层硬依赖，同时消除 `memory_flow_service.py` 中的四层 getattr 反模式。此批改造为后续批次奠定基础——MemoryService 新增的公共方法是 WebUI 隔离的前提。

### 1.1 MemoryService 顶层导入改为延迟导入

- [ ] 修改 `src/services/memory_service.py`：删除第6行顶层导入 `from src.A_memorix.host_service import a_memorix_host_service`
- [ ] 在 `MemoryService` 类中新增 `_get_host_service()` 方法，方法体内延迟导入并返回 `a_memorix_host_service`
- [ ] 将 `_invoke()` 方法中 `a_memorix_host_service.invoke(...)` 改为 `self._get_host_service().invoke(...)`
- [ ] 检查 `memory_service.py` 中所有直接使用 `a_memorix_host_service` 的位置，统一改为 `self._get_host_service()`
- **验收**：`src/services/memory_service.py` 模块顶层不再出现 `from src.A_memorix` 导入；所有记忆检索/写入/管理功能正常

### 1.2 AMemorixHostService.invoke 新增 metadata_get_paragraphs_by_source 组件名

- [ ] 修改 `src/A_memorix/host_service.py` 的 `invoke()` 方法：在 `connectionist_stats` 分支之后、`_ADMIN_HANDLER_MAP` 之前，新增 `metadata_get_paragraphs_by_source` 分支
- [ ] 新增 `_disabled_response()` 中对应的降级响应（返回空列表）
- **验收**：`a_memorix_host_service.invoke("metadata_get_paragraphs_by_source", {"source": "test"})` 返回段落列表（或空列表）

### 1.3 MemoryService 新增 get_paragraphs_by_source 方法

- [ ] 修改 `src/services/memory_service.py`：在 `MemoryService` 类中新增 `get_paragraphs_by_source(source: str) -> list[dict[str, Any]]` 方法
- [ ] 方法内部通过 `self._invoke("metadata_get_paragraphs_by_source", {"source": source})` 委托
- [ ] A_memorix 未启用时返回空列表
- **验收**：`memory_service.get_paragraphs_by_source("chat_summary:xxx")` 返回段落列表

### 1.4 ChatSummaryWritebackService getattr 链消除

- [ ] 修改 `src/services/memory_flow_service.py` 的 `_load_last_trigger_message_count()` 方法：删除四层 getattr 链（`getattr(memory_service_module, "a_memorix_host_service", None)` → `getattr(runtime_manager, "_ensure_kernel", None)` → `await ensure_kernel()` → `getattr(kernel, "metadata_store", None)`）
- [ ] 改为直接调用 `memory_service.get_paragraphs_by_source(f"chat_summary:{session_id}")`
- [ ] 删除 `from src.services import memory_service as memory_service_module` 导入（不再需要通过模块访问属性）
- **验收**：`memory_flow_service.py` 中不再出现 `getattr.*a_memorix_host_service` 或 `getattr.*_ensure_kernel` 或 `getattr.*metadata_store`；聊天摘要写回游标恢复功能正常

## 2. WebUI runtime_registry 访问消除 + 配置管理消除（第2批）

**目标**：消除 WebUI 对 `runtime_registry` 和 `host_service` 的直接导入，所有访问改为通过 MemoryService 公共方法。此批改造后，WebUI 不再直接导入任何 A_memorix 内部模块。

### 2.1 AMemorixHostService.invoke 新增 metadata_query 组件名

- [ ] 修改 `src/A_memorix/host_service.py` 的 `invoke()` 方法：新增 `metadata_query` 分支，委托 `kernel.metadata_store.query(sql, params)`
- [ ] **SQL 只读保护**：在 `metadata_query` 分支内，对 `sql` 参数进行只读校验——仅允许以 `SELECT` 开头的 SQL 语句（大小写不敏感），非 SELECT 语句抛出 `ValueError("metadata_query 仅支持只读查询")`。这是防止 SQL 注入和误操作的最小防护，不引入过度兜底
- [ ] 新增 `_disabled_response()` 中对应的降级响应（返回空列表）
- **验收**：`a_memorix_host_service.invoke("metadata_query", {"sql": "SELECT 1", "params": ()})` 返回查询结果列表；`a_memorix_host_service.invoke("metadata_query", {"sql": "DROP TABLE xxx", "params": ()})` 抛出 ValueError

### 2.2 MemoryService 新增 query_metadata 方法

- [ ] 修改 `src/services/memory_service.py`：在 `MemoryService` 类中新增 `query_metadata(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]` 方法
- [ ] 方法内部通过 `self._invoke("metadata_query", {"sql": sql, "params": params})` 委托
- [ ] A_memorix 未启用时返回空列表
- **验收**：`memory_service.query_metadata("SELECT hash FROM paragraphs LIMIT 1")` 返回查询结果

### 2.3 MemoryService 新增配置管理方法

- [ ] 修改 `src/services/memory_service.py`：在 `MemoryService` 类中新增以下 6 个方法：
  - `get_config_schema() -> dict[str, Any]`：委托 `self._get_host_service().get_config_schema()`
  - `get_config() -> dict[str, Any]`：委托 `self._get_host_service().get_config()`
  - `get_config_path() -> str`：委托 `self._get_host_service().get_config_path()`
  - `get_raw_config_with_meta() -> dict[str, Any]`：委托 `self._get_host_service().get_raw_config_with_meta()`
  - `async update_config(config: dict[str, Any]) -> dict[str, Any]`：委托 `await self._get_host_service().update_config(config)`
  - `async update_raw_config(raw_config: str) -> dict[str, Any]`：委托 `await self._get_host_service().update_raw_config(raw_config)`
- **验收**：6 个方法可通过 `memory_service.xxx()` 调用，返回值与直接调用 `a_memorix_host_service.xxx()` 完全等价

### 2.4 WebUI 消除 runtime_registry 导入

- [ ] 修改 `src/webui/routers/memory.py`：删除第17行 `from src.A_memorix.runtime_registry import get_runtime_kernel`
- [ ] 删除 `_get_memory_metadata_store()` 函数（第723-725行）
- [ ] 改造 `_query_memory_rows()` 函数：改为调用 `memory_service.query_metadata(sql, params)`
- [ ] 所有 `_timeline_*_events` 函数和 `_graph_get_paragraph_detail` 等函数无需修改（它们只调用 `_query_memory_rows()`）
- **验收**：`src/webui/routers/memory.py` 中不再出现 `from src.A_memorix.runtime_registry` 和 `get_runtime_kernel`；WebUI 时间线功能正常

### 2.5 WebUI 消除 host_service 直接导入

- [ ] 修改 `src/webui/routers/memory.py`：删除第16行 `from src.A_memorix.host_service import a_memorix_host_service`
- [ ] 将所有 `a_memorix_host_service.get_config_schema()` 改为 `memory_service.get_config_schema()`
- [ ] 将所有 `a_memorix_host_service.get_config()` 改为 `memory_service.get_config()`
- [ ] 将所有 `a_memorix_host_service.get_config_path()` 改为 `memory_service.get_config_path()`
- [ ] 将所有 `a_memorix_host_service.get_raw_config_with_meta()` 改为 `memory_service.get_raw_config_with_meta()`
- [ ] 将所有 `await a_memorix_host_service.update_config(config)` 改为 `await memory_service.update_config(config)`
- [ ] 将所有 `await a_memorix_host_service.update_raw_config(config)` 改为 `await memory_service.update_raw_config(config)`
- **验收**：`src/webui/routers/memory.py` 中不再出现 `from src.A_memorix.host_service`；WebUI 配置管理功能（查看/编辑/保存）正常

## 3. 适配器层延迟导入消除（第3批）

**目标**：消除 `AMemorixMemoryServicePort` 中 `build_profile_injection_text` 方法对 `src.A_memorix.host_service` 的延迟导入，改为构造函数注入。

### 3.1 AMemorixMemoryServicePort 构造函数注入 host_service

- [ ] 修改 `src/core/adapters/memory_service.py`：为 `AMemorixMemoryServicePort` 新增 `__init__(self, host_service: Any) -> None` 构造函数，存储为 `self._host_service`
- [ ] 修改 `build_profile_injection_text` 方法：删除 `from src.A_memorix.host_service import a_memorix_host_service` 延迟导入，改为 `return self._host_service.build_profile_injection_text(raw_text)`
- **验收**：`src/core/adapters/memory_service.py` 中不再出现 `from src.A_memorix` 导入；`build_profile_injection_text` 功能正常

### 3.2 更新所有 AMemorixMemoryServicePort 实例化处

- [ ] 修改 `src/maisaka/agent_autonomy/agent.py`（第180-182行）：传入 `host_service` 参数
- [ ] 修改 `src/maisaka/memory/heuristic_injector.py`（第70-71行）：传入 `host_service` 参数
- [ ] 修改 `src/maisaka/agent_interaction/memory/adapter.py`（第35-36行）：传入 `host_service` 参数
- [ ] 修改 `src/maisaka/builtin_tool/context.py`（第62-63行）：传入 `host_service` 参数
- [ ] 修改 `src/maisaka/utils/tool_post_execution.py`（第62-63行）：传入 `host_service` 参数
- [ ] 修改 `src/maisaka/memory/person_profile.py`（第23-24行）：传入 `host_service` 参数
- [ ] 各实例化处通过 `from src.common.service_registry import service_registry` 获取 `host_service = service_registry.get("a_memorix")` 并传入。核心层禁止直接导入 `from src.A_memorix.host_service`，必须通过 ServiceRegistry 间接获取（与任务4.1的 ServiceRegistry 联动，因此第3批和第4批需合并执行或第4批提前到第3批之前）
- **验收**：所有 `AMemorixMemoryServicePort()` 实例化处都传入了 `host_service` 参数；`src/maisaka/` 目录中不再出现 `from src.A_memorix` 导入；核心模块记忆检索/画像注入功能正常

## 4. main.py 直接导入消除（第4批）

**目标**：消除 `main.py` 对 `a_memorix_host_service` 的直接导入，通过 ServiceRegistry 间接访问。

### 4.1 创建 ServiceRegistry 全局注册点

- [ ] 新建 `src/common/service_registry.py`，实现 `ServiceRegistry` 类：
  - `_services: dict[str, Any]` 存储注册的服务实例
  - `register(name: str, service: Any) -> None`：注册服务
  - `get(name: str) -> Any`：获取服务，未找到时抛出 KeyError（不兜底）
  - `has(name: str) -> bool`：检查服务是否已注册
- [ ] 创建模块级单例 `service_registry = ServiceRegistry()`
- **验收**：`ServiceRegistry` 可正常注册和获取服务

### 4.2 main.py 启动路径注册 A_memorix

- [ ] 修改 `src/main.py` 的 `_init_components()` 方法（第132-135行附近）：在 `a_memorix_host_service` 导入后，新增 `service_registry.register("a_memorix", a_memorix_host_service)`
- [ ] `_init_components()` 中的 `from src.A_memorix.host_service import a_memorix_host_service` 保留在函数体内（启动阶段需要创建实例，这是合理的延迟导入）
- **验收**：`_init_components()` 执行后，`service_registry.get("a_memorix")` 返回 `a_memorix_host_service` 实例

### 4.3 main.py 停止路径改为通过 ServiceRegistry

- [ ] 修改 `src/main.py` 的 `main()` 函数 finally 块（第276-283行附近）：删除 `from src.A_memorix.host_service import a_memorix_host_service` 导入
- [ ] 改为 `from src.common.service_registry import service_registry`，然后 `memorix = service_registry.get("a_memorix")`
- [ ] 将 `await a_memorix_host_service.stop()` 改为 `await memorix.stop()`（需处理 `service_registry.get()` 可能抛出 KeyError 的情况——如果 `_init_components()` 未执行到注册步骤，`get` 会抛 KeyError，这是正确行为：启动失败就不应该尝试停止）
- **验收**：`src/main.py` 的 `main()` 函数中不再出现 `from src.A_memorix` 导入；系统启动/停止流程正常

## 5. 隔离验证脚本与回归测试（第5批）

**目标**：提供自动化隔离检测能力，确保改造结果可持续维护，并验证所有改造后功能无回归。

### 5.1 编写 CI 隔离检测脚本

- [ ] 新建 `scripts/check_memorix_isolation.py`，实现以下检测规则：
  - 规则1：扫描 `src/core/` 和 `src/maisaka/`，匹配 `from src.A_memorix` → 零匹配（适配器层 `src/core/adapters/memory_service.py` 除外）
  - 规则2：扫描 `src/services/`、`src/webui/`、`src/main.py`，匹配 `from src.A_memorix.core` → 零匹配
  - 规则3：扫描 `src/`（排除 `src/A_memorix/`），匹配 `from src.A_memorix.runtime_registry` → 零匹配
  - 规则4：扫描 `src/`（排除 `src/A_memorix/`），匹配 `get_runtime_kernel` → 零匹配
  - 规则5：扫描 `src/`（排除 `src/A_memorix/`），匹配 `kernel\.metadata_store` 或 `kernel\._` → 零匹配
- [ ] 输出格式：`PASS`（零违规）或 `FAIL`（列出违规文件和行号）
- [ ] 白名单：`src/core/adapters/memory_service.py` 中的 `from src.A_memorix.host_service` 导入（构造函数注入后此导入也应消除，若已消除则无需白名单）
- **验收**：运行 `python scripts/check_memorix_isolation.py` 输出 `PASS`

### 5.2 功能回归验证

- [ ] 启动系统，验证 A_memorix 初始化成功（日志中无报错）
- [ ] 通过 WebUI 验证记忆搜索功能正常
- [ ] 通过 WebUI 验证配置查看/编辑/保存功能正常
- [ ] 通过 WebUI 验证时间线功能正常（段落/Episode/反馈/删除/画像/维护事件查询）
- [ ] 验证聊天摘要自动写回功能正常（游标恢复不重复摘要）
- [ ] 验证核心模块记忆检索/画像注入功能正常（Orchestrator/ThinkingOrgan 调用 MemoryServicePort）
- [ ] 验证系统停止流程正常（A_memorix 优雅关闭）
- **验收**：所有功能与改造前行为一致，无回归

### 5.3 隔离状态最终确认

- [ ] 运行 `python scripts/check_memorix_isolation.py`，确认输出 `PASS`
- [ ] 在 `src/core/` 和 `src/maisaka/` 目录执行 `grep -r "from src.A_memorix" .`，确认零匹配（适配器层除外）
- [ ] 在 `src/services/`、`src/webui/`、`src/main.py` 执行 `grep -r "from src.A_memorix.core" .`，确认零匹配
- [ ] 在 `src/`（排除 `src/A_memorix/`）执行 `grep -r "get_runtime_kernel" .`，确认零匹配
- [ ] 在 `src/`（排除 `src/A_memorix/`）执行 `grep -r "from src.A_memorix.runtime_registry" .`，确认零匹配
- **验收**：所有隔离检测规则通过，核心禁止项6（禁止核心导入 A_memorix 内部模块）完全满足

## 任务依赖关系

```
1.1 ──→ 1.3（MemoryService 延迟导入是新增方法的前提）
1.2 ──→ 1.3（invoke 组件名是 MemoryService 方法的前提）
1.3 ──→ 1.4（get_paragraphs_by_source 是消除 getattr 链的前提）

2.1 ──→ 2.2（invoke 组件名是 MemoryService 方法的前提）
2.2 ──→ 2.4（query_metadata 是消除 WebUI runtime_registry 的前提）
2.3 ──→ 2.5（配置管理方法是消除 WebUI host_service 导入的前提）
1.1 ──→ 2.3（MemoryService 延迟导入是新增配置方法的前提）

4.1 ──→ 4.2（ServiceRegistry 是注册的前提）
4.2 ──→ 3.2（ServiceRegistry 注册是核心层获取 host_service 的前提）
3.1 ──→ 3.2（构造函数改造是更新实例化处的前提）

1-4 全部完成 ──→ 5（验证脚本依赖所有改造完成）

注意：第4批（ServiceRegistry）必须在第3批（适配器层改造）之前执行，
因为核心层通过 ServiceRegistry 获取 host_service 引用。
```

## 改造涉及的文件清单

| 文件 | 改造类型 | 涉及任务 |
|------|---------|---------|
| `src/services/memory_service.py` | 修改 | 1.1, 1.3, 2.2, 2.3 |
| `src/A_memorix/host_service.py` | 修改 | 1.2, 2.1 |
| `src/services/memory_flow_service.py` | 修改 | 1.4 |
| `src/webui/routers/memory.py` | 修改 | 2.4, 2.5 |
| `src/core/adapters/memory_service.py` | 修改 | 3.1 |
| `src/maisaka/agent_autonomy/agent.py` | 修改 | 3.2 |
| `src/maisaka/memory/heuristic_injector.py` | 修改 | 3.2 |
| `src/maisaka/agent_interaction/memory/adapter.py` | 修改 | 3.2 |
| `src/maisaka/builtin_tool/context.py` | 修改 | 3.2 |
| `src/maisaka/utils/tool_post_execution.py` | 修改 | 3.2 |
| `src/maisaka/memory/person_profile.py` | 修改 | 3.2 |
| `src/common/service_registry.py` | 新建 | 4.1 |
| `src/main.py` | 修改 | 4.2, 4.3 |
| `scripts/check_memorix_isolation.py` | 新建 | 5.1 |