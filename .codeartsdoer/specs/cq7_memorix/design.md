# CQ-7 Design: A_memorix 记忆系统重设计

## 架构决策

### AD-1: 接口拆分策略

**决策**：MemoryServicePort 拆分为 `MemoryServicePort`（核心 6 方法）+ `MemoryAdminPort`（管理 9 方法）。

**核心 6 方法**（高频，每次对话必调用）：

| 方法 | 职责 |
|------|------|
| `observe_experience` | 写入观察 |
| `search` | 检索记忆 |
| `recall` | 概念激活扩散召回 |
| `recall_with_intuition` | 直觉召回 |
| `derive_profile` | 画像实时视图 |
| `build_profile_injection_text` | 构建画像注入文本 |

**管理 9 方法**（低频，运维/管理操作）：

| 方法 | 职责 |
|------|------|
| `get_person_profile` | 查询人物画像 |
| `profile_admin` | 画像管理 |
| `maintain_memory` | 记忆维护 |
| `delete_admin` | 删除管理 |
| `enqueue_feedback_task` | 反馈纠错 |
| `set_memory_personality` | 设置记忆性格 |
| `reflect` | 反思 |
| `weave_narrative` | 叙事编织 |
| `heartbeat_maintenance` | 心跳维护 |

**理由**：核心 6 方法是智能体每次对话的必经路径，管理 9 方法只在特定场景调用。拆分后 NullMemoryServicePort 只需实现核心 6 方法，管理操作在未启用时直接不可用（抛 `NotImplementedError` 或返回空结果）。

### AD-2: NullMemoryServicePort 实现

**决策**：新建 `NullMemoryServicePort` 类，实现核心 6 方法，返回类型安全的空结果。

**返回值设计**：

| 方法 | 返回值 |
|------|--------|
| `observe_experience` | `MemoryWriteResult(success=False, observation_id="", concept_names=[])` |
| `search` | `MemorySearchResult(items=[], total=0)` |
| `recall` | `[]` |
| `recall_with_intuition` | `RecallResult(items=[], context="")` |
| `derive_profile` | `ProfileView.empty()` 或空 dict |
| `build_profile_injection_text` | `""` |

**管理 9 方法**：全部返回空 dict 或抛 `MemoryServiceNotAvailableError`（自定义异常，不吞没）。

**属性**：`disabled: bool = True` 标记，消费方可据此判断是否跳过记忆相关逻辑。

### AD-3: config_manager 导入消除

**决策**：`_build_service_ports()` 中 `config_manager` 替换为 `ModelConfigPort` + `BotConfigPort`。

**理由**：`AMemorixServicePorts` 中 `config_manager` 有两处实际使用：
1. `kernel_initializer.py:502-506`：`config_manager.get_global_config()` 获取 `bot.nickname` 和 `bot.personality` — 这是 **BotConfig**，不是模型配置
2. `summary_importer.py:189`：存储为 `_config_manager` 但从未使用 — **死代码**，可直接删除

`ModelConfigPort` 只覆盖模型配置（API key、model name、temperature），**无法替代** BotConfig 调用。需同时引入 `BotConfigPort`（已有 `GlobalConfigBotConfigPort` 适配器实现）。

**改动**：
1. `AMemorixServicePorts` 构造参数 `config_manager` → 删除，新增 `bot_config_port: BotConfigPort`
2. `_build_service_ports()` 中 `from src.config.config import config_manager` → 删除
3. `kernel_initializer.py:502-506` 改为 `bot_config_port.get_bot_nickname()` / `bot_config_port.get_bot_personality()`
4. `summary_importer.py` 中 `_config_manager` 死代码 → 删除

### AD-4: migration 路径直连

**决策**：`search` / `get_person_profile` / `build_profile_injection_text` 三个方法从 `migration_*` 路径切换为直接调用连接主义方法。

**理由**：migration 路径是旧范式（段落式记忆）→ 新范式（连接主义记忆）的过渡桥，Phoenix 完成后连接主义已是唯一范式，migration 路径只剩不必要的间接层。

**实现**：
- `search()` → 直接调用 `host_service.invoke("search", ...)`，透传全部 Protocol 签名参数
- `get_person_profile()` → 直接调用 `host_service.invoke("get_person_profile", ...)` 
- `build_profile_injection_text()` → 直接调用 `host_service.invoke("build_profile_injection_text", ...)`

### AD-5: 中间层消除策略（P2 延后）

**决策**：P0/P1 阶段不消除 `src/services/memory_service.py` 中间层。

