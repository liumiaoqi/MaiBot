# 炉火纯青 CQ-2 — 设计方案

## 总体策略

CQ-2 四项债务按难度分两类：
- **机械替换**（CQ-11）：`import logging` → `get_logger`，纯文本替换，可自动化
- **上下文理解迁移**（CQ-13/14/15/16）：需理解每个导入点的用途，选择正确的 Port 和注册点

## CQ-11：`import logging` → `get_logger`

### 替换规则

| 场景 | 操作 |
|------|------|
| 既有 `get_logger` 也有 `import logging` | 删除 `import logging` 行 + 删除 `logger = logging.getLogger(...)` 行（已有 `logger = get_logger(...)`） |
| 仅有 `import logging` | 添加 `from src.common.logger import get_logger`，替换 `logger = logging.getLogger("xxx")` → `logger = get_logger("xxx")`，删除 `import logging` |
| `log_utils.py` | 特殊：它是日志格式辅助模块，`import logging` 仅用于 `logging.getLogger`，同上替换 |

### 自动化方案

写 Python 脚本 `fix_import_logging.py`：
1. 扫描 `src/maisaka/**/*.py`
2. 对每个文件检测 `import logging` 行
3. 按上述规则替换
4. 输出变更报告

### 验证

- `rg "^import logging$" src/maisaka/ --type py` 应返回 0 结果
- Docker 内启动无 ImportError

## CQ-15：`chat_manager` 直接导入

### 需迁移点

**`chat/message_receive/uni_message_sender.py:39`**：
```python
from src.webui.routers.chat import WEBUI_CHAT_PLATFORM, chat_manager
```
用途：获取 WebUI 广播器（ChatConnectionManager + platform）。

**迁移方案**：引入 `WebUIBroadcasterPort` Protocol，或在 uni_message_sender 中通过依赖注入获取。但考虑到这是跨层（chat → webui）的桥接，且 chat_manager 是 webui 的 WebSocket 连接管理器而非核心业务对象，最简方案是：

- 将 `_webui_chat_broadcaster` 的初始化改为延迟导入 + 协议化接口
- 新增 `WebUIChatPort` Protocol（仅含 `send_message`/`broadcast_to_group`）
- 在 webui 适配器层注册实现

**`chat/message_receive/message_registry.py:8`**：
```python
from .chat_manager import BotChatSession
```
这是导入**类**而非管理器实例，且是同包（chat）内部。**豁免**——同包类导入不违反核心隔离原则。

### 最终方案

- uni_message_sender.py：通过 `WebUIChatPort` Protocol 获取广播器，不再直接导入 webui 内部模块
- message_registry.py：豁免（同包类导入）

## CQ-14：`config_manager` 直接导入

### 需迁移点分析

| 文件 | 用法 | 迁移目标 |
|------|------|---------|
| `A_memorix/host_service.py` L28,646 | `_get_config_manager()` 返回 config_manager 实例，用于 `get_global_config().a_memorix`、`reload_config`、`register_reload_callback` | `AppConfigPort`（已有 `get_a_memorix_integration_config`、`register_reload_callback`、`unregister_reload_callback`）；`reload_config` 需新增 Port 方法 |
| `emoji_system/emoji_manager.py` L290,298,306 | fallback：Port 不可用时回退 config_manager | 删除 fallback 分支，强制走 Port（Port 在启动时已注册） |
| `services/html_render_service.py` L27 | `config_manager.get_global_config().plugin_runtime.render` | `AppConfigPort.get_plugin_runtime_config()` 返回快照 |
| `services/telemetry_stats_service.py` L13 | `config_manager.get_model_config().model_task_config` | `ModelConfigPort.get_task_config()` |
| `webui/routers/chat/routes.py` L38 | `config_manager.reload_config(changed_scopes=["bot"])` ×5 | 新增 `AppConfigPort.reload_config()` 方法 |

### 新增 Port 方法

**AppConfigPort.reload_config**：
```python
async def reload_config(self, changed_scopes: tuple[str, ...] = ()) -> bool:
    """热重载配置。"""
    ...
```

**AppConfigPort.get_global_config_snapshot**（供 A_memorix 使用）：
A_memorix 已有 `get_a_memorix_integration_config()` 返回 `AMemorixIntegrationSnapshot`，应够用。
A_memorix 的 `reload_config` 和 `register_reload_callback` 已在 AppConfigPort 中有对应方法。

### emoji_manager fallback 消除

emoji_manager 已有 `self._model_config_port` 和 `self._app_config_port` 属性，fallback 分支是过渡期残留。Port 在启动时已注册，直接删除 fallback 分支，若 Port 为 None 则抛 `RuntimeError`。

## CQ-13：`heartflow_manager` 直接导入

### 需迁移点

**`webui/routers/chat/routes.py:14`**：
```python
from src.chat.heart_flow.heartflow_manager import heartflow_manager
```
用途：L1022 `heartflow_manager.heartflow_chat_list.pop(session_id, None)`

**迁移方案**：通过 `get_chat_runtime_registry()` 获取 `ChatRuntimeRegistry`，用 `list_runtimes()` 或新增 `remove_runtime()` 替代直接访问 `heartflow_chat_list`。

具体：`heartflow_manager.heartflow_chat_list.pop(session_id)` 等价于 `registry.remove_runtime(session_id)`。ChatRuntimeRegistry 已有 `remove_runtime` 方法。

## CQ-16：`global_config` 直接导入

### 需迁移点

| 文件 | 用法 | 迁移目标 |
|------|------|---------|
| `webui/routers/chat/routes.py` L38 | `global_config.chat.reply_style` | `ChatConfigPort.get_reply_style()` |
| `mcp_module/__init__.py` L7 | `global_config.mcp` | `AppConfigPort.get_mcp_enable()` + `get_mcp_sampling_task_name()` 或新增 `get_mcp_config()` |

### mcp_module 迁移

`MCPManager.from_app_config(global_config.mcp)` 传入整个 MCP 配置对象。需在 AppConfigPort 新增：
```python
def get_mcp_config(self) -> MCPSnapshot:
    """获取 MCP 配置快照。"""
    ...
```
或让 MCPManager 接受逐属性参数。取决于 MCPManager 接口复杂度——最简方案是新增 `get_mcp_config()` 返回快照。

## 执行顺序

1. **CQ-11**（机械替换，Codex 执行）→ 验证无 ImportError
2. **CQ-13**（1 处，最简）→ routes.py heartflow_manager → registry
3. **CQ-16**（2 处）→ routes.py global_config + mcp_module
4. **CQ-14**（5 文件 8 处，最复杂）→ 需先扩 Port 接口再迁移
5. **CQ-15**（1 处）→ uni_message_sender WebUIChatPort

## 风险

- **Port 方法扩展**：新增 `reload_config`、`get_mcp_config` 需同步更新适配器层实现
- **emoji_manager fallback 消除**：需确认 Port 在 emoji_manager 初始化时已注册
- **A_memorix host_service**：`_get_config_manager()` 是延迟导入，迁移后需改为延迟获取 Port