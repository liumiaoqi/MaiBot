# SDKMemoryKernel 完全隔离 — 实施任务列表

## 阶段1：AMemorixServicePorts 定义 + SDKMemoryKernel 注入点

- [x] T1.1 新建 `src/A_memorix/core/ports.py`，定义 `AMemorixServicePorts` 数据类
  - 验收：文件存在，包含 llm_service/message_service/config_manager/db_session_factory/db_person_info_model/llm_models_* 字段
  - 验收：包含 require_llm_service() / require_message_service() 方法

- [x] T1.2 SDKMemoryKernel.__init__ 新增 `ports: Optional[AMemorixServicePorts] = None` 参数
  - 验收：`self._ports = ports` 存储在实例上
  - 验收：SDKMemoryKernel 顶层 `from src.services` / `from src.config.config` 导入移除
  - 验收：`self._feedback_classifier` 和 `self._fuzzy_modify_planner` 从 `self._ports.llm_service` 创建

## 阶段2：host_service 注入编排

- [x] T2.1 host_service._ensure_kernel() 构建 AMemorixServicePorts 实例
  - 验收：从 MaiBot 服务层导入具体类，构建 ports 对象
  - 验收：传入 SDKMemoryKernel 构造函数
  - 验收：host_service 自身的 `_get_config_manager()` / `_get_bot_config_path()` 保留（host_service 允许导入 MaiBot 服务）

## 阶段3：子模块逐个改造（按依赖深度排序）

### 第1层：叶子模块

- [x] T3.1 `model_routing.py`：消除 `from src.services import llm_service` 和 `from src.common.data_models.llm_service_data_models import LLMServiceResult`
  - 改造：所有函数新增 `llm_api` 参数（已有 `get_text_generation_model_tasks(llm_api)` 模式）
  - 改造：`generate_with_resolved_model()` 新增 `llm_api` 参数
  - 验收：文件中搜索 `from src.services` → 无匹配
  - 注意：`from src.common.data_models.llm_service_data_models import LLMServiceResult` 保留（共享数据模型，允许）

- [x] T3.2 `feedback_config.py`：`from_global_config()` 改为 `from_config_dict(config_dict)`
  - 改造：从传入的 config 字典读取，不再导入 global_config
  - 验收：文件中搜索 `from src.config.config` → 无匹配

- [x] T3.3 `fuzzy_modify_config.py`：同 T3.2
  - 验收：文件中搜索 `from src.config.config` → 无匹配

### 第2层：依赖第1层的模块

- [x] T3.4 `retrieval_tuning_manager.py`：消除 `from src.services import llm_service`
  - 改造：构造函数新增 `llm_api` 参数，内部使用注入的 llm_api
  - 改造：model_routing 调用传递 llm_api 参数
  - 验收：文件中搜索 `from src.services` → 无匹配

- [x] T3.5 `web_import_manager.py`：消除 `from src.services import llm_service`
  - 改造：通过 `plugin._ports.require_llm_service()` 获取 llm_api
  - 验收：文件中搜索 `from src.services` → 无匹配

- [x] T3.6 `episode_segmentation_service.py`：消除 `from src.services import llm_service` 和 `from src.config.model_configs import TaskConfig`
  - 改造：构造函数新增 `llm_api` 参数
  - 验收：文件中搜索 `from src.services` → 无匹配
  - 验收：文件中搜索 `from src.config` → 无匹配

- [x] T3.7 `llm_concept_extractor.py`：消除 `from src.services.llm_service import LLMServiceClient`
  - 改造：构造函数 `llm_client` 改为必选参数，删除延迟导入回退
  - 改造：MemoryField 新增 `llm_client` 注入
  - 验收：文件中搜索 `from src.services` → 无匹配

- [x] T3.8 `api_adapter.py`：消除 `from src.config.config import config_manager` / `from src.config.model_configs import APIProvider, ModelInfo` / `from src.llm_models.*`
  - 改造：构造函数新增 `config_manager` / `client_registry` / `embedding_request_cls` / `network_connection_error_cls` 参数
  - 验收：文件中搜索 `from src.config` → 无匹配
  - 验收：文件中搜索 `from src.llm_models` → 无匹配

### 第3层：依赖第2层的模块

- [x] T3.9 `person_profile_service.py`：消除 4 处违规导入（llm_service / global_config / database / database_model）
  - 改造：构造函数新增 `llm_api` / `db_session_factory` / `person_info_model` 参数
  - 验收：文件中搜索 `from src.services` → 无匹配
  - 验收：文件中搜索 `from src.config` → 无匹配
  - 验收：文件中搜索 `from src.common.database` → 无匹配

