"""推理生成 — 用归纳规则库组合生成新旋律（推理层）。

架构（Learnable Rule Engine）：
- 规则库 = induction.py 归纳的可读规则（音高转移/音程补偿/三音模式/动机）
- 推理 = 前向链：起点音 → 转移规则选下一音 → 跳进补偿约束 →
         乐句尾强制终止式（3-2-1）→ 动机发展（重复/变奏）
- 与 v1（rule_gen.py 纯理论规则）的区别：规则来自数据归纳，
  不是手工音乐理论——"积累"以规则形态参与推理

用法：
  uv run python infer_gen.py --seed 42
  uv run python infer_gen.py --seed 7 --bars 8 --motif "1 2 3"
"""

import argparse
import random
from collections import Counter
from pathlib import Path

from corpus import CORPUS
from induction import apriori_pairs, induct_transitions, mine_motifs


class LearnedRuleEngine:
    """学习型规则引擎：归纳规则库 + 前向链推理生成。"""

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        # ── 规则库（学习层归纳产物）─────────────────────────
        self.transitions = induct_transitions()          # 音高转移
        self.apriori = apriori_pairs()                   # 三音模式（含终止式）
        self.motifs = mine_motifs()                      # 跨曲目动机
        # 终止式规则：3-2-1（最高置信度的下行收束）
        endings = [r for r in self.apriori if r[0] == 3 and r[1] == 2]
        self.end_motif = [3, 2, 1] if endings else [1, 2, 1]
        # 常用动机（除终止式外）
        self.usable_motifs = [list(m[0]) for m in self.motifs[:5]
                              if m[0] != tuple(self.end_motif)]

    # ── 推理：前向链生成 ─────────────────────────────────────

    def _next_pitch(self, prev: int, jump_rate: float = 0.3) -> int:
        """音高转移规则推理：if prev → 按归纳分布选下一音。

        jump_rate：跳进率旋钮——0 时纯归纳级进（如实反映语料风格），
        高时混合跳进（音程 ±3/±4，跳进后补偿规则兜底）。
        """
        if self.rng.random() < jump_rate:
            # 跳进：音程 ±3/±4（大跳由 _compensate 反向级进补偿）
            step = self.rng.choice([-4, -3, 3, 4])
            nxt = max(1, min(7, prev + step))
            return nxt
        counter = self.transitions.get(prev)
        if not counter:
            return self.rng.choice([1, 2, 3, 5, 6])
        items = list(counter.items())
        weights = [c for _, c in items]
        return self.rng.choices([n for n, _ in items], weights=weights)[0]

    def _compensate(self, prev: int, last_step: int) -> int:
        """跳进补偿规则：大跳（≥4 度）后反向级进（归纳规则：+5→-1 80%）。"""
        if abs(last_step) >= 4:
            direction = -1 if last_step > 0 else 1  # 反向
            return max(1, min(7, prev + direction))
        return prev

    def generate(self, bars: int = 4, motif: list[int] | None = None,
                 jump_rate: float = 0.3) -> list[int]:
        """前向链生成：乐句 = 动机/自由 + 转移推理 + 跳进补偿 + 终止式收束。"""
        melody: list[int] = []
        per_bar = 4  # 每小节 4 音（简化）

        for bar_idx in range(bars):
            bar_notes: list[int] = []
            # 动机发展：重复 → 变奏 → 对比
            base = motif or (self.usable_motifs[0] if self.usable_motifs else [1, 2, 3])
            if bar_idx % 3 == 0:
                bar_notes = list(base)
            elif bar_idx % 3 == 1:
                shift = self.rng.choice([-1, 1])
                bar_notes = [max(1, min(7, n + shift)) for n in base]
            else:
                # 对比：转移推理自由生成
                bar_notes = [self.rng.choice([1, 3, 5, 6])]

            # 填充到小节长度（推理链）
            while len(bar_notes) < per_bar:
                prev = bar_notes[-1]
                last_step = bar_notes[-1] - bar_notes[-2] if len(bar_notes) > 1 else 0
                nxt = self._next_pitch(prev, jump_rate)
                nxt = self._compensate(nxt, last_step)
                bar_notes.append(nxt)

            # 乐句尾（最后一小节）：终止式收束（3-2-1）
            if bar_idx == bars - 1:
                bar_notes = bar_notes[:per_bar - 3] + self.end_motif

            melody.extend(bar_notes)

        return melody

    # ── 输出 ─────────────────────────────────────────────────

    def to_jianpu(self, notes: list[int]) -> str:
        parts: list[str] = ["1=C 90 4/4"]
        for i, n in enumerate(notes):
            if i % 4 == 0:
                parts.append("|")
            parts.append(str(n))
        parts.append("|")
        return " ".join(parts)

    def show_rules(self) -> None:
        """展示推理用到的规则库（可读、可验证）。"""
        print("=== 规则库（归纳产物）===")
        print(f"音高转移: {len(self.transitions)} 条")
        for p in sorted(self.transitions):
            top = self.transitions[p].most_common(2)
            total = sum(self.transitions[p].values())
            print(f"  if {p} → {' '.join(f'{n}({c/total:.0%})' for n, c in top)}")
        print(f"三音模式: {len(self.apriori)} 条（终止式 {self.end_motif}）")
        print(f"动机: {self.usable_motifs[:3]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="归纳规则推理生成")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--bars", type=int, default=4)
    parser.add_argument("--motif", type=str, default="", help="动机种子（如 '1 2 3'）")
    parser.add_argument("--jump", type=float, default=0.3, help="跳进率旋钮（0-1）")
    parser.add_argument("--wav", type=str, default="output/inferred.wav")
    args = parser.parse_args()

    engine = LearnedRuleEngine(seed=args.seed)
    engine.show_rules()

    motif = [int(x) for x in args.motif.split()] if args.motif else None
    melody = engine.generate(bars=args.bars, motif=motif, jump_rate=args.jump)
    print(f"\n=== 推理生成（{args.bars} 小节）===")
    print(f"简谱: {engine.to_jianpu(melody)}")

    # 渲染（复用 rule_gen 的渲染逻辑）
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parent))
    from rule_gen import RuleGen

    renderer = RuleGen(bpm=90, seed=args.seed)
    notes = [(n, 1.0) for n in melody]
    out = _P(__file__).resolve().parent / args.wav
    out.parent.mkdir(parents=True, exist_ok=True)
    renderer.render_wav(notes, out)


if __name__ == "__main__":
    main()
