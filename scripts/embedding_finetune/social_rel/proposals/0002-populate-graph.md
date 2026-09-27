# 申请 0002 · 让图存储有数据 —— 从而让 `confidence` 的两档**进入可观测路径**（**待 lmq 拍**）

> 2026-09-27 · 提出：dsh（lead）· **状态：可执行（干跑 + 诊断后）** —— 见 `../NOTES.md §8.7/§8.8`
> ⚠️⚠️ **原推荐已被我自己的干跑否掉**：一次调用能让图"有数据"，但**有数据 ≠ 能召回**
> （干跑：图 27,597 节点 / 76 边，`recall()` 仍返回 **0 候选**），且 **184 条关系只建出 76 条边**（按节点对去重 ⇒ 边权被覆盖）。
> ⭐ **2026-09-27 诊断后更新**：
> · **阻碍 B 撤销** —— 是我的 seed 用法错（只给 subject；边是 `subject → object` **有向**的）。
>   正确 seed（含一条关系的**两个端点**）下 `recall()` 返回 **2 个候选** ✓ ⇒ **召回路径可用**（`NOTES §8.8`）。
> · **阻碍 A 仍成立但绕得过去** —— 边按节点对去重（184 关系 → 76 边，同边挂 7 个 hash 但只有 1 个权重）；
>   ⚠️ 但候选的 `confidence` **是从 metadata 库读的**（`graph_relation_recall.py:344/368`），**不是图边权** ⇒ **DB 两档会进入候选** ✓
> ⇒ **状态：可执行**（下面三选一**重新适用**，我推荐 (a) 执行）。
> 依据：`../NOTES.md` **§8.5**（A 线 artefact 级验收）· 申请 **0001**（已执行：`DISTINCT 1→2`）

---

## 〇、一句话

**`confidence` 的值已经有了（1.0 × 47 / 0.5 × 137），但消费它的那条路（图召回）在真库里是空的** ⇒
**一次重建调用**就能让它活起来 —— 而且重建代码里**边权直接取自 `confidence`**。

---

## 一、现状（全实测，只读）

| 事实 | 数字 / 位置 |
|---|---|
| `confidence` 已两档 | `{1.0: 47, 0.5: 137}`（申请 0001 执行结果） |
| ⚠️ **图存储两表** | `metadata.db`：`graph_nodes` **0** · `graph_edges` **0**<br>`concept_graph.db`：`concept_nodes` **0** · `relation_edges` **0** · `trace_edges` **0** |
| ⇒ 后果 | ⭐ **`GraphRelationRecallService.recall()` 无候选** ⇒ 本次改动**效果不可观测**（§8.5 已量） |
| ⭐ **数据源齐备** | `entities` **27,588** 行（全 `is_deleted=0`）· `relations` **184** 行 |
| ⭐ **重建入口存在** | `graph_ops.py:772 rebuild_graph_from_metadata()`（管理员层 `admin/graph.py:50` 有调用） |

**重建函数做的事**（原文摘）：
```python
self._graph_store.clear()                       # 先清空（当前图本就是空的 ⇒ 无损）
if names: self._graph_store.add_nodes(names)    # 节点 = entities + 关系的 subject/object
if relation_rows:
    self._graph_store.add_edges(
        [(subject, object) for row in relation_rows],
        weights=[float(row.get("confidence", 1.0) or 1.0) for row in relation_rows],  # ⭐ 边权 = confidence
        relation_hashes=[str(row.get("hash", "")) for row in relation_rows])
```

---

## 二、我建议做什么（**一次调用**）

> **调一次 `rebuild_graph_from_metadata()`** ⇒ 图从 **0 节点 / 0 边** 变成 **≈27,588 节点 / 184 边**，
> 且 **184 条边的权重 = 两档 `confidence`（47×1.0 / 137×0.5）**。

**判据（缺一不可）**：
1. `graph_nodes` > 0 **且** `graph_edges` = **184**（可查真库）；
2. ⭐ **`recall(seed_entities=[…])` 返回非空候选**（用真组件跑，不再只是"组件单跑"）；
3. ⭐ 候选的 `confidence` 分布**含两档** ⇒ **改动从此进入可观测路径**；
4. ⚠️ **质量仍不可判定**（无相关性标注）—— 本申请**不声称**"排序变好了"，只声称"**从此可观测**"。

**风险 / 回滚**：
- `clear()` 会清空图 —— **当前就是空的 ⇒ 无损**；但**仍是写操作** ⇒ **备份先行**（同 0001 的做法）；
- 回滚：`DELETE FROM graph_nodes; DELETE FROM graph_edges;`（回到 0/0 = 现状）；
- ⚠️ **不碰** `relations` / `paragraphs` 等任何业务表。

---

## 三、我**不建议**做的

| ⛔ | 理由 |
|---|---|
| 顺手接 `record_access` | **顺序定律**（`NOTES §4.5`）：无真值时抬覆盖 = **伤害放大 3.7×** ⇒ 与 0001 同一纪律 |
| 顺便改 `add_edges` 的权重口径 | 重建里 `weights=confidence` 已经**正是我们要的**；改它是另一件事 |
| 一次性重建 `concept_graph.db` 那三张表 | 它们是**另一套**（概念图/轨迹图），入口与语义都不同 ⇒ 另案 |

---

## 四、需要你拍的一点

> **是否执行这一次重建？**
> (a) ⭐ **执行**（推荐）：让 `confidence` 进入可观测路径 —— 之后**任何效果都能被看见**（哪怕质量仍要靠下游观察）；
> (b) **先不执行**：保持现状（改动的效果继续不可观测），等别的事情清楚了再说；
> (c) 执行，但**先只建 184 条边、不建 27,588 个节点**（⚠️ 需要改代码 —— 与"最小改动"冲突，我不推荐）。

---

## 五、批准后我会做什么（写死）

```
真库快照备份 → 调 rebuild_graph_from_metadata() → 量 graph_nodes/graph_edges
→ 用真组件跑 recall(seed_entities) 拿候选 → 核候选 confidence 是否两档
→ 报告；任一判据不过 ⇒ 走回滚 SQL
```
