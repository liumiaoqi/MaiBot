# 炉火纯青 CQ-2 — 编码任务

## T1：CQ-11 `import logging` → `get_logger`（45 处）

**负责人**：Codex [CX]
**类型**：机械替换，可自动化

### 步骤

- [ ] 编写 `fix_import_logging.py` 脚本（参考 CQ-1 的 `fix_silent_exceptions.py`）
- [ ] 脚本逻辑：
  1. 扫描 `src/maisaka/**/*.py`
  2. 对 12 个已有 `get_logger` 的文件：删除 `import logging` 行 + 删除 `logger = logging.getLogger(...)` 行
  3. 对 33 个仅有 `import logging` 的文件：添加 `from src.common.logger import get_logger`，替换 `logger = logging.getLogger("xxx")` → `logger = get_logger("xxx")`，删除 `import logging`
  4. 特殊处理 `log_utils.py`：同规则 3
- [ ] 执行脚本
- [ ] 验证：`rg "^import logging$" src/maisaka/ --type py` 返回 0
- [ ] 提交：`feat(maisaka): 统一日志 get_logger，消除 import logging [CX]`

### 12 个已有 get_logger 的文件（仅删 import logging 行）

```
src/maisaka/agent/registry.py
src/maisaka/agent/router.py
src/maisaka/agent_autonomy/reminder.py
src/maisaka/agent_interaction/engine.py
src/maisaka/agent_interaction/monologue_engine.py
src/maisaka/agent_interaction/scheduler.py
src/maisaka/agent_interaction/memory/adapter.py
src/maisaka/agent_interaction/memory/profile.py
src/maisaka/subagent/fork_context.py
src/maisaka/subagent/agents/checkpoint_writer.py
src/maisaka/subagent/agents/dream_trigger.py
src/maisaka/time_awareness/lunar.py
```

### 33 个需添加 get_logger 的文件

```
src/maisaka/agent/config.py
src/maisaka/agent/config_loader/loader.py
src/maisaka/agent_autonomy/log_utils.py
src/maisaka/agent_interaction/bootstrap.py
src/maisaka/agent_interaction/cooldown.py
src/maisaka/agent_interaction/echo_detector.py
src/maisaka/agent_interaction/event_store.py
src/maisaka/agent_interaction/trigger_scheduler.py
src/maisaka/agent_interaction/triggers/memory_driven.py
src/maisaka/consolidation/distill.py
src/maisaka/consolidation/knowledge_store.py
src/maisaka/consolidation/scheduler.py
src/maisaka/cross_chat/injector.py
src/maisaka/cross_chat/service.py
src/maisaka/cross_chat/sharing.py
src/maisaka/cross_chat/summarizer.py
src/maisaka/event_sensor/priority.py
src/maisaka/event_sensor/reaction.py
src/maisaka/event_sensor/sensor.py
src/maisaka/goal/judge.py
src/maisaka/goal/manager.py
src/maisaka/goal/scheduler.py
src/maisaka/migration/coordinator.py
src/maisaka/subagent/interactive_gate.py
src/maisaka/subagent/lifecycle.py
src/maisaka/subagent/parallel.py
src/maisaka/subagent/scheduler.py
src/maisaka/subagent/agents/compaction.py
src/maisaka/subagent/agents/compaction_trigger.py
src/maisaka/subagent/agents/dream.py
src/maisaka/time_awareness/context_builder.py
src/maisaka/time_awareness/scheduler.py
src/maisaka/time_awareness/service.py
```

---

## T2：CQ-13 heartflow_manager → ChatRuntimeRegistry（1 处）

**负责人**：CC
**类型**：上下文理解迁移

### 步骤

- [ ] `webui/routers/chat/routes.py`：
  - 删除 `from src.chat.heart_flow.heartflow_manager import heartflow_manager`
  - 添加 `from src.core.runtime_port_registry import get_chat_runtime_registry`
  - L1022 `heartflow_manager.heartflow_chat_list.pop(session_id, None)` → `get_chat_runtime_registry().remove_runtime(session_id)`
- [ ] 验证：routes.py 不再导入 heartflow_manager
- [ ] 提交：`refactor(webui): heartflow_manager → ChatRuntimeRegistry [CC]`

---

## T3：CQ-16 global_config → Port（2 处）

**负责人**：CC
**类型**：上下文理解迁移

### 步骤

- [ ] `webui/routers/chat/routes.py` L585：
  - `global_config.chat.reply_style` → `get_chat_config_port().get_reply_style()`
  - 删除 import 行中的 `global_config`
- [ ] `mcp_module/__init__.py`：
  - 新增 AppConfigPort 方法 `get_mcp_config()` 返回 MCP 配置快照（需在 protocols.py + app_config_port.py 适配器同步新增）
  - `global_config.mcp` → `get_app_config_port().get_mcp_config()`
  - 删除 `from src.config.config import global_config`
