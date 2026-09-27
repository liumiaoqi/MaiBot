# social_rel 实验笔记：把「社会关系模型」嵌进 MaiBot

> 建立：2026-09-27（lmq：「核心目的是**在 maiobot 内嵌入社会关系模型**」·「你来吧，写域可以」）
> 归属：**dsh**（本目录由 dsh 写；⚠️ **`snn_behavior/` 是 WB 的，本线不动它**）
> 规矩：`scripts/embedding_finetune/RULES.md`（新实验 = 独立子目录 + 本 NOTES.md + 报告进 `.shared/research/`；数据/产物不入库）
> 环境：**独立 `.venv`（Python 3.12 + torch cu128）**；⚠️ **不要用根目录 `uv run`**（会用主项目 .venv）
> ⚠️ 本线**只做离线实验**，**先不改 `src/A_memorix/` 核心**（验证有效再谈接入）

---

## 0. 使命与判据（这一层到底要做什么）

**使命**：在 MaiBot 内**嵌入**「社会关系模型」——不是彩蛋，是融进 MaiBot 的一部分。

**已被判定过的前提**（2026-09-27，另一条会话的结论，我复核后认同）：

| 前提 | 内容 |
|---|---|
| ⭐ **生物回路能当的零件只有一个** | **「记忆的强化学习仲裁层」**（行为引擎 ❌——MB 不做行为；检索器 ❌——bge+faiss 更强，且 KC 编码是**气味空间**不是语义空间） |
| ⭐ **拿不到"完整且社会化"的脑** | 「靠学习」与「有连接组」几乎反着排（人/鸣禽只有碎片；果蝇/线虫/斑马鱼连接组完整但社会化靠基因）⇒ **只能取零件，不能取整脑** |
| ⭐ **不需要下全量数据** | 切片 11,814 节点 / 76,061 边 ≈ **0.3 s / 1000 步**（纯 numpy 本机单核）；按边数外推全量 **~8.2 min / 1000 步**（1643×）⇒ **深度改造最需要的是快迭代** |

**本实验的验收判据**（一条，来自上面那条会话，我把它具体化）：

> ⭐ **它得实现某个既有接口，且比现有实现好。**
> ⇒ 具体化为：**「关系强度」参与检索排序后，检索质量在一个可分辨的指标上变好**——**指标必须先定出来，再谈实现**。

---

## 1. s1 已核实：现有资产地图（2026-09-27 实测，只读）

**结论先说**：⭐ **MaiBot 里早就有一套社会关系记忆**——本线**不是从零建**，是**给它加一层"学出来的关系强度 / 仲裁"**。

| 资产 | 位置 | 实测规模/事实 |
|---|---|---|
| 记忆子系统（**含"人物画像与关系记忆"**） | `src/A_memorix/` | 一体维护（无上游同步约束） |
| 关系存储 | `core/storage/stores/relation_store.py` | **1183 行**；`add/get/get_by_hashes/get_by_entity_names/get_all_triples/count/compute_relation_hash` |
| 画像存储 | `core/storage/stores/profile_store.py` | 24.6 KB（快照表，带 version） |
| 图关系召回 | `core/retrieval/graph_relation_recall.py` | **373 行**；`GraphRelationRecallService.recall()` + 直接对/两跳/一跳候选收集 |
| 双路检索 | `core/retrieval/dual_path.py` | score 归一化在 L614-617 |
| 画像服务 | `core/utils/person_profile_service.py` | **47.8 KB** |
| 画像证据 | `core/runtime/services/profile_evidence.py` | 14.2 KB |
| 认知存储（**置信度累积**） | `core/storage/stores/cognitive_store.py` | ⭐ `confidence REAL NOT NULL DEFAULT 0.3`；L151-167 **有 `confidence_delta` 累加 + `evidence_count`** |
| 统一画像（图边 → 置信度） | `core/concept_graph/unified_profile_service.py:115` | `confidence = min(1.0, max(0.0, edge.weight))` |
| 融合路由 | `core/.../fusion_router.py:76` | 输出里**带着** confidence |

