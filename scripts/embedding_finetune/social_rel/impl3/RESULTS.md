# social_rel · s4 结果：让系统开始记录真值 —— 接线方案与**顺序陷阱**

> 落盘：2026-09-27 ｜ 写域：`social_rel/impl3/` ｜ 归属：**dsh**
> 任务书：`task-4` ｜ 依据：`social_rel/NOTES.md §4.3`（收益 ∝ ρ(痕迹,真值)，ρ<0.36 为负收益）
> 环境：`scripts/embedding_finetune/` 自己的 `.venv`（Python 3.12.11 + numpy 2.5.1）· **无新增依赖**
> ⚠️ **未改 `src/A_memorix/` 一个字节**；**未 commit**；`NOTES.md` 只读（建议正文见 §9）。
> ⚠️ 数字口径：`wiring_plan.py` **默认重复 30 次**（与 `impl2` 同口径）。

---

## 0. 一句话结论（四条）

1. ⭐⭐ **`confidence` 恒为 1.0 的根因不是「没人写」—— 是「写了但写不动」**。
   `relations.confidence` 的**列默认值是 1.0**，而**唯一跑过的写路径** `remember_forever` 写的是
   `MAX(confidence, 0.1)` ⇒ **`MAX(1.0, 0.1) = 1.0`，恒为空操作**。
   ⇒ 现有证据（47 条 `is_pinned`）证明这条显式反馈路**已经跑过 47 次** —— 它只是把记录写进了一个**已经饱和的字段**。
2. ⛔⛔ **顺序陷阱是真的**：κ=0（痕迹里没有真值）时把覆盖率从 12% 抬到 75%，
   派生规则的伤害**从 −0.0139 放大到 −0.0520（3.7×，p=8.4e-6）**。
   ⇒ **先接 `record_access` 会把事情弄得更糟**；覆盖率必须**排在真值之后**。
3. ⭐ **覆盖率本身极便宜**：离线模拟里只要 **约 17 次检索**就覆盖到 75%（不是瓶颈）。**瓶颈是真值，不是覆盖。**
4. ⭐ **现成的真值候选只有一个**：`is_pinned`（47/184 = 25.5%，写入者是**显式 admin 动作**，
   **不在检索环内** ⇒ 不构成自证）。`last_reinforced` 因**写入者在环内**被排除（拿它当真值 = 自证）。

---

## 1. 怎么跑（秒级）

```powershell
cd E:\Users\lmq\MaiBot\scripts\embedding_finetune\social_rel\impl3
..\..\.venv\Scripts\python.exe truth_sources.py --dump   # 真值通道体检（0.14 s）
..\..\.venv\Scripts\python.exe wiring_plan.py            # 2×2 顺序验证 + 覆盖增长 + 机械判定（3.00 s）
..\..\.venv\Scripts\python.exe wiring_plan.py --reps 60  # 加大重复
```

⚠️ 真库访问：`mode=ro`（只读）。**副作用披露**：打开时会 touch 同目录的 `metadata.db-shm`
（共享内存索引）——**不改任何数据**，但确实是"碰了库"，照本线惯例明写。
⛔ 不用 `immutable=1`（本库 WAL 有未合并内容，用它读到的不是当前状态）。

---

## 2. 真值通道体检（真库**只读** + 代码**只读**）

`truth_sources.py` 把"谁写这条通道"写成**文件:行 + 该行应含的片段**，**每次运行回读那 9 行核对**，
对不上就响亮失败（防"声明漂移"）。本次 9/9 ✓。

```
relations 共 184 行 · confidence 列默认值 = 1.0
通道                    覆盖      取值数   在环内    可区分对子   判定
is_pinned              47/184       1      否       6,439    候选可用
last_reinforced        22/184      15      是       3,784    不能用（在检索环内 ⇒ 自证）
access_count            0/184       0      —            0    不能用（通道为空）
last_accessed           0/184       0      —            0    不能用（通道为空）
confidence            184/184       1      否            0    不能用（常数 ⇒ 零信息）
is_permanent            0/184       0      —            0    不能用（通道为空）
memory_feedback_tasks       0/0      0      否            0    不能用（通道为空）
memory_feedback_action_logs 0/0      0      否            0    不能用（通道为空）
```

**四条预登记判据**：**A 独立性**（写入者不在被评估的检索环内）· **B 可分辨** · **C 覆盖** · **D 可证伪**。

