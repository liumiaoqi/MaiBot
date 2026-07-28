# Phoenix-4：能力层 Protocol 化 — 编码任务

# 任务总览

| 批次 | 任务 | 依赖 | 负责人 | 预估行数 |
|------|------|------|--------|----------|
| T1 | 新增快照类型 | 无 | CC | ~30 |
| T2 | 扩展 Protocol + 适配器 | T1 | CC | ~80 |
| T3 | AppConfigPort docstring 分组 | T2 | CC | ~10 |
| T4 | 可立即拆解的 5 处 noqa 消除 | T2 | Codex | ~80 |
| T5 | 需新增 Port 方法的 7 处 noqa 消除 | T2 | CC/Codex | ~150 |
| T6 | runtime.py noqa 消除 | T2 | CC | ~40 |
| T7 | 核心禁止项 #7 验证 | 无 | CA | 0 |
| T8 | ruff 守卫 + AGENTS.md 更新 | T3,T4,T5,T6 | CC | ~20 |

---

## T1：新增快照类型

**文件**：`src/core/types.py`

**新增**：

1. `CacheCleanupConfig` — frozen dataclass
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

2. `MaimMessageConfigSnapshot` — frozen dataclass
   ```python
   @dataclass(frozen=True)
   class MaimMessageConfigSnapshot:
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

**验证**：`uv run python -c "from src.core.types import CacheCleanupConfig, MaimMessageConfigSnapshot; print('OK')"`

---

## T2：扩展 Protocol + 适配器

### T2.1 扩展 ModelConfigPort

**文件**：`src/core/protocols.py`

新增方法：
```python
def list_model_names(self) -> list[str]:
    """返回所有已配置模型名称列表。

    Returns:
        list[str] — 模型名列表
    """
```

**文件**：`src/core/adapters/model_config_port.py`

新增实现：
```python
def list_model_names(self) -> list[str]:
    from src.config.config import config_manager  # noqa: TID251 — 适配器层
    mc = config_manager.get_model_config()
    return [m.name for m in mc.models]
```

### T2.2 扩展 ChatConfigPort

**文件**：`src/core/protocols.py`

新增方法：
```python
def get_reply_style_chat_prompts(self) -> list[str]: ...
def get_reply_timing_talk_value(self) -> float: ...
def get_reply_timing_private_talk_value(self) -> float: ...
```

**文件**：`src/core/adapters/chat_config_port.py`

新增实现：
```python
def get_reply_style_chat_prompts(self) -> list[str]:
    return list(self._get_cfg().chat.reply_style.chat_prompts or [])

def get_reply_timing_talk_value(self) -> float:
    return float(self._get_cfg().chat.reply_timing.talk_value)

def get_reply_timing_private_talk_value(self) -> float:
    return float(self._get_cfg().chat.reply_timing.private_talk_value)
```

### T2.3 扩展 AppConfigPort（新增方法）

**文件**：`src/core/protocols.py` — AppConfigPort 新增方法签名

| 方法 | 签名 |
|------|------|
| `get_mmc_version` | `def get_mmc_version(self) -> str: ...` |
| `get_emoji_cache_cleanup_config` | `def get_emoji_cache_cleanup_config(self) -> CacheCleanupConfig: ...` |
| `get_image_cache_cleanup_config` | `def get_image_cache_cleanup_config(self) -> CacheCleanupConfig: ...` |
| `get_maim_message_config` | `def get_maim_message_config(self) -> MaimMessageConfigSnapshot: ...` |
| `get_jargon_learning_list` | `def get_jargon_learning_list(self) -> list[str]: ...` |
| `get_jargon_groups` | `def get_jargon_groups(self) -> list[Any]: ...` |

**文件**：`src/core/adapters/app_config_port.py` — 新增实现

```python
def get_mmc_version(self) -> str:
    from src.config.config import MMC_VERSION  # noqa: TID251 — 适配器层
    return MMC_VERSION

