# Phoenix-4：能力层 Protocol 化 — 技术设计

# **1. 设计目标**

将组件层对 `global_config`/`config_manager` 的直接访问替换为 Protocol 接口调用，消除 noqa TID251 整体对象遗留（23→~11），新增必要的 Protocol 方法和快照类型，并通过 docstring 分组优化 AppConfigPort（~82 方法）的可读性。

# **2. 整体架构**

## **2.1 改造路径**

```
组件层代码 ──(直接导入 global_config)──→ global_config
     ↓ 改造后
组件层代码 ──(Protocol 方法调用)──→ AppConfigPort / ModelConfigPort / ChatConfigPort
                                         ↓ 适配器层
                                    GlobalConfig*Port ──(合法导入)──→ global_config
```

## **2.2 noqa TID251 分类与处置**

| 分类 | 数量 | 处置 |
|------|------|------|
| 可立即拆解（已有 Port 方法） | 5 | 直接替换导入为 Port 调用 |
| 需新增 Port 方法 | 7 | 扩展 Protocol + 适配器 + 替换 |
| 暂不可拆解（整体对象/反射） | 6 | 保留 noqa + 注释原因 |
| 适配器层合法 | 4 | 不动 |

## **2.3 AppConfigPort 组织策略**

采用 **docstring 分组**模式：在 AppConfigPort 的 docstring 中按配置域分组注释，不拆分为子 Protocol。

**理由**（CC 审查 Q2 结论）：
1. 现有代码全部通过 `AppConfigPort` 访问，子 Protocol 只在文档层面提供分类，无实际调用方
2. 5 个子 Protocol + 继承组合增加 `protocols.py` 复杂度，但 `@runtime_checkable` 对多继承组合的可靠性未经验证
3. docstring 分组注释能达到同样的"让开发者更容易找到对应方法"的效果
4. 如果未来有调用方只需要 emoji 配置，届时再拆分不迟

```python
@runtime_checkable
class AppConfigPort(Protocol):
    """应用配置查询接口。
    
    配置域分组：
    - Emoji: get_emoji_*, get_emoji_cache_cleanup_*
    - Visual: get_visual_*, get_image_cache_cleanup_*
    - Expression/Jargon: get_expression_*, get_jargon_*
    - PluginRuntime: get_plugin_runtime_*, get_mcp_*
    - System: get_debug_*, get_experimental_*, get_webui_*, get_log_*, ...
    """
```

注册表不变。

# **3. noqa TID251 可立即拆解（5 处）**

## **3.1 emoji_manager.py**

**现状**：导入 `config_manager`，使用 `get_model_config()`、`register_reload_callback()`、`unregister_reload_callback()`。

**改造**：注入 `ModelConfigPort` + `AppConfigPort`，替换为：
- `config_manager.get_model_config()` → `model_config_port.get_model_config()`
- `config_manager.register_reload_callback(cb)` → `app_config_port.register_reload_callback(cb)`
- `config_manager.unregister_reload_callback(cb)` → `app_config_port.unregister_reload_callback(cb)`

**注入方式**：`EmojiManager` 是模块级单例（`emoji_manager.py:1320`，21 处导入）。不能简单改 `__init__` 参数——模块级实例化时 port 可能尚未注册。

**方案**：采用延迟注入模式——`EmojiManager.__init__` 不变，新增 `set_ports(model_config_port, app_config_port)` 方法，在 `main.py` 初始化阶段调用。内部访问改为 `self._model_config_port.get_model_config()` 而非 `config_manager.get_model_config()`。`_model_config_port` 初始为 None，访问时如果为 None 则 fallback 到 `config_manager`（过渡期兼容）。

```python
class EmojiManager:
    _model_config_port: ModelConfigPort | None = None
    _app_config_port: AppConfigPort | None = None
    
    def set_ports(self, model_config_port: ModelConfigPort, app_config_port: AppConfigPort) -> None:
        self._model_config_port = model_config_port
        self._app_config_port = app_config_port
    
    def _get_model_config(self):
        if self._model_config_port is not None:
            return self._model_config_port.get_model_config()
        from src.config.config import config_manager  # noqa: TID251 — 过渡期 fallback
        return config_manager.get_model_config()
```

