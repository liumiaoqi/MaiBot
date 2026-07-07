# A_Memorix 修改规定

## 定位

`src/A_memorix` 是 MaiBot 项目的核心记忆子系统，与 MaiBot 一体维护，不存在上游同步约束。

A_Memorix 在 MaiBot 中承担以下职责：

- 人物画像与关系记忆
- 启发式记忆检索
- 行为模式学习
- 情感记忆（规划中）

## 修改原则

1. **A_Memorix 是 MaiBot 的一部分**，可以自由修改其内部实现，无需考虑上游兼容
2. **核心隔离原则**：MaiBot 核心模块（`src/maisaka/`、`src/core/`）不直接导入 `src/A_memorix/core/` 的内部模块，只通过 `MemoryServicePort` Protocol 接口交互
3. **适配器模式**：`src/core/adapters/memory_service.py` 中的 `AMemorixMemoryServicePort` 是核心与 A_Memorix 之间的桥梁，A_Memorix 内部变更不应影响核心接口
4. **反向依赖禁止**：A_Memorix 内部不应导入 `chat_manager`、`send_service` 等外部组件。如需查询会话信息，应通过 `SessionInfoPort` Protocol 获取

## 可自由修改的范围

所有 `src/A_memorix/` 下的文件均可自由修改，包括但不限于：

- `src/A_memorix/core/` — 核心记忆引擎
- `src/A_memorix/scripts/` — 脚本与工具
- `src/A_memorix/plugin.py` — 插件入口
- `src/A_memorix/paths.py` — 路径配置
- `src/A_memorix/runtime_registry.py` — 运行时注册

## 修改约束

唯一的约束来自 MaiBot 自身的架构原则，而非上游：

- 遵守核心 Protocol 接口契约（`MemoryServicePort`、`SessionInfoPort`）
- 不在 A_Memorix 内部引入对 MaiBot 组件具体实现的直接依赖
- 修改后确保 `AMemorixMemoryServicePort` 适配器仍能正常工作

## 历史说明

A_Memorix 曾是独立上游仓库 `https://github.com/A-Dawn/A_memorix.git` 的同步目录，MaiBot 通过 `MaiBot_branch` 分支对接。自 MaiBot 确立独立开发方向后，两者已完全解耦，A_Memorix 作为 MaiBot 内置子系统直接维护。
