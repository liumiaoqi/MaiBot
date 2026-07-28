# model_cfg_rev — 编码任务清单

## 批次 1：Protocol 定义 + 适配器实现（零风险引入）

> 本批次仅新增代码，不修改任何现有消费者，系统行为零变化。

### 1.1 定义 ModelConfigPort Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `ModelConfigPort` Protocol，包含以下方法签名：
  - `get_task_config(task_name: str, *, agent_id: str = "") -> TaskConfig`
  - `get_model_info(model_name: str) -> ModelInfo`
  - `get_provider(provider_name: str) -> APIProvider`
  - `get_model_config() -> ModelConfig`
  - `register_reload_callback(callback) -> None`
  - `unregister_reload_callback(callback) -> None`
- [ ] 在 `src/core/protocols.py` 顶部 TYPE_CHECKING 块中补充 `TaskConfig`、`ModelInfo`、`APIProvider`、`ModelConfig` 的条件导入（从 `src.config.model_configs`）
- [ ] 添加 `@runtime_checkable` 装饰器，方法文档字符串遵循现有 Protocol 风格（中文描述 + Args/Returns/Raises）

**涉及文件**：`src/core/protocols.py`

**验证标准**：
- `isinstance(adapter_instance, ModelConfigPort)` 返回 True
- ruff check 无新增错误

---

### 1.2 实现 ConfigManagerModelConfigPort 适配器

- [ ] 新建 `src/core/adapters/model_config_port.py`，实现 `ConfigManagerModelConfigPort` 类：
  - `__init__(self, config_manager: ConfigManager, agent_config_resolver: Callable[[str], AgentConfig | None])` — 持有 ConfigManager 引用 + 智能体配置解析回调
  - `get_task_config(task_name, *, agent_id="")` — 从 ConfigManager 获取全局 ModelConfig，提取 TaskConfig；若 agent_id 非空，查找 AgentConfig.model_config_override 并浅合并
  - `get_model_info(model_name)` — 遍历 `config_manager.get_model_config().models` 查找匹配项
  - `get_provider(provider_name)` — 遍历 `config_manager.get_model_config().api_providers` 查找匹配项
  - `get_model_config()` — 直接委托 `config_manager.get_model_config()`
  - `register_reload_callback(callback)` — 注册到内部回调列表；适配器自身注册为 ConfigManager 的回调，收到通知后传播
  - `unregister_reload_callback(callback)` — 从内部回调列表移除
- [ ] 实现智能体级配置浅合并算法：
  1. deepcopy 全局 TaskConfig 作为基准
  2. 遍历 override 字典，类型校验不兼容时跳过并记录 WARNING
  3. 直接替换字段（不递归合并）
  4. model_list 合并后为空时回退到全局并记录 WARNING
  5. 覆盖项引用不存在的任务名时跳过并记录 WARNING
- [ ] 实现热重载回调中继：适配器注册为 ConfigManager 的回调，收到 changed_scopes 后遍历内部回调列表传播

**涉及文件**：`src/core/adapters/model_config_port.py`（新建）

**验证标准**：
- `ConfigManagerModelConfigPort` 实例满足 `ModelConfigPort` Protocol
- `get_task_config("replyer")` 返回与 `config_manager.get_model_config().model_task_config.replyer` 一致的 TaskConfig
- `get_model_info(name)` / `get_provider(name)` 返回正确实例
- agent_id 非空且 AgentConfig.model_config_override 有值时，返回合并后的 TaskConfig
- agent_id 非空但 override 为 None 时，返回全局 TaskConfig
- 热重载回调注册/注销/传播正常工作

---

### 1.3 在 main.py 中创建适配器实例（暂不注入）

- [ ] 在 `src/main.py` 的 `_init_components` 方法中，ConfigManager 初始化之后，创建 `ConfigManagerModelConfigPort` 实例
- [ ] `agent_config_resolver` 回调暂用 `lambda aid: None`（阶段 2 接入真实 AgentRegistry）
- [ ] 仅验证适配器可创建、方法可调用，不注入到任何消费者

**涉及文件**：`src/main.py`

**验证标准**：
- 系统启动无报错
- 适配器实例创建成功，`get_task_config("replyer")` 返回正确值
- 现有消费者行为零变化

---

