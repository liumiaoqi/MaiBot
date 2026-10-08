# 申请 0003 —— 关系端点实体补建 ＋ DEL-1 残留清理

**状态**：可执行（待 lmq 拍）
**日期**：2026-09-27 ｜ 作者：dsh（华）｜ 依据：本目录 `NOTES.md §1.11 / §1.16 / §1.17 / §1.18`
**风险**：低（改动局部、可回滚、有对照组）｜ **收益**：端点覆盖 **62/71 → 71/71**（+13%），并消除两处"永不触发/幽灵读者"

---

## 一、问题（三条，都已由我亲自复核）

### 问题 1 9 个关系端点没有 `entities` 行（**端点覆盖的硬上限**）

```
真库：relations 71 个不同端点 → 62 个在 entities 里，**9 个不在**（87% 是当前上限）
按来源管线分组（我复核过）：
  web_import:%    137 条关系 → **0 个**孤儿端点
  chat_summary:%   47 条关系 → **9 个**孤儿端点   ← 9 个**全部**来自这一条管线
代码差异（我读过）：
  web_import_manager.py:3915-3916  写关系**前**先补建两端实体  ← **全仓唯一这么做的地方**
  summary_importer.py:749-755      只建 LLM JSON 里**列出的** entities
  summary_importer.py:761+         关系段**直接** upsert，**不补端点**
⇒ 模型在 `relations` 里用了没列进 `entities` 的短语（考试科目/习惯/道具）⇒ **孤儿**
```
**影响**：任何依赖"关系端点能在实体表里落地"的功能（图构建、端点覆盖统计、将来的社会场）都被卡在 87%。

### 问题 2 `hit_filter.py` 里有一条**永不触发**的硬过滤分支

```
core/runtime/services/hit_filter.py:41-56  load_paragraph_stale_marks()
    → 函数体里 marks_by_paragraph = {} 后**直接返回**，**从不查库**（硬编码空字典的桩）
它原该调的 get_paragraph_stale_relation_marks_batch：**整个 src/ 0 命中**
⇒ hit_filter.py:213 的 paragraph_hidden_by_stale_marks() 永远拿不到 mark ⇒ **该分支不可能触发**
```
**影响**：一段**看起来还在工作**的过滤逻辑实际是死码（读的人会误判行为）。

### 问题 3 4 张表是 DEL-1 的**残留**（写入者被删、表还在）

```
2f5688e76「DEL-1 删除模糊修改系统 — ~4000行代码清算」（2026-07-28）删掉了：
  feedback_correction.py(1630) · fuzzy_modify.py(1111) · feedback_config.py · fuzzy_modify_config.py …
这 4 张表的 INSERT 在 HEAD **0 命中**，而在 2f5688e76^ 上分别是：
  memory_feedback_tasks        ← metadata_store.py:7078
  memory_feedback_action_logs  ← :7317
  memory_fuzzy_modify_plans    ← :4104
  paragraph_stale_relation_marks ← :7382 与 :7601
且 `sqlite_sequence` 探针证明它们**自建库以来零 INSERT**（对照表 person_profile_snapshots = 1220）
```
**影响**：schema 与代码不一致（表在、没人写），新人会以为"这功能只是没启用"。

---

## 二、改动（最小、逐条可回滚）

| # | 改哪 | 怎么改 | 为什么是最小 |
|---|---|---|---|
| **1** | `core/utils/summary_importer.py` 关系段（`:761+`） | 在 `upsert_relation_with_vector(...)` **之前**，对 `subject`/`object` 各调一次 `_add_entity_with_vector(name, source_paragraph=hash_value)` —— **照抄 `web_import_manager.py:3915-3916` 的两行** | 只加 2 行；不动写入语义、不动 DDL |
| **2** | `core/runtime/services/hit_filter.py:41-56` | **二选一**：(a) 删掉这个桩 + 其调用点（若 `paragraph_hidden_by_stale_marks` 已无意义）· (b) 恢复查库并接线。**建议 (a) 删除** —— 表零 INSERT、读者零调用 ⇒ 无功能可恢复 | 删除比恢复更小、更安全（无数据依赖）|
| **3** | 4 张残留表 | ⚠️ **不改**（见 §五）—— 只在本申请登记，**建议留到"schema 清理"单独拍** | 删表是不可逆动作，**不该混在这份里** |

---

## 三、判据（执行后逐条验，命令都写死）

| # | 判据 | 命令 | 期望 |
|---|---|---|---|
| 1 | 端点覆盖 | `SELECT COUNT(*) FROM (SELECT DISTINCT subject AS e FROM relations UNION SELECT DISTINCT object FROM relations) WHERE e NOT IN (SELECT name FROM entities)` | **9 → 0**（下次导入后）⚠️ 见 §四 caveat |
| 2 | 管线对照不再分裂 | 按 `paragraphs.source` 分组的孤儿数 | `web_import` **0** · `chat_summary` 新导入 **0** |
| 3 | 既有数据未被波及 | `relations`/`entities` 行数 | 184 / 27,588 **不变**（只影响**新**导入）|
| 4 | 桩已消失 | `grep -n "marks_by_paragraph = {}" ` **限定在 `hit_filter.py`** | **0 命中**，且 `python -m py_compile` 通过<br>⚠️ 该字面量在仓里**共 2 处**（另一处是 `person_profile_service.py:577`，**与本申请无关**）⇒ 判据必须**限定文件**，否则全局 grep 会误报 ✓ |
| 5 | 门 | `git hook run pre-commit` | **rc=0** |

⚠️ **判据 1 的执行前提**：这 9 个孤儿是**历史数据**，补建逻辑只对**将来**的导入生效 ⇒
若要让**存量**也补上，需要**单独的一次回填脚本**（按 `relations.source_paragraph` 反查段落 → 为缺失端点建实体行）
—— **本申请不含回填**（那要另一份申请，因为有写库动作）✓

---

## 四、诚实标注（本申请不能声称的）

1. **9 个孤儿端点的"为什么"只到管线级**：是"LLM 在 relations 里用了没列进 entities 的短语"这一条**机制**，
   但**没验证**是否还有别的路径（例如同一函数在别的分支里也会漏建）；
2. **判据 1 只对"新导入"成立**：存量 9 个不会自动消失（见上）；
3. 问题 2 的"删除"是**我的建议**：若你记得 `paragraph_stale_relation_marks` 还有用途，应改为**恢复查库** ✓

---

## 五、不做（明确排除）

- ⛔ **不删任何表**（4 张残留表只登记，等 schema 清理单独拍）；
- ⛔ **不做存量回填**（要写库，另立申请）；
- ⛔ **不动 `confidence` / `is_pinned` 相关**（那是申请 0001/0002 与 S2 回滚的事）；
- ⛔ **不碰 `src/A_memorix/` 里的检索主链**（`dual_path` / `graph_relation_recall`）—— 本申请只碰导入侧与一个死桩。

---

## 六、回滚

| # | 回滚方式 |
|---|---|
| 1 | `git revert <commit>`（两行）|
| 2 | `git revert <commit>`（删除桩）|

两处都**不涉及数据迁移** ⇒ 回滚零成本 ✓
