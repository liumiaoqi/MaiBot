# SSD-6：智能体配置协议化 — 编码任务规划

## 概述

将 `AgentConfigRegistry` 具体类依赖解耦为 `AgentConfigProvider` Protocol 接口，使核心层和组件层通过接口契约访问智能体配置。共 7 批次 38 个子任务，覆盖 49 处导入迁移、1 个 Protocol 定义、1 个适配器实现、1 个 ruff 守卫规则。

## 智能体分工

| 批次　　　　　　　　　　　　　 | 负责人 | 理由　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| --------------------------------| --------| -----------------------------------------------------------------|
| 批次 1（基础设施）　　　　　　 | CC　　 | Protocol 定义 + 注册点 + 适配器，后续所有批次的基础，需首次正确 |
| 批次 2（核心自主性层）　　　　 | Codex　| 机械性导入替换，10 个文件模式统一　　　　　　　　　　　　　　　 |
| 批次 3（组件层-交互）　　　　　| Codex　| 机械性导入替换，6 个文件模式统一　　　　　　　　　　　　　　　　|
| 批次 4（组件层-优化器）　　　　| Codex　| 机械性导入替换，6 个文件模式统一　　　　　　　　　　　　　　　　|
| 批次 5（组件层-其他）　　　　　| Codex　| 机械性导入替换，6 个文件模式统一　　　　　　　　　　　　　　　　|
| 批次 6（基础设施层+解耦+守卫） | CC　　 | AgentRouter 解耦涉及架构变更，ruff 守卫需精确配置　　　　　　　 |
| 批次 7（测试+验证）　　　　　　| Codex　| 验证性任务，模式清晰　　　　　　　　　　　　　　　　　　　　　　|

## 文件锁

| 批次 | 修改文件 | 锁定方 |
|------|---------|--------|
| 1 | `src/core/protocols.py`, `src/core/types.py`, `src/core/adapters/agent_config_port.py`(新建), `src/core/adapters/__init__.py`, `src/main.py` | CC |
| 2 | `src/maisaka/agent_autonomy/` 下 10 个文件 | Codex |
| 3 | `src/maisaka/agent_interaction/` 5 个文件 + `src/maisaka/builtin_tool/butler.py` | Codex |
| 4 | `src/maisaka/deepseek/` 5 个文件 + `src/maisaka/consolidation/scheduler.py` | Codex |
| 5 | `src/maisaka/memory/` 2 个文件 + `src/maisaka/relationship/manager.py` + `src/maisaka/subagent/fork_context.py` + `src/maisaka/runtime.py` + `src/maisaka/chat_loop_service.py` | Codex |
| 6 | `src/chat/` 2 个文件 + `src/webui/` 3 个文件 + `src/plugin_runtime/capabilities/core.py` + `src/services/statistics_service.py` + `src/tools/data_migration.py` + `src/maisaka/agent/router.py` + `pyproject.toml` + `src/main.py` | CC |
| 7 | `tests/` 2 个文件 | Codex |

**注意**：批次 6 中 `src/main.py` 与批次 1 重叠，但批次 1 仅在 `_init_agent_registry()` 中新增注册点调用，批次 6 修改 `_init_session_submodules()` 和 `_init_model_config_port()` 中的 `AgentConfigRegistry` 引用。两个批次修改不同函数，不冲突。

---

## 1. 基础设施 — Protocol + 适配器 + 注册点

**负责人**：CC  
**依赖**：无  
**目标**：建立 `AgentConfigProvider` Protocol 和适配器，注册到全局注册点

### 1.1 T1.1 — 新增 AgentConfigProvider Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `AgentConfigProvider` Protocol（`@runtime_checkable`），定义 7 个方法：
  - `get_agent(agent_id: str) -> AgentConfig`
  - `list_agents() -> list[AgentConfig]`
  - `get_default_agent() -> AgentConfig`
  - `has_agent(agent_id: str) -> bool`
  - `reload() -> None`
  - `reload_agent(agent_id: str) -> bool`
  - `load() -> None`
- 验收标准：Protocol 定义编译通过，方法签名与 `AgentConfigRegistry` 公共方法一一对应；Protocol 不暴露 `_agents`/`_loader`/`_loaded`/`_default_agent` 等私有属性

### 1.2 T1.2 — ~~新增 AgentConfig re-export~~ 取消（CC审查修正）

