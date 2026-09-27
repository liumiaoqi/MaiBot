# -*- coding: utf-8 -*-
"""social_rel · s3.1 —— 真库快照（**只读** · **只取聚合量，不取内容**）

取什么 / 不取什么（承 `NOTES.md §1.2` 的既定纪律：**只取聚合量，不取内容**）：
  ✅ 取：每条关系的**支撑度**（段落数）· `last_reinforced` 的**有无与相对时间** · 向量是否就绪 · 主体**分组编号**
  ⛔ 不取：`subject` / `predicate` / `object` / `source_paragraph` 的**任何文本** · 任何段落内容 · 任何 embedding

分组编号是"第几个不同主体"的整数，不含任何词面信息 —— 它的唯一用途是让离线侧能按真实分组重建候选池。

⚠️ 打开方式（安全边界）：
  `file:...?mode=ro` —— **只读**，SQLite 不会写库、不会 checkpoint、不会恢复 WAL。
  ⛔ **不用 `immutable=1`**：本库 `journal_mode=wal` 且 `-wal` 有 391,432 B 未合并内容，
     `immutable=1` 会**忽略 WAL** ⇒ **读到的不是当前状态**（数字会错）。
  ⚠️ 副作用如实记录：`mode=ro` 打开时 SQLite 仍会 touch 同目录的 `metadata.db-shm`
     （共享内存索引，任何读写者本来都会动它）。**2026-09-27 实测**：`-shm` mtime 14:09:16 → 14:14:42。
     这不改任何数据，但**它确实是"碰了库"**，故在此明写。
  ⇒ 本脚本**只在需要刷新快照时手动跑**；下游 `rebuild.py` / `rank_eval.py` 一律读 JSON，**不再碰库**。

用法：
  python snapshot.py            # 重建 real_sample.json 并打印实测事实
  python snapshot.py --check    # 只交叉核对（与 NOTES.md §1.2 的既有数字比），不写文件
"""

from argparse import ArgumentParser
import json
import os
import sqlite3
from collections import Counter
from typing import Dict, List, Optional

DB_PATH = r"E:\Users\lmq\MaiBot\data\MaiMBot\a-memorix\metadata\metadata.db"
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_sample.json")

# --- 与 `NOTES.md §1.2` 已登记的数字交叉核对（不一致就报错，不静默放过） ---
EXPECTED: Dict[str, object] = {
    "n_relations": 184,
    "n_subjects": 36,
    "confidence_distinct": 1,
    "last_reinforced_nonnull": 22,
    "last_reinforced_distinct": 15,
    "access_count_sum": 0,
}


def connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"真库不存在：{db_path}")
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)


def extract(con: sqlite3.Connection) -> Dict[str, object]:
    q = lambda s: con.execute(s).fetchall()  # noqa: E731 —— 局部小工具，只读

    # 关系主表：按 hash 稳定排序（hash 本身**不导出**），只取聚合列
    rows = q("""
        select hash, subject, confidence, last_reinforced, vector_state, created_at
        from relations order by hash
    """)
    support = dict(q("""
        select relation_hash, count(*) from paragraph_relations group by relation_hash
    """))

    # 主体 → 整数分组编号（按主体字符串排序后编号；**导出的是编号，不是主体名**）
    subjects: List[str] = sorted({r[1] for r in rows})
    group_of = {s: i for i, s in enumerate(subjects)}

    reinf = [r[3] for r in rows if r[3] is not None]
    base = min(reinf) if reinf else 0.0

    rels: List[Dict[str, object]] = []
    for h, subj, conf, lr, vstate, _created in rows:
        rels.append({
            "g": group_of[subj],                                  # 主体分组编号（无词面信息）
            "sup": int(support.get(h, 0)),                        # 支撑度：几个段落支撑
            # ⚠️ 存**秒差**，不存"天"：真库里最近的两个强化时刻只差 **4.774 s**；
            #    换算成天再 round(,4) 会把它俩合并（分辨率 8.64 s）⇒ distinct 从 15 掉到 14。
            #    2026-09-27 实测踩到，靠下面的 assert 拦住。
            "reinf_sec": (None if lr is None else round(lr - base, 6)),
            "vec_ok": 1 if vstate == "ready" else 0,              # 相似度(向量)是否就绪
            "conf": float(conf),                                  # 现状值（预期恒为 1.0）
        })

    return {
        "source_db": os.path.basename(DB_PATH),
        "db_bytes": os.path.getsize(DB_PATH),
        "note": "只含聚合量；无任何文本/向量内容",
        "n_relations": len(rels),
        "n_subjects": len(subjects),
        "relations": rels,
    }


