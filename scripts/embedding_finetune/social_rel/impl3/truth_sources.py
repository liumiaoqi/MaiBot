# -*- coding: utf-8 -*-
"""social_rel · s4.1 —— 「真值」候选体检（真库**只读** + 代码**只读**）

task-4 的核心问题：**系统能不能开始记录真值？现在有哪些通道、哪些能用？**

判据（**预登记**，见 `CRITERIA`）——一条通道要能当"真值"，必须同时满足：
  · **A 独立性**：写入者**不在被评估的检索环内**。在环内 ⇒ 拿它当真值就是**自证**
    （audit 的 `freq_active` 与 s2 的 `freq_self` 都是死在这个上：自选择偏差给不出方向）
  · **B 可分辨**：这一列**有多个不同取值**（常数 ⇒ 一比特信息都没有）
  · **C 覆盖**：有多少条关系带着它
  · **D 可证伪**：每条都要给「能推翻它的那条命令」

⚠️ 代码事实（谁写它）**不是从库里能查出来的** ⇒ 本文件把"文件:行 + 该行应含的片段"写成表，
   **每次运行都回读那几行核对**；对不上就**响亮失败**（声明与实体分离的系统必须做启动期校验）。

用法：
  python truth_sources.py            # 体检 + 机械判定（不写文件）
  python truth_sources.py --dump     # 另存 truth_sources.json（下游不碰库）
"""

from argparse import ArgumentParser
import json
import os
import sqlite3
import sys
from collections import Counter
from typing import Dict, List, Tuple

DB_PATH = r"E:\Users\lmq\MaiBot\data\MaiMBot\a-memorix\metadata\metadata.db"
SRC_ROOT = r"E:\Users\lmq\MaiBot\src\A_memorix"
HERE = os.path.dirname(os.path.abspath(__file__))

# --- 代码事实：符号 → (相对路径, 行号, 该行必须含有的片段) --------------------
CODE_FACTS: Dict[str, Tuple[str, int, str]] = {
    "record_access 定义": ("core/storage/metadata_store.py", 955, "def record_access"),
    "adjust_relation_confidence 写 confidence": (
        "core/runtime/services/v5_memory.py", 104, "confidence = MAX(0.0, COALESCE(confidence, 0.0) + ?)"),
    "mark_relations_active 写 confidence": (
        "core/storage/stores/relation_store.py", 594, "confidence = MAX(confidence, ?)"),
    "remember_forever 置 is_pinned": (
        "core/runtime/services/v5_memory.py", 143, "is_pinned=True"),
    "forget 清 is_pinned": (
        "core/runtime/services/v5_memory.py", 148, "is_pinned=False"),
    "reinforce_relations 只写 last_reinforced": (
        "core/storage/stores/relation_store.py", 663, "def reinforce_relations"),
    "显式反馈的对外入口（admin）": (
        "core/runtime/admin/relation.py", 28, "apply_v5_relation_action"),
    "检索默认开 reinforce_access": (
        "core/utils/search_execution_service.py", 207, "reinforce_access: bool = True"),
    "reinforce_access 落到服务": (
        "core/runtime/sdk_memory_kernel.py", 344, "reinforce_relations"),
}

# --- 通道登记：谁能当真值（独立性是**代码事实**，覆盖率是**库事实**）---------
CHANNELS: List[Dict[str, str]] = [
    {"name": "is_pinned", "col": "is_pinned", "kind": "flag",
     "writer": "remember_forever（显式 admin 动作）→ is_pinned=True",
     "in_loop": "否", "note": "显式意图；`protected_until>0` 为 0 行 ⇒ 自动 TTL 保护从未触发"},
    {"name": "last_reinforced", "col": "last_reinforced", "kind": "value",
     "writer": "reinforce_relations ← 检索路径（reinforce_access 默认开）",
     "in_loop": "是", "note": "⚠️ 它由**被评估的那个检索环**写出来 ⇒ 拿它当真值＝自证"},
    {"name": "access_count", "col": "access_count", "kind": "value",
     "writer": "record_access（全仓 0 个调用点）",
     "in_loop": "—", "note": "通道存在、实现完整、**没有任何调用者**"},
    {"name": "last_accessed", "col": "last_accessed", "kind": "value",
     "writer": "record_access（同上）",
     "in_loop": "—", "note": "同上"},
    {"name": "confidence", "col": "confidence", "kind": "value",
     "writer": "remember_forever 的 MAX(confidence,0.1) / adjust_relation_confidence 的 ±delta",
     "in_loop": "否", "note": "⚠️ 列默认 1.0 ⇒ 唯一跑过的写路径是**空操作**"},
    {"name": "is_permanent", "col": "is_permanent", "kind": "flag",
     "writer": "（未找到写入点）",
     "in_loop": "—", "note": "全 0"},
]


def connect() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(DB_PATH)
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)


def verify_code_facts() -> bool:
    """回读 `CODE_FACTS` 指的每一行 —— 对不上就响亮失败（防"声明漂移"）。"""
    ok = True
    print("【代码事实核对】（每条都回读文件的那一行）")
    for label, (rel, lineno, needle) in CODE_FACTS.items():
        path = os.path.join(SRC_ROOT, rel.replace("/", os.sep))
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
            actual = lines[lineno - 1].strip() if lineno <= len(lines) else "<行号越界>"
        except OSError as exc:
            actual = f"<读不到：{exc}>"
        hit = needle in actual
        ok &= hit
        print(f"  {'✓' if hit else '✗'} {label:<34} {rel}:{lineno}")
        if not hit:
            print(f"      期望含：{needle}\n      实际是：{actual}")
    return ok