## **3.2 expression_selector.py**

**现状**：导入 `model_config`，使用 `model_config.model_task_config.embedding.model_list`。

**改造**：注入 `ModelConfigPort`，替换为 `model_config_port.get_task_config("embedding").model_list`。

**注意**：`ModelConfigPort.get_task_config()` 已存在（`src/core/protocols.py:746`），返回 `TaskConfig`，其 `model_list: list[str]` 字段可直接使用。

## **3.3 reply.py**

**现状**：导入 `config_module` 但未使用。

**改造**：直接删除导入行。

## **3.4 remote.py**

**现状**：导入 `MMC_VERSION` 常量，用于构建心跳包。

**改造**：在 `AppConfigPort` 新增 `get_mmc_version() -> str` 方法。`remote.py` 注入 `AppConfigPort`，调用 `app_config_port.get_mmc_version()`。

## **3.5 service_task_resolver.py**

**现状**：过渡期 fallback 导入 `config_manager`，当 Port 未注册时触发。

**改造**：`ModelConfigPort` 已在运行时注册（SSD-12 完成），fallback 路径不再触发。直接删除 fallback 分支和 noqa 导入。

# **4. noqa TID251 需新增 Port 方法（7 处）**

## **4.1 新增 Protocol 方法总表**

| Protocol | 新方法 | 签名 | 替代文件 |
|----------|--------|------|----------|
| ModelConfigPort | `list_model_names` | `def list_model_names(self) -> list[str]` | mode_utils, send_emoji |
| AppConfigPort | `get_mmc_version` | `def get_mmc_version(self) -> str` | remote |
| AppConfigPort | `get_emoji_cache_cleanup_config` | `def get_emoji_cache_cleanup_config(self) -> CacheCleanupConfig` | emoji_cache_cleanup |
| AppConfigPort | `get_image_cache_cleanup_config` | `def get_image_cache_cleanup_config(self) -> CacheCleanupConfig` | image_cache_cleanup |
| AppConfigPort | `get_maim_message_config` | `def get_maim_message_config(self) -> MaimMessageConfigSnapshot` | api.py |
| AppConfigPort | `get_jargon_learning_list` | `def get_jargon_learning_list(self) -> list[str]` | utils_config |
| AppConfigPort | `get_jargon_groups` | `def get_jargon_groups(self) -> list[Any]` | utils_config |
| ChatConfigPort | `get_reply_style_chat_prompts` | `def get_reply_style_chat_prompts(self) -> list[str]` | utils_config |

## **4.2 新增快照类型**

### **4.2.1 CacheCleanupConfig**

```python
@dataclass(frozen=True)
class CacheCleanupConfig:
    """缓存清理配置快照 — emoji/image cache_cleanup 通用。"""
    enabled: bool = False
    check_interval_hours: float = 24.0
    file_retention_days: float = 30.0
    no_file_record_retention_days: float = 90.0
```

emoji 和 image 的 cache_cleanup 结构高度相似，用同一个快照类型。适配器实现中从各自的配置域映射字段：

- emoji: `emoji_file_retention_days` → `file_retention_days`
- image: `image_file_retention_days` → `file_retention_days`

### **4.2.2 MaimMessageConfigSnapshot**

```python
@dataclass(frozen=True)
class MaimMessageConfigSnapshot:
    """MaimMessage 配置快照 — 替代 global_config.maim_message 整体对象。"""
    enable_api_server: bool = False
    api_server_host: str = ""
    api_server_port: int = 0
    api_server_use_wss: bool = False
    api_server_cert_file: str = ""
    api_server_key_file: str = ""
    api_server_allowed_api_keys: tuple[str, ...] = ()
    ws_server_host: str = ""
    ws_server_port: int = 0
    auth_token: str = ""
```

## **4.3 mode_utils.py / send_emoji.py — ModelConfigPort 扩展**