def cross_check(snap: Dict[str, object], con: sqlite3.Connection) -> bool:
    """与 NOTES §1.2 的既有数字交叉核对 —— 不一致必须响亮失败。"""
    rels = snap["relations"]  # type: ignore[index]
    db_distinct = int(con.execute(
        "select count(distinct last_reinforced) from relations where last_reinforced is not null"
    ).fetchone()[0])
    got = {
        "n_relations": len(rels),
        "n_subjects": snap["n_subjects"],
        "confidence_distinct": len({r["conf"] for r in rels}),
        "last_reinforced_nonnull": sum(1 for r in rels if r["reinf_sec"] is not None),
        "last_reinforced_distinct": len({r["reinf_sec"] for r in rels if r["reinf_sec"] is not None}),
        "access_count_sum": int(con.execute("select sum(access_count) from relations").fetchone()[0] or 0),
    }
    ok = True
    print("【交叉核对 · 与 NOTES.md §1.2 已登记的数字】")
    for k, want in EXPECTED.items():
        hit = got[k] == want
        ok &= hit
        print(f"  {k:<28} 本次 = {got[k]:<6} 已登记 = {want:<6} {'✓' if hit else '✗ 不一致！'}")

    # ⭐ 导出保真度守卫：导出后的 distinct 必须等于库里的 distinct。
    #    （否则就是**导出过程**丢了精度 —— 2026-09-27 实测发生过一次：天数+round(,4) 把 4.774 s 的差合并了）
    fid = got["last_reinforced_distinct"] == db_distinct
    ok &= fid
    print(f"  导出保真度：JSON distinct = {got['last_reinforced_distinct']} vs 库内 distinct = {db_distinct}"
          f"  {'✓' if fid else '✗ 导出丢精度！'}")
    return ok


def degeneracy(snap: Dict[str, object]) -> None:
    """⭐ 真数据上**精确可算**的表达力：痕迹派生 confidence 到底能区分多少「关系对」。

    这一节不依赖任何模型假设 —— 它只数真库里的并列。
    ⚠️ 「可区分」**只说明权重值不同**，不说明这些差异指向真值（那取决于耦合 κ，真库给不出）。
    """
    rels: List[Dict[str, object]] = snap["relations"]  # type: ignore[index]
    n = len(rels)
    reinforced = [r for r in rels if r["reinf_sec"] is not None]
    nr = len(reinforced)
    vals = Counter(r["reinf_sec"] for r in reinforced)
    # 可区分对子 = 总数 − 同值（并列）对数
    total_pairs = n * (n - 1) // 2
    within = Counter(r["reinf_sec"] if r["reinf_sec"] is not None else -1 for r in rels)
    tied = sum(c * (c - 1) // 2 for c in within.values())
    distinguishable = total_pairs - tied

    print()
    print("【真实侧表达力 · 精确计数（不含任何模型假设）】")
    print(f"  关系总数 = {n} · 有强化痕迹 = {nr}（{nr / n:.2%}）· 无痕迹 = {n - nr}（{(n - nr) / n:.2%}）")
    print(f"  ⭐ 无痕迹的 {n - nr} 条在「只由 last_reinforced 派生」的 confidence 下**必然全部并列**"
          f"（它们与彼此的 {n - nr - 1} 个对子都分不开）")
    print(f"  有痕迹的 {nr} 条里只有 {len(vals)} 个不同值 ⇒ 内部还有 {sum(c * (c - 1) // 2 for c in vals.values())} 个对子并列")
    print(f"  ⇒ 可区分对子 = {distinguishable:,} / {total_pairs:,} = **{distinguishable / total_pairs:.2%}**"
          f"（其余 {tied / total_pairs:.2%} 的对子上与常数完全等价）")
    sup = Counter(r["sup"] for r in rels)
    tied_sup = sum(c * (c - 1) // 2 for c in sup.values())
    print(f"  支撑度分布 = {sorted(sup.items())} ⇒ 可区分 {total_pairs - tied_sup:,} / {total_pairs:,}"
          f" = {(total_pairs - tied_sup) / total_pairs:.2%}（但覆盖 184/184）")


def main() -> None:
    ap = ArgumentParser(description="s3.1 真库快照（只读 / 只取聚合量）")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--out", default=SNAPSHOT_PATH)
    ap.add_argument("--check", action="store_true", help="只核对，不写文件")
    args = ap.parse_args()

    con = connect(args.db)
    try:
        snap = extract(con)
        ok = cross_check(snap, con)
    finally:
        con.close()
    degeneracy(snap)

    print()
    print(f"  主体分组数 = {snap['n_subjects']} · 库大小 = {snap['db_bytes'] / 1e6:.1f} MB")
    if args.check:
        raise SystemExit(0 if ok else 1)
    if not ok:
        raise SystemExit("✗ 交叉核对失败 —— 拒绝写出与本线已登记数字不一致的快照")

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=1)
    print(f"  ✓ 已写出 {os.path.basename(args.out)}（{os.path.getsize(args.out)} B，"
          f"**只含聚合量**，下游一律读它、不再碰库）")


if __name__ == "__main__":
    main()
