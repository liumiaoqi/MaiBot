# Agent Note: WebUI 契约层 —— 从 OpenAPI 生成前端类型，只补一层不重构

Status: implemented

## Problem

决策判断「后端免费产出契约、前端一个都没读」，但落地前三条前提都已过期：

1. **规模过期**：原决策书写 315 端点，实测 **405 paths / 448 operations / 339 schemas**。
2. **验收前提不成立**：`config` 域核心端点（`/config/schema/*`、`/config/get`、`/config/mutate`）**没有响应模型**；全仓响应模型覆盖率仅 **214/448（47.8%）**，`/api/config` 为 0/5。原验收「config 域全量使用生成类型」按字面做不到。
3. **因果过期**：原决策写「9 个功能域手抄 fetch」，实测裸 `fetch` 只剩 **5 处 / 4 文件**（请求样板已收编到统一 client）。真实痛点是 **211 处路径字面量 / 179 unique** 与 **1174 行手写类型**——后端改字段，前端不会红。

## Decision

本期只补**契约生成层**，不动后端：

- `openapi-typescript@7.13.0`（`--save-exact`）从 `/openapi.json` 生成单文件 `src/lib/contract/api-schema.d.ts`。
- 唯一手写映射层 `src/lib/contract/index.ts`：响应方向 `Required<T>` / `Omit<Required<T>,'success'>`，请求方向直连；试点 `config` 域**只加类型、不改调用**。
- 快照与报告入库（`openapi/`）；`last-check.json` / `last-generate.json` 不入库。
- `contract:check` 五态（consistent / stale / handEdited / missing / skipped），**退出码恒 0**；CI 只读快照，不访问后端。
- 本期明确不做：补 `response_model`、路径字面量下降、星图重写。

## Alternatives considered

- **orval / 生成 client + hooks**：会与现有 `src/lib/*-api.ts` 写法冲突并引入运行时，与「零运行时产物」直接矛盾——拒绝。
- **tRPC / GraphQL**：后端是 FastAPI（Python），改造面远超本期边界——拒绝。
- **继续手写类型、不建契约层**：211 处路径 + 1174 行手写类型没有漂移检测——拒绝。
- **顺手补后端 `response_model`**：`response_model` 是运行时序列化契约，会按模型过滤响应字段；属后端行为变更，会改变响应形状。拆为独立后续批次，不在本期顺手做。

## Consequences

**实测（2026-11-19，运行中后端 `127.0.0.1:18001`）**：405/448/339；覆盖 214/448，缺口 **234**；路径基线 v1 **211 处 / 179 unique / 26 文件**（`config-api.ts` 18）；产物 **873,671 bytes**、零 `any`、零值导出；同快照两次生成逐字节一致；tsc 0（4s）· lint 0 · test **155 文件 / 1519 用例** · build 0；generate 3s。

**实施中修正的口径**：

- R1 从 `*.ts` 改为 `*.{ts,tsx}`：`restart-context.tsx` 有 1 处 `/api/webui/system/status`；只算 `.ts` 得 210/179/25。已同步 spec §6.3、design §2.3.2-⑤ 与报告规则。
- 「映射层是唯一允许 `Omit`/`Required` 的地方」与现状不符：`pack-api.ts`、`plugin-stats.ts`、`settings-manager.ts` 早已使用 `Omit`。本期未动它们；该约束应读作「本次新增变换集中在本文件」。
- 测试基线过期：`AGENTS.md` 记 142/1357，实测 155/1519。

**后续批次（按触发条件，不并行）**：config 核心 5 端点补 `response_model` → `/api/import`（0/25）与 `/api/retrieval_tuning`（0/14）→ 记忆星图重写。补模型批次必须含「重新生成 + 人工审查 diff」：响应字段一变，本期产物与快照即失效。

**回滚**：六层可独立退（试点类型 → 映射层/产物 → 依赖 → 脚本 → 快照报告 → CI）；任一层回滚后 `tsc --noEmit` 应保持退出码 0。全程无运行时行为变化。

**复算**：`NODE_OPTIONS= pnpm run contract:report` / `contract:check -- --source snapshot` / `pnpm exec tsc --noEmit`（工作目录 `mingtang`）。