**现状**：两处都通过 `config_manager.get_model_config()` 获取 `ModelConfig`，然后：
- `model_config.model_task_config.{task_name}` → 获取任务配置
- `{model.name: model for model in model_config.models}` → 构建模型名→模型信息映射

**改造**：`ModelConfigPort` 已有 `get_task_config(task_name)` 和 `get_model_info(model_name)`。新增 `list_model_names() -> list[str]`（返回模型名列表，而非 Pydantic model dict——避免返回可变对象）。

**理由**（CC 审查 Q3 结论）：`ModelInfo` 是 Pydantic model（非 frozen dataclass），返回它违反"Protocol 返回不可变快照"的原则。如果调用方只需模型名列表，`list_model_names()` 足够。如果需要查询特定模型信息，用 `get_model_info(model_name)` 逐个查。

mode_utils 改造：
```python
# 前：model_config = config_manager.get_model_config()
#     task_config = getattr(model_config.model_task_config, task_name)
#     models_by_name = {model.name: model for model in model_config.models}
# 后：
task_config = model_config_port.get_task_config(task_name)
model_names = model_config_port.list_model_names()
models_by_name = {name: model_config_port.get_model_info(name) for name in model_names}
```

send_emoji 改造同理。

## **4.4 emoji_cache_cleanup.py / image_cache_cleanup.py**

**现状**：两处都通过 `global_config.{emoji|visual}.cache_cleanup` 获取整体对象，该对象需满足 `ConfigLike` Protocol（有 `enabled`、`check_interval_hours`、`*_retention_days` 属性）。

**改造**：新增 `CacheCleanupConfig` 快照类型，让 `CacheCleanupConfig` 也满足消费方的 Protocol 约束（duck typing）。消费方代码不依赖类型标注，只依赖属性访问，所以 frozen dataclass 天然兼容。

**关键**：`emoji_cache_cleanup.py` 的 `_interval_seconds(config)` 和 `_should_cleanup(config)` 函数接受 `config` 参数并访问 `.enabled`、`.check_interval_hours`、`.emoji_file_retention_days` 等属性。`CacheCleanupConfig` 的 `file_retention_days` 需要映射到消费方期望的属性名——但消费方代码访问的属性名不同（emoji 用 `emoji_file_retention_days`，image 用 `image_file_retention_days`）。

**决策**：不统一属性名。为 emoji 和 image 分别新增适配器方法，返回各自原始配置对象满足的 duck-typed 快照。`CacheCleanupConfig` 使用通用字段名，消费方代码需做属性名适配（`file_retention_days` → 消费方读 `config.file_retention_days`）。

**更简洁的方案**：直接在 `CacheCleanupConfig` 中同时包含两种属性名：

```python
@dataclass(frozen=True)
class CacheCleanupConfig:
    enabled: bool = False
    check_interval_hours: float = 24.0
    emoji_file_retention_days: float = 30.0
    no_file_record_retention_days: float = 90.0
    image_file_retention_days: float = 30.0
    no_file_result_retention_days: float = 90.0
```

emoji 场景只用 `emoji_file_retention_days`，image 场景只用 `image_file_retention_days`，未用字段保持默认值。消费方代码零修改。

## **4.5 utils_config.py — 多域混合**

**现状**：访问 `global_config.expression`、`global_config.experimental`、`global_config.jargon`、`global_config.chat.reply_style`、`global_config.a_memorix` 五个域。

**改造**：
- `expression.*` → `AppConfigPort` 已有方法（`get_expression_learning_list` 等）
- `experimental.*` → `AppConfigPort` 已有方法
- `jargon.*` → 新增 `get_jargon_learning_list()` + `get_jargon_groups()`
- `chat.reply_style.chat_prompts` → 新增 `ChatConfigPort.get_reply_style_chat_prompts()`
- `a_memorix.shared_memory_groups` → `AppConfigPort` 已有 `get_a_memorix_shared_memory_groups()`

**注入方式**：采用 registry 模式——`utils_config.py` 新增模块级 port 变量 + `set_utils_config_ports()` 注册函数，避免修改所有调用链。这与项目已有的 `app_config_port_registry` 模式一致。

