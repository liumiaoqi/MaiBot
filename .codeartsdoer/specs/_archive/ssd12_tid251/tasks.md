# SSD-12 编码任务：剩余 TID251 违规消除

> 目标：消除 10 处非 global_config 的 TID251 违规（config_manager 4 处 / heartflow_manager 2 处 / Person 4 处）
>
> Codex 典型错误模式提醒（每个批次执行前必读）：
> 1. 替换调用但忘了添加新 import（F821）
> 2. 替换调用但忘了删除旧 import（F401）
> 3. noqa 注释被当成 import 路径的一部分
> 4. 变量替换后后续引用未同步更新
> 5. Windows 环境：PowerShell 不支持 `&&`，用 `;` 或分步执行

## 批次 0：基础设施（快照类型 + Protocol 方法签名 + 全局注册点）

> 依赖：无（后续所有批次依赖本批次）

- [ ] **T0.1** 在 `src/core/types.py` 新增 2 个快照类型
  - `PluginRuntimeSnapshot`（frozen dataclass：enabled: bool / ipc_socket_path: str / health_check_interval_sec: float / max_restart_attempts: int / runner_spawn_timeout_sec: float / hook_blocking_timeout_sec: float，全部有默认值）
  - `PersonDetailSnapshot`（frozen dataclass：is_known: bool / person_id: str / person_name: str / nickname: str，全部有默认值）
  - 更新 `__all__` 导出列表
  - 验证：`ruff check src/core/types.py` 通过
  - CC/Codex 建议：CC（快照设计需理解 frozen dataclass 兼容性，首次设计必须正确）

- [ ] **T0.2** 在 `src/core/protocols.py` 扩展 `AppConfigPort` 新增 5 个方法签名
  - `get_plugin_runtime_config(self) -> PluginRuntimeSnapshot`
  - `register_reload_callback(self, callback: object) -> None`
  - `unregister_reload_callback(self, callback: object) -> None`
  - `get_global_config_json(self) -> str`
  - `get_model_config_json(self) -> str`
  - 更新 docstring：覆盖域列表新增 plugin_runtime / 热重载回调 / 配置序列化
  - 验证：`ruff check src/core/protocols.py` 通过
  - CC/Codex 建议：CC

- [ ] **T0.3** 在 `src/core/protocols.py` 扩展 `ChatRuntimeRegistry` 新增 2 个方法签名
  - `get_runtime_sync(self, session_id: str) -> Optional[ChatRuntime]` — 同步字典查找
  - `remove_runtime(self, session_id: str) -> Optional[ChatRuntime]` — 同步移除并返回
  - 更新 docstring
  - 验证：`ruff check src/core/protocols.py` 通过
  - CC/Codex 建议：CC

- [ ] **T0.4** 在 `src/core/protocols.py` 扩展 `PersonInfoPort` 新增 5 个方法签名
  - `get_person_id(self, platform: str, user_id: str) -> str`
  - `get_person_id_by_name(self, person_name: str) -> str`
  - `get_person_attribute(self, person_id: str, field_name: str) -> Any`
  - `get_person_detail(self, person_id: str) -> Optional[PersonDetailSnapshot]`
  - `async def store_person_memory(self, person_name: str, fact: str, session_id: str, *, person_id: str = "", evidence_source: str = "user_supported", evidence_message_ids: list[str] | None = None) -> None`
  - 更新 docstring
  - 验证：`ruff check src/core/protocols.py` 通过
  - CC/Codex 建议：CC

- [ ] **T0.5** 新建 `src/core/model_config_port_registry.py`
  - 遵循 `app_config_port_registry.py` 的 `register/get/reset` 三函数模式
  - `register_model_config_port(port: ModelConfigPort) -> None`
  - `get_model_config_port() -> Optional[ModelConfigPort]`
  - `reset_model_config_port() -> None`
  - 使用 `TYPE_CHECKING` 避免循环导入
  - 验证：`ruff check src/core/model_config_port_registry.py` 通过
  - CC/Codex 建议：Codex（参照 `app_config_port_registry.py` 机械复制，改名称即可）

