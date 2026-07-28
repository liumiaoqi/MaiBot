# CQ-7 Tasks: A_memorix 记忆系统重设计

## 依赖关系

```
P0: T1 → T2 → T3 → T4
P1: T5 → T6 → T7（依赖 P0 全部完成）
P2: T8~T11（延后）
```

---

## T1: config_manager 导入消除

**对应需求**: N1
**对应设计**: AD-3, M1
**负责人**: CC
**预估**: 1.5h

- [ ] 分析 `AMemorixServicePorts` 中 `config_manager` 的所有使用点：
  - `kernel_initializer.py:502-506`：获取 bot.nickname / bot.personality → 改用 `BotConfigPort`
  - `summary_importer.py:189`：存储但从未使用 → 删除死代码
- [ ] `_build_service_ports()` 中删除 `from src.config.config import config_manager` 和 `config_manager=config_manager`
- [ ] `AMemorixServicePorts` 构造参数删除 `config_manager`，新增 `bot_config_port: BotConfigPort`
- [ ] `kernel_initializer.py:502-506` 改为 `bot_config_port.get_bot_nickname()` / `bot_config_port.get_bot_personality()`
- [ ] `summary_importer.py` 中删除 `_config_manager` 死代码
- [ ] 检查 `src/A_memorix/plugin.py` 中 `_build_service_ports()` 调用是否受影响
- [ ] 验证：`ruff check src/A_memorix/host_service.py` 无 TID251 告警

**验证**: A_memorix 启动无 ImportError，config_manager 不再被 A_memorix 直接导入

---

## T2: migration 路径直连

**对应需求**: N2
**对应设计**: AD-4, M2
**负责人**: CC
**预估**: 1h

- [ ] `AMemorixMemoryServicePort.search()` 改为直接调用 `host_service.invoke("search", ...)`，透传全部 Protocol 签名参数（limit, mode, chat_id, time_start, time_end, respect_filter, user_id, group_id）
- [ ] `AMemorixMemoryServicePort.get_person_profile()` 改为直接调用 `host_service.invoke("get_person_profile", ...)`
- [ ] `AMemorixMemoryServicePort.build_profile_injection_text()` 改为直接调用 `host_service.invoke("build_profile_injection_text", ...)`
- [ ] 删除 `src/services/memory_service.py` 中 `migration_search`、`migration_get_person_profile`、`migration_build_profile_injection_text` 三个方法（如果无其他调用方）
- [ ] 单元测试：验证 search 透传全部参数

**验证**: search 不再忽略 Protocol 签名参数；migration_* 方法无调用方

---

## T3: NullMemoryServicePort 新建

**对应需求**: N3
**对应设计**: AD-2, M3
**负责人**: CC
**预估**: 1h

- [ ] 在 `src/core/adapters/memory_service.py` 中新建 `NullMemoryServicePort` 类
- [ ] 实现核心 6 方法（observe_experience, search, recall, recall_with_intuition, derive_profile, build_profile_injection_text），返回类型安全的空结果（见 design.md AD-2）
- [ ] 实现管理 9 方法，返回空 dict 或抛 `MemoryServiceNotAvailableError`
- [ ] 添加 `disabled: bool = True` 属性
- [ ] 修改 `get_memory_service_port()` 逻辑：A_memorix 未启用时返回 `NullMemoryServicePort` 实例
- [ ] 单元测试：每个方法返回值类型正确

**验证**: A_memorix 未启用时，所有记忆方法返回类型安全空结果而非类型不匹配的 dict

---

## T4: 方法计数修正

**对应需求**: N4
**对应设计**: M4
**负责人**: Codex
**预估**: 5min

- [ ] `AGENTS.md` 中 "16方法" → "15方法"（拆分后改为 "6核心+9管理"）
- [ ] `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc` 中同步修正

**验证**: 文档与代码一致

---

## T5: MemoryServicePort 拆分

**对应需求**: N5
**对应设计**: AD-1, M5
**负责人**: CC
**预估**: 2h

- [ ] `src/core/protocols.py` 中 `MemoryServicePort` 保留核心 6 方法
- [ ] 新增 `MemoryAdminPort(Protocol)` 含管理 9 方法
- [ ] `AMemorixMemoryServicePort` 同时实现两个 Protocol
- [ ] `NullMemoryServicePort` 只实现 `MemoryServicePort`（6 方法）
- [ ] 新增 `NullMemoryAdminPort` 实现管理 9 方法的空实现
- [ ] 导出更新：`src/core/adapters/__init__.py` 导出 `get_memory_admin_port`

**验证**: `isinstance(port, MemoryServicePort)` 和 `isinstance(admin_port, MemoryAdminPort)` 均为 True

---

## T6: NullMemoryServicePort 适配拆分

**对应需求**: N6
**对应设计**: AD-6, M6
**负责人**: Codex
**预估**: 30min

- [ ] `NullMemoryServicePort` 只保留核心 6 方法
- [ ] 新建 `NullMemoryAdminPort` 实现管理 9 方法的空实现
- [ ] 未启用时 `get_memory_admin_port()` 返回 `NullMemoryAdminPort`

**验证**: 未启用时核心方法返回空结果，管理方法返回空 dict

---

## T7: 消费方更新

**对应需求**: N7
**对应设计**: M7
**负责人**: CC/Codex
**预估**: 2h

- [ ] 审计 15 个消费方文件，分类：
  - **只需 MemoryServicePort**：orchestrator, agent, chat_loop_service, prompt_builder, tool_post_execution, heuristic_injector, context.py, person_info
  - **需要 MemoryAdminPort**：memory_flow_service, webui/routers/agent, capabilities/data
- [ ] 需要管理方法的消费方额外导入 `get_memory_admin_port()`
- [ ] 编译检查：所有 15 个文件 import 无报错

**验证**: `ruff check` + 所有消费方文件无 import 错误

---

## T8~T11: P2 架构清理（延后）

- T8: 数据目录重命名 `data/plugins/a-dawn.a-memorix/` → `data/a_memorix/`（含迁移脚本）
- T9: 消除 `src/services/memory_service.py` 中间层
- T10: 删除 `src/A_memorix/plugin.py`
- T11: `paths.py` 清理（删除 `a-dawn.a-memorix` 硬编码）