**接口契约（改动必须遵守）**：
- 核心（`src/maisaka/`、`src/core/`）**不直接导入** A_memorix 内部 ⇒ 只走 **`MemoryServicePort`**（桥 = `src/core/adapters/memory_service.py` 的 `AMemorixMemoryServicePort`）+ **`SessionInfoPort`**
- 反向依赖禁止；14 条核心禁止项见 `AGENTS.md`「核心架构：微内核 + 接口契约」
- A_memorix **内部可自由改**（`MODIFICATION_POLICY.md`）

### ⭐ 可改进点（本线的靶子，实测）

> **`confidence` 有存储、有累积、有映射 —— 但（在实测到的代码里）没看到它参与检索排序。**
> 没有 `score = sim × confidence` 这类边权重；`relation_store` 的查询只见排序用 `created_at` / `last_activated_at`。
> ⚠️ 与 `zg30` 规格自陈一致：「**confidence 已存储但未作边权重**」。
> ⇒ **本线第一步的改进点就是这个**：让**学出来的**关系强度真正进排序。

### ⭐⭐⭐ 1.1 机制层根因（2026-09-27 · 只读 grep + 真库聚合）

**一句话：MaiBot 的"使用痕迹"整条链路在【段落】与【关系】两张表上都是空的 —— 写入方法早就写好，但全仓没有任何调用点。**

| 层 | 实测 |
|---|---|
| **写入方法存在** | `metadata_store.py:955` `record_access(hash, item_type)` —— `table_map = {"paragraph": "paragraphs", "relation": "relations"}`；SQL = `UPDATE … SET last_accessed = ?, access_count = access_count + 1 WHERE hash = ?` ✓ 完整实现 |
| ⭐ **调用点** | **全 `src/` 只有 1 处出现 —— 就是它自己的定义** ⇒ **从未被调用** |
| 关系层数据 | `relations.access_count` **全 0**（184/184）· `last_accessed` **全 None** |
| 段落层数据 | `paragraphs.access_count` **全 0**（4,692/4,692）· `last_accessed` **全 None** |
| 旧路径 | `update_relation_timestamp`（`relation_store.py:377` + `metadata_store.py:493`）**同样无调用点** |
| ⭐ 唯一的例外 | `relations.last_reinforced`：**22/184 非空 · 15 个不同值**（全库唯一"活着"的强化痕迹） |

⭐⭐ **结论：本线缺的不是模型，是「反馈回路没接线」。**
它与 audit 的合成侧结论**正好对接**：**只要有频次信号，现有机制就能学到 0.9924**（audit 反例②）。
⇒ ⭐ **第一步因此变成一个"小而硬的工程动作"**：在检索路径上挂 `record_access` 的调用点（检索命中谁 ⇒ 记一次）。
**判据**：① 调用后 `access_count > 0`（可查真库）② 离线复刻里"带痕迹的排序"优于"现状排序"。
⚠️ **但先不动 `src/A_memorix/`** —— 先在离线复刻里把"有了痕迹 ⇒ 排序更好"证明出来（最小改动纪律）。

### ⭐⭐⭐ 1.2 真库实测（2026-09-27 · 只读 · **只取聚合量，不取内容**）