```python
# utils_config.py
_app_config_port: AppConfigPort | None = None
_chat_config_port: ChatConfigPort | None = None

def set_utils_config_ports(app_config_port: AppConfigPort, chat_config_port: ChatConfigPort) -> None:
    global _app_config_port, _chat_config_port
    _app_config_port = app_config_port
    _chat_config_port = chat_config_port

def _get_app_port() -> AppConfigPort:
    if _app_config_port is None:
        from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
        return GlobalConfigAppConfigPort()
    return _app_config_port
```

各函数内部将 `global_config.*` 替换为 `_get_app_port().get_*()`，调用方无需修改。

## **4.6 supervisor.py**

**现状**：访问 `global_config.plugin_runtime` 整体对象，读取 `health_check_interval_sec`、`runner_spawn_timeout_sec`、`max_restart_attempts`。

**改造**：`AppConfigPort.get_plugin_runtime_config()` 已存在，返回 `PluginRuntimeSnapshot`（含全部所需字段）。supervisor 注入 `AppConfigPort`，调用 `app_config_port.get_plugin_runtime_config()`。

## **4.7 api.py（message_server）**

**现状**：访问 `global_config.maim_message` 整体对象（10+ 字段）。

**改造**：新增 `AppConfigPort.get_maim_message_config()` 返回 `MaimMessageConfigSnapshot`。api.py 注入 `AppConfigPort`。

## **4.8 runtime.py — MCPConfig 整体对象**

**现状**：`_get_mcp_config()` 返回 `global_config.mcp`，被 `MCPManager.from_app_config()` 消费。

**问题**：`MCPManager.from_app_config()` 需要 MCPConfig 的完整结构（含 client、server 等嵌套配置），无法逐属性 Port 化。

**决策**：归入"暂不可拆解"类别。`MCPManager.from_app_config()` 的接口设计需要重构（接受快照而非 Pydantic model），超出 Phoenix-4 范围。保留 noqa + 注释。

# **5. AppConfigPort 组织优化**

不拆分为子 Protocol，改为 docstring 分组注释（见 2.3 节）。AppConfigPort 保持单体，在 docstring 中按配置域分组，提升可读性。

# **6. 核心禁止项第 7 项验证**

搜索 `src/core/` 目录中 `enqueue_proactive_task` 的调用方：

- `ChatRuntime.enqueue_proactive_task()` — Protocol 定义，合法
- `MaisakaHeartFlowChatting.enqueue_proactive_task()` — 实现，合法
- Orchestrator 是否调用？需 grep 确认

如果 Orchestrator 未调用 `enqueue_proactive_task`，则禁止项 #7 标记为 ✅。

# **7. 暂不可拆解的 6 处 noqa**

| # | 文件 | 原因 | 预期解决 |
|---|------|------|----------|
| 1 | `routes.py` (heartflow_manager) | WebUI 直接访问 heartflow_chat_list 整体字典 | 需 SessionLifecyclePort 扩展 |
| 2 | `routes.py` (global_config 读写) | chat.reply_style 整体对象 + config_manager.reload_config() | 需 ChatConfigPort 扩展 + ConfigManagerPort |
| 3 | `config.py` | WebUI 配置管理 CRUD 直接操作配置对象 | 需重新设计 WebUI 配置接口 |
| 4 | `core.py` (capabilities) | 插件动态配置需 global_config 整体对象反射访问 | 需 AppConfigPort.get_config_value_by_key() |
| 5 | `runtime.py` (MCPConfig, L2237) | MCPManager.from_app_config() 需完整 MCPConfig | 需重构 MCPManager 接口 |
| 6 | `runtime.py` (expression, L1437) | `global_config.expression` 整体对象遍历 | 需 AppConfigPort 新增 expression 整体快照 |
| 7 | `runtime.py` (reply_timing, L1051-1052) | `global_config.chat.reply_timing.talk_value` | 需 ChatConfigPort 新增 reply_timing 方法 |