⚠️ **B 的判据对布尔标志位与取值通道不同**（我第一版判错过一次）：
`is_pinned` 的 47 条**取值**只有一个 `1`，但"**是否被固定过**"把 184 条切成 **47 / 137** —— 那是信息。
⇒ 标志位用「`0 < 覆盖 < 总数`」，取值通道用「覆盖内取值数 > 1」。改正后 `is_pinned` 判为**候选可用**。
「可区分对子」列与 `impl2` §3 **同一口径**（总对子 − 同值对子）：`last_reinforced` = 3,784（两处一致 ✓）。

### ⭐⭐ 为什么 `confidence` 恒为 1.0 —— 机制（**修正 `NOTES §1.3` 的表述**）

`NOTES §1.3` 说「`reinforce_relations` **只写** `last_reinforced`，不写 `confidence`」。**这一句对那个函数是对的**，
但作为**根因**不完整 —— 本轮查到的完整机制是：

| 事实 | 证据 |
|---|---|
| ① **列默认值 = 1.0**（一出生就在天花板） | `pragma table_info(relations)`：`confidence REAL default=1.0` |
| ② **唯一跑过的写路径是空操作** | `remember_forever` → `relation_store.py:594` `confidence = MAX(confidence, ?)`，`? = max(prune_threshold, 0.1)` ⇒ `MAX(1.0, 0.1) = 1.0` |
| ③ 另外三条路径**能把值打下来**，但库里一条都没有 | `v5_memory.py:104` `confidence = MAX(0.0, COALESCE(confidence,0.0) + ?)`：`weaken(−0.5)`→0.5 · `forget(−2.0)`→0.0 |
| ④ `reinforce(+0.5)` **没有上界钳位** | 同上式只有 `MAX(0.0, …)`，没有 `MIN(1.0, …)` ⇒ 若跑过，库里会出现 **>1.0 的值** —— 也没有 |

⇒ ⭐ **观测到的「全 1.0」只能由「只跑过 `remember_forever`」解释**，而 **47 条 `is_pinned` 正好是它的签名**
（`v5_memory.py:143` 写的是 `protected_until=0.0, is_pinned=True`；
实测 47 条 `is_pinned=1` 的 `protected_until` **全部为空/0**，且 `protected_until > 0` 的行为 **0 条**
⇒ 自动 TTL 保护那条路**从未触发**）。

⭐ **顺带一条可执行发现**：显式反馈的四个动作（`reinforce` / `weaken` / `remember_forever` / `forget`）
**代码全都在**，对外入口也在（`core/runtime/admin/relation.py:28` → `apply_v5_relation_action`）。
**真正缺的不是管道，是让 `confidence` 能动的量程。**

---

## 3. ⭐⭐ 2×2：接线顺序（本文件的核心）

真值通道（κ）× 覆盖率，配对基线**各格都是同批样本上的「现状」**：

| κ（痕迹里有没有真值） | 覆盖 | Δhit@5 | p | Δcov1 | p | Δsel1 | p |
|---|---|---|---|---|---|---|---|
| 0.0（**无**真值 = 真库当下） | 0.1196（真库现状） | **−0.0139** | 0.0037 | −0.0132 | 0.024 | −0.0252 | 0.0081 |
| 0.0（**无**真值） | 0.75（接完 `record_access`） | **−0.0520** | **8.4e-6** | −0.0701 | 0.0023 | −0.0380 | 0.14 |
| 0.5（带真值，ρ≈0.70） | 0.1196 | **+0.0467** | 1.9e-9 | +0.0770 | 3.0e-6 | +0.0889 | 1.5e-5 |
| 0.5（带真值） | 0.75 | **+0.0924** | 1.9e-9 | +0.1219 | 1.9e-9 | +0.0741 | 5.5e-4 |

⛔ **左下 vs 左上**：没有真值时，把覆盖率抬上去让伤害**从 −0.0139 放大到 −0.0520（3.7×）**。
⭐ **右上 vs 右下**：有真值时，覆盖率让增益**从 +0.0467 抬到 +0.0924（约 2×）**。

⇒ ⭐⭐ **同一件事（提高覆盖率）在两种前提下后果相反** ——
**「先把覆盖做上去」不是"先铺路"，是"先把噪声灌满"。**

---

## 4. 覆盖率有多贵？（离线模拟）

| 检索行为 | 到 75% 覆盖需要的检索次数 | 达到目标的模拟比例 |
|---|---|---|
| 均匀返回 k=20 | **12.4 次** | 100% |
| 按相似度返回 top-20（**真实检索的样子**） | **17.3 次** | 100% |