- [x] ~~在 `src/core/types.py` 中新增 re-export~~ — **已取消**：`from src.maisaka.agent.config import AgentConfig` 引入 core→maisaka 运行时依赖，违反核心隔离原则
- **修正方案**：不添加 re-export。`protocols.py` 已有 `TYPE_CHECKING` 守卫 + `from __future__ import annotations`，AgentConfig 类型引用只在 Protocol 签名中使用，运行时无需加载。消费方通过 `TYPE_CHECKING` 守卫从 `src.maisaka.agent.config` 导入类型注解

### 1.3 T1.3 — 新建适配器文件 agent_config_port.py

- [ ] 新建 `src/core/adapters/agent_config_port.py`，包含：
  - `AgentConfigProviderAdapter` 类：构造函数接受 `AgentConfigRegistry` 实例，7 个方法纯委托调用
  - 模块级变量 `_provider: AgentConfigProvider | None = None`
  - `get_agent_config_provider() -> AgentConfigProvider`：返回全局实例，未注册时抛出 `RuntimeError("AgentConfigProvider 未注册，请先调用 set_agent_config_provider()")`
  - `set_agent_config_provider(provider: AgentConfigProvider) -> None`：注册全局实例，重复注册时覆盖并记录 warning 日志
  - `reset_agent_config_provider() -> None`：重置全局实例（仅用于测试）
  - logger 使用 `get_logger("core.adapters.agent_config_port")`
- 验收标准：适配器的 `get_agent()` 返回值与直接调用 `AgentConfigRegistry.get_instance().get_agent()` 完全一致；未注册时 `get_agent_config_provider()` 抛出 `RuntimeError`

### 1.4 T1.4 — 更新适配器包导出

- [ ] 在 `src/core/adapters/__init__.py` 中新增 `from src.core.adapters.agent_config_port import get_agent_config_provider, reset_agent_config_provider  # noqa: F401`
- 验收标准：`from src.core.adapters import get_agent_config_provider` 可正常导入

### 1.5 T1.5 — 启动时注册 AgentConfigProvider

- [ ] 在 `src/main.py` 的 `_init_agent_registry()` 方法中，在 `self._agent_registry.load()` 之后新增：
  ```python
  from src.core.adapters.agent_config_port import AgentConfigProviderAdapter, set_agent_config_provider
  set_agent_config_provider(AgentConfigProviderAdapter(self._agent_registry))
  ```
- 验收标准：启动后 `get_agent_config_provider().get_agent("silver_wolf")` 返回正确的 `AgentConfig` 实例；`get_agent_config_provider().list_agents()` 返回所有已注册智能体列表

---

## 2. 核心自主性层迁移

**负责人**：Codex  
**依赖**：批次 1 完成  
**目标**：`src/maisaka/agent_autonomy/` 下所有消费者迁移到 `AgentConfigProvider`

### 2.1 T2.1 — orchestrator.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/orchestrator.py` 第 1212 行，将函数内延迟导入 `from src.maisaka.agent.registry import AgentConfigRegistry` + `AgentConfigRegistry.get_instance()` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider` + `get_agent_config_provider()`
- 验收标准：文件中不再存在 `from src.maisaka.agent.registry import AgentConfigRegistry` 导入；不再存在 `AgentConfigRegistry.get_instance()` 调用

### 2.2 T2.2 — vitality_manager.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/vitality_manager.py` 第 87-98 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.3 T2.3 — prompt_builder.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/prompt_builder.py` 第 90 行和第 231 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.4 T2.4 — expression_organ.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/expression_organ.py` 第 65 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.5 T2.5 — butler.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/butler.py` 第 23 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 102 行 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.6 T2.6 — behavior_intent.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/behavior_intent.py` 第 126 行和第 172 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.7 T2.7 — ambient_awareness.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/ambient_awareness.py` 第 118 行和第 141 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.8 T2.8 — agent.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/agent.py` 第 55 行和第 165 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.9 T2.9 — session_recovery.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/session_recovery.py` 第 84 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 2.10 T2.10 — summary_generator.py 迁移

- [ ] 在 `src/maisaka/agent_autonomy/state_awareness/summary_generator.py` 第 185 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

---

## 3. 组件层-交互迁移

**负责人**：Codex  
**依赖**：批次 1 完成  
**目标**：`src/maisaka/agent_interaction/` 和 `src/maisaka/builtin_tool/` 下消费者迁移

### 3.1 T3.1 — trigger_scheduler.py 迁移