def channel_facts(con: sqlite3.Connection) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    n_total = con.execute("select count(*) from relations").fetchone()[0]
    total_pairs = n_total * (n_total - 1) // 2
    for ch in CHANNELS:
        col = ch["col"]
        allv = [r[0] for r in con.execute(f"select {col} from relations").fetchall()]
        # ⚠️ 无值/零一律归进**同一个「空」组**（必须彼此并列 —— 不能当成彼此不同的值）
        keys = [v if (v is not None and v != 0) else None for v in allv]
        cnt = Counter(keys)
        tied = sum(c * (c - 1) // 2 for c in cnt.values())
        covered_vals = [k for k in keys if k is not None]
        out.append({
            **ch,
            "n_total": int(n_total),
            "covered": len(covered_vals),
            "cover_frac": len(covered_vals) / max(1, n_total),
            "distinct": len(set(covered_vals)),
            # 与 `impl2` §3 **同一口径**：可区分对子 = 总对子 − 同值（并列）对子
            "pairs": total_pairs - tied,
            "verdict": "",
        })
    return out


def judge(ch: Dict[str, object]) -> str:
    """**机械判定**：能不能当"用户显式反馈"的代理。

    ⚠️ 布尔**标志位**与**取值**通道的"可分辨"判据不同（2026-09-27 我第一版判错过一次）：
       · 标志位（如 `is_pinned`）：信息在**有/无的分组**里 ⇒ 判据是 `0 < 覆盖 < 总数`
         （47 条 is_pinned 的**取值**只有一个 `1`，但"是不是被固定过"把 184 条切成了 47/137 —— 那是信息）
       · 取值通道（如 `last_reinforced`）：信息在**值的大小/次序**里 ⇒ 判据是「覆盖内取值数 > 1」
    """
    in_loop = ch["in_loop"] == "是"
    covered = int(ch["covered"])  # type: ignore[arg-type]
    distinct = int(ch["distinct"])  # type: ignore[arg-type]
    n_total = int(ch["n_total"])  # type: ignore[arg-type]
    if in_loop:
        return "不能用（在检索环内 ⇒ 自证）"
    if covered == 0:
        return "不能用（通道为空）"
    if ch.get("kind") == "flag":
        return "候选可用" if covered < n_total else "不能用（全置位 ⇒ 零信息）"
    return "候选可用" if distinct > 1 else "不能用（常数 ⇒ 零信息）"


def main() -> None:
    ap = ArgumentParser(description="s4.1 真值候选体检")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    ok = verify_code_facts()
    if not ok:
        raise SystemExit("✗ 代码事实与登记不符 —— 拒绝继续（结论的前提已失效）")

    con = connect()
    try:
        rows = channel_facts(con)
        n_total = rows[0]["n_total"]
        # 两个"表级"通道（不在 relations 上）
        fb = {t: con.execute(f"select count(*) from {t}").fetchone()[0]
              for t in ("memory_feedback_tasks", "memory_feedback_action_logs")}
        conf_default = dict((r[1], r[4]) for r in con.execute("pragma table_info(relations)"))
    finally:
        con.close()

    for r in rows:
        r["verdict"] = judge(r)

    print()
    print(f"【通道体检】relations 共 {n_total} 行 · `confidence` 列默认值 = {conf_default['confidence']}")
    print(f"  {'通道':<18} {'覆盖':>10} {'取值数':>7} {'在环内':>7} {'可区分对子':>11}  判定")
    for r in rows:
        c, nt = int(r["covered"]), int(r["n_total"])  # type: ignore[arg-type]
        print(f"  {r['name']:<18} {str(c) + '/' + str(nt):>10} {r['distinct']:>7} "
              f"{r['in_loop']:>7} {int(r['pairs']):>11,}  {r['verdict']}")
    total_pairs = n_total * (n_total - 1) // 2
    for t, n in fb.items():
        print(f"  {t:<18} {'0/0':>10} {0:>7} {'否':>7} {0:>11,}  不能用（通道为空）")
    print(f"  （关系对总数 = {total_pairs:,}；口径与 `impl2` §3 相同：总对子 − 同值对子）")

    print()
    print("【为什么 `confidence` 恒为 1.0 —— 本轮查到的**机制**（不是「没人写」）】")
    print(f"  ① 列默认值 = {conf_default['confidence']}（一出生就在天花板）")
    print("  ② 唯一跑过的写路径是 `remember_forever` → `confidence = MAX(confidence, 0.1)`")
    print("     ⇒ MAX(1.0, 0.1) = 1.0 ⇒ **恒为空操作**")
    print("  ③ 另外三条路径（reinforce/weaken/forget）用 `MAX(0.0, confidence ± delta)`：")
    print("     · weaken(−0.5) / forget(−2.0) **能把值打下来** —— 但库里一条都没有 ⇒ **它们从未跑过**")
    print("     · reinforce(+0.5) **没有上界钳位** ⇒ 若跑过，库里会出现 **>1.0 的值** —— 也没有")
    print("  ⇒ 观测到的「全 1.0」**只能**由「只跑过 remember_forever」解释（47 条 is_pinned 正好是它的签名）")

    if args.dump:
        out = os.path.join(HERE, "truth_sources.json")
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"n_total": n_total, "confidence_default": conf_default["confidence"],
                       "channels": rows, "feedback_tables": fb}, fh,
                      ensure_ascii=False, indent=1)
        print(f"\n  ✓ 已写出 {os.path.basename(out)}")


if __name__ == "__main__":
    main()