- [ ] **T0.6** 提交批次 0
  - commit message: `feat(core): SSD-12 批次0 — 快照类型(PluginRuntime/PersonDetail)+Protocol方法签名+model_config_port_registry [CC]`
  - 验证：`ruff check src/core/` 通过

## 批次 1：适配器实现

> 依赖：批次 0

- [ ] **T1.1** 在 `src/core/adapters/app_config_port.py` 新增 5 个方法实现
  - `get_plugin_runtime_config()` → 从 `_get_cfg().plugin_runtime` 构造 `PluginRuntimeSnapshot`（6 字段映射）
  - `register_reload_callback(callback)` → 委托 `config_manager.register_reload_callback(callback)`
  - `unregister_reload_callback(callback)` → 委托 `config_manager.unregister_reload_callback(callback)`
  - `get_global_config_json()` → `config_manager.get_global_config().model_dump(mode="json")`
  - `get_model_config_json()` → `config_manager.get_model_config().model_dump(mode="json")`
  - 注意：`register_reload_callback`/`unregister_reload_callback` 需通过 `_get_config_manager()` 获取 config_manager 实例（适配器是唯一允许导入 config_manager 的地方）
  - 更新类 docstring
  - 验证：`ruff check src/core/adapters/app_config_port.py` 通过
  - CC/Codex 建议：Codex（按 design.md D2-D4 字段映射表机械编写，但需注意 config_manager 获取方式）

- [ ] **T1.2** 在 `src/core/adapters/runtime_registry.py` 新增 2 个方法实现
  - `get_runtime_sync(session_id)` → `self._heartflow_manager.heartflow_chat_list.get(session_id)`（同步字典查找）
  - `remove_runtime(session_id)` → `self._heartflow_manager.heartflow_chat_list.pop(session_id, None)`（同步移除并返回）
  - 验证：`ruff check src/core/adapters/runtime_registry.py` 通过
  - CC/Codex 建议：Codex（2 个简单方法，纯委托）

- [ ] **T1.3** 在 `src/core/adapters/person_info_port.py` 新增 5 个方法实现
  - `get_person_id(platform, user_id)` → 委托 `person_info.get_person_id(platform, user_id)`（参照 `person_info.py:49-55`，纯 MD5 无数据库访问）
  - `get_person_id_by_name(person_name)` → 委托 `get_person_id_by_person_name(person_name)`（`person_info.py:58-67`，查数据库）
  - `get_person_attribute(person_id, field_name)` → 创建 `Person(person_id=person_id)` 实例，`getattr(person, field_name)`，字段不存在返回 None
  - `get_person_detail(person_id)` → 创建 `Person(person_id=person_id)` 实例，构造 `PersonDetailSnapshot(is_known=person.is_known, person_id=person.person_id, person_name=person.person_name or "", nickname=person.nickname or "")`
  - `async def store_person_memory(...)` → 委托 `store_person_memory_from_answer(person_name, fact, session_id, person_id=person_id, evidence_source=evidence_source, evidence_message_ids=evidence_message_ids)`
  - 注意：`store_person_memory` 是异步方法，需导入 `store_person_memory_from_answer`
  - 验证：`ruff check src/core/adapters/person_info_port.py` 通过
  - CC/Codex 建议：Codex（按 design.md D7-D11 委托模式机械编写，注意异步方法）

- [ ] **T1.4** 提交批次 1
  - commit message: `feat(core): SSD-12 批次1 — AppConfigPort/ChatRuntimeRegistry/PersonInfoPort适配器新增12方法实现 [CX]`
  - 验证：`ruff check src/core/adapters/` 通过

## 批次 2：现有注入点迁移到 model_config_port_registry