- [ ] 提交：`refactor: global_config → Port (routes.py + mcp_module) [CC]`

---

## T4：CQ-14 config_manager → Port（5 文件 8 处）

**负责人**：CC
**类型**：上下文理解迁移 + Port 扩展
**前置**：T2+T3 完成后（routes.py 已部分改造）

### 步骤

#### T4a：扩展 AppConfigPort

- [ ] `protocols.py`：AppConfigPort 新增 `async def reload_config(self, changed_scopes: tuple[str, ...] = ()) -> bool`
- [ ] `core/adapters/app_config_port.py`：实现 `reload_config`，委托 `config_manager.reload_config()`
- [ ] 提交：`feat(core): AppConfigPort 新增 reload_config [CC]`

#### T4b：emoji_manager fallback 消除

- [ ] `emoji_system/emoji_manager.py`：
  - `_get_model_config()`：删除 fallback 分支，Port 为 None 时抛 `RuntimeError("ModelConfigPort 未注册")`
  - `_register_reload_callback()`：同上
  - `_unregister_reload_callback()`：同上
  - 删除 3 处 `from src.config.config import config_manager` 导入
- [ ] 提交：`refactor(emoji): 消除 config_manager fallback，强制走 Port [CC]`

#### T4c：A_memorix host_service

- [ ] `A_memorix/host_service.py`：
  - `_get_config_manager()` → `_get_app_config_port()` 返回 `get_app_config_port()`
  - L673 `config_manager.get_global_config().a_memorix` → `port.get_a_memorix_integration_config()`
  - L723 `config_manager.reload_config(changed_scopes=("bot",))` → `await port.reload_config(changed_scopes=("bot",))`
  - L731 `config_manager.register_reload_callback(self.on_config_reload)` → `port.register_reload_callback(self.on_config_reload)`
  - 删除 2 处 `from src.config.config import config_manager`
- [ ] 提交：`refactor(A_memorix): config_manager → AppConfigPort [CC]`

#### T4d：services

- [ ] `services/html_render_service.py`：
  - `config_manager.get_global_config().plugin_runtime.render` → `get_app_config_port().get_plugin_runtime_config().render`
  - 删除 `from src.config.config import config_manager`
- [ ] `services/telemetry_stats_service.py`：
  - `config_manager.get_model_config().model_task_config` → `get_model_config_port().get_task_config("telemetry").model_task_config`（需确认 API）
  - 删除 `from src.config.config import config_manager`
- [ ] 提交：`refactor(services): config_manager → Port [CC]`

#### T4e：webui/routes/chat/routes.py

- [ ] 5 处 `config_manager.reload_config(changed_scopes=["bot"])` → `await get_app_config_port().reload_config(changed_scopes=("bot",))`
- [ ] 删除 import 行中的 `config_manager`
- [ ] 提交：`refactor(webui): config_manager → AppConfigPort.reload_config [CC]`

---

## T5：CQ-15 chat_manager 跨层导入（1 处）

**负责人**：CC
**类型**：上下文理解迁移 + 新 Port

### 步骤

- [ ] 新增 `WebUIChatPort` Protocol（protocols.py）：
  ```python
  class WebUIChatPort(Protocol):
      async def send_message(self, session_id: str, data: dict) -> None: ...
      async def broadcast_to_group(self, group_id: str, data: dict) -> None: ...
  ```
- [ ] 新增注册点 `webui_chat_port_registry.py`
- [ ] webui 适配器层注册 ChatConnectionManager 实现
- [ ] `chat/message_receive/uni_message_sender.py`：通过 Port 获取广播器
- [ ] 提交：`refactor: chat_manager → WebUIChatPort [CC]`

---

## T6：全局验证

**负责人**：CA

### 步骤

- [ ] `rg "from.*config_manager" src/ --type py` 验证仅剩适配器层 + 启动编排器 + 配置 CRUD 页面
- [ ] `rg "from.*heartflow_manager" src/ --type py` 验证仅剩 heart_flow 包内 + main.py
- [ ] `rg "from.*global_config" src/ --type py` 验证仅剩豁免位置
- [ ] `rg "^import logging$" src/maisaka/ --type py` 验证 0 结果
- [ ] Docker 内启动验证无 ImportError
- [ ] 更新 AGENTS.md 债务追踪表

---

## 执行计划

| 任务 | 负责人 | 依赖 | 预估 |
|------|--------|------|------|
| T1 | CX | 无 | 机械替换 |
| T2 | CC | 无 | 1 处 |
| T3 | CC | 无 | 2 处 + Port 扩展 |
| T4a | CC | 无 | Port 扩展 |
| T4b | CC | T4a | fallback 消除 |
| T4c | CC | T4a | A_memorix 迁移 |
| T4d | CC | T4a | services 迁移 |
| T4e | CC | T4a+T2+T3 | routes.py 收尾 |
| T5 | CC | 无 | 新 Port |
| T6 | CA | T1~T5 | 验证 |