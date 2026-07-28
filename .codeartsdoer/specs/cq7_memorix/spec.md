# CQ-7: A_memorix 记忆系统重设计

## 目标

让记忆系统在当前核心架构下正确运行，消除"插件"假象，瘦身接口，补齐 NullMemoryServicePort 降级路径。

## 现状分析

### 代码结构

5 子系统全部活跃：NarrativeWeaver / CognitiveStratifier / LifecycleManager / IntuitionEngine / MemoryField。

核心入口：`src/A_memorix/host_service.py`（AMemorixHostService 单例）

### 接口匹配度（15 方法）

| 问题方法 | 现状 | 问题 |
|---------|------|------|
| `search` | 走 `migration_search` 而非 `search_memory` | 不必要的间接层 |
| `get_person_profile` | 走 `migration_get_person_profile` | 同上 |
| `build_profile_injection_text` | 走 `migration_build_profile_injection_text` | 同上 |

其余 12 方法正常。AGENTS.md 中"16方法"应为"15方法"。

### 配置兼容性

- AMemorixConfig 含 13 子配置段
- AMemorixIntegrationSnapshot 只暴露 integration 子集（15 字段）
- `_read_config()` 返回扁平化运行时字典，但 SDKMemoryKernel 期望完整配置——storage/embedding 等段可能缺失

### 初始化路径和时序

时序正确：model_config_port 在 CORE_SERVICES 阶段注入，SUBSYSTEMS 阶段启动时已就绪。

残留问题：`_build_service_ports()` 直接导入 `config_manager`（CQ-14 残留）。

### 数据目录问题

- 路径 `data/plugins/a-dawn.a-memorix/` 含 `plugins/`，但 A_memorix 不是插件
- `paths.py` 硬编码 `a-dawn.a-memorix`
- 实际内容：`artifacts/retrieval_tuning/` 数据文件

### 已知问题

1. CQ-14 残留：`_build_service_ports()` 直接导入 `config_manager`
2. 3 层调用链冗余：Protocol → Adapter → MemoryService → HostService → Kernel
3. migration 路径硬编码：search 等走 migration_* 即使迁移完成也不直连
4. "16方法"计数错误：实际 15
5. 无 NullMemoryServicePort：未启用时返回类型不匹配的 dict
6. plugin.py 废弃残留
7. 数据目录"插件"假象

### 使用方清单

15 个文件，约 20 处调用。核心消费方：`maisaka/agent_autonomy/`（6 处）、`maisaka/memory/`（2 处）

## 需求

### P0：最小修复

- N1：修复 `_build_service_ports()` 中 config_manager 直接导入
- N2：修复 search/get_person_profile/build_profile_injection_text 走 migration 路径
- N3：添加 NullMemoryServicePort 类型安全的降级实现
- N4：修正"16方法"为"15方法"

### P1：接口瘦身

- N5：MemoryServicePort 拆分为核心 6 方法 + MemoryAdminPort 管理 9 方法
- N6：NullMemoryServicePort 只实现核心 6 方法
- N7：更新所有消费方（15 文件）

### P2：架构清理（可延后）

- N8：数据目录重命名 `data/plugins/a-dawn.a-memorix/` → `data/a_memorix/`
- N9：消除 MemoryService 中间层
- N10：删除 plugin.py
- N11：paths.py 清理

## 验收标准

1. A_memorix 启动无 ModelConfigPort 错误
2. 未启用时所有方法返回类型安全的空结果
3. search 等在迁移完成后走直连路径
4. `_build_service_ports()` 不直接导入 config_manager
5. MemoryServicePort 方法数 = 6，MemoryAdminPort 方法数 = 9
6. 15 个消费方编译通过
7. 方法计数正确

## 风险

| 风险 | 缓解 |
|------|------|
| 接口拆分消费方遗漏 | grep 全量扫描 |
| migration 路径切换召回质量变化 | A/B 对比 |
| NullMemoryServicePort 返回值不兼容 | 加 disabled=True 标记 |
| 数据目录迁移丢数据 | 独立迁移脚本+备份+回滚 |