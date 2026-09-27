"""B 线试点 · 源问题集生成器（social_rel/sat/）

设计约束（照 NOTES §7.6）：
  · ⭐ 答案**唯一**且**可机械判定**  ⇒ 每题带答案键，校验器不依赖人眼
  · ⭐ 成员**会失手**（不是白给）    ⇒ 埋"口径陷阱"：空值有三种写法、派生关系有方向
  · ⭐ **无法靠检索作弊**            ⇒ 数据是本脚本合成的，外部没有第三处可查
  · ⭐ 题面**不含答案**              ⇒ 源依赖审计（机械版）的前提

三类题（每类都能机械判分）：
  T1 `empty_col`  —— 6 列里哪一列**整列为空**（陷阱：`""` / `"-"` / `"0"` / `"NULL"` 写法混用）
  T2 `tampered_row` —— 哪一行**违反了列间的派生关系**（如 col_c = round(col_a·k, 1)）
  T3 `derived_from` —— 两列谁**派生自**谁（方向题，差一点就反）

用法：
  python make_problems.py --gen --seed 20260927 --n 7   # 生成 problems.json
  python make_problems.py --verdict sat/answers.json    # 机械判分（答案键在 problems.json 里）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
from typing import Dict, List

HERE = pathlib.Path(__file__).resolve().parent

# ⚠️ 空值的多种写法 —— 陷阱之源：成员必须**先定口径**再答（"哪个算空"）
NULLISH = ["", "-", "0", "NULL", "n/a"]


def _fmt(v) -> str:
    return f"{v:.1f}" if isinstance(v, float) else str(v)


def make_table(rows: int, cols: List[str], rng: random.Random) -> List[List[str]]:
    return [[_fmt(round(rng.uniform(1, 99), 1)) for _ in cols] for _ in range(rows)]


def gen_t1(rng: random.Random, rows: int = 40) -> Dict:
    """哪一列整列为空（口径：只有 '' 与 '-' 算空；'0' 与 'NULL' 是**值**）"""
    cols = ["A", "B", "C", "D", "E", "F"]
    t = make_table(rows, cols, rng)
    empty_i = rng.randrange(len(cols))
    for r in range(rows):
        t[r][empty_i] = rng.choice(["", "-"])
    # 干扰项：另有一列**看起来**像空（全是 '0'）—— 但它不是空，是有值
    decoy = rng.choice([i for i in range(len(cols)) if i != empty_i])
    for r in range(rows):
        t[r][decoy] = "0"
    return {
        "kind": "empty_col",
        "table": {"cols": cols, "rows": t},
        "question": "哪一列**整列为空**？（口径：只有空字符串与 '-' 算空；'0'/'NULL' 算有值）"
                    " 只答列名。",
        "answer": cols[empty_i],
        "decoy": cols[decoy],
    }


def gen_t2(rng: random.Random, rows: int = 30) -> Dict:
    """哪一行违反了 col_c = round(col_a * 3.0, 1)（有一行被改过）"""
    cols = ["t", "col_a", "col_b", "col_c", "note"]
    t = []
    for r in range(rows):
        a = round(rng.uniform(1, 30), 1)
        b = round(rng.uniform(1, 30), 1)
        c = round(a * 3.0, 1)
        t.append([str(r + 1), _fmt(a), _fmt(b), _fmt(c), rng.choice(["ok", "seen", "auto"])])
    bad = rng.randrange(1, rows - 1)                      # 不取首尾，避免"边界行"成为线索
    t[bad][3] = _fmt(round(float(t[bad][1]) * 3.0 + rng.choice([1.3, -1.7, 2.9]), 1))
    return {
        "kind": "tampered_row",
        "table": {"cols": cols, "rows": t},
        "question": "表中**只有一行**违反派生关系 `col_c = round(col_a * 3.0, 1)`（允许 0.0 的舍入误差）。"
                    " 只答 `t` 的值（正整数）。",
        "answer": t[bad][0],
    }


def gen_t3(rng: random.Random, rows: int = 24) -> Dict:
    """两列谁派生自谁：v = round(u * k, 1)，问**源**是哪一列"""
    cols = ["id", "u", "v", "w"]
    k = rng.choice([2.5, 4.0, 7.5])
    order = rng.random() < 0.5
    t = []
    for r in range(rows):
        a = round(rng.uniform(1, 50), 1)
        b = round(a * k, 1)
        u, v = (a, b) if order else (b, a)                 # 谁是谁**随机**，防位置偏见
        t.append([str(r + 1), _fmt(u), _fmt(v), _fmt(round(rng.uniform(1, 9), 1))])
    src, dst = ("u", "v") if order else ("v", "u")
    return {
        "kind": "derived_from",
        "table": {"cols": cols, "rows": t},
        "question": f"`u` 与 `v` 之间是 `目标 = round(源 * {k}, 1)` 的派生关系。**哪一列是源**？ 只答 `u` 或 `v`。",
        "answer": src,
    }


def gen_t4(rng: random.Random, rows: int = 26) -> Dict:
    """⭐ 口径硬题：哪一行的**四舍五入约定**与其余行不一致（多数派 vs 唯一违规行）

    ⚠️ 这是 wave 1 的教训直接产物：两位成员**都**在自陈里担心"舍入约定"（HALF_UP vs HALF_EVEN）
       ⇒ 把难度加在**口径歧义**上，而不是加计算量。
    做法：先造出若干"两种约定会给出不同结果"的中点行（如 x.25 → 0.3 vs 0.2），
          多数派用约定 A，**恰好一行**用约定 B。
    """
    from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN

    def r1(v: Decimal, mode) -> str:
        return str(v.quantize(Decimal("0.1"), rounding=mode))

    cols = ["t", "col_a", "col_c"]
    k = Decimal("3.0")
    majority = rng.choice([ROUND_HALF_UP, ROUND_HALF_EVEN])
    minority = ROUND_HALF_EVEN if majority is ROUND_HALF_UP else ROUND_HALF_UP

    rows_out: List[List[str]] = []
    sensitive: List[int] = []                                # 两种约定结果不同的行
    for i in range(rows):
        for _ in range(200):                                 # 找一个"有分歧"的 a
            a = Decimal(str(round(rng.uniform(0.05, 40), 2)))
            c = a * k
            if r1(c, ROUND_HALF_UP) != r1(c, ROUND_HALF_EVEN):
                break
        else:
            a, c = Decimal("10.25"), Decimal("10.25") * k
        rows_out.append([str(i + 1), str(a), r1(c, majority)])
        if r1(c, ROUND_HALF_UP) != r1(c, ROUND_HALF_EVEN):
            sensitive.append(i)
    if not sensitive:                                        # 兜底：正常不会走到
        raise RuntimeError("没能造出约定敏感行")
    bad = rng.choice(sensitive[1:-1] if len(sensitive) > 2 else sensitive)
    a_bad = Decimal(rows_out[bad][1])
    rows_out[bad][2] = r1(a_bad * k, minority)                # 唯一违规行

    conv = "HALF_UP(四舍五入)" if majority is ROUND_HALF_UP else "HALF_EVEN(银行家舍入)"
    return {
        "kind": "rounding_outlier",
        "table": {"cols": cols, "rows": rows_out},
        "question": "`col_c` = `col_a × 3.0` 保留 1 位小数（**精确十进制**，不是二进制浮点）。"
                    "**表中恰好有一行**的四舍五入约定与**其余所有行**不一致"
                    "（其余行统一用同一种约定）。只答 `t` 的值（正整数）。",
        "answer": rows_out[bad][0],
        "majority_convention": conv,
    }


def gen_t5_undecidable(rng: random.Random, rows: int = 6) -> Dict:
    """⭐ 难度轴转向（wave 2 的结论）：**信息不足 ⇒ 正解是「无法判定」**

    形态：表中 `col_c` 由某简单规则生成，给两个候选规则 R1/R2：
      · **一半的题**：R1、R2 在**全部给定行上都成立** ⇒ 正确答 **「无法判定」**（数据不足以区分）
      · **另一半**：R1 全部成立、R2 至少一行不成立 ⇒ 正确答 **「R1」**
    ⚠️ 两类各半 ⇒ **答案不是常数**（照"提示位"判据，防题型本身成为提示）。
    ⚠️ 可机械验证：生成时就断言"两类各自的成立情况"，并写进键里供复核。
    """
    cols = ["t", "col_a", "col_b", "col_c"]
    undecidable = rng.random() < 0.5
    break_at = rng.randrange(rows)               # ⚠️ 破坏行**随机**（固定末行=位置提示）
    rows_out: List[List[str]] = []
    for i in range(rows):
        a = round(rng.uniform(1, 20), 1)
        if undecidable:
            b = round(a * 2.0, 1)                # 两个规则都被满足
            c = round(a * 2.0, 1)
        else:
            b = round(a * 2.0, 1)
            c = round(a * 2.0, 1)
            if i == break_at:                    # ⭐ 随机一行破坏 R2（不是固定末行）
                b = round(a * 2.0 + rng.choice([0.3, -0.4]), 1)
        rows_out.append([str(i + 1), _fmt(a), _fmt(b), _fmt(c)])

    # ⭐ 机械核（生成时自证）：两规则各自"全部行成立"与否
    r1_ok = all(abs(round(float(r[1]) * 2.0, 1) - float(r[3])) < 1e-9 for r in rows_out)
    r2_ok = all(abs(float(r[2]) - float(r[3])) < 1e-9 for r in rows_out)
    if undecidable:
        assert r1_ok and r2_ok, "undecidable 题必须两规则都成立"
        answer = "无法判定"
    else:
        assert r1_ok and not r2_ok, "decidable 题必须 R1 成立、R2 不成立"
        answer = "R1"
    return {
        "kind": "undecidable",
        "table": {"cols": cols, "rows": rows_out},
        "question": "`col_c` 由**某一条**简单规则生成。候选：(R1) `col_c = 2 × col_a`；"
                    "(R2) `col_c = col_b`。**仅凭这张表**能唯一确定是 R1 还是 R2 吗？"
                    "若**不能**，答 `无法判定`；若能，答 `R1` 或 `R2`。",
        "answer": answer,
        "verify": {"R1_fits_all_rows": r1_ok, "R2_fits_all_rows": r2_ok},
    }


GENS = [gen_t1, gen_t2, gen_t3, gen_t4, gen_t5_undecidable]


def _answers_distinct(problems: List[Dict]) -> bool:
    """同型题的答案必须**两两不同**（防"提示位"：同型题答案跨题规律会被成员看出来）"""
    by_kind: Dict[str, List[str]] = {}
    for p in problems:
        by_kind.setdefault(p["kind"], []).append(str(p["answer"]))
    return all(len(v) == len(set(v)) for v in by_kind.values())


def gen_all(n: int, seed: int) -> Dict:
    """⭐ 生成时**强制同型题答案两两不同**（"提示位"判据）——
    同一 seed 下重试最多 200 次，取第一个满足分散条件的集合；并把检查结果写进键里。"""
    rng = random.Random(seed)
    problems: List[Dict] = []
    for attempt in range(200):
        problems = []
        r = random.Random(seed + attempt * 7919)
        for i in range(n):
            p = GENS[i % len(GENS)](r)
            p["pid"] = f"P{i + 1:02d}"
            problems.append(p)
        if _answers_distinct(problems):
            break
    else:
        raise RuntimeError("200 次重试仍无法让同型题答案两两不同 —— 请增加题量或改设计")
    return {"seed": seed, "n": n, "problems": problems,
            "answers_distinct_within_kind": _answers_distinct(problems),
            "note": "答案键在本文件里；发给成员时**必须剥掉 answer/decoy/kind/verify/majority_convention 字段**。"}


def strip_for_solver(problems: Dict) -> Dict:
    """发给成员的那一份：只留 pid/table/question（源依赖审计的机械前提）"""
    return {"problems": [{"pid": p["pid"], "table": p["table"], "question": p["question"]}
                         for p in problems["problems"]]}


def verdict(answers_path: str, problems: Dict) -> None:
    """机械判分：answers = [{"pid": "P01", "answer": "C"}, ...]"""
    given = {a["pid"]: str(a.get("answer", "")).strip() for a in
             json.loads(pathlib.Path(answers_path).read_text(encoding="utf-8"))}
    hit = 0
    for p in problems["problems"]:
        ok = given.get(p["pid"], "?") == p["answer"]
        hit += ok
        print(f"   {p['pid']} [{p['kind']:<13}] 答={given.get(p['pid'], '缺失'):<8} "
              f"真值={p['answer']:<6} {'✓' if ok else '✗'}")
    n = len(problems["problems"])
    print(f"   === 命中 {hit}/{n} = {hit / n:.3f} ===")


def audit(data: Dict) -> int:
    """⭐ 题集审计（"提示位探针"的可执行版）：答案有没有**可观察的形状**？

    检查三类（每命中一条 → 记 1 个问题，返回问题数）：
      ① **同型答案重复**（跨题规律的最小版）
      ② **位置相关**：某型的答案**总是**落在首行/末行（或首列/末列）
      ③ **类别常量**：`undecidable` 这类"答案是个类别"的题，类别是否恒定

    ⚠️ 这只覆盖"答案 ↔ 位置/类别"这一层；**真正的一般性检查无法穷举**（这是本探针的已知上限，如实标注）。
    """
    problems = data["problems"]
    flags: List[str] = []

    by_kind: Dict[str, List[Dict]] = {}
    for p in problems:
        by_kind.setdefault(p["kind"], []).append(p)

    # ① 同型答案重复
    for kind, ps in by_kind.items():
        ans = [str(p["answer"]) for p in ps]
        if len(ans) != len(set(ans)):
            flags.append(f"① {kind}: 同型答案重复 {ans}")

    # ② 位置相关（把答案翻译成"在表里的位置"）
    def pos_of(p: Dict):
        rows = p["table"]["rows"]
        cols = p["table"]["cols"]
        if p["kind"] in ("tampered_row", "rounding_outlier"):
            idx = [i for i, r in enumerate(rows) if r[0] == str(p["answer"])]
            return ("row", idx[0], len(rows)) if idx else None
        if p["kind"] == "empty_col":
            return ("col", cols.index(p["answer"]), len(cols)) if p["answer"] in cols else None
        if p["kind"] == "derived_from":
            return ("col", cols.index(p["answer"]), len(cols)) if p["answer"] in cols else None
        return None

    for kind, ps in by_kind.items():
        poss = [pos_of(p) for p in ps]
        poss = [x for x in poss if x]
        if len(poss) < 2:
            continue
        axis = poss[0][0]
        idxs = [x[1] for x in poss]
        lens = [x[2] for x in poss]
        edges = {0, -1}
        rel = {i - (n - 1) if i > n // 2 else i for i, n in zip(idxs, lens)}  # 0=首, -1=末
        if rel and rel <= edges:
            flags.append(f"② {kind}: 答案位置全在边缘 {idxs}/{lens}（位置即提示）")
        if len(set(idxs)) == 1 and len(ps) > 1:
            flags.append(f"② {kind}: 答案位置全同 {idxs[0]}/{lens[0]}（位置即提示）")

    # ③ 类别常量
    for kind, ps in by_kind.items():
        ans = {str(p["answer"]) for p in ps}
        if kind == "undecidable" and len(ans) == 1:
            flags.append(f"③ {kind}: 答案类别恒定 {ans}（正解永远是同一个 ⇒ 可被猜中）")

    print('   【题集审计】')
    for kind, ps in sorted(by_kind.items()):
        show = [f"{p['pid']}={p['answer']}" for p in ps]
        pos = [pos_of(p) for p in ps]
        print(f'      {kind:<18} {show}   位置={pos}')
    if flags:
        print(f'   ⛔ 命中 {len(flags)} 条可疑形状：')
        for f in flags:
            print('      ' + f)
    else:
        print('   ✓ 三类检查均未命中（⚠️ 不等于"无提示"—— 本审计只覆盖位置/类别这一层）')
    return len(flags)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--n", type=int, default=7)
    ap.add_argument("--verdict", default="")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--file", default="", help="--audit 要审的文件（默认 problems.json）")
    args = ap.parse_args()

    pfile = HERE / "problems.json"
    if args.gen:
        data = gen_all(args.n, args.seed)
        # ⚠️ 显式 newline="\n"：Python 在 Windows 默认会把 \n 翻成 CRLF（本仓规范是 LF）
        pfile.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                         encoding="utf-8", newline="\n")
        solver = HERE / "problems_solver.json"
        solver.write_text(json.dumps(strip_for_solver(data), ensure_ascii=False, indent=1),
                          encoding="utf-8", newline="\n")
        print(f"   写出 {pfile.name}（含答案键）与 {solver.name}（发给成员的那一份）")
        print(f"   题目 {data['n']} 道：" + ", ".join(f"{p['pid']}:{p['kind']}" for p in data["problems"]))
    if args.verdict:
        verdict(args.verdict, json.loads(pfile.read_text(encoding="utf-8")))
    if args.audit:
        data = json.loads((HERE / args.file if args.file else pfile).read_text(encoding="utf-8"))
        bad = audit(data)
        raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