def get_emoji_cache_cleanup_config(self) -> CacheCleanupConfig:
    from src.core.types import CacheCleanupConfig
    cfg = self._get_cfg().emoji.cache_cleanup
    return CacheCleanupConfig(
        enabled=bool(cfg.enabled),
        check_interval_hours=float(cfg.check_interval_hours or 24.0),
        emoji_file_retention_days=float(cfg.emoji_file_retention_days or 30.0),
        no_file_record_retention_days=float(cfg.no_file_record_retention_days or 90.0),
    )

def get_image_cache_cleanup_config(self) -> CacheCleanupConfig:
    from src.core.types import CacheCleanupConfig
    cfg = self._get_cfg().visual.image_cache_cleanup
    return CacheCleanupConfig(
        enabled=bool(cfg.enabled),
        check_interval_hours=float(cfg.check_interval_hours or 24.0),
        image_file_retention_days=float(cfg.image_file_retention_days or 30.0),
        no_file_result_retention_days=float(cfg.no_file_result_retention_days or 90.0),
    )

def get_maim_message_config(self) -> MaimMessageConfigSnapshot:
    from src.core.types import MaimMessageConfigSnapshot
    cfg = self._get_cfg().maim_message
    return MaimMessageConfigSnapshot(
        enable_api_server=bool(cfg.enable_api_server),
        api_server_host=str(cfg.api_server_host or ""),
        api_server_port=int(cfg.api_server_port or 0),
        api_server_use_wss=bool(cfg.api_server_use_wss),
        api_server_cert_file=str(cfg.api_server_cert_file or ""),
        api_server_key_file=str(cfg.api_server_key_file or ""),
        api_server_allowed_api_keys=tuple(cfg.api_server_allowed_api_keys or []),
        ws_server_host=str(cfg.ws_server_host or ""),
        ws_server_port=int(cfg.ws_server_port or 0),
        auth_token=str(cfg.auth_token or ""),
    )

def get_jargon_learning_list(self) -> list[str]:
    return list(self._get_cfg().jargon.learning_list)

def get_jargon_groups(self) -> list[Any]:
    return list(self._get_cfg().jargon.jargon_groups or [])
```

**验证**：`uv run python -c "from src.core.protocols import AppConfigPort, ModelConfigPort, ChatConfigPort; print('OK')"`

---

## T3：AppConfigPort docstring 分组

**文件**：`src/core/protocols.py`

将 AppConfigPort 的 docstring 改为分组注释：

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

**验证**：`uv run python -c "from src.core.protocols import AppConfigPort; print(AppConfigPort.__doc__[:50])"`

---

## T4：可立即拆解的 5 处 noqa 消除

### T4.1 reply.py — 删除未使用导入

**文件**：`src/maisaka/builtin_tool/reply.py`

- 删除 `from src.config import config as config_module  # noqa: TID251`

### T4.2 service_task_resolver.py — 删除 fallback 分支

**文件**：`src/services/service_task_resolver.py`

- 删除 fallback 分支中的 `from src.config.config import config_manager  # noqa: TID251`
- 删除 `return config_manager.get_model_config()` 分支
- 保留 `ModelConfigPort` 路径作为唯一路径

### T4.3 emoji_manager.py — 延迟注入 ModelConfigPort + AppConfigPort

**文件**：`src/emoji_system/emoji_manager.py`

1. 删除 `from src.config.config import config_manager  # noqa: TID251`
2. 新增延迟注入模式：
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
3. 替换：
   - `config_manager.get_model_config()` → `self._get_model_config()`
   - `config_manager.register_reload_callback(cb)` → `self._app_config_port.register_reload_callback(cb)` （需加 None 检查）
   - `config_manager.unregister_reload_callback(cb)` → 同上
4. **main.py 初始化阶段**：在 `emoji_manager` 创建后调用 `emoji_manager.set_ports(model_config_port, app_config_port)`

### T4.4 expression_selector.py — 注入 ModelConfigPort

**文件**：`src/maisaka/replyer/expression_selector.py`