## 批次 2：核心消费者迁移（LLMOrchestrator + service_task_resolver + model_client）

> 本批次将 LLM 调度链路从 config_manager 直接导入迁移到 ModelConfigPort。

### 2.1 LLMOrchestrator 迁移到 ModelConfigPort

- [ ] 修改 `src/llm_models/utils_model.py`：
  - `__init__` 新增 `model_config_port: ModelConfigPort | None = None` 参数
  - 删除 `from src.config.config import config_manager`
  - `_get_task_config_or_raise()` 改用 `self._model_config_port.get_task_config(self.task_name)`，保留 EMPTY_TASK_FALLBACKS 逻辑
  - `_refresh_task_config()` 同步修改
  - 当 `model_config_port` 为 None 时抛出 RuntimeError（错误完整暴露，不兜底）
- [ ] 修改 `src/services/llm_service.py`：LLMService 构造 LLMOrchestrator 时传入 `model_config_port`
- [ ] 修改 `src/services/embedding_service.py`：EmbeddingService 构造 LLMOrchestrator 时传入 `model_config_port`
- [ ] LLMService / EmbeddingService 需要获取 ModelConfigPort 实例——通过模块级变量 + setter 注入（与 service_task_resolver 同模式）

**涉及文件**：`src/llm_models/utils_model.py`、`src/services/llm_service.py`、`src/services/embedding_service.py`

**验证标准**：
- `src/llm_models/utils_model.py` 中无 `from src.config.config import config_manager`
- LLMOrchestrator 构造时必须传入 model_config_port，缺失时 RuntimeError
- 所有 LLM 请求功能正常（replyer/planner/utils/vlm/embedding）
- 热重载后 LLMOrchestrator 实时感知配置变更

---

### 2.2 service_task_resolver 迁移到 ModelConfigPort

- [ ] 修改 `src/services/service_task_resolver.py`：
  - 删除 `from src.config.config import config_manager`
  - 新增模块级变量 `_model_config_port: ModelConfigPort | None = None`
  - 新增 `set_model_config_port(port: ModelConfigPort)` setter 函数
  - `get_available_models()` 改用 `_model_config_port.get_model_config().model_task_config`
  - `_model_config_port` 为 None 时抛出 RuntimeError

**涉及文件**：`src/services/service_task_resolver.py`

**验证标准**：
- `src/services/service_task_resolver.py` 中无 `from src.config.config import config_manager`
- `set_model_config_port()` 调用前 `get_available_models()` 抛出 RuntimeError
- 调用后功能与迁移前一致

---

### 2.3 model_client 模块迁移到 ModelConfigPort

- [ ] 修改 `src/llm_models/model_client/base_client.py`：
  - 删除 `from src.config.config import config_manager`
  - `ClientRegistry.__init__` 中 `config_manager.register_reload_callback(self.clear_client_instance_cache)` 改为通过模块级 ModelConfigPort 注入
  - 新增模块级变量 `_model_config_port: ModelConfigPort | None = None` + setter
- [ ] 修改 `src/llm_models/model_client/__init__.py`：
  - 删除 `from src.config.config import config_manager`
  - `ensure_configured_clients_loaded()` 改用 `_model_config_port.get_model_config().api_providers`
  - 模块级变量 + setter 模式

**涉及文件**：`src/llm_models/model_client/base_client.py`、`src/llm_models/model_client/__init__.py`

**验证标准**：
- 两个文件中无 `from src.config.config import config_manager`
- 客户端注册和热重载回调正常
- `ensure_configured_clients_loaded()` 正确加载配置中的客户端类型

---

### 2.4 main.py 注入 ModelConfigPort 到消费者

- [ ] 修改 `src/main.py` 的 `_init_components`：
  - 创建 `ConfigManagerModelConfigPort` 实例，`agent_config_resolver` 接入真实的智能体配置解析（从 maisaka agent registry 获取）
  - 调用 `set_model_config_port()` 注入到 service_task_resolver、llm_service、embedding_service、model_client 模块
  - 注入顺序在 ConfigManager.initialize() 之后、A_memorix 启动之前

**涉及文件**：`src/main.py`

**验证标准**：
- 所有消费者通过 ModelConfigPort 获取配置
- 系统启动后 LLM 请求、热重载功能正常
- 现有测试全部通过