⭐ **覆盖率极其便宜** —— 十几次检索就到了。⇒ **瓶颈从来不是覆盖率，是真值。**
⚠️ 建模说明：相似度那一路**必须让"兴趣方向"随查询变化**；我第一版把它写成一条**固定排序**
⇒ 每次返回同一批 20 条 ⇒ 覆盖永远卡在 10.9%，实测 `nan`（已修，见 `coverage_growth` 的 docstring）。
⚠️ 并且"按相似度返回"会让覆盖**偏向反复被检索到的那些** ⇒ `access_count` 会与 `sim` 相关，
**不等于**与真值相关 —— **又一次自选择偏差**（同 audit 的 `freq_active` / s2 的 `freq_self`）。

---

## 5. 交付①：`record_access` 的接线方案

**先看现成的调用链**（全部**只读**核对过，`truth_sources.py` 每次回读校验）：

```
检索命中 → search_execution_service.py:207  reinforce_access: bool = True（默认开）
         → :314-324  await plugin_instance.reinforce_access(relation_hashes)
         → sdk_memory_kernel.py:338  async def reinforce_access(...)
         → :344  self.metadata_store.reinforce_relations(hashes)     ← 只写 last_reinforced
```

⭐ **接线点就是同一处的一行**：`sdk_memory_kernel.py:344` 旁边加
`self.metadata_store.record_access(h, item_type="relation")`（`record_access` 定义在 `metadata_store.py:955`；
其 `table_map = {"paragraph": "paragraphs", "relation": "relations"}`）。
**不需要新的调用链、不需要新的参数、不需要改 `search_execution_service`** —— 这是最小改动。

**覆盖会怎么走**：§4 实测 **~17 次检索到 75%**。

⛔ **但顺序（§3）**：**这一步排在真值之后。** 现在接 = 把伤害放大 3.7×。

---

## 6. 交付②：什么是「真值」

| 候选 | 覆盖 | 在检索环内？ | 能当"用户显式反馈"的代理？ |
|---|---|---|---|
| ⭐ **`is_pinned`** | **47/184（25.5%）** | **否**（`remember_forever`，显式 admin 动作） | ⭐ **能**（布尔，二档；现成、已在库里） |
| ⭐ **`apply_v5_relation_action` 四动作** | 0（`confidence` 被 1.0 顶住） | 否 | ⭐ **修好量程就能立刻拿到 4 档**（reinforce/weaken/forget + 强度） |
| ⛔ `last_reinforced` | 22/184 | **是**（被评估的检索环自己写的） | **不能** —— 拿它当真值 = **自证** |
| ⛔ `access_count` / `last_accessed` | 0/184 | — | 不能（通道为空；且见 §4 的自选择偏差） |
| ⛔ `memory_feedback_tasks` / `_action_logs` | **0 行** | 否 | 设计上是**带 rollback 的决策日志**，但从没跑过；要它得先有东西去写 |
| ⛔ `is_permanent` | 0/184 | — | 不能（全 0，且未找到写入点） |

⭐⭐ **结论**：**真值不是"再存一个新字段"，而是"让已有的显式动作真的能改变一个值"。**
最省的一步是：**把 `confidence` 的量程从"出生即天花板"解下来**（例如默认值与派生式对齐到 `[floor, 1.0]`），
这样 §6 表里第二条那 4 个动作**立刻**变成真值来源。

---

## 7. 预登记判据 · 机械判定

```
W1  ✓ 通过   覆盖 12%→75%：Δhit +0.0467 → +0.0924（p=1.9e-9）⇒ 增益确实变大 ✓
W2  ✓ 通过   κ=0 下覆盖 12%→75%：Δhit -0.0139 → -0.0520（p=8.4e-6）⇒ **显著更差** ⇒ ⛔ **顺序反了会放大伤害**
W3  ✓ 通过   `is_pinned` 47/184（25.5%）· 可区分对子 6,439 · 写入者=显式 admin 动作
W4  ✓ 通过   `last_reinforced` 写入者在检索环内 ⇒ 排除（自证）
W5  ✓ 通过   `confidence` 恒 1.0 = 列默认 1.0 + `MAX(confidence,0.1)` 空操作
W6  — 已测   均匀 12.4 次 / 最相似 17.3 次（k=20，目标 75%）
```

---

## 8. 每条结论 → 它的证伪命令