- [ ] 在 `src/maisaka/agent_interaction/trigger_scheduler.py` 第 13 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 59 行 `self._config_registry = AgentConfigRegistry.get_instance()` 替换为 `self._config_registry = get_agent_config_provider()`；类型注解从 `AgentConfigRegistry` 改为 `AgentConfigProvider`（需 `from src.core.protocols import AgentConfigProvider`，TYPE_CHECKING 导入）
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用；`self._config_registry` 类型注解为 `AgentConfigProvider`

### 3.2 T3.2 — scheduler.py 迁移

- [ ] 在 `src/maisaka/agent_interaction/scheduler.py` 第 12 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 34 行 `self._config_registry = AgentConfigRegistry.get_instance()` 替换为 `self._config_registry = get_agent_config_provider()`；类型注解从 `AgentConfigRegistry` 改为 `AgentConfigProvider`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 3.3 T3.3 — relationship_manager.py 迁移

- [ ] 在 `src/maisaka/agent_interaction/relationship_manager.py` 第 8 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 31 行 `self._registry = AgentConfigRegistry.get_instance()` 替换为 `self._registry = get_agent_config_provider()`；类型注解从 `AgentConfigRegistry` 改为 `AgentConfigProvider`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 3.4 T3.4 — monologue_engine.py 迁移

- [ ] 在 `src/maisaka/agent_interaction/monologue_engine.py` 第 20 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 86 行 `self._config_registry = AgentConfigRegistry.get_instance()` 替换为 `self._config_registry = get_agent_config_provider()`；类型注解从 `AgentConfigRegistry` 改为 `AgentConfigProvider`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 3.5 T3.5 — emotion_registry.py 迁移

- [ ] 在 `src/maisaka/agent_interaction/emotion_registry.py` 第 3 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 11 行 `self._registry = AgentConfigRegistry.get_instance()` 替换为 `self._registry = get_agent_config_provider()`；类型注解从 `AgentConfigRegistry` 改为 `AgentConfigProvider`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 3.6 T3.6 — builtin_tool/butler.py 迁移

- [ ] 在 `src/maisaka/builtin_tool/butler.py` 第 23 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

---

## 4. 组件层-优化器迁移

**负责人**：Codex  
**依赖**：批次 1 完成  
**目标**：`src/maisaka/deepseek/` 和 `src/maisaka/consolidation/` 下消费者迁移

### 4.1 T4.1 — optimizer.py 迁移

- [ ] 在 `src/maisaka/deepseek/optimizer.py` 第 67 行、第 90 行、第 219 行，将 3 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 4.2 T4.2 — prefix_cache.py 迁移

- [ ] 在 `src/maisaka/deepseek/prefix_cache.py` 第 127 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 4.3 T4.3 — model_scheduler.py 迁移

- [ ] 在 `src/maisaka/deepseek/model_scheduler.py` 第 77 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 4.4 T4.4 — budget.py 迁移

- [ ] 在 `src/maisaka/deepseek/budget.py` 第 95 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 4.5 T4.5 — batch_scheduler.py 迁移

- [ ] 在 `src/maisaka/deepseek/batch_scheduler.py` 第 135 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 4.6 T4.6 — consolidation/scheduler.py 迁移

- [ ] 在 `src/maisaka/consolidation/scheduler.py` 第 129 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

---

## 5. 组件层-其他迁移

**负责人**：Codex  
**依赖**：批次 1 完成  
**目标**：`src/maisaka/` 下剩余消费者迁移

### 5.1 T5.1 — heuristic_injector.py 迁移

- [ ] 在 `src/maisaka/memory/heuristic_injector.py` 第 300 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 5.2 T5.2 — person_profile.py 迁移

- [ ] 在 `src/maisaka/memory/person_profile.py` 第 40 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 5.3 T5.3 — relationship/manager.py 迁移

- [ ] 在 `src/maisaka/relationship/manager.py` 第 210 行，将函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 5.4 T5.4 — fork_context.py 迁移

- [ ] 在 `src/maisaka/subagent/fork_context.py` 第 154 行、第 172 行、第 195 行，将 3 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 5.5 T5.5 — runtime.py 迁移

- [ ] 在 `src/maisaka/runtime.py` 第 1023 行和第 1452 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 5.6 T5.6 — chat_loop_service.py 迁移

- [ ] 在 `src/maisaka/chat_loop_service.py` 第 647 行和第 724 行，将 2 处函数内延迟导入 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