**先说怎么量的**：`data/MaiBot.db`（764 KB）是**空壳**（相关表 0 行）⇒ ⚠️ **真库是**
`data\MaiMBot\a-memorix\metadata\metadata.db`（**261.7 MB**，49 表）。
量法：复制到 `C:\hub\.scratch\social_rel_snap\` 后 `mode=ro` 打开（**不碰运行中的库**）。

| 事实 | 数字 |
|---|---|
| 活关系 `relations` | **184** |
| 已删关系 `deleted_relations` | **14,868**（≈活的 **81×**） |
| ⭐⭐ `relations.confidence` | n=184 · min=1 max=1 avg=1 · **不同取值 = 1** |
| `deleted_relations.confidence` | n=14,868 · 同样**全是 1** |
| 段落 `paragraphs`（含 FTS/分词/ngram） | 4,692（ngram **753,551**） |
| 实体提及 `paragraph_entities` | **40,904** |
| 画像快照 `person_profile_snapshots` | **1,220** |
| 段↔关系 `paragraph_relations` | 217 |
| ⚠️ 图存储 `graph_edges` / `graph_nodes`（`concept_graph.db` 的 `relation_edges`/`trace_edges` 也是） | **全 0** ⇒ **图召回现在没米下锅** |
| ⚠️ `memory_feedback_tasks` / `memory_feedback_action_logs`（V5 反馈回路） | **全 0** ⇒ **这条回路从没跑过** |
| `person_profile_active_persons` | 0 |

⭐⭐ **三条定案**：

1. ⭐⭐ **顺序要改**：现在 `confidence` **零区分度（不同取值=1）** ⇒ **"让 confidence 进排序"这件事今天选不出任何东西**。
   ⇒ **本线的第一件事不是"让信号进排序"，是"产生信号"**（合成侧照旧可以先验证机制，但**真实侧的前置是"有没有可分辨的信号"**）。
2. ⭐ **`boost_weight` 是一条现成入口且从未被用过**：`relation_store.py:583-597` 的
   `confidence = MAX(confidence, ?)`（外部可抬升）—— 这与"没人写过非 1 值"的事实一致 ⇒ **它就是"显式偏好信号"的接入口**。
3. ⚠️ **关系维度是稀疏的**：关系 **184** vs 段落 **4,692** vs 实体提及 **40,904** ⇒
   关系抽取的产出率很低（约 **0.004 关系/提及**）⇒ ⭐ **"关系太少"本身也是一条可改进点**（比"权重不准"更上游）。

---

### ⭐⭐⭐ 1.3 定版靶子：`confidence` 的**值从来没被生产过**（2026-09-27 · 代码级证据链）

**一句话：`reinforce_relations` 只写 `last_reinforced`，不写 `confidence`** ⇒
即使检索服务**默认开着** `reinforce_access=True`，`confidence` 也**永远是 1.0** ⇒
**"confidence 作边权重"（已实验证明有效 ＋ 护栏 ＋ 接线全落地）在真实数据上恒为恒等变换。**

| 环节 | 状态 | 证据 |
|---|---|---|
| **实验依据** | ✅ | `.shared/research/2026-08/confidence_edge_weight_compare_0817.md` —— **CA 响应 dsh 派发**（`dsh2ca_confidence_edge_weight_exp_0817.md`）；结论：3/4 场景显著提升（**nDCG +5-20% · MAP +61-215% · Recall +72-160%**），仅**反对齐**场景有害 ⇒ 建议做 ZG-30 P2 |
| **排序接线 ＋ 双护栏** | ✅ **已落地** | `confidence_guard.py`（floor `0.3` ＋ Spearman 反对齐降级告警）＋ `graph_relation_recall.py:119-128`（候选按 confidence 权重排序） |
| **写入入口** | ✅ **在跑** | `search_execution_service.py:207` `reinforce_access=True`（默认开）⇒ `plugin.reinforce_access` ⇒ `reinforce_relations` |
| ⭐ **值本身** | ❌ **从来没有** | `relation_store.py:663-680`：`SET last_reinforced = ?, is_inactive = 0, inactive_since = NULL` —— **不碰 `confidence`** |
| **旁证（真库）** | ✅ 完全吻合 | `last_reinforced` **22/184 非空 · 15 个不同值**（**说明 reinforce 跑过**）· `confidence` **全 1.0** |

⚠️ **对我前两轮说法的两次更正**（形状都是"没读全就当结论" —— 复盘 0035 同族）：

1. s1 说「confidence 未参与排序」 ⇒ **不准确**：**接线早就有了**（我当时只 grep 了部分用法，没读到 `:119-128`）；
2. §1.1 说「缺的是反馈回路没接线」 ⇒ **不准确**：**reinforce 回路在跑**；没接线的是**另一条**（`record_access` → `access_count`/`last_accessed`），而它**不是这条链的必需件**。

⭐ **定版靶子（最小改动、可验证）**：
> 让 `reinforce_relations` **顺带写 `confidence`**（由 `last_reinforced` / 强化次数 / 段落支撑度派生一条规则）。
> **判据**：① 真库 `confidence` 出现非 1 值（可查）② **离线复刻**里 `sim × confidence` 排序优于基线（CA 的实验可复现）。
> ⚠️ **先在离线复刻证明，再谈改 `src/A_memorix/`**（最小改动纪律）。

## 2. 边界（我不做什么）

| ⛔ 不做 | 理由 |
|---|---|
| **不抢 `zg30`（P0 并发/一致性修复）** | 那是 **dsh 8-18 派给 CA 的 SSD 任务** ⇒ 归 CA |
| **不动 `snn_behavior/`** | WB 的线（`exp3e_homeo_sweep.py` 现在还挂着 `??`） |
| **不先改 `src/A_memorix/` 核心** | 先离线验证机制 ⇒ 有效再谈接入（判据：**最小改动 + 判据先行**） |
| **不新增依赖**（先） | 想只用 **numpy**（WB 那条线证明"纯 numpy + 秒级"完全可跑） |
| **数据/产物不入库** | `RULES.md` + `.gitignore` |

---

## 3. s2 输入：指标 + 三个假设（2026-09-27 起草，待团队验证）

### 3.0 ⭐ 先抄一条**近邻事实**（WB 那条线 2026-09-27 的定案，本线必须当先验）

> 来源：`snn_behavior/NOTES.md` 的 `exp3e` 两节（`ad0c74ffe` + `a896678f5`）。
> ⚠️ **它把 MaiBot 的含义直接写出来了**：「**只靠"互动好/坏"的评价，学不会"该对谁热情"** ——
> 必须有**显式的偏好信号**（角色设定 / 明确示范），否则会**卡在 50% 那个状态**。」

它测到（2×2 + 归因实验）：

| 机制 | 对**正确率** | 对**选择性**（无关 Δ） |
|---|---|---|
| **`+1` 加强"该选的那位"**（`boostonly`） | ✅ **决定性**：50% → **99.9%** | ❌ 不减（+195） |
| `−1` 削弱"错的那位"（`contrast`） | ✅（同样是 99.6%） | ✅ 压到 +98 |
| **per-MBON 稳态（cap）** | ❌ 无影响 | ✅ **压到 ≈0**（+1428 → +98） |
| 探索噪声 / 线性竞争 / 全局归一化 | ❌ 无效 | ❌ 无效 |

⭐⭐ **一句话**：**`+1` 是发动机，`−1`/稳态是守门人；而"该给谁 +1"必须从外部来。**
⚠️ 且它自陈：`boostonly`/`contrast` **都用了标签** ⇒ 更接近监督/对比学习，**纯 R-STDP 在这任务上学不动**。

⭐ **方法论教训（它的原话）**：「改不动时，**先做"把机制拆开"的归因实验**，而不是换机制」（它连开错 3 个处方）。

### 3.1 指标（必须先定，再谈实现）

**判据来源**：验收判据是"它比现有实现好" ⇒ 那就必须有**能分辨好坏的量**。

| 层 | 指标 | 为什么 |
|---|---|---|
| **① 机制层（合成数据，有 ground truth）** | 学出来的关系权重 vs 注入的**真实强度**的相关（Spearman）＋ 排序命中率 | ⭐ **先用合成数据** —— 有真值 ⇒ **"正确性可论证"**（论文 SAT 的 demonstrability 判据） |
| **② 接入层（真实数据，离线）** | 检索质量：**Recall@k / MRR / nDCG**（在"哪些关系该被召回"的标注上） | 这是"比现有实现好"的可比量 |
| **③ 选择层（独立评）** | ⭐ **生成 ≠ 选择**：产出过正确排序的比例（coverage） vs 最终选中的准确率 | 抄论文：WB 那条线的 50% 就死在这一环 |

> ⚠️ **基线怎么量**：先量**现状**——现在的排序（`created_at` / `last_activated_at` / 图召回权重）在①②上各是多少 ⇒ **没有基线，"更好"是空话**。

### 3.2 三个假设（每个含"替换哪个接口的哪个函数、怎么判它更好"）

| # | 假设 | 接入点（实测位置） | 判据（怎么算"更好"） |
|---|---|---|---|
| **H1 ⭐ 迁移假设** | WB 的机制组合（**`+1` 发动机 ＋ 稳态守门人**）迁到"关系强度学习"上仍成立 | 离线：`social_rel/` 自己的学习循环 | 合成数据上：权重 vs 真值的 **Spearman 显著 > 基线**，且"无关关系"的 Δ≈0 |
| **H2 信号来源假设** | ⭐ **纯频次/"互动好坏"信号学不动**；必须**显式偏好信号**（明确示范/角色设定/事件标签） | 同上（两路对照） | 对照实验：纯频次组的排序质量 ≈ 无学习基线；显式组的显著更好 —— ⚠️ **若纯频次组也学得动 ⇒ H2 被证伪**（那反而更好，结论要改） |
| **H3 仲裁层位置假设** | 学出来的强度**接在检索排序**（`score = sim × f(confidence)`）比接在写入侧/融合路由更有效 | `core/retrieval/graph_relation_recall.py` 的 `recall()` 排序处 · `dual_path.py` 归一化处 | ②层指标（Recall@k / MRR / nDCG）相对基线的提升幅度 |

⚠️ **H3 只是"最终接入形态"的假设** ⇒ **本轮不碰 `src/A_memorix/`**：先在离线复刻它的排序逻辑，验证有效再谈接入（最小改动纪律）。

### 3.3 团队分工（按 SAT：提案 / 实现 / 证伪，写域互不重叠）

| 角色 | 产物 | 写域 |
|---|---|---|
| **提案者** | 把上面三条假设**写成可跑的对照实验设计**（含"能证伪它的那条命令"） | `social_rel/proposals/` |
| **实现者** | 合成数据生成器 ＋ 最小学习循环（**秒级**）＋ 基线测量 | `social_rel/impl/` |
| **证伪者** | ⭐ 造反例：① 随机权重是不是也一样好 ② 纯频次组真学不动吗 ③ 指标是不是被同义改写（生成≠选择） | `social_rel/audit/` |
| **我（lead）** | 裁分歧 · 独立复跑 · 定接入与否 | `social_rel/NOTES.md` |

---

### 3.4 ⭐ s2 验收与改判（2026-09-27 · **lead 独立复跑**，非采信报告）

**证伪者交付**：`social_rel/audit/`（4 文件 **1,453 行** · **独立实现**，未看过 `impl/`）。
**我的验收**：用本目录 `.venv` 亲自跑三份脚本 ⇒ **3.76 s**，数字与 `AUDIT.md` **逐条一致** ⇒ **采信**。

**① 反例① 不成立**（指标有分辨力）：监督上界 **0.9958** vs 随机权重 **0.5227**（差 **0.4731** = **7.1×** 阈值 0.0663）。
⚠️ 但附带一条硬约束：**固定摆放时"永远选左" = 1.0000** ⇒ ⭐ **评估必须随机摆放候选顺序**。

**② ⛔ H2 被证伪（照实改判）**：

| 信号 | 用标签 | 成对排序率 | 判决 |
|---|---|---|---|
| `freq_passive`（频次·外部日记） | 否 | **0.9924** | ★**学得动** |
| `freq_active`（频次·自己选择的） | 否 | 0.4773 | 学不动 |
| `reward_1sided`（互动好坏） | 否 | **1.0000** | ★**学得动** |
| `reward_sym`（互动好坏） | 否 | 0.9928 | ★**学得动** |

⇒ ⭐ **分界线不是"用不用标签"，而是"信号里有没有方向信息"**；
`freq_active` 学不动的原因是**自选择偏差**（"我选了谁"这件事本身给不出方向）。
⇒ ⚠️ 这同时**修正了 §3.0 抄来的 WB 先验**在本任务上的适用性：WB 那句「纯奖励学不动」在**它的架构**（有界+有底读出）成立，
**在排序读出上不成立** —— 证伪者**试图复现 50% 而失败**（bounded+floor 版本仍然 1.0000）。

**③ H1 = 部分支持**：`+1` 发动机 ✅（1.0000）；**"守门人"在本任务可测收益 = 0**（+0.0042 ≈ 0）且封顶有代价（0.8409 < 1.0000）
⇒ ⚠️ **WB 的"稳态守门人"不可直接迁移到排序读出**。

**④ 反例③ 成立**（指标会被同义改写）：同一批 run、k=12 时 **coverage_strict = 0.000 而选择准确率 = 1.0000**
⇒ ⭐ **任何"机制有效"的报告必须两个数同时给**（报哪个，结论就反过来）。

**⑤ audit 的三条可执行结论**：① **coverage 与 selection 同时给** ② ⭐ **"现有实现"基线不是 0.5000** ——
若现成的激活频次与关系强度同向，它本身就在 **0.9924** 那一档 ⇒ **真实侧基线必须先量**（→ 修 §1.1 靶子，见 `task-3`）
③ **评估随机摆放候选顺序**。

**⑥ audit 自报局限**（照转，不替它打包票）：未碰 H3 · 未碰真实数据②层 · 合成数据无并列/hard negative（`AUDIT.md §5`）；
它自己脚本的两处缺陷（位置对照组算错、检索基线打到天花板）**已自查修复并记入 §5.4**。

---

## 4. H3 待批提案（2026-09-27 · **等 task-3 的证据** · 现在不动 `src/`）

### 4.0 前置核验

- ✅ **PII 核验通过**：`impl2/real_sample.json` 全是聚合量（184 条 × `['g','sup','reinf_sec','vec_ok','conf']`，**无姓名/无文本/无向量**），
  且 `n_relations=184` / `n_subjects=36` 与 §1.2 实测**吻合** ⇒ **可入库** ✓
- ⚠️ **接线侧不用动**：`confidence_guard.py`（floor 0.3 ＋ 反对齐降级）＋ `graph_relation_recall.py:119-128` 都已落地 ⇒ **H3 只剩"值"这一件事**。

### 4.1 两种改法（判据 = **最小改动优先**）

| 型 | 改法 | 动 schema？ | 评价 |
|---|---|---|---|
| **① 累加型** | 在 `reinforce_relations` 的 UPDATE 里补 `confidence = min(1.0, confidence + δ)` | ⚠️ **要**（"再强化一次 +δ" 需计数列否则无法去重） | 直观，但动表结构 ⇒ 后备 |
| **⭐ ② 派生型** | **不动 reinforce**：加一个**回填过程**，用现有字段算并写回 —— 输入只要 `last_reinforced`（时间）＋ `paragraph_relations` 支撑度 | ✅ **零 schema 改动** | ⭐ **首选**（用的全是已在跑的字段） |
| ③ 查询时算 | 检索时实时算（不落库） | ✅ 零改动 | ⚠️ 不推荐：每次查询都算 ⇒ 与"秒级迭代"相悖的长期开销 |

### 4.2 提案（草稿 · ❗等证据）—— 让 `confidence` 有值

> 加一个**派生回填**（②），规则形如 `confidence = f(days_since_reinforced, support_count)`。
> **量纲必须按 `[0,1]` 缩放**（⚠️ task-3 那个 `+1` 无量纲的坑，别在这里再踩）。

**判据（缺一不可）**：① 真库可查 —— 回填后 `COUNT(DISTINCT confidence) > 1`；② **离线复刻**里 `sim × confidence` 优于"**常数权重 = 现状**"基线，且 ⭐ **coverage 与 selection 两个数同时给** ＋ 候选随机摆放（audit 两条硬约束）；③ ⚠️ **护栏不被误触**（新值不得让 `ConfidenceGuard` 判"反对齐"降级，否则白改）。

**边界**：**只在 task-3 离线复刻证明有效之后**才提交 lmq 批；**在那之前一个字都不改 `src/A_memorix/`**。

### 4.3 task-3 进展（impl-synth）

`impl2/snapshot.py`（8.5 KB）＋ `impl2/real_sample.json`（15.9 KB，14:16 落盘）⇒ 正在做真库样本；我的交叉核验：规模与 §1.2 一致 ✓。

---

## 5. 写域声明（避免三方撞车）

- **我写**：`scripts/embedding_finetune/social_rel/`（本目录）· 本线在 `INDEX.md` 的登记行 · 报告落 `.shared/research/`
- **我不写**：`snn_behavior/`（WB）· `src/A_memorix/`（先）· CA 的 `.codeartsdoer/specs/zg30_*` · `TOOL_ISSUES.md`（WB 提交）