**理由**：中间层虽冗余但无害，消除需要改写 `AMemorixMemoryServicePort` 的所有方法调用路径（15 处），风险大于收益。P2 阶段在接口拆分稳定后再消除。

### AD-6: 数据目录重命名（P2 延后）

**决策**：P0/P1 阶段不重命名 `data/plugins/a-dawn.a-memorix/`。

**理由**：重命名涉及数据迁移、路径引用更新、Docker 挂载调整，风险高且不影响功能。P2 阶段处理。

### AD-7: plugin.py 处理（P2 延后）

**决策**：P0/P1 阶段不删除 `src/A_memorix/plugin.py`。

**理由**：文件头部已标注 legacy，主线不加载。删除需确认无任何外部引用。P2 阶段处理。

## 修改清单

### P0：最小修复

#### M1: config_manager 导入消除
- **文件**: `src/A_memorix/host_service.py`
- **改动**:
  1. `_build_service_ports()` 中删除 `from src.config.config import config_manager`
  2. `AMemorixServicePorts` 构造中删除 `config_manager=config_manager`
  3. 检查 `AMemorixServicePorts` 内部使用 `config_manager` 的地方，改为使用 `model_config_port`
- **文件**: `src/A_memorix/plugin.py`（如果 AMemorixServicePorts 签名变化）
- **对应需求**: N1

#### M2: migration 路径直连
- **文件**: `src/core/adapters/memory_service.py`
- **改动**:
  1. `search()` → 直接调用 `host_service.invoke("search", ...)`，透传全部参数
  2. `get_person_profile()` → 直接调用 `host_service.invoke("get_person_profile", ...)`
  3. `build_profile_injection_text()` → 直接调用 `host_service.invoke("build_profile_injection_text", ...)`
- **对应需求**: N2

#### M3: NullMemoryServicePort 新建
- **文件**: `src/core/adapters/memory_service.py`（同文件添加）
- **改动**: 新建 `NullMemoryServicePort` 类，实现核心 6 方法（见 AD-2）
- **对应需求**: N3

#### M4: 方法计数修正
- **文件**: `AGENTS.md`、`.codeartsdoer/rule/MaiBot智能体自主性架构.mdc`
- **改动**: "16方法" → "15方法"（拆分后为"6核心+9管理"）
- **对应需求**: N4

### P1：接口瘦身

#### M5: MemoryServicePort 拆分
- **文件**: `src/core/protocols.py`
- **改动**:
  1. `MemoryServicePort` 保留核心 6 方法
  2. 新增 `MemoryAdminPort(Protocol)` 含管理 9 方法
  3. `MemoryAdminPort` 可选组合：消费方按需导入
- **对应需求**: N5

#### M6: NullMemoryServicePort 适配
- **文件**: `src/core/adapters/memory_service.py`
- **改动**: `NullMemoryServicePort` 只实现 `MemoryServicePort`（6 方法），不实现 `MemoryAdminPort`
- **对应需求**: N6

#### M7: 消费方更新
- **文件**: 15 个消费方文件（见调研报告第 6 节）
- **改动**:
  1. 需要管理方法的消费方额外导入 `MemoryAdminPort`
  2. 核心消费方（orchestrator、agent、chat_loop_service）只需 `MemoryServicePort`
  3. WebUI/运维消费方需要 `MemoryAdminPort`
- **对应需求**: N7

### P2：架构清理（延后）

- M8: 数据目录重命名 `data/plugins/a-dawn.a-memorix/` → `data/a_memorix/`
- M9: 消除 `src/services/memory_service.py` 中间层
- M10: 删除 `src/A_memorix/plugin.py`
- M11: `paths.py` 清理

## 不做的事

1. **不重写 `_dispatch()` 巨型 if-elif**：可维护性差但功能正确，重构风险高
2. **不改变消费方的延迟导入模式**：59 处引用改为依赖注入是全局重构，不在 CQ-7 范围
3. **不修改 AMemorixConfig 结构**：13 个子配置段虽多但功能完整，无重构必要
4. **不修改 A_memorix 核心算法**（5 子系统）：CQ-7 只改接口层和胶水代码

## 测试策略

1. **单元测试**：`NullMemoryServicePort` 每个方法返回值类型正确
2. **单元测试**：`AMemorixMemoryServicePort.search()` 透传全部参数（不再忽略）
3. **集成测试**：A_memorix 启动 → `observe_experience` → `search` → 结果非空
4. **集成测试**：A_memorix 未启用 → `NullMemoryServicePort` → 所有方法返回类型安全空结果
5. **编译检查**：15 个消费方文件 import 无报错