---

## 批次 3：A_memorix 迁移（替换 config_manager 为 model_config_port）

> 本批次将 A_memorix 内部的 config_manager 模型配置消费迁移到 ModelConfigPort。

### 3.1 AMemorixServicePorts 新增 model_config_port 字段

- [ ] 修改 `src/A_memorix/core/ports.py`：
  - 新增 `model_config_port: Any = None` 字段（过渡期用 Any，避免 A_memorix/core/ 导入 Protocol）
  - 新增 `require_model_config_port()` 方法，None 时抛出 RuntimeError
  - 保留 `config_manager` 字段（kernel_initializer 仍需 `get_global_config()` 读取 a_memorix 配置段）

**涉及文件**：`src/A_memorix/core/ports.py`

**验证标准**：
- `AMemorixServicePorts` 同时拥有 `config_manager` 和 `model_config_port` 字段
- `require_model_config_port()` 在字段为 None 时抛出 RuntimeError

---

### 3.2 EmbeddingAPIAdapter 迁移到 ModelConfigPort

- [ ] 修改 `src/A_memorix/core/embedding/api_adapter.py`：
  - 构造参数 `config_manager` → `model_config_port`
  - `self._config_manager` → `self._model_config_port`
  - `_get_current_model_config()` → `self._model_config_port.get_model_config()`
  - `_find_model_info(model_name)` → `self._model_config_port.get_model_info(model_name)`
  - `_find_provider(provider_name)` → `self._model_config_port.get_provider(provider_name)`
  - `_resolve_candidate_model_names()` → `self._model_config_port.get_task_config("embedding")` 提取 model_list
- [ ] 修改 `create_embedding_api_adapter` 工厂函数（同文件末尾），参数同步替换

**涉及文件**：`src/A_memorix/core/embedding/api_adapter.py`

**验证标准**：
- EmbeddingAPIAdapter 构造参数无 `config_manager`，有 `model_config_port`
- 嵌入维度检测正常
- 编码请求正常

---

### 3.3 kernel_initializer 迁移

- [ ] 修改 `src/A_memorix/core/runtime/services/kernel_initializer.py`：
  - `create_embedding_api_adapter(...)` 调用处：`config_manager=kernel._ports.config_manager` → `model_config_port=kernel._ports.model_config_port`
  - 其他 `kernel._ports.config_manager` 调用（如 `get_global_config()`）保留不变

**涉及文件**：`src/A_memorix/core/runtime/services/kernel_initializer.py`

**验证标准**：
- EmbeddingAPIAdapter 通过 `kernel._ports.model_config_port` 获取配置
- `get_global_config()` 调用仍通过 `kernel._ports.config_manager`

---

### 3.4 summary_importer 迁移

- [ ] 修改 `src/A_memorix/core/utils/summary_importer.py`：
  - 构造参数 `config_manager` → `model_config_port`
  - `self._config_manager` → `self._model_config_port`
  - 内部 `self._config_manager.get_model_config()` 调用 → `self._model_config_port.get_model_config()`
  - `getattr(self._config_manager.get_model_config(), "models_dict", {})` → 通过 `self._model_config_port.get_model_config()` 获取

**涉及文件**：`src/A_memorix/core/utils/summary_importer.py`

**验证标准**：
- summary_importer 通过 ModelConfigPort 获取模型配置
- 记忆写入/检索功能正常

---

### 3.5 host_service 注入 model_config_port

- [ ] 修改 `src/A_memorix/host_service.py`：
  - `_build_service_ports()` 新增 `model_config_port` 参数，传入 `AMemorixServicePorts`
  - 在 main.py 中将 ModelConfigPort 适配器传入 `_build_service_ports()`

**涉及文件**：`src/A_memorix/host_service.py`、`src/main.py`

**验证标准**：
- A_memorix 启动后 `kernel._ports.model_config_port` 非 None
- 嵌入功能正常
- 记忆系统端到端正常

---

## 批次 4：ruff TID251 守卫封堵旧导入 + 清理

> 本批次封堵旧导入路径，确保新增代码无法绕过 ModelConfigPort。

### 4.1 新增 banned-api 规则

