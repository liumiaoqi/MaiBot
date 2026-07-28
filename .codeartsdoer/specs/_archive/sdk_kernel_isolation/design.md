# **1. 实现模型**

## **1.1 上下文视图**

### 改造前

```
核心模块 ──MemoryServicePort──> AMemorixMemoryServicePort ──延迟导入──> memory_service ──延迟导入──> a_memorix_host_service
                                                                                                      │
SDKMemoryKernel ──直接导入──> llm_service / message_service / global_config / config_manager        │
子模块(15个文件) ──直接导入──> llm_service / message_service / global_config / config_manager / database
runtime_registry ──直接暴露──> SDKMemoryKernel 实例 + 内部属性
migration_router ──延迟导入──> memory_service.MemoryService
```

### 改造后

```
核心模块 ──MemoryServicePort──> AMemorixMemoryServicePort ──延迟导入──> memory_service ──延迟导入──> a_memorix_host_service
                                                                                                      │
SDKMemoryKernel <──构造注入── host_service ──注入──> LLMServicePort / MessageServicePort / config_dict
子模块 <──构造注入── SDKMemoryKernel ──传递──> llm_client / message_port / config_dict
runtime_registry ──移除──> get_runtime_kernel() / get_runtime_components()
migration_router ──回调注入──> search/ingest 回调（不再导入 memory_service）
```

## **1.2 服务/组件总体架构**

### 依赖注入容器：AMemorixServicePorts

A_memorix 内部统一的服务端口容器，由 host_service 在 `_ensure_kernel()` 时注入到 SDKMemoryKernel，再由 kernel 传递给子模块。

```python
@dataclass
class AMemorixServicePorts:
    """A_memorix 所需的外部服务端口 — 由 host_service 在启动时注入。"""
    llm_service: Any          # llm_service 模块（提供 generate/LLMServiceClient 等）
    message_service: Any      # message_service 模块（提供消息摘要等）
    config_manager: Any       # config_manager 实例（提供 get_global_config 等）
    db_session_factory: Any   # get_db_session 工厂函数
    db_person_info_model: Any # PersonInfo ORM 模型
    llm_models_client: Any    # client_registry / EmbeddingRequest 等
    llm_exceptions: Any       # NetworkConnectionError 等
```

### 注入链路

```
main.py（组合根）
  └─> host_service.start()
        └─> _ensure_kernel()
              ├─> SDKMemoryKernel(config=config, ports=ports)
              └─> kernel.initialize()  # kernel 将 ports 传递给子模块
```

### 子模块改造策略

| 子模块 | 当前依赖 | 改造方式 |
|--------|----------|----------|
| `sdk_memory_kernel.py` | llm_service, message_service, global_config | 构造注入 ports，__init__ 接收 |
| `feedback_correction.py` | llm_service, message_service | 构造注入（已有模式，LLMServiceClient 已注入） |
| `fuzzy_modify.py` | llm_service | 构造注入（已有模式，LLMServiceClient 已注入） |
| `retrieval_tuning_manager.py` | llm_service | 构造注入 llm_api 参数 |
| `web_import_manager.py` | llm_service | 构造注入 llm_api 参数 |
| `summary_importer.py` | llm_service, message_service, global_config, config_manager | 构造注入 |
| `person_profile_service.py` | llm_service, global_config, database | 构造注入 |
| `model_routing.py` | llm_service, LLMServiceResult | 函数参数注入 llm_api |
| `episode_service.py` | global_config | 构造注入 config_dict |
| `episode_segmentation_service.py` | llm_service, TaskConfig | 构造注入 llm_api |
| `llm_concept_extractor.py` | LLMServiceClient | 构造注入 llm_client |
| `api_adapter.py` | config_manager, model_configs, llm_models | 构造注入 |
| `feedback_config.py` | global_config | from_global_config 改为 from_config_dict |
| `fuzzy_modify_config.py` | global_config | from_global_config 改为 from_config_dict |
| `migration_router.py` | memory_service.MemoryService | 回调注入（search/ingest 函数） |

## **1.3 实现设计文档**

### 阶段1：AMemorixServicePorts 定义 + SDKMemoryKernel 注入点

1. 在 `src/A_memorix/core/ports.py` 定义 `AMemorixServicePorts` 数据类
2. SDKMemoryKernel.__init__ 新增 `ports: Optional[AMemorixServicePorts] = None` 参数
3. SDKMemoryKernel 消除顶层 `from src.services` / `from src.config.config` 导入，改为 `self._ports.llm_service` 等

### 阶段2：host_service 注入编排

1. host_service._ensure_kernel() 中构建 AMemorixServicePorts 实例
2. 传入 SDKMemoryKernel 构造函数
3. 消除 host_service 中的 `_get_config_manager()` 等延迟导入辅助函数（改用 ports）

### 阶段3：子模块逐个改造（按依赖深度排序）

**第1层：无 A_memorix 内部依赖的叶子模块**
- `model_routing.py`：所有函数新增 `llm_api` 参数，消除模块级导入
- `feedback_config.py`：`from_global_config()` 改为 `from_config_dict(config_dict)`
- `fuzzy_modify_config.py`：同上

**第2层：依赖第1层的模块**
- `retrieval_tuning_manager.py`：构造注入 `llm_api`
- `web_import_manager.py`：构造注入 `llm_api`
- `episode_segmentation_service.py`：构造注入 `llm_api`
- `llm_concept_extractor.py`：构造注入 `llm_client`
- `api_adapter.py`：构造注入 `config_manager`, `model_info_factory`, `embedding_client_factory`

