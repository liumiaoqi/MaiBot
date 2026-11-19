# Agent Notes —— 公开决策记录区

> 本目录是**本仓（`liumiaoqi/MaiBot`）对外可见的决策记录区**——照 dsh 的 `.agents/notes/` 形态设立（单语版，不做双语）。
> 与 `.shared/`（**私有仓**，外部看不到）的分工：**事故故事 → `.shared/postmortem/`**；**工作交接 → `.shared/handoff/`**；**决策记录 → 本目录**。

## 规矩

1. **每个事实只有一个家**：决策的 why / 放弃了什么 / 怎么验证 → 放这里；事故叙事 → `.shared/postmortem/`；交接件 → `.shared/handoff/`。别重复记。
2. **状态用文件名或头部标注**：`implemented`（已交付，现在时描述现实）· `proposed`（提案）· `archived`（冻结历史，不再代表现状）。
3. **一篇一个决策**：命名 `YYYY-MM-DD-<slug>.md`；正文至少含 **背景 / 决策 / 放弃了什么 / 验证方式**。
4. **改动同步**：决策被推翻或取代时，不改旧文，新写一篇并在旧文头部标注指向。

## 索引

| 日期 | 决策 | 状态 |
|---|---|---|
| 2026-10-17 | [版本线：主版本号从 0 起钉](2026-10-17-version-line-decision.md) | accepted |
| 2026-10-17 | [向 dsh 看齐的路线图（构建/门禁/文档不腐）](proposed/process/2026-10-17-dsh-alignment-roadmap.md) | proposed |
| 2026-10-17 | [轨二阶段 D 的前置：记忆子系统当前是关闭的](proposed/process/2026-10-17-stage-d-blocked-memory-disabled.md) | proposed |
| 2026-11-19 | [通道能力契约：让上层知道当前通道能做什么](proposed/architecture/2026-11-19-channel-capability-contract.md) | proposed |
| 2026-11-19 | [模型配置按「格式」分层，而不是按「厂商」堆超集](proposed/architecture/2026-11-19-model-config-format-layer.md) | proposed |
| 2026-11-19 | [依赖升级清单与分批计划](proposed/process/2026-11-19-dependency-upgrade-inventory.md) | proposed |
| 2026-11-19 | [WebUI 契约层：从 OpenAPI 生成前端类型，只补一层不重构](implemented/architecture/2026-11-19-webui-contract-layer.md) | implemented |
| 2026-11-19 | [Phase 3 六项收尾决策（raw 下线 / 旧读两步走 / Git 留档 / F13 / 104 域 / 数据侧）](proposed/process/2026-11-19-phase3-config-decisions.md) | proposed（已拍板，待实施） |
| 2026-11-19 | [配置组合系统（自由组合 + 多级管理）](proposed/architecture/2026-11-19-config-composition-system.md) | proposed（非当务之急，先登记） |
| 2026-11-19 | [MaiBot 缓慢 Rust 化方向（边缘优先 / 旁路替代 / 不重写核心）](proposed/process/2026-11-19-rust-migration-direction.md) | proposed（方向登记，非当务之急） |
