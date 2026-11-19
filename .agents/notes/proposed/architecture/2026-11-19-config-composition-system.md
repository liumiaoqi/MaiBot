# Agent Note: 配置组合系统（自由组合 + 多级管理）

Status: proposed（2026-11-19 立项讨论，明确非当务之急）

## Problem

现有配置体系是**单一正本 + `.bak` 覆盖**：

- `.bak` 每次保存覆盖上一份，只能回滚 1 步；
- `old/` 只在启动/升级路径产生，且无上限增长；
- 配置之间没有"片段复用/按场景组合"的能力——想换一套角色/场景配置，只能整份替换；
- Phase 3 的 mutate 写的是合并后的正本，读路径只认这一个文件。

目标不是"给配置做备份"，而是**借 Git 的设施做更自由的配置组合系统**：多级管理（基线/角色/场景/用户覆盖）+ 自由组合（按清单拼出最终配置）。**明确不是当务之急**，先登记形态与参照，排期再定。

## 现状参照（dsh 新版 `E:\Users\lmq\deepseek-harness`）

### 多级管理：有现成参照，可直接照搬语义

- 解析顺序：**schema defaults → composition base → user layer**（`packages/settings/settings/src/types.ts:29`；`index.ts` 同语义）。
- 合并函数 `mergeLayers`（`index.ts:170-182`）：plain object 递归合并；**其他值（含数组）整体替换**；`undefined` 不覆盖下层。
- 写入只进 user 层（稀疏 patch）；`replace` 重置后缺席键重新继承 base 与默认值；同 namespace 写入串行；解析值是深冻结快照。
- 密钥按 `role('secret')` 剥离，对外只给 value-free view（`redactSecrets`）。
- 新版另有 `configEditor`（Cordis patch 持久化）与 `profileContext`（定位当前 profile patch）——可作为"写哪一层"的参照。

### 自由片段组合：**没有现成整件**

- dsh 的 profile 是**部署配置档 + 补丁**，不是任意片段组合；
- `agent-preset-registry` 的 `composeFrom`/`recompose` 组合的是 **agent 预设子树**，不是配置树；
- `config-catalog.md` 里的 `localInstructionFileCandidates`（base + local overlay）只用于**指令文件**，不是配置。

克隆库其他项目也未找到通用实现。通用生态（Pkl / CUE / Jsonnet / Helm overlay / Spring profiles）要么引入新语言，要么绑定特定生态，与"借 Git 设施"不重合。

### Git 仓的实操口径（`C:\Users\lmq\.dsh`，可直接照搬）

用户侧 `.dsh` 已经在用这套做法（2026-09-27 建仓），要点：

- **无远程**（用户明确：不需要远程仓库）。
- **建仓前做一次密钥扫描**：1281 个候选文件，`gh[pousr]_` / `AKIA` / 私钥头三类 0 命中；两处命中被 `.gitignore` 挡住（`.credentials.yaml`、`secrets/github.pat`）。
- **只追踪"了解的少数文件"**，不是 `git add -A`：实际 `git ls-files` 只有 `profiles/`、`preset-bundles/`、`skills/`、`README.md`、`.gitignore`。
- 黑名单挡住：凭据（`.credentials.yaml`、`secrets/`、`*.pat/*.key/*.pem`、`.env*`）、备份/会话/存储（`_backup-*/`、`_session-dump/`、`sessions/`、`storages/`）、导入残留（`settings.yaml.imported`）、依赖（`**/node_modules/`）。

## Proposal（C 形态）

```
config/
  base.toml              # 公共基线
  overlays/
    role_a.toml          # 角色差异
    scene_b.toml         # 场景差异
  profiles/
    default.toml         # 组合清单：base + role_a + scene_b
```

- **组合器放应用层**（约 150–250 行）：按清单顺序 `mergeLayers`；对象递归、数组整体替换、`undefined` 不覆盖；类型冲突显式报错，不静默强转。
- **Git 只做版本与方案存储**：分支/标签/diff 存这些文件；**不做 `git merge` 组合**（文本级合并对 TOML 不可靠）。
- **追踪口径照 `.dsh`**：只 add `base.toml`、`overlays/`、`profiles/`、`active-profile` 这类已知文件；不 add 备份/日志/缓存/临时文件；建仓前先扫密钥；无远程。
- **切换方案**：改 `active-profile` 指针 + reload，不 `checkout` 运行中的工作区。

## 必须先定的架构选择

| 选择 | 含义 | 代价 |
|---|---|---|
| **A. 写用户层，运行时解析**（dsh 路线） | 物理只有 base + overlay，正本是解析结果 | 与现有 revision/mutate/文件监听冲突；改造大，但"自由组合"是真的 |
| **B. 组合只做生成器** | 组合出一份合并正本，运行时仍读单文件 | 改动小、与现状兼容；但组合是构建期能力，不是运行时自由切换 |

**A 才配得上"更自由的配置组合系统"**；B 只是配置生成器。选 A 必须同时重做写路径（mutate 写哪层、revision 定义、热重载听哪些文件）。

## Alternatives considered

- **Git merge 做组合**：文本级三方合并，对 TOML 注释/键序/数组不可靠；要语义合并得自写 merge driver，等于自研且更复杂——拒绝。
- **Pkl / CUE / Jsonnet**：表达力强，但引入新语言与运行时，超出"借 Git 设施"目标——暂不采用。
- **环形备份（保留 N 份）**：能解决回滚，但不解决"组合"——只能作为过渡。
- **把组合塞进当前 #3（Git 留档）**：范围不同；#3 是单正本留档，A 形态下仓结构完全不同——**#3 暂停，等本决策定稿**。

## Acceptance（未来立项时）

- 同一组输入必得同一输出（组合确定性），有单测；
- 冲突规则可断言：类型冲突必须报错，不静默覆盖；
- 密钥不进入任何物理层（只存引用），或明确接受本地明文并加 pre-push 拒绝；
- 方案切换有 reload 闭环，且不与保存锁冲突；
- 与 Phase 3 revision/mutate 的关系有明确落点（写哪层）。

## Risks

- **前置条件（不是可选项）**：MaiBot 的 `bot_config.toml` 本身含明文密钥，与 `.dsh` 的 `cordis.patch.yml` 不同（后者密钥在 `.credentials.yaml`，已被挡住）。若整文件进白名单，历史仍保留明文；要么先把密钥改为**引用**（env / secret provider），要么把该文件排除在历史外——但后者就没有配置历史。这决定 C 形态能否成立。
- 密钥历史放大：Git 每版留一份明文；必须走"引用 + 脱敏"或加密。
- 运行期文件真空：Git/组合器故障时要有降级，不能既无 `.bak` 又无提交。
- bind mount 上的 Git 性能与仓库膨胀：需定义 gc 策略。
- 这是架构级改造，不是 #3 的延伸；**先定 A/B，再排期**。

## 与当前任务的关系

- 决策 #3（Git 留档）**暂停**：A 形态下定稿会改变仓结构与写路径，现在按"单正本"建仓可能白做。
- 本 note 只登记形态与参照，不构成本期实施承诺。