**第3层：依赖第2层的模块**
- `person_profile_service.py`：构造注入 `llm_api`, `config_dict`, `db_session_factory`, `person_info_model`
- `summary_importer.py`：构造注入 `llm_api`, `message_api`, `config_dict`, `config_manager`
- `episode_service.py`：构造注入 `config_dict`

**第4层：SDKMemoryKernel 整合**
- kernel.initialize() 将 ports 传递给各子模块
- 消除 kernel 对 `message_api` / `LLMServiceClient` / `global_config` 的直接使用

### 阶段4：runtime_registry 隔离 + migration_router 回调注入

1. `runtime_registry.py`：移除 `get_runtime_kernel()` 和 `get_runtime_components()`
2. `search_runtime_initializer.py`：改为从 kernel 实例直接获取组件（通过 plugin_config 传递）
3. `search_execution_service.py`：同上
4. `migration_router.py`：将 `_legacy_search` / `_legacy_ingest` 中的 `MemoryService._coerce_*` 改为回调注入

### 阶段5：核心侧违规消除 + 静态守卫

1. `memory_service.py`：消除延迟导入 `a_memorix_host_service`，改用注册点或 Protocol
2. `AMemorixMemoryServicePort.set_memory_personality()`：消除直接导入 `a_memorix_host_service`
3. 添加 ruff 规则守卫

# **2. 接口设计**

## **2.1 总体设计**

核心原则：**构造函数注入优先，回调注入次之，延迟导入最后淘汰**。

A_memorix 内部模块不再直接导入 MaiBot 服务层，而是通过以下三种方式获取外部能力：
1. **构造函数注入**：子模块在 `__init__` 中接收外部服务实例
2. **回调注入**：对于仅需少量功能的场景，注入 Callable
3. **配置字典传递**：对于 global_config，传递已解析的 config_dict 而非 global_config 对象

## **2.2 接口清单**

### AMemorixServicePorts（新增）

```python
@dataclass
class AMemorixServicePorts:
    llm_service: Any
    message_service: Any
    config_manager: Any
    db_session_factory: Callable[..., Any]
    db_person_info_model: Any
    llm_models_client_registry: Any
    llm_models_exceptions: Any
    llm_models_base_client: Any
    llm_data_models: Any
```

### SDKMemoryKernel（修改）

```python
class SDKMemoryKernel:
    def __init__(
        self,
        *,
        plugin_root: Path,
        config: Optional[Dict[str, Any]] = None,
        ports: Optional[AMemorixServicePorts] = None,  # 新增
    ) -> None:
```

### FeedbackConfig / FuzzyModifyConfig（修改）

```python
@classmethod
def from_config_dict(cls, config: Dict[str, Any]) -> FeedbackConfig:
    # 从已解析的 config 字典读取，不再导入 global_config
```

### MigrationRouter（修改）

```python
class MigrationRouter:
    def __init__(
        self,
        migration_adapter: MigrationAdapter,
        memory_field: MemoryField,
        kernel: Any,
        translator: ConnectionistTranslator,
        coerce_search_result: Callable[[Any], MemorySearchResult],  # 新增
        coerce_write_result: Callable[[Any], MemoryWriteResult],    # 新增
    ) -> None:
```

### runtime_registry（删除）

移除 `get_runtime_kernel()` 和 `get_runtime_components()` 公共函数。仅保留 `set_runtime_kernel()` 供 host_service 内部使用。

# **4. 数据模型**

## **4.1 设计目标**

1. AMemorixServicePorts 是唯一的外部服务入口，所有子模块通过它获取外部能力
2. 配置数据以纯字典形式传递，不传递 global_config 对象
3. 数据库访问通过工厂函数注入，不直接导入 database 模块

## **4.2 模型实现**

### AMemorixServicePorts

```python
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class AMemorixServicePorts:
    """A_memorix 所需的外部服务端口。"""
    llm_service: Any = None
    message_service: Any = None
    config_manager: Any = None
    db_session_factory: Callable[..., Any] = None
    db_person_info_model: Any = None
    llm_models_client_registry: Any = None
    llm_models_exceptions: Any = None
    llm_models_base_client: Any = None
    llm_data_models: Any = None

    def require_llm_service(self) -> Any:
        if self.llm_service is None:
            raise RuntimeError("A_memorix: LLM 服务未注入，无法执行需要 LLM 的操作")
        return self.llm_service

    def require_message_service(self) -> Any:
        if self.message_service is None:
            raise RuntimeError("A_memorix: 消息服务未注入")
        return self.message_service
```

### host_service 构建端口

```python
# host_service._ensure_kernel() 中
from src.A_memorix.core.ports import AMemorixServicePorts

ports = AMemorixServicePorts(
    llm_service=__import__("src.services.llm_service", fromlist=["LLMServiceClient"]),
    message_service=__import__("src.services.message_service", fromlist=["message_service"]),
    config_manager=_get_config_manager(),
    db_session_factory=get_db_session,
    db_person_info_model=PersonInfo,
    llm_models_client_registry=client_registry,
    llm_models_exceptions=NetworkConnectionError,
    llm_models_base_client=EmbeddingRequest,
    llm_data_models=LLMServiceResult,
)
kernel = SDKMemoryKernel(plugin_root=repo_root(), config=config, ports=ports)
```

注：host_service 位于 `src/A_memorix/` 包内，允许导入 MaiBot 服务层（它是组合根的代理）。但 A_memorix/core/ 内部模块禁止直接导入。