---

## 6. 基础设施层迁移 + AgentRouter 解耦 + ruff 守卫

**负责人**：CC  
**依赖**：批次 2-5 完成（确保消费方迁移完毕后再上线守卫）  
**目标**：基础设施层迁移、AgentRouter 解耦、ruff TID251 守卫上线

### 6.1 T6.1 — chat_manager.py 迁移

- [ ] 在 `src/chat/message_receive/chat_manager.py` 第 7 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 57 行 `registry = AgentConfigRegistry()` 替换为 `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.2 T6.2 — binding_restorer.py 迁移

- [ ] 在 `src/chat/message_receive/binding_restorer.py` 第 6 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 25 行 `registry = AgentConfigRegistry()` 替换为 `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.3 T6.3 — webui/agent.py 迁移

- [ ] 在 `src/webui/routers/agent.py` 第 14 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 89 行 `AgentConfigRegistry.get_instance()` 替换为 `get_agent_config_provider()`；第 1390 行 `from src.maisaka.agent.registry import AgentConfigRegistry` 延迟导入删除；第 1392 行 `registry = AgentConfigRegistry()` 替换为 `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.4 T6.4 — webui/deepseek.py 迁移

- [ ] 在 `src/webui/routers/deepseek.py` 第 9 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 24 行 `AgentConfigRegistry()` 替换为 `get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.5 T6.5 — webui/chat/routes.py 迁移

- [ ] 在 `src/webui/routers/chat/routes.py` 第 39 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 265 行 `registry = AgentConfigRegistry()` 替换为 `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.6 T6.6 — plugin_runtime/core.py 迁移

- [ ] 在 `src/plugin_runtime/capabilities/core.py` 第 736 行，将函数内延迟导入 `from src.maisaka.agent.registry import AgentConfigRegistry` + 第 738 行 `registry = AgentConfigRegistry()` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider` + `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.7 T6.7 — statistics_service.py 迁移

- [ ] 在 `src/services/statistics_service.py` 第 12 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 227 行 `registry = AgentConfigRegistry()` 替换为 `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.8 T6.8 — data_migration.py 迁移

- [ ] 在 `src/tools/data_migration.py` 第 24 行，将模块级导入 `from src.maisaka.agent.registry import AgentConfigRegistry` 替换为 `from src.core.adapters.agent_config_port import get_agent_config_provider`；第 72 行 `registry = AgentConfigRegistry()` 替换为 `registry = get_agent_config_provider()`
- 验收标准：文件中不再存在 `AgentConfigRegistry` 引用

### 6.9 T6.9 — AgentRouter 解耦

- [ ] 在 `src/maisaka/agent/router.py` 中：
  - 第 7 行 `from .registry import AgentConfigRegistry` 替换为 `from src.core.protocols import AgentConfigProvider`（TYPE_CHECKING 导入）
  - 第 19 行 `def __init__(self, registry: AgentConfigRegistry) -> None:` 改为 `def __init__(self, registry: AgentConfigProvider) -> None:`
  - 内部 `self._registry.has_agent()`/`self._registry.get_agent()`/`self._registry.get_default_agent()`/`self._registry.list_agents()` 调用不变（方法签名一致）
- 验收标准：`AgentRouter.__init__` 参数类型为 `AgentConfigProvider` Protocol；文件中不再存在 `from .registry import AgentConfigRegistry` 导入

### 6.10 T6.10 — ruff banned-api 守卫上线

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 中新增：
  ```toml
  "src.maisaka.agent.registry.AgentConfigRegistry" = {msg = "禁止直接导入 AgentConfigRegistry，请使用 AgentConfigProvider Protocol 接口（get_agent_config_provider()）"}
  ```
- 验收标准：在核心层文件中添加 `from src.maisaka.agent.registry import AgentConfigRegistry` 后 `ruff check` 报 TID251 错误；`src/core/adapters/*` 和 `src/main.py` 因 per-file-ignores 不报错

### 6.11 T6.11 — main.py AgentRouter 构造迁移