> 依赖：批次 0（model_config_port_registry.py）

- [ ] **T2.1** 迁移 `src/services/service_task_resolver.py` 的注入点
  - 将 `set_model_config_port(port)` 改为调用 `model_config_port_registry.register_model_config_port(port)`
  - 将 `_model_config_port` 变量改为从 `model_config_port_registry.get_model_config_port()` 获取
  - 移除模块级 `_model_config_port` 变量和 `set_model_config_port()` 函数（或改为委托 registry）
  - 注意：`_get_model_config()` 中的回退逻辑保留，但改为从 registry 获取 Port
  - 验证：`ruff check src/services/service_task_resolver.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T2.2** 迁移 `src/llm_models/model_client/__init__.py` 的注入点
  - 将 `set_model_config_port(port)` 改为调用 `model_config_port_registry.register_model_config_port(port)`
  - 将 `_model_config_port` 变量改为从 `model_config_port_registry.get_model_config_port()` 获取
  - 验证：`ruff check src/llm_models/model_client/__init__.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T2.3** 迁移 `src/llm_models/utils_model.py` 的注入点
  - 将 `set_model_config_port(port)` 改为调用 `model_config_port_registry.register_model_config_port(port)`
  - 将 `_model_config_port` 变量改为从 `model_config_port_registry.get_model_config_port()` 获取
  - 注意：该文件有 17 处 `_model_config_port` 引用，需逐一替换为 registry 调用
  - 验证：`ruff check src/llm_models/utils_model.py` 通过
  - CC/Codex 建议：Codex（17 处引用替换，机械但量大）

- [ ] **T2.4** 提交批次 2
  - commit message: `refactor: SSD-12 批次2 — 3处ModelConfigPort注入点迁移到model_config_port_registry [CX]`

## 批次 3：config_manager 违规迁移 — VLM/planner 查询

> 依赖：批次 1（ModelConfigPort 适配器）+ 批次 2（model_config_port_registry）

- [ ] **T3.1** 迁移 `src/chat/image_system/image_manager.py` 的 config_manager 访问
  - 替换 `config_manager.get_model_config().model_task_config.vlm.model_list` → `get_model_config_port().get_task_config("vlm").model_list`
  - 替换 `from src.config.config import config_manager` → `from src.core.model_config_port_registry import get_model_config_port`
  - 处理 `_is_vlm_task_configured()` 中的 None 情况（Port 未注册时返回 False）
  - 验证：`ruff check src/chat/image_system/image_manager.py` 通过
  - CC/Codex 建议：Codex（1 处替换，模式明确）

