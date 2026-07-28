# 炉火纯青 CQ-2 — P1 级债务清算：Port 迁移与统一日志

## 背景

CQ-1 已消除 P0 级 `except Exception: pass` 吞没和 identity.py None 防御问题。CQ-2 聚焦 P1 级"拿未来换现在"债务——绕过 Port 省事但透支重构自由度的直接导入，以及绕过统一日志的 `import logging`。

## 需求

### CQ-11：`import logging` → `get_logger`（45 处 → 0）

**现状**：maisaka 下 45 个文件仍用 `import logging` + `logging.getLogger()`，绕过项目统一日志 `src.common.logger.get_logger`。

**分类**：
- 12 个文件已有 `get_logger`，只需删除 `import logging` 行和 `logging.getLogger()` 行
- 33 个文件仅有 `import logging`，需添加 `from src.common.logger import get_logger`、替换 `logger = logging.getLogger(...)` → `logger = get_logger(...)`、删除 `import logging`
- 特殊：`agent_autonomy/log_utils.py` 是日志格式辅助模块，自身 `import logging` + `logging.getLogger` 应改为 `get_logger`

**验收标准**：
- [x] maisaka 下 `import logging` 数量 = 0（`log_utils.py` 除外，若其本身是日志基础设施则可保留）
- [x] 所有替换后 `logger = get_logger(...)` 模式一致
- [x] 无功能回归：日志输出名称不变

### CQ-15：`chat_manager` 直接导入 → Port（~3 处非 webui 内部）

**现状**：
| 文件 | 行 | 导入方式 | 分析 |
|------|-----|---------|------|
| `webui/routers/chat/__init__.py` | 4 | `from .service import chat_manager` | webui 内部，ChatConnectionManager 是 webui 自身组件，**豁免** |
| `chat/message_receive/uni_message_sender.py` | 39 | `from src.webui.routers.chat import chat_manager` | 跨层导入 webui 内部对象，需迁移 |
| `chat/message_receive/message_registry.py` | 8 | `from .chat_manager import BotChatSession` | 导入的是类而非管理器实例，需评估 |

**验收标准**：
- [x] 非 webui 目录下不再直接导入 `chat_manager` 实例
- [x] webui 内部 `ChatConnectionManager` 使用不受影响

### CQ-14：`config_manager` 直接导入 → AppConfigPort/ModelConfigPort（~9 处非适配器层）

**现状**：
| 文件 | 行 | 分析 |
|------|-----|------|
| `A_memorix/host_service.py` | 28, 646 | 需迁移到 Port |
| `main.py` | 273, 282, 376, 611 | 启动编排器，**豁免**（启动阶段 Port 尚未注册） |
| `emoji_system/emoji_manager.py` | 290, 298, 306 | 已标 `noqa: TID251`，需迁移 |
| `services/html_render_service.py` | 27 | 需迁移 |
| `services/telemetry_stats_service.py` | 13 | 需迁移 |
| `webui/routers/config.py` | 20 | 配置管理页面直接操作配置对象，**豁免**（WebUI 配置编辑需 CRUD） |
| `webui/routers/chat/routes.py` | 38 | 已标 `noqa: TID251`，需迁移 |
| `core/adapters/app_config_port.py` | 346-358 | 适配器层，**豁免** |
| `core/adapters/model_config_port.py` | 184 | 适配器层，**豁免** |

**需迁移**：5 个文件（A_memorix/host_service.py ×2, emoji_manager.py ×3, html_render_service.py ×1, telemetry_stats_service.py ×1, webui/routes/chat/routes.py ×1）= 8 处导入

**验收标准**：
- [x] 非适配器层、非启动阶段、非配置 CRUD 页面不再直接导入 `config_manager`
- [x] 适配器层和启动编排器保持 `noqa: TID251` 标注

### CQ-13：`heartflow_manager` 直接导入 → ChatRuntimeRegistry（2 处）

**现状**：
| 文件 | 行 | 分析 |
|------|-----|------|
| `main.py` | 355 | 启动编排器，**豁免** |
| `webui/routers/chat/routes.py` | 14 | 需迁移到 `ChatRuntimeRegistry` |
| `chat/heart_flow/heartflow_message_processor.py` | 5 | 同包内部导入，**豁免**（heart_flow 包内部协作） |

**需迁移**：1 处（webui/routes/chat/routes.py）

**验收标准**：
- [x] 非 heart_flow 包内部、非启动阶段不再直接导入 `heartflow_manager`

### CQ-16（新增）：`global_config` 直接导入审计

**现状**：17 处。其中：
- 适配器层（app_config_port.py, chat_config_port.py, bot_config_port.py）：**豁免**
- 启动编排器（main.py）：**豁免**
- `maisaka/runtime.py`：已标 `noqa: TID251`，MCPConfig 整体对象无法逐属性 Port 化，**暂豁免**
- `plugin_runtime/capabilities/core.py`：已标 `noqa: TID251`，插件反射访问，**暂豁免**
- `webui/routers/chat/routes.py`：需迁移
- `mcp_module/__init__.py`：**无需迁移**（global_config 仅出现在文档注释，非运行时代码）
- `A_memorix/scripts/process_knowledge.py`：离线脚本，**豁免**

**需迁移**：1 处（webui/routes/chat/routes.py）

**验收标准**：
- [x] 非豁免位置不再直接导入 `global_config`

## 豁免规则

1. **适配器层**（`src/core/adapters/`）：允许导入具体实现，标注 `noqa: TID251`
2. **启动编排器**（`main.py`）：Port 注册前需直接导入，标注 `noqa: TID251`
3. **WebUI 配置 CRUD 页面**（`webui/routers/config.py`）：需直接操作配置对象
4. **同包内部协作**：heart_flow 包内导入 heartflow_manager 豁免
5. **WebUI 内部组件**：ChatConnectionManager 是 webui 自身组件，内部使用豁免
6. **离线脚本**：A_memorix/scripts/ 不参与运行时

## 不做的事

- 不重构 Port 接口本身（接口已定义，只做消费方迁移）
- 不处理 P2 级代码质量债（noqa 残留、getattr 残留等）
- 不处理 `main.py` 启动编排器的直接导入（豁免）