**注意**：runtime.py 有 4 处直接使用 global_config（L1051/L1052/L1437/L2238），加上 L25 的导入和 L2237 的延迟导入。其中 L1051-1052 的 `reply_timing` 可通过 ChatConfigPort 新增方法解决；L1437 的 `expression` 整体对象遍历需新增快照方法；L2237-2238 的 MCPConfig 暂不可拆解。

# **8. 新增文件/类型清单**

| 文件 | 变更 |
|------|------|
| `src/core/types.py` | +`CacheCleanupConfig` dataclass, +`MaimMessageConfigSnapshot` dataclass |
| `src/core/protocols.py` | AppConfigPort docstring 分组, +`ModelConfigPort.list_model_names()`, +`ChatConfigPort.get_reply_style_chat_prompts()`, +`ChatConfigPort.get_reply_timing_talk_value()`, +`ChatConfigPort.get_reply_timing_private_talk_value()` |
| `src/core/adapters/app_config_port.py` | +`get_mmc_version()`, +`get_emoji_cache_cleanup_config()`, +`get_image_cache_cleanup_config()`, +`get_maim_message_config()`, +`get_jargon_learning_list()`, +`get_jargon_groups()` |
| `src/core/adapters/model_config_port.py` | +`list_model_names()` |
| `src/core/adapters/chat_config_port.py` | +`get_reply_style_chat_prompts()`, +`get_reply_timing_talk_value()`, +`get_reply_timing_private_talk_value()` |

# **9. 组件层改造清单**

| 文件 | 改造 | 注入方式 |
|------|------|----------|
| `emoji_manager.py` | 删 config_manager 导入，改用 ModelConfigPort + AppConfigPort | 延迟注入：`set_ports()` 方法 + 过渡期 fallback |
| `expression_selector.py` | 删 model_config 导入，改用 ModelConfigPort | 构造函数/方法参数 |
| `reply.py` | 删 config_module 导入 | 无需注入 |
| `remote.py` | 删 MMC_VERSION 导入，改用 AppConfigPort | 函数参数 |
| `service_task_resolver.py` | 删 fallback 分支和 noqa 导入 | 已有 ModelConfigPort |
| `mode_utils.py` | 删 config_manager 导入，改用 ModelConfigPort | 函数参数 |
| `send_emoji.py` | 删 config_manager 导入，改用 ModelConfigPort | 函数参数 |
| `emoji_cache_cleanup.py` | 删 global_config 导入，改用 AppConfigPort | 函数参数 |
| `image_cache_cleanup.py` | 删 global_config 导入，改用 AppConfigPort | 函数参数 |
| `utils_config.py` | 删 global_config 导入，改用 AppConfigPort + ChatConfigPort | registry 模式：`set_utils_config_ports()` |
| `supervisor.py` | 删 global_config 导入，改用 AppConfigPort | `__init__` 参数注入 |
| `api.py` | 删 global_config 导入，改用 AppConfigPort | 函数参数 |
| `runtime.py` (L25+L1051+L1052) | 删 global_config 导入，reply_timing 改用 ChatConfigPort | 注入 ChatConfigPort |
| `runtime.py` (L1437) | expression 整体对象 → AppConfigPort 方法 | 注入 AppConfigPort |

# **10. 风险与缓解**

| 风险 | 缓解 |
|------|------|
| emoji_manager 模块级单例初始化时 port 未注册 | 延迟注入 + 过渡期 fallback（port 为 None 时回退 config_manager） |
| utils_config.py 调用链改动大 | registry 模式：`set_utils_config_ports()` 注册，函数内部用 `_get_app_port()`，调用方零修改 |
| CacheCleanupConfig 字段名与消费方不匹配 | 保留原始字段名（emoji_file_retention_days / image_file_retention_days），消费方零修改 |
| runtime.py 多处直接使用 global_config | 按位置分别处理：reply_timing→ChatConfigPort，expression→AppConfigPort，MCPConfig→暂保留 |
| ModelConfigPort.list_model_names() 返回 list[str] | 调用方需 `get_model_info(name)` 逐个查，比直接返回 dict 多一步，但保持不可变原则 |