1. 删除 `from src.config.config import model_config  # noqa: TID251`
2. 注入 `ModelConfigPort`（构造函数参数或方法参数）
3. 替换 `model_config.model_task_config.embedding.model_list` → `model_config_port.get_task_config("embedding").model_list`

### T4.5 remote.py — 注入 AppConfigPort

**文件**：`src/common/remote.py`

1. 删除 `from src.config.config import MMC_VERSION  # noqa: TID251`
2. 注入 `AppConfigPort`（函数参数或类属性）
3. 替换 `MMC_VERSION` → `app_config_port.get_mmc_version()`

**验证**：`uv run ruff check src/ --select TID251` — TID251 违规数应减少 5

---

## T5：需新增 Port 方法的 7 处 noqa 消除

### T5.1 mode_utils.py — 注入 ModelConfigPort

**文件**：`src/maisaka/visual/mode_utils.py`

1. 删除 `from src.config.config import config_manager  # noqa: TID251`
2. 函数签名新增 `model_config_port: ModelConfigPort` 参数
3. 替换：
   - `config_manager.get_model_config()` → `model_config_port`
   - `model_config.model_task_config.{task_name}` → `model_config_port.get_task_config(task_name)`
   - `{m.name: m for m in model_config.models}` → `{name: model_config_port.get_model_info(name) for name in model_config_port.list_model_names()}`

### T5.2 send_emoji.py — 注入 ModelConfigPort

**文件**：`src/maisaka/builtin_tool/send_emoji.py`

1. 删除 `from src.config.config import config_manager  # noqa: TID251`
2. 注入 `ModelConfigPort`
3. 替换同 T5.1

### T5.3 emoji_cache_cleanup.py — 注入 AppConfigPort

**文件**：`src/emoji_system/emoji_cache_cleanup.py`

1. 删除 `from src.config.config import global_config  # noqa: TID251`
2. 函数签名新增 `app_config_port: AppConfigPort` 参数
3. 替换 `global_config.emoji.cache_cleanup` → `app_config_port.get_emoji_cache_cleanup_config()`

### T5.4 image_cache_cleanup.py — 注入 AppConfigPort

**文件**：`src/chat/image_system/image_cache_cleanup.py`

1. 删除 `from src.config.config import global_config  # noqa: TID251`
2. 函数签名新增 `app_config_port: AppConfigPort` 参数
3. 替换 `global_config.visual.image_cache_cleanup` → `app_config_port.get_image_cache_cleanup_config()`

### T5.5 utils_config.py — registry 模式注入

**文件**：`src/common/utils/utils_config.py`

1. 删除 `from src.config.config import global_config  # noqa: TID251`
2. 新增模块级 port 变量 + 注册函数：
   ```python
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

   def _get_chat_port() -> ChatConfigPort:
       if _chat_config_port is None:
           from src.core.adapters.chat_config_port import GlobalConfigChatConfigPort
           return GlobalConfigChatConfigPort()
       return _chat_config_port
   ```
3. 替换：
   - `global_config.expression.*` → `_get_app_port().get_expression_*()`
   - `global_config.experimental.*` → `_get_app_port().get_experimental_*()`
   - `global_config.jargon.*` → `_get_app_port().get_jargon_*()`
   - `global_config.chat.reply_style.chat_prompts` → `_get_chat_port().get_reply_style_chat_prompts()`
   - `global_config.a_memorix.shared_memory_groups` → `_get_app_port().get_a_memorix_shared_memory_groups()`
4. **main.py 初始化阶段**：调用 `set_utils_config_ports(app_config_port, chat_config_port)`

### T5.6 supervisor.py — 注入 AppConfigPort

**文件**：`src/plugin_runtime/host/supervisor.py`

1. 删除 `from src.config.config import global_config  # noqa: TID251`
2. `Supervisor.__init__` 新增 `app_config_port: AppConfigPort` 参数
3. 替换 `global_config.plugin_runtime` → `app_config_port.get_plugin_runtime_config()`

### T5.7 api.py — 注入 AppConfigPort

**文件**：`src/common/message_server/api.py`

