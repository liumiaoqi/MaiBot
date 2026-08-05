"""规则归纳 — 从旋律语料归纳可读规则（学习层）。

架构（Learnable Rule Engine 第一块实验田）：
- 学习层（本文件）：从 ~20 条旋律归纳规则——不是拟合参数，是归纳离散规则
  - 音高转移规则（if 当前音高 then 下一音高分布——但以可读规则输出）
  - 音程关联规则（if 音程 X then 下一音程倾向——回旋/级进/跳进结构）
  - 强关联规则（Apriori：{a,b} → c，三音模式）
  - 旋律模式挖掘（重复子序列——动机）
- 规则库：归纳结果（可读、可验证）
- 推理层：infer_gen.py 用规则库组合生成

用法：
  uv run python induction.py              # 全量归纳
  uv run python induction.py --top 10     # 每类规则展示 top-N
"""

import argparse
from collections import Counter, defaultdict

from corpus import CORPUS


# ── 音高转移规则（马尔可夫式的可读规则形态）────────────────────

def induct_transitions(min_support: int = 2) -> dict[int, Counter]:
    """归纳音高转移：if 当前音高 X then 下一音高分布（支持度 ≥ min_support）。"""
    trans: dict[int, Counter] = defaultdict(Counter)
    for _, notes in CORPUS:
        for a, b in zip(notes, notes[1:], strict=False):
            trans[a][b] += 1
    # 过滤低频转移
    return {a: c for a, c in trans.items() if sum(c.values()) >= min_support}


# ── 音程关联规则（旋律运动的结构规律）──────────────────────────

def intervals(notes: list[int]) -> list[int]:
    """旋律 → 音程序列（相邻音高差）。"""
    return [b - a for a, b in zip(notes, notes[1:], strict=False)]


def induct_interval_rules(min_support: int = 3) -> dict[int, Counter]:
    """归纳音程转移：if 当前音程 X then 下一音程分布（回旋/级进/跳进结构）。"""
    trans: dict[int, Counter] = defaultdict(Counter)
    for _, notes in CORPUS:
        seq = intervals(notes)
        for a, b in zip(seq, seq[1:], strict=False):
            trans[a][b] += 1
    return {a: c for a, c in trans.items() if sum(c.values()) >= min_support}


# ── Apriori 强关联规则（三音模式）─────────────────────────────

def apriori_pairs(min_support: int = 2, min_conf: float = 0.4) -> list[tuple]:
    """归纳三音模式：{a,b} → c（a 后面是 b，则 c 常跟 b 后）。

    支持度 = 模式出现次数；置信度 = P(c | a,b 连续出现)。
    输出可读规则："1-5 之后常跟 6（置信度 0.5）"
    """
    # 统计三元组
    triples: Counter = Counter()
    pair_counts: Counter = Counter()
    for _, notes in CORPUS:
        for i in range(len(notes) - 2):
            a, b, c = notes[i], notes[i + 1], notes[i + 2]
            triples[(a, b, c)] += 1
            pair_counts[(a, b)] += 1

    rules: list[tuple] = []
    for (a, b, c), count in triples.items():
        if count < min_support:
            continue
        conf = count / pair_counts[(a, b)]
        if conf >= min_conf:
            rules.append((a, b, c, count, conf))
    rules.sort(key=lambda r: (-r[3], -r[4]))
    return rules


# ── 旋律模式挖掘（重复子序列——动机）─────────────────────────

def mine_motifs(min_len: int = 3, min_occur: int = 2) -> list[tuple]:
    """挖掘跨曲目重复的旋律模式（动机）。

    子序列 = 连续片段（n-gram），跨曲目出现 ≥ min_occur 次为候选动机。
    """
    seq_counts: Counter = Counter()
    for _, notes in CORPUS:
        for i in range(len(notes) - min_len + 1):
            seq_counts[tuple(notes[i:i + min_len])] += 1
    motifs = [(seq, count) for seq, count in seq_counts.items()
              if count >= min_occur]
    motifs.sort(key=lambda m: (-m[1], -len(m[0])))
    return motifs


# ── 展示 ─────────────────────────────────────────────────────

def show_transitions(top: int = 8) -> None:
    print("## 音高转移规则（if 当前音高 then 下一音高 top3）")
    trans = induct_transitions()
    for pitch, counter in sorted(trans.items()):
        top3 = counter.most_common(3)
        total = sum(counter.values())
        desc = " ".join(f"{n}({c / total:.0%})" for n, c in top3)
        print(f"  if {pitch} → {desc}")


def show_interval_rules(top: int = 8) -> None:
    print("\n## 音程转移规则（旋律运动结构——级进/回旋/跳进）")
    rules = induct_interval_rules()
    for interval, counter in sorted(rules.items()):
        top3 = counter.most_common(3)
        total = sum(counter.values())
        desc = " ".join(f"{n:+d}({c / total:.0%})" for n, c in top3)
        print(f"  if 音程{interval:+d} → {desc}")


def show_apriori(top: int = 10) -> None:
    print("\n## 强关联规则（三音模式 {a,b} → c）")
    rules = apriori_pairs()
    for a, b, c, count, conf in rules[:top]:
        print(f"  if {a}-{b} → {c}（支持度 {count}，置信度 {conf:.0%}）")


def show_motifs(top: int = 10) -> None:
    print("\n## 跨曲目重复模式（动机候选）")
    for seq, count in mine_motifs()[:top]:
        print(f"  {'-'.join(map(str, seq))}（出现 {count} 次）")


def main() -> None:
    parser = argparse.ArgumentParser(description="简谱规则归纳（学习层）")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    print(f"语料: {len(CORPUS)} 首旋律, "
          f"总音符 {sum(len(n) for _, n in CORPUS)}")
    show_transitions(args.top)
    show_interval_rules(args.top)
    show_apriori(args.top)
    show_motifs(args.top)


if __name__ == "__main__":
    main()