- [ ] 在 `src/main.py` 第 271 行，将 `agent_router = AgentRouter(AgentConfigRegistry())` 替换为 `agent_router = AgentRouter(get_agent_config_provider())`；需新增 `from src.core.adapters.agent_config_port import get_agent_config_provider` 导入
- [ ] 在 `src/main.py` 第 343 行，将 `_init_model_config_port()` 中的 `lambda aid: self._agent_registry.get_agent(aid) if self._agent_registry.has_agent(aid) else None` 替换为 `lambda aid: get_agent_config_provider().get_agent(aid) if get_agent_config_provider().has_agent(aid) else None`（或保留 `self._agent_registry` 引用，因为 `_init_agent_registry()` 已注册到全局注册点，两者等价）
- 验收标准：`_init_session_submodules()` 中不再存在 `AgentConfigRegistry()` 直接实例化

---

## 7. 测试层迁移 + 全量验证

**负责人**：Codex  
**依赖**：批次 6 完成  
**目标**：`tests/` 下消费者迁移，全量验证零违规

### 7.1 T7.1 — test_t093_m3_e2e.py 迁移

- [ ] 在 `tests/test_t093_m3_e2e.py` 中，将 6 处 `from src.maisaka.agent.registry import AgentConfigRegistry` + `AgentConfigRegistry()` 替换为 `from src.core.adapters.agent_config_port import AgentConfigProviderAdapter, get_agent_config_provider` + 使用 `AgentConfigProviderAdapter(AgentConfigRegistry(...))` 或直接 mock `AgentConfigProvider`
- 验收标准：文件中不再存在直接 `AgentConfigRegistry()` 实例化（通过适配器包裹或 mock 替代）

### 7.2 T7.2 — test_t092_stress.py 迁移

- [ ] 在 `tests/test_t092_stress.py` 中，将 10 处 `from src.maisaka.agent.registry import AgentConfigRegistry` + `AgentConfigRegistry()` 替换为适配器包裹或 mock
- 验收标准：文件中不再存在直接 `AgentConfigRegistry()` 实例化

### 7.3 T7.3 — 验证：AgentConfigRegistry 导入仅剩适配器层和 main.py

- [ ] 运行 `rg "from src.maisaka.agent.registry import AgentConfigRegistry" src/` → 仅剩 `src/core/adapters/agent_config_port.py` 和 `src/main.py`
- 验收标准：grep 结果仅包含适配器层和启动入口

### 7.4 T7.4 — 验证：AgentConfigRegistry.get_instance() 零结果

- [ ] 运行 `rg "AgentConfigRegistry.get_instance()" src/` → 零结果
- 验收标准：grep 结果为空

### 7.5 T7.5 — 验证：AgentConfigRegistry() 直接实例化仅剩适配器层和 main.py

- [ ] 运行 `rg "AgentConfigRegistry\(\)" src/` → 仅剩 `src/core/adapters/agent_config_port.py`（适配器构造）和 `src/main.py`（启动时创建 registry 实例）
- 验收标准：grep 结果仅包含适配器层和启动入口

### 7.6 T7.6 — 验证：ruff check 零 TID251 违规

- [ ] 运行 `ruff check src/ --select TID251` → 零违规
- 验收标准：ruff 输出为空，确认所有 `AgentConfigRegistry` 违规导入已被守卫拦截

---

## 迁移模式速查

### 模式 A：函数内延迟导入替换（最常见，~30 处）

```python
# 迁移前
def some_method(self):
    from src.maisaka.agent.registry import AgentConfigRegistry
    registry = AgentConfigRegistry.get_instance()
    agent_cfg = registry.get_agent(agent_id)

# 迁移后
def some_method(self):
    from src.core.adapters.agent_config_port import get_agent_config_provider
    provider = get_agent_config_provider()
    agent_cfg = provider.get_agent(agent_id)
```

### 模式 B：构造函数注入替换（~5 处）

```python
# 迁移前
class SomeClass:
    def __init__(self):
        self._registry = AgentConfigRegistry.get_instance()

# 迁移后
class SomeClass:
    def __init__(self):
        from src.core.adapters.agent_config_port import get_agent_config_provider
        self._registry = get_agent_config_provider()
```

### 模式 C：直接实例化替换（~9 处）

```python
# 迁移前
registry = AgentConfigRegistry()

# 迁移后
from src.core.adapters.agent_config_port import get_agent_config_provider
registry = get_agent_config_provider()
```

### 模式 D：AgentRouter 解耦（1 处）

```python
# 迁移前
class AgentRouter:
    def __init__(self, registry: AgentConfigRegistry) -> None:

# 迁移后
from src.core.protocols import AgentConfigProvider

class AgentRouter:
    def __init__(self, registry: AgentConfigProvider) -> None:
```