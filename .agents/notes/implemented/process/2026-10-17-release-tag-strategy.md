# Agent Note: 发版标签策略（semver + 预发布阶梯 + tag 自带验证记录）

Status: implemented

## Problem

本仓只有一个 tag（`v0.1.0`），而"**这个 tag 描述的状态被验证过**"这件事**只以手写形式存在它的注释里**：

- `pitfalls #52` 立的判据是「**被验证状态 = 主仓 SHA + 每个 gitlink 各自指向哪个提交**」；
- 实测过：**同一个主仓 SHA**（`428c07af2`）配插件 `9d643c0` ⇒ 全量 33 = 基线；配 `61021af` ⇒ **多一条红**；
- 而那份手写指纹**会腐**：`verified_state.py --check v0.1.0`（漂移口径）实测出 **2 项已不可复现**（main 与 v1-compat 都前进了）。

于是每次发版都要重新讨论三件事：**打在哪个 SHA · 它算什么状态 · 镜像跟不跟着版本走**。没有策略，就没有可复算的"发布"。

## Decision

采用 **semver + 预发布阶梯 + tag 自带验证记录**：

1. **日常小步提交，不 tag。**
2. 要发版 ⇒ 打 **`vX.Y.Z-rc.N`**（**annotated**），注释必须含四件：
   ① **全量结果**（`N failed = 基线、新增 0`）② **门禁结果**（ruff / 版本一致性等）③ **`scripts/verified_state.py --emit` 的指纹** ④ **关键未验证项**（如实列出）。
   之后 `python scripts/verified_state.py --check vX.Y.Z-rc.N` **必须绿**（自洽性口径：注释 vs 该 tag 自己的树）。
3. **镜像从 rc 建**；验证过（拉下来 → 起容器 → healthcheck 过）⇒ 打 **`vX.Y.Z`**（final）。
   ⭐ **final 的镜像指向与 rc 同一个 digest**（**不重编**）—— 由此消掉"tag 与镜像不一致"这一类问题。
4. **hotfix = 下一个 patch**（`0.1.2`），**不用** `post`/`+build` 之类后缀。
5. **`--drift`（注释 vs 当前工作区）只作报告，绝不接进门**：仓在 tag 之后前进是正常事，接进门就会造出**永远红的闸**（`pitfalls #47` 那族）。

## Alternatives considered

- **dsh 式（`dsh-v0.2.1-alpha.5` → `-rc.2` → final，家族前缀 + 预发布阶梯）**：**借它的版本阶梯**，但**不借它的可信度来源** —— dsh 靠 `release:verify` / `verify-packed-install` 那条流水线背书，我们没有那么厚的流水线。于是我们把"可信度"落在**tag 注释里可机检的记录**上（`verified_state.py --check`）。
- **Linux 式（`vX.Y-rcN`，一个合并窗口一串 rc，tag = 时间截面）**：**拒绝**。它的可信度来自"rc 被海量 CI/机器压过"，我们没有那个测试纵深；学形不学神只会造出"**没人压过的 rc**"，那是把信誉机制抽掉只留名字。而且我们是"**功能到位才发**"，不是"到点就发"。
- **不 tag、只发镜像**：**拒绝**。代码与产物脱钩之后，`#52` 那种"同一 SHA 两种结果"就没人能复现。

## Consequences

- ✅ 每个 tag **自带可机检的验证记录**：`verified_state.py --check <tag>`（自洽性）能回答"这个 tag 承诺了什么、它自己说不说得圆"。
- ✅ **rc 与 final 共用同一 digest** ⇒ "tag ↔ 镜像"不再有两套真相。
- ✅ 发版前**必须有一次全量**（约 20 分钟）—— 这条是成本，也是这个策略的支点。
- ⚠️ **rc 若没人压，它就只是我们自己的预演**。因此 **rc 阶段的门要比 final 更严**：rc 必须附「镜像起来 + healthcheck 过」的证据；final 主要确认"与 rc 同一 digest"。
- ⚠️ **本仓尚未搬入 `.agents/notes/README.md`（格式规范）与 `verify-agent-note-format` 那道门**。本文件按 dsh 的 file-format 写（`{lifecycle}/{class}/yyyy-mm-dd-topic.md` + `# Agent Note:` 头 + `Status:` + `Problem → Decision → Alternatives → Consequences`）。**下一个 process 件应当补这两样**，否则格式只靠约定、不靠机器。
- ⚠️ **`verified_state.py` 的指纹格式成了发布契约的一部分** ⇒ 改它的输出格式 = 改发布契约，须按"一处改动 = 一处回退"对待。