- [ ] 修改 `pyproject.toml`：
  - 新增 `"src.config.config.config_manager" = {msg = "禁止直接导入 config_manager 获取模型配置，请使用 ModelConfigPort Protocol 接口"}`
  - 新增 `"src.config.config.model_config" = {msg = "禁止直接导入 model_config 模块变量，请使用 ModelConfigPort Protocol 接口"}`

**涉及文件**：`pyproject.toml`

**验证标准**：
- `ruff check src/llm_models/ src/services/` 对 config_manager/model_config 导入报 TID251

---

### 4.2 扩展 per-file-ignores

- [ ] 修改 `pyproject.toml`：
  - 新增 `"src/config/config.py" = ["TID251"]` — ConfigManager 自身允许导入

**涉及文件**：`pyproject.toml`

**验证标准**：
- `ruff check src/config/config.py` 无 TID251 报错
- 适配器文件和 main.py 的 per-file-ignores 仍然生效

---

### 4.3 清理剩余的 config_manager 直接导入

- [ ] 扫描并清理 `src/llm_models/`、`src/services/` 中剩余的 `from src.config.config import config_manager` 导入
- [ ] 对 `src/services/html_render_service.py` 和 `src/services/telemetry_stats_service.py` 中的 config_manager 使用进行评估：
  - 若仅使用 `get_global_config()`（非模型配置），保留导入但添加 per-file-ignores 注释说明
  - 若使用 `get_model_config()`，迁移到 ModelConfigPort

**涉及文件**：`src/services/html_render_service.py`、`src/services/telemetry_stats_service.py` 等

**验证标准**：
- `ruff check src/llm_models/ src/services/service_task_resolver.py` 零 TID251 违规
- `ruff check src/A_memorix/core/` 零 config_manager.get_model_config() 调用

---

### 4.4 更新 AGENTS.md 核心接口层表格和核心禁止项

- [ ] 在 AGENTS.md 核心接口层表格中新增 ModelConfigPort 行
- [ ] 在核心禁止项中新增"禁止核心直接导入 config_manager 获取模型配置"
- [ ] 同步更新项目规则文件中的核心接口层表格

**涉及文件**：`AGENTS.md`、`.codeartsdoer/rule/` 规则文件

**验证标准**：
- AGENTS.md 核心接口层表格行数 == `src/core/protocols.py` 中 Protocol 数量
- 核心禁止项状态与代码实际一致

---

## 批次 5：集成验证

> 全链路端到端验证，确保迁移后系统功能完整。

### 5.1 LLM 请求链路验证

- [ ] 验证 replyer/planner/utils/vlm/embedding 各任务的 LLM 请求正常
- [ ] 验证热重载 model_config.toml 后，LLMOrchestrator 实时感知配置变更
- [ ] 验证 EMPTY_TASK_FALLBACKS 回退逻辑正常（如 expression_use → utils）

**验证标准**：
- 各任务 LLM 请求成功
- 热重载后无需重启即生效

---

### 5.2 A_memorix 嵌入链路验证

- [ ] 验证 EmbeddingAPIAdapter 通过 ModelConfigPort 获取 embedding 配置
- [ ] 验证嵌入维度检测正常
- [ ] 验证记忆写入/检索端到端正常

**验证标准**：
- 嵌入功能正常
- 记忆系统端到端正常

---

### 5.3 智能体级配置覆盖验证

- [ ] 在 AgentConfig 中配置 `model_config_override = {"replyer": {"temperature": 0.7}}`
- [ ] 验证该智能体调用 replyer 任务时使用 temperature=0.7
- [ ] 验证其他智能体仍使用全局配置
- [ ] 验证热重载后覆盖基于最新全局配置重新合并
- [ ] 验证覆盖项引用不存在的任务名时跳过并记录 WARNING
- [ ] 验证覆盖后 model_list 为空时回退到全局并记录 WARNING

**验证标准**：
- 智能体级配置覆盖生效
- 异常场景有 WARNING 日志且不阻断系统

---

### 5.4 ruff 守卫验证

- [ ] `ruff check src/llm_models src/services src/A_memorix/core` 零 TID251 违规
- [ ] `ruff check src/` 对 config_manager/model_config 的 banned-api 报错正确
- [ ] 适配器文件和 main.py 的 per-file-ignores 生效

**验证标准**：
- ruff check 无意外违规
- 守卫规则正确阻止旧导入路径