1. 删除 `from src.config.config import global_config  # noqa: TID251`
2. 函数签名新增 `app_config_port: AppConfigPort` 参数
3. 替换 `global_config.maim_message` → `app_config_port.get_maim_message_config()`

**验证**：`uv run ruff check src/ --select TID251` — TID251 违规数应进一步减少 7

---

## T6：runtime.py noqa 消除

**文件**：`src/maisaka/runtime.py`

runtime.py 有 4 处直接使用 global_config：

| 行号 | 用途 | 处置 |
|------|------|------|
| L25 | `from src.config.config import global_config  # noqa: TID251` | 删除此导入 |
| L1051-1052 | `global_config.chat.reply_timing.talk_value/private_talk_value` | 注入 ChatConfigPort，替换为 `chat_config_port.get_reply_timing_talk_value()` |
| L1437 | `global_config.expression` 整体对象遍历 | 注入 AppConfigPort，用已有 `get_expression_*()` 方法替换 |
| L2237-2238 | `global_config.mcp` MCPConfig 整体对象 | **暂保留**（MCPManager.from_app_config() 需完整结构） |

**改造**：

1. 删除 L25 的 `from src.config.config import global_config  # noqa: TID251`
2. runtime.py 注入 `ChatConfigPort` + `AppConfigPort`（通过构造函数或属性）
3. L1051-1052：`global_config.chat.reply_timing.talk_value` → `self._chat_config_port.get_reply_timing_talk_value()`
4. L1437：`global_config.expression` → 用 `self._app_config_port.get_expression_*()` 逐属性替换
5. L2237-2238 保留 noqa（MCPConfig 整体对象）

**验证**：`uv run ruff check src/maisaka/runtime.py --select TID251`

---

## T7：核心禁止项 #7 验证

**执行者**：CA

1. `grep -r "enqueue_proactive_task" src/core/` — 确认 Orchestrator 未调用
2. 如果无违规 → AGENTS.md 禁止项 #7 标记为 ✅
3. 如果有违规 → 记录违规位置，设计修复方案

**CA 已验证**：`enqueue_proactive_task` 仅在 protocols.py（定义）、runtime.py:658（实现）、capabilities/core.py:246（合法调用方）中出现，Orchestrator 未调用。禁止项 #7 可标记 ✅。

---

## T8：ruff 守卫 + AGENTS.md 更新

### T8.1 更新 AGENTS.md

- 核心禁止项 #7 标记为 ✅
- noqa TID251 统计更新（23→~11）
- Protocol 接口表更新（新增方法：list_model_names、get_reply_style_chat_prompts、get_reply_timing_*、get_mmc_version、get_emoji_cache_cleanup_config、get_image_cache_cleanup_config、get_maim_message_config、get_jargon_*）
- 快照类型表更新（新增 CacheCleanupConfig、MaimMessageConfigSnapshot）

### T8.2 验证 ruff

```bash
uv run ruff check src/ --select TID251
```

确认剩余违规均为合法保留（适配器层 4 + 暂不可拆解 ~7）。

### T8.3 最终集成测试

```bash
docker exec maim-bot-core bash -c "cd /MaiMBot && PYTHONPATH=/MaiMBot uv run pytest tests/ -v --tb=short -x"
```

---

## 依赖关系

```
T1 → T2 → T3
T2 → T4, T5, T6
T3, T4, T5, T6 → T8
T7（独立，已完成）
```

T4 和 T5 可并行执行。T6 需 CC 执行（runtime.py 是高风险文件）。

## 派发建议

- **T1+T2+T3**：CC — Protocol 签名设计是高风险工作
- **T4.1+T4.2+T4.4+T4.5**：Codex — 机械替换，定义清晰
- **T4.3**（emoji_manager 延迟注入）：CC — 模块级单例改造需谨慎
- **T5.1-T5.4+T5.6+T5.7**：Codex — 机械替换
- **T5.5**（utils_config registry 模式）：CC — 较复杂，需确认所有调用方
- **T6**：CC — runtime.py 是高风险文件（~2200 行）
- **T8**：CC — 最终守卫
