# 决策：记忆子系统的四处**接线缺陷**及处置

> 立：2026-09-27 ｜ 类型：**决策 + 缺陷处置** ｜ 生命周期：`implemented`
> 落点：领域（MaiBot） ｜ 相关：`../NOTES.md §1.16 / §1.29 / §1.32 / §1.33 / §1.34 / §1.37 / §1.42–§1.46` ·
> `../proposals/0003-endpoint-backfill-and-del1-residue.md`

---

## 一、问题（四处，互相独立）

| # | 缺陷 | 规模 |
|---|---|---|
| 1 | **552/694 条 episode 被屏蔽在用户可见结果之外** | **79.5%**（每天损失）|
| 2 | `episode_pending_paragraphs` 的 `running` 是**死状态**（中断即永久卡死）| 真库已卡 1 行 ≈46 天 |
| 3 | **关系端点补建缺失** ⇒ 9/71 个端点没有 `entities` 行 | 端点覆盖卡在 **87%** |
| 4 | 人–人关系**没有产出路径**（`person_fact` 573 段 → **0** 条关系挂链）| 使命级（见 §三）|

## 二、决策与改动（四处都已落地）

| # | 决策 | 关键一行 |
|---|---|---|
| 1 | **让那个已声明却从未生效的开关真的生效** | `hit_filter._episode_query_block_enabled()`：**总闸 `feedback_correction_enabled=false` ⇒ 屏蔽失效** ✓ |
| 2 | **族级修**（三张队列表一起治）：启动时把残留 `running` 拉回 `pending` | 新增 `metadata_store.reset_running_queue_rows()` ＋ `kernel_initializer` 启动调用 ✓ |
| 3 | **写关系前补建两端实体**（用本文件自己的写法 ✓ 不跨文件抄）| `summary_importer` 关系循环开头 ✓ |
| 4 | ⚠️ **不擅自补 `person_fact` 的关系抽取**（属核心语义改动）⇒ 只登记、写进简报 ✓ | 见 §三 |

## 三、为什么 552 那个是"接线"而不是"改语义"（重要）

```
DEL-1（commit 2f5688e76，2026-07-28）删掉了整条反馈纠错链；但在 2f5688e76^ 上：
  feedback_config.py:31   enabled=bool(integration.get("feedback_correction_enabled", False))
  feedback_config.py:43   episode_query_block_enabled=bool(integration.get("feedback_correction_episode_query_block_enabled", True))
⇒ 这些开关**有过接线**，是被 DEL-1 删掉的 —— **不是"从未接线"** ✓（§1.34 更正了我 §1.33 的说法）
⇒ 而判定函数 `is_episode_source_query_blocked` **活了下来** ⇒ 变成"消费者没了、开关也没了、判定还在" ✓
⇒ 又因为它查的那张表**没有消费者**（唯一取件 API 在 HEAD 调用点为 **0**）⇒ 屏蔽**永不解除** ✓
```

## 四、备选与取舍

| 方案 | 判定 |
|---|---|
| **①′ 恢复读取（本轮采用）** | ✅ 采用 —— 最小、可回滚、立刻恢复 **552 条可见** ✓ |
| ① 改成"只屏蔽 running / 加时限" | ⏸ 备选 —— 若原则是"DEL-1 删的东西不复活"，走这条 ✓ |
| ② 排空队列（恢复消费者跑一批）| ❌ **未采用** —— 贵，且⚠️ **必须先处理 3 行"毒丸"**：`rebuild_source` 对"无活段落的 source"会走 `replace_episodes_for_source(token, [])`，而其内部是 **`DELETE FROM episodes WHERE source=?`（metadata_store.py:1994）** ⇒ **会真删掉那 12 条 episode** ✓ |
| ③ 清理陈旧 pending | ⏸ 也可（治现象）✓ |

## 五、后果

- ✅ 552 条 episode 恢复可被用户看到；`running` 不再永久卡死（族级 ⇒ 三张表都受益）✓
- ⚠️ **端点覆盖 71/71 要等一次新导入**（本修复只对**将来**的导入生效；存量 9 个孤儿需**另立回填申请**）✓
- ⚠️ `reset_running_queue_rows()` 的安全性依赖**单实例**消费同一 DB（已写进 docstring）✓
- ⚠️ **DEL-1 边界**（本决策的隐性产出）：`feedback_correction_*`（15）＋ `fuzzy_modify_*`（6）共 **21 个字段**
  在 HEAD **零引用**（接线`审计工具 tools/audit_wiring.py` 可复跑 ✓）⇒ **不复活、只在需要时按声明语义接线** ✓

## 六、验证证据（都可复现）

```bash
cd E:/Users/lmq/MaiBot
# ① 552：同一代码 + 同一数据，只换配置（A/B）
#    现状（总闸 false）⇒ 屏蔽 0 个 source；总闸 true ⇒ 8 个 source（承载 552 条）= 修复前 ✓
# ② running：真库副本 ⇒ 重置前取件 [] → 重置后取到 d4fc5c8067e3（卡了 46 天那条）✓
# ③ 端点补建：py_compile + 行为不变检验（桩内不触碰 metadata_store）✓
# ④ 接线审计：uv run python scripts/embedding_finetune/social_rel/tools/audit_wiring.py
```