- [x] T3.10 `summary_importer.py`：消除 4 处违规导入（llm_service / message_service / global_config / config_manager / TaskConfig）
  - 改造：构造函数新增 `llm_api` / `message_api` / `config_manager` 参数
  - 验收：文件中搜索 `from src.services` → 无匹配
  - 验收：文件中搜索 `from src.config` → 无匹配

- [x] T3.11 `episode_service.py`：消除 `from src.config.config import global_config`
  - 改造：构造函数新增 `config_dict` 参数（已有 plugin_config，合并使用）
  - 验收：文件中搜索 `from src.config` → 无匹配

### 第4层：SDKMemoryKernel 整合

- [x] T3.12 SDKMemoryKernel.initialize() 将 ports 传递给各子模块
  - 改造：所有子模块创建时传递注入的 llm_api / message_api / config_dict 等
  - 改造：kernel 自身使用 `self._ports.require_llm_service()` 替代 `from src.services`
  - 验收：sdk_memory_kernel.py 中搜索 `from src.services` → 无匹配
  - 验收：sdk_memory_kernel.py 中搜索 `from src.config.config` → 无匹配

- [x] T3.13 feedback_correction.py：消除 `from src.services import message_service` 和 `from src.services.llm_service import LLMServiceClient`
  - 改造：LLMServiceClient 已通过构造注入，message_service 改为构造注入
  - 验收：文件中搜索 `from src.services` → 无匹配

- [x] T3.14 fuzzy_modify.py：消除 `from src.services.llm_service import LLMServiceClient`
  - 改造：LLMServiceClient 已通过构造注入
  - 验收：文件中搜索 `from src.services` → 无匹配

## 阶段4：runtime_registry 隔离 + migration_router 回调注入

- [x] T4.1 runtime_registry.py：移除 `get_runtime_kernel()` 和 `get_runtime_components()` 公共函数
  - 改造：仅保留 `set_runtime_kernel()` 供 host_service 内部使用
  - 验收：`src/A_memorix/core/` 中搜索 `get_runtime_kernel` / `get_runtime_components` → 无匹配

- [x] T4.2 search_runtime_initializer.py：消除对 `get_runtime_components()` 的依赖
  - 改造：删除 fallback 分支，plugin_config 未提供组件时直接返回空 bundle
  - 验收：文件中搜索 `get_runtime_components` → 无匹配

- [x] T4.3 search_execution_service.py：消除对 `get_runtime_kernel()` 的依赖
  - 改造：删除 fallback 分支，plugin_config 未提供 plugin_instance 时返回 None
  - 验收：文件中搜索 `get_runtime_kernel` → 无匹配

- [x] T4.4 migration_router.py：消除 `from src.services.memory_service import MemoryService`
  - 改造：内联 `_coerce_search_result` / `_coerce_write_result` 函数
  - 改造：`build_profile_injection_text` 中的 `from src.A_memorix.host_service` 改为回调注入
  - 验收：文件中搜索 `from src.services` → 无匹配
  - 验收：文件中搜索 `from src.A_memorix.host_service` → 无匹配

## 阶段5：核心侧违规消除 + 静态守卫

- [x] T5.1 memory_service.py：消除延迟导入 `a_memorix_host_service`
  - 注意：`_get_host_service()` 的延迟导入保留（MemoryService 是服务层，允许导入 host_service）
  - 注意：`build_profile_injection_text` 的延迟导入保留（同上）
  - 改造：新增 `register_agent()` 方法，供适配器层调用

- [x] T5.2 AMemorixMemoryServicePort.set_memory_personality()：消除直接导入 `a_memorix_host_service`
  - 改造：改为通过 `memory_service.register_agent()` 中转
  - 验收：文件中搜索 `from src.A_memorix` → 无匹配

- [x] T5.3 验证：全局扫描确认零违规
  - 验收：`src/A_memorix/core/` 中搜索 `from src.services` → 无匹配 ✅
  - 验收：`src/A_memorix/core/` 中搜索 `from src.config.config` → 无匹配 ✅
  - 验收：`src/A_memorix/core/` 中搜索 `from src.common.database` → 无匹配 ✅
  - 验收：`src/A_memorix/core/` 中搜索 `from src.llm_models` → 无匹配 ✅
  - 验收：`src/core/` 中搜索 `from src.A_memorix` → 无匹配 ✅
  - 验收：`src/A_memorix/core/` 中搜索 `from src.A_memorix.host_service` → 无匹配 ✅

- [ ] T5.4 添加 ruff 守卫规则（可选，视项目配置）
  - 改造：在 ruff 配置中添加 banned-imports 规则
  - 验收：核心模块新增 `from src.A_memorix.core` 导入时 CI 检查失败