| 结论 | 证伪它的命令 | 看什么 |
|---|---|---|
| 顺序陷阱（先接覆盖会放大伤害） | `wiring_plan.py` | κ=0 两格：−0.0139 → −0.0520（p=8.4e-6）；**若 75% 那格反而更好 ⇒ W2 不成立** |
| `is_pinned` 是**显式**信号（不是自动 TTL） | `truth_sources.py` | 47 条 `is_pinned=1` 的 `protected_until` 全为空/0，且 `>0` 的行为 **0 条** |
| `confidence` 的机制是"饱和"不是"没写" | `truth_sources.py` | 列默认 `1.0` + `MAX(confidence,0.1)`；**若库里出现 >1.0 的 confidence ⇒ 机制解释被推翻** |
| 覆盖率极便宜 | `wiring_plan.py` | 覆盖增长段：12.4 / 17.3 次 |
| 真值通道覆盖率 | `truth_sources.py` | 通道体检表 |
| 代码事实没有漂移 | `truth_sources.py` | 开头 9 行「代码事实核对」必须全 ✓，否则脚本**拒绝继续** |

---

## 9. 建议 lead 落笔 `NOTES.md` 的正文（我不写 NOTES，只给稿）

> ### ⭐⭐⭐ 1.5 s4 判决：`confidence` 是**饱和**，不是"没人写"；接线要**先真值后覆盖**（2026-09-27 · 离线 + 代码只读）
>
> **修正 §1.3 的表述**：`reinforce_relations` 只写 `last_reinforced` 是对的，但**根因不完整**。
> 完整机制 = **`relations.confidence` 列默认 `1.0`** ＋ **唯一跑过的写路径 `remember_forever` 写的是 `MAX(confidence, 0.1)`** ⇒ 恒为空操作。
> 旁证：47 条 `is_pinned`（`remember_forever` 的签名）⇒ **这条显式反馈路已经跑过 47 次**，只是写进了饱和字段。
> 另：`reinforce(+0.5)` 走 `MAX(0.0, confidence+delta)` —— **没有上界钳位**，若跑过会出现 >1.0 的值（库里没有 ⇒ 从未跑过）。
>
> **顺序**（`impl3/wiring_plan.py` 2×2）：κ=0 时覆盖率 12%→75% 让伤害 **−0.0139 → −0.0520（3.7×, p=8.4e-6）**；
> κ=0.5 时同一动作让增益 **+0.0467 → +0.0924（2×）**。⇒ ⛔ **先把 `record_access` 接上会把噪声灌满。**
>
> **覆盖面不贵**：离线模拟 **~17 次检索**即到 75% 覆盖 ⇒ **瓶颈是真值，不是覆盖**。
>
> **最小动作**：① 让 `confidence` 的量程能表达「未确认 → 已确认」（现在出生即天花板）；
> ② 于是 `apply_v5_relation_action` 的 `reinforce/weaken/remember_forever/forget` 四动作**立刻**成为真值来源；
> ③ 真值有了以后再在 `sdk_memory_kernel.py:344` 旁加 `record_access`（一行）把覆盖做到 75%。

---

## 10. 局限（本线**没有**证明的东西）

1. ⛔ **`confidence` 的机制是"推断"不是"实测"**：我由"全 1.0 + 三条路径各自的算术后果"**反推**出"只跑过 `remember_forever`"。
   **没有**任何执行日志能直接证实（系统没有记录谁调用过 admin 动作）。可能的替代解释：手工 SQL 写过、或历史版本行为不同。
   **证伪命令**：库里出现 `confidence != 1.0` 的任何一行（尤其 >1.0）即可推翻。
2. ⛔ **`is_pinned` 是不是"用户"点的，本线无法证明** —— 我只能证明它是**显式 admin 动作**写的（不是自动 TTL）。
   "显式动作"可能来自用户，也可能来自 agent 的自主判断。**这正是 audit 的"自选择偏差"要追问的那一层。**
3. **真值仍是假设**：2×2 里的 κ 依然是我注入的（真库没有相关性标注）。本节能回答的是**顺序**，不是**ρ 的真实值**。
4. **覆盖增长是模拟**：`similar` 那一路用 latent 内积近似真实检索；真实检索的候选池还受图召回/段落约束（而 `graph_edges` 现在是 0）。
5. **未验证任何改动的实际效果** —— 本轮**一行 `src/A_memorix/` 都没改**（任务书要求）。

---

## 11. 未做 / 待决

1. ⭐ **`confidence` 量程怎么改**（默认值 / 派生式 / 是否要 `MIN(1.0, ...)` 上界钳位）—— **建议 lead 批了再动核心**。
2. `record_access` 接到**段落**侧（`paragraphs.access_count` 也全 0，4692 行）本轮只提了方案，没做离线验证。
3. `memory_feedback_*`（带 rollback 的决策日志）**从未跑过** —— 要它得先有真值写进去，顺序上排在第 ② 步之后。