- [ ] **T3.2** 迁移 `src/maisaka/visual/chat_history_refresher.py` 的 config_manager 访问
  - 替换 `config_manager.get_model_config().model_task_config.vlm.model_list` → `get_model_config_port().get_task_config("vlm").model_list`
  - 替换 `from src.config.config import config_manager` → `from src.core.model_config_port_registry import get_model_config_port`
  - 验证：`ruff check src/maisaka/visual/chat_history_refresher.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T3.3** 迁移 `src/cli/maisaka_cli.py` 的 config_manager 访问
  - 替换 `config_manager.get_model_config().model_task_config.planner.model_list[0]` → `get_model_config_port().get_task_config("planner").model_list[0]`
  - 替换 `from src.config.config import config_manager` → `from src.core.model_config_port_registry import get_model_config_port`
  - 注意：该文件还导入了 `heartflow_manager`（批次 5 处理），本期仅迁移 config_manager 部分
  - 验证：`ruff check src/cli/maisaka_cli.py` 通过
  - CC/Codex 建议：Codex

- [ ] **T3.4** 提交批次 3
  - commit message: `refactor: SSD-12 批次3 — config_manager VLM/planner查询迁移到ModelConfigPort [CX]`

## 批次 4：config_manager 违规迁移 — integration.py

> 依赖：批次 1（AppConfigPort 适配器）

- [ ] **T4.1** 迁移 `src/plugin_runtime/integration.py` 的全部 config_manager 访问（7 处）
  - **插件运行时配置查询（2 处）**：
    - L290: `config_manager.get_global_config().plugin_runtime` → `get_app_config_port().get_plugin_runtime_config()`
    - L565: `config_manager.get_global_config().plugin_runtime` → `get_app_config_port().get_plugin_runtime_config()`
    - 后续属性访问改为快照属性访问（如 `_cfg.enabled` → `config.enabled`，`_cfg.ipc_socket_path` → `config.ipc_socket_path`）
  - **热重载回调注册/注销（3 处）**：
    - L600: `config_manager.register_reload_callback(self._config_reload_callback)` → `get_app_config_port().register_reload_callback(self._config_reload_callback)`
    - L609: `config_manager.unregister_reload_callback(self._config_reload_callback)` → `get_app_config_port().unregister_reload_callback(self._config_reload_callback)`
    - L630: `config_manager.unregister_reload_callback(self._config_reload_callback)` → `get_app_config_port().unregister_reload_callback(self._config_reload_callback)`
  - **配置序列化广播（2 处）**：
    - L1116: `config_manager.get_global_config().model_dump(mode="json")` → `get_app_config_port().get_global_config_json()`
    - L1118: `config_manager.get_model_config().model_dump(mode="json")` → `get_app_config_port().get_model_config_json()`
  - 替换 `from src.config.config import config_manager` → `from src.core.app_config_port_registry import get_app_config_port`
  - 注意：`_resolve_supervisor_socket_paths()` 是 `@staticmethod`，需改为从 registry 获取 Port
  - 验证：`ruff check src/plugin_runtime/integration.py` 通过
  - CC/Codex 建议：CC（integration.py 面积大 1676 行，7 处替换需确保不引入副作用，且 _resolve_supervisor_socket_paths 静态方法需特殊处理）

- [ ] **T4.2** 提交批次 4
  - commit message: `refactor: SSD-12 批次4 — integration.py config_manager迁移到AppConfigPort [CC]`

## 批次 5：heartflow_manager 违规迁移

> 依赖：批次 1（HeartflowRuntimeRegistry 适配器）

- [ ] **T5.1** 迁移 `src/cli/maisaka_cli.py` 的 heartflow_manager 访问
  - 替换 L123: `heartflow_manager.heartflow_chat_list.pop(self._session_id, None)` → `get_chat_runtime_registry().remove_runtime(self._session_id)`
  - 替换 `from src.chat.heart_flow.heartflow_manager import heartflow_manager` → `from src.core.runtime_port_registry import get_chat_runtime_registry`
  - 注意：`remove_runtime()` 返回 `Optional[ChatRuntime]`，与 `dict.pop()` 行为等价
  - 验证：`ruff check src/cli/maisaka_cli.py` 通过
  - CC/Codex 建议：Codex（1 处替换，模式明确）

- [ ] **T5.2** 迁移 `src/services/send_service.py` 的 heartflow_manager 访问
  - 替换 L737-739: 延迟导入 `from src.chat.heart_flow.heartflow_manager import heartflow_manager` + `heartflow_manager.heartflow_chat_list.get(session_id)` → `from src.core.runtime_port_registry import get_chat_runtime_registry` + `get_chat_runtime_registry().get_runtime_sync(session_id)`
  - 注意：原代码是延迟导入（在函数体内），替换后保持延迟导入模式
  - 验证：`ruff check src/services/send_service.py` 通过
  - CC/Codex 建议：Codex（1 处替换，保持延迟导入模式）

- [ ] **T5.3** 提交批次 5
  - commit message: `refactor: SSD-12 批次5 — heartflow_manager迁移到ChatRuntimeRegistry [CX]`

## 批次 6：Person 违规迁移 — data.py

> 依赖：批次 1（PersonInfoPortAdapter）

- [ ] **T6.1** 迁移 `src/plugin_runtime/capabilities/data.py` 的 Person 访问（3 处延迟导入）
  - `_cap_person_get_id` (L562-575)：替换 `from src.person_info.person_info import Person` + `Person(platform=platform, user_id=str(user_id)).person_id` → `from src.core.person_info_port_registry import get_person_info_port` + `get_person_info_port().get_person_id(platform, str(user_id))`
  - `_cap_person_get_value` (L577-593)：替换 `from src.person_info.person_info import Person` + `Person(person_id=person_id)` + `getattr(person, field_name)` → `get_person_info_port().get_person_attribute(person_id, field_name)`
  - `_cap_person_get_id_by_name` (L595-607)：替换 `from src.person_info.person_info import Person` + `Person(person_name=person_name).person_id` → `get_person_info_port().get_person_id_by_name(person_name)`
  - 注意：3 处均为方法内延迟导入，替换后保持延迟导入模式
  - 验证：`ruff check src/plugin_runtime/capabilities/data.py` 通过
  - CC/Codex 建议：Codex（3 处替换，模式明确）

- [ ] **T6.2** 提交批次 6
  - commit message: `refactor: SSD-12 批次6 — data.py Person迁移到PersonInfoPort [CX]`

## 批次 7：Person 违规迁移 — memory_flow_service.py

> 依赖：批次 1（PersonInfoPortAdapter）

- [ ] **T7.1** 迁移 `src/services/memory_flow_service.py` 的 Person 访问
  - 替换 `from src.person_info.person_info import Person, get_person_id, store_person_memory_from_answer` → `from src.core.person_info_port_registry import get_person_info_port`
  - **`_writeback_person_facts` 方法 (L120-131)**：
    - 替换 `await store_person_memory_from_answer(...)` → `await get_person_info_port().store_person_memory(...)`
    - 替换 `str(getattr(target_person, "person_id", "")).strip()` → `target_person_detail.person_id`（需配合下方 `_resolve_target_person` 重构）
  - **`_resolve_target_person` 方法 (L133-144)**：
    - 替换 `person_id = get_person_id(session_platform, session_user_id)` → `person_id = get_person_info_port().get_person_id(session_platform, session_user_id)`
    - 替换 `person = Person(person_id=person_id)` + `person.is_known` → `detail = get_person_info_port().get_person_detail(person_id)` + `detail.is_known if detail else False`
    - 返回值从 `Optional[Person]` 改为 `Optional[PersonDetailSnapshot]`
  - **`_person_from_user_message` 方法 (L183-193)**：
    - 替换 `person_id = get_person_id(platform, user_id)` → `person_id = get_person_info_port().get_person_id(platform, user_id)`
    - 替换 `person = Person(person_id=person_id)` + `person.is_known` → `detail = get_person_info_port().get_person_detail(person_id)` + `detail.is_known if detail else False`
    - 返回值从 `Optional[Person]` 改为 `Optional[PersonDetailSnapshot]`
  - **`_filter_target_user_messages` 方法 (L263-284)**：
    - 替换 `get_person_id(platform, user_id)` → `get_person_info_port().get_person_id(platform, user_id)`
    - 注意：该方法是 `@staticmethod`，需改为普通方法或传入 port 参数
  - **类型标注更新**：
    - `_collect_user_evidence(self, message: Any, person: Person)` → `_collect_user_evidence(self, message: Any, person: PersonDetailSnapshot)`
    - `_filter_target_user_messages(messages, person: Person, seen_ids)` → 参数类型更新
  - 验证：`ruff check src/services/memory_flow_service.py` 通过
  - CC/Codex 建议：CC（memory_flow_service.py 涉及 Person 类的 3 种用法——实例化判断 is_known、get_person_id 函数、store_person_memory_from_answer 函数——返回值类型从 Person 改为 PersonDetailSnapshot 影响面较大，需确保所有下游引用同步更新）

- [ ] **T7.2** 提交批次 7
  - commit message: `refactor: SSD-12 批次7 — memory_flow_service.py Person迁移到PersonInfoPort [CC]`

## 批次 8：收尾（ruff 守卫验证 + AGENTS.md 更新）

> 依赖：批次 3-7（所有违规文件迁移完成后）

- [ ] **T8.1** 收紧 `pyproject.toml` 的 per-file-ignores
  - 移除已完成迁移文件的 TID251 豁免：
    - `src/chat/image_system/image_manager.py`（config_manager 已迁移）
    - `src/maisaka/visual/chat_history_refresher.py`（config_manager 已迁移）
    - `src/cli/maisaka_cli.py`（config_manager + heartflow_manager 已迁移）
    - `src/plugin_runtime/integration.py`（config_manager 已迁移）
    - `src/services/send_service.py`（heartflow_manager 已迁移）
    - `src/plugin_runtime/capabilities/data.py`（Person 已迁移）
    - `src/services/memory_flow_service.py`（Person 已迁移）
  - 保留合法豁免：`src/core/adapters/*`、`src/main.py`、`src/config/config.py`、`src/A_memorix/**`、`src/person_info/person_info.py` 等
  - 验证：`ruff check` 全项目通过（config_manager/heartflow_manager/Person 相关 TID251 清零）
  - CC/Codex 建议：CC

- [ ] **T8.2** 更新 `AGENTS.md` Protocol 表格
  - `ModelConfigPort`：方法数不变（4+2），新增全局注册点 `model_config_port_registry.py`
  - `AppConfigPort`：方法数 +5（plugin_runtime 快照 1 + 热重载回调 2 + 配置序列化 2）
  - `ChatRuntimeRegistry`：方法数 3 → 5（+get_runtime_sync +remove_runtime）
  - `PersonInfoPort`：方法数 1 → 6（+get_person_id +get_person_id_by_name +get_person_attribute +get_person_detail +store_person_memory）
  - 新增 `PluginRuntimeSnapshot` / `PersonDetailSnapshot` 快照类型说明
  - 新增 `model_config_port_registry.py` 全局注册点说明
  - CC/Codex 建议：CC

- [ ] **T8.3** 更新 `AGENTS.md` 已完成 SSD 摘要
  - 添加 SSD-12 行：主题="剩余 TID251 违规消除"，关键成果="config_manager 4处/heartflow_manager 2处/Person 4处 TID251 清零，AppConfigPort +5方法，ChatRuntimeRegistry +2方法，PersonInfoPort +5方法，新建 model_config_port_registry"
  - 更新"待后续"清单：移除 SSD-12 已完成项
  - CC/Codex 建议：CC

- [ ] **T8.4** 最终验证
  - `ruff check` 全项目通过
  - 容器启动正常，功能无回归
  - 10 处 TID251 违规清零：
    - `config_manager` 违规：0 处（原 4 处）
    - `heartflow_manager` 违规：0 处（原 2 处）
    - `Person` 违规：0 处（原 4 处）
  - CC/Codex 建议：CC

- [ ] **T8.5** 提交收尾
  - commit message: `chore: SSD-12 收尾 — ruff守卫收紧+AGENTS.md更新+Protocol表格同步 [CC]`

## 延迟项（不在 SSD-12 范围，defer to SSD-13）

- ⬜ **G1**: `src/maisaka/memory/heuristic_injector.py:17` 导入 `get_person_id`（非 TID251 违规，但架构上是同一反模式）→ 替换为 `get_person_info_port().get_person_id(platform, user_id)`
- ⬜ **G2**: `pytests/A_memorix_test/test_memory_flow_service.py` 测试文件 — monkeypatch 目标从模块级函数改为 Port 方法，需同步更新 mock 路径