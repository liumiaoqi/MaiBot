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

---

## 2. 边界（我不做什么）

| ⛔ 不做 | 理由 |
|---|---|
| **不抢 `zg30`（P0 并发/一致性修复）** | 那是 **dsh 8-18 派给 CA 的 SSD 任务** ⇒ 归 CA |
| **不动 `snn_behavior/`** | WB 的线（`exp3e_homeo_sweep.py` 现在还挂着 `??`） |
| **不先改 `src/A_memorix/` 核心** | 先离线验证机制 ⇒ 有效再谈接入（判据：**最小改动 + 判据先行**） |
| **不新增依赖**（先） | 想只用 **numpy**（WB 那条线证明"纯 numpy + 秒级"完全可跑） |
| **数据/产物不入库** | `RULES.md` + `.gitignore` |

---

## 3. 下一步（s2：三个零件假设，每个必须写清"替换哪个接口的哪个函数、怎么判它更好"）

待起团队（提案 / 实现 / 证伪三角色，写域互不重叠）。

⭐ **必须带上的一课**（来自 WB 那条线）：它的卡点是 **`homeo` 方向已经对了、训练正确率还是 50%** ⇒
⭐ **"生成 ≠ 选择"**（论文 SAT：团队产出过正确答案 **87.9%**，最终准确率只 **72.8%**）⇒
**本线必须把"选择侧"（评分/判据）当独立环节设计**，不能只堆生成。

---

## 4. 写域声明（避免三方撞车）

- **我写**：`scripts/embedding_finetune/social_rel/`（本目录）· 本线在 `INDEX.md` 的登记行 · 报告落 `.shared/research/`
- **我不写**：`snn_behavior/`（WB）· `src/A_memorix/`（先）· CA 的 `.codeartsdoer/specs/zg30_*` · `TOOL_ISSUES.md`（WB 提交）
