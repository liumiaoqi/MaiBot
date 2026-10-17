# Agent Note: 向 dsh 看齐的路线图（构建/门禁/文档不腐）

Status: proposed

## Problem

本季真正硬起来的只有"**判据面**"（`pitfalls` 11 条 + 十四条红线 + `verified_state.py` 的 `gen/check` 成对）。而**三件该由机器接手的活还在人手里**：

1. **验收命令是散的** —— `uv run pytest tests pytests -q`、`ruff check`、`npm run lint/test/build`、`verified_state.py --check`、几条点名单跑…… **每次都要人记得跑哪几条、按什么顺序**，且"哪几条属于快速档 / 哪几条是发版前全量"没有成文。
2. **文档与清单会腐** —— 已有成对雏形只有两处（`session_id` 生成器 `--check`、`legacy_face` selfcheck），其余（`pitfalls` 编号、两仓镜像表、`legacy_face_surface.json` 之外的清单）仍靠人守。
3. **发布物没有验收** —— 我们验的全是"**源码树里跑得通**"；**"拉下来、起来、healthcheck 过"**这道门只在 CI 里有一半（`verify-anonymous` 验的是可拉取，不是可用）。

对照物：dsh（本机 `E:\Users\lmq\deepseek-harness\`）。它的实物形态已核（不是印象）：

- **成对生成器**：`gen-*` ⇒ `verify-* --check`，共 **17 对**（tsconfig-paths / cli-help / cordis-catalog / cordis-api / tool-catalog / config-catalog / doc-graphs / module-graph / dependency-catalog / persistence-catalog / session-format-catalog / third-party-notices / plugin-packages / official-bundle-catalog / provider-data / workflow-guest / client-catalog）
- **命名门集 + 一个 runner**：`scripts/run-gates.ts` 的 `check-all` / `ci-*` / `doc-sync` / `hygiene` / `node-compat`
- **声明式钩子清单**：`lefthook.yml` + `postinstall = install-lefthook.mjs`（装完依赖，门自动上）
- **发布物验收**：`release:verify` / `verify-packed-install`（"装出来的那份真能跑吗"）
- **约 40 条 `verify-*`**（含 `verify-agent-note-format` / `-classification` / `verify-archived-agent-notes`）
- ⚠️ **它没有 Docker**（交付是 npm 包 + 桌面打包；`Dockerfile`/`compose`/`deploy` 全无）⇒ **这一块我们反而领先**（容器 = 开箱即用）

## Decision

按"**便宜且能立刻受益**"排序推进；每阶段独立可交付、可回退。**不抄它的检查表，只抄它的机制。**

| 阶段 | 做什么 | 形态 | 验收（这一阶段自己的门） |
|---|---|---|---|
| **P0 ✅ 已做** | 判据面硬化 + **`verified_state.py`**（本仓第一对 `gen/check`） | `scripts/verified_state.py`：`--emit` / `--check <ref>` / `--drift` | 自洽性绿 · 造红能红 · `--drift` 不接门 |
| **P1** | **命名门集 + 一个 runner** | `scripts/gates.py`：`quick` / `full` / `docs` 三档；每条门一行、失败即停 | 每档能跑出**一条命令**的结论；`quick` 的目标时间 < 2 分钟 |
| **P2** | **声明式钩子清单** | 把 `.githooks` 里散落的脚本升级成可读清单（按文件类型分派）；**仍用 `core.hooksPath`**，不引入新依赖 | 清单能被"读"（不是只能被执行）；钩子误报有一次实测豁免记录 |
| **P3** | **给已有生成物补 `--check`** | 逐件补：`docs/pitfalls.md` 的**编号连续性**（不写条数，只查编号不重不缺）· 两仓镜像表 · `legacy_face_surface.json` | 每件都有 `--check`；**生成器与校验器同一处定义** |
| **P4** | **发布物验收（学 `release:verify`）** | `scripts/verify_image.sh`：拉镜像 → 起容器 → 等 healthcheck 过 → 打印三件证据（digest / 架构集 / healthcheck 原文） | 在 CI 与本地都能跑；**架构集要进验收官**（降级事实不能被静默） |
| **P5** | **把"约定"逐条变成机器判** | 本仓自己的 `verify-*` 家族：从 `pitfalls` 与十四条红线里长出来（例：`verify-agent-note-format` 先落地——我们已有 `.agents/notes/` 的路径约定） | 每条只判一件事、失败即停；**先有"会红"的实证，才允许进 CI** |

## Alternatives considered

- **照抄 dsh 那约 40 条 `verify-*`**：**拒绝**。每一条都对应**它自己踩过的坑**；抄表 = 抄别人的病史。⭐ 分界是"**把约定变成机器判**"，不是"抄检查表"。
- **学 Linux 的 cadence（`vX.Y-rcN` 时间窗口）**：**拒绝**（与发版标签策略同一条理由：我们没有它的 rc 测试纵深，学形不学神只会造出"没人压过的 rc"）。
- **P1 直接用 dsh 的 `run-gates.ts` 形态（TS）**：不建议。本仓 CI 主力是 Python 与 shell，**加一层 TS 工具链**只会多一个要维护的入口；用 `scripts/gates.py` 即可。
- **把 P4 塞进现有 `verify-anonymous`**：不够。那一步验的是"**匿名可拉**"，不是"**起来能用**"；P4 要的是**起容器 + healthcheck**。

## Consequences

- ✅ P1/P2 落地后，"**该跑哪些门、按什么顺序**"从人脑变成文件；P3 之后"清单类文档"从"靠人守"变成"**不一致即红**"；P4 之后"发布出去的那份能不能用"**第一次有证据**。
- ⚠️ **每加一道门都要先付"它会红"的实证**（本季的教训：闸不红过等于没闸；而**判得过严**同样有害——`attestation-manifest` 那次就是把正当的 SBOM 当非法架构）。
- ⚠️ **门越多越贵**：`full` 档已经 20 分钟量级 ⇒ **P1 的 `quick` 档必须真快**，否则大家会绕过它。
- ⚠️ **本仓尚未搬入 `.agents/notes/README.md`（格式规范）与 `verify-agent-note-format` 那道门** ⇒ P5 的第一件就它（否则本文件这种"靠约定"的格式继续裸奔）。
- ⚠️ **不引入新体系**：P2 坚持 `core.hooksPath`、P1 不引入任务编排框架 —— **减少入口数量**本身就是对齐 dsh 的一部分（它再大也只有**一个** `run-gates`）。
