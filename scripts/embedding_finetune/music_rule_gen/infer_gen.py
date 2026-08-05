"""推理生成 v2 — 归纳规则 + 音乐结构升级（推理层）。

v2 升级（用户反馈"乐曲太简单"）：
1. 节奏：全四分音符 → 节奏型库（长短/切分/附点/长音）——节奏算术填满小节
2. 音域：单八度 → 两个八度（音高值 -6..14，八度偏移/高低音记号）
3. 结构：4 小节 → 8 小节 A-A-B-A（A 段半终止 / B 段对比 / 回归全终止）
4. 和弦：推理时 40% 锚定和弦音（I-V-vi-IV 循环）——和声支撑

规则库仍来自 induction.py 归纳（学习层不变，推理层升级）。
"""

import argparse
import random
from pathlib import Path

from corpus import CORPUS
from induction import apriori_pairs, induct_transitions, mine_motifs

# ── 音高编码：值 -6..14（两个八度），音级 = ((v-1)%7)+1，八度 = (v-1)//7 ──
PITCH_NAMES = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7"}


def pitch_info(value: int) -> tuple[int, int]:
    """音高值 → (音级 1-7, 八度偏移 -1/0/+1)。"""
    grade = ((value - 1) % 7) + 1
    octave = (value - 1) // 7
    return grade, octave


def pitch_value(grade: int, octave: int = 0) -> int:
    return grade + octave * 7


# 节奏型库（每小节时值组合，**总和必须 = 4 拍**——节奏算术）
RHYTHMS = [
    [1, 1, 1, 1],                # 均匀
    [0.5, 0.5, 1, 1, 1],         # 短-短-长-长-长
    [1, 0.5, 0.5, 1, 1],         # 长-短-短-长-长
    [0.5, 1, 0.5, 1, 1],         # 短-长-短-长-长（切分感）
    [1, 1, 2],                   # 长音结尾
    [2, 1, 1],                   # 长音开头
    [0.5, 0.5, 0.5, 0.5, 1, 1],  # 密集 + 长音
    [0.75, 0.25, 1, 1, 1],       # 附点
]

# 12/8 拍节奏型（每小节 **总和必须 = 12 个 8 分单位**——璃月原谱密度）
RHYTHMS_12_8 = [
    [1] * 12,                                        # 均匀 8 分流动
    [0.5, 0.5, 1] * 6,                               # 16 分密集交替（18 音）
    [1, 1, 1, 0.5, 0.5, 1, 1, 1, 1, 1, 1, 1, 1],     # 短音点缀（13 音）
    [2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],               # 长音开头（11 音）
    [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1],               # 长音中间（12 音）
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],            # 均匀（同上）
]

# 和弦走向（I-V-vi-IV 循环，每小节锚定）
PROGRESSION = [1, 5, 6, 4]
CHORD_TONES = {1: [1, 3, 5], 5: [5, 7, 2], 6: [6, 1, 3], 4: [4, 6, 1]}


class LearnedRuleEngine:
    """学习型规则引擎：归纳规则库 + 前向链推理生成（v2 结构升级）。"""

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        # ── 规则库（学习层归纳产物）─────────────────────────
        self.transitions = induct_transitions()
        self.apriori = apriori_pairs()
        self.motifs = mine_motifs()
        endings = [r for r in self.apriori if r[0] == 3 and r[1] == 2]
        self.end_motif = [3, 2, 1] if endings else [1, 2, 1]
        self.usable_motifs = [list(m[0]) for m in self.motifs[:5]
                              if m[0] != tuple(self.end_motif)]

    # ── 推理原语 ─────────────────────────────────────────────

    def _next_pitch(self, prev: int, chord: int, jump_rate: float) -> int:
        """转移规则推理 + 跳进 + 和弦锚定。"""
        if self.rng.random() < jump_rate:
            # 大跳（含八度）：±3/±4/±7，由补偿规则反向回正
            step = self.rng.choice([-7, -4, -3, 3, 4, 7])
            nxt = max(-6, min(14, prev + step))
            if self.rng.random() < 0.5:
                # 跳进目标倾向和弦音（高八度/低八度的和弦音）
                tone = self.rng.choice(CHORD_TONES[chord])
                nxt = pitch_value(tone, self.rng.choice([-1, 0, 1]))
            return nxt
        # 归纳转移（音级层推理，八度保持）
        grade, octave = pitch_info(prev)
        counter = self.transitions.get(grade)
        if not counter:
            grade = self.rng.choice([1, 2, 3, 5, 6])
        else:
            items = list(counter.items())
            weights = [c for _, c in items]
            grade = self.rng.choices([n for n, _ in items], weights=weights)[0]
        nxt = pitch_value(grade, octave)
        # 和弦锚定（40% 落回当前和弦音）
        if self.rng.random() < 0.4 and grade not in CHORD_TONES[chord]:
            nxt = pitch_value(self.rng.choice(CHORD_TONES[chord]), octave)
        return max(-6, min(14, nxt))

    def _compensate(self, prev: int, last_step: int) -> int:
        """跳进补偿（归纳：大跳后反向级进）。"""
        if abs(last_step) >= 4:
            direction = -1 if last_step > 0 else 1
            return max(-6, min(14, prev + direction))
        return prev

    # ── 小节生成 ─────────────────────────────────────────────

    def _fill_bar(self, chord: int, motif: list[int] | None,
                  jump_rate: float) -> list[tuple[int, float]]:
        """生成一小节（音高, 时值）。节奏型从库中选，音高由推理链填充。"""
        rhythm = self.rng.choice(RHYTHMS)
        # 音高数 = 节奏型音符数（节奏算术：时值总和 = 4 拍）
        pitches: list[int] = []
        if motif:
            # 动机铺进小节（八度/音级保留，长度不足用推理补）
            pitches = [pitch_value(m, 0) for m in motif[:len(rhythm)]]
        prev = pitches[-1] if pitches else pitch_value(self.rng.choice([1, 3, 5]), 0)
        while len(pitches) < len(rhythm):
            last_step = pitches[-1] - pitches[-2] if len(pitches) > 1 else 0
            nxt = self._next_pitch(prev, chord, jump_rate)
            nxt = self._compensate(nxt, last_step)
            pitches.append(nxt)
            prev = nxt
        return list(zip(pitches, rhythm, strict=False))

    def generate(self, bars: int = 8, motif: list[int] | None = None,
                 jump_rate: float = 0.3) -> list[tuple[int, float]]:
        """A-A-B-A 结构生成：A 段（动机+半终止）/ B 段（对比+全终止）/ 回归。

        - 半终止：停在 2/5（未解决——乐句未完感）
        - 全终止：3-2-1（终止式收束）
        """
        base = motif or (self.usable_motifs[0] if self.usable_motifs else [1, 2, 3])
        # A-A-B-A 分段（bars 为 4 的倍数时每段 bars//4 小节）
        seg_len = max(1, bars // 4)
        notes: list[tuple[int, float]] = []

        for seg_idx, seg_kind in enumerate(["A1", "A2", "B", "A3"]):
            seg_motif = None
            if seg_kind == "A1":
                seg_motif = base  # 动机原样
            elif seg_kind == "A2":
                shift = self.rng.choice([-1, 1])  # 变奏
                seg_motif = [max(1, min(7, m + shift)) for m in base]
            elif seg_kind == "B":
                seg_motif = [max(1, min(7, m + 2)) for m in base]  # 对比（高移）
            # A3 回归：动机原样

            for bar_i in range(seg_len):
                chord = PROGRESSION[bar_i % len(PROGRESSION)]
                bar_notes = self._fill_bar(chord, seg_motif, jump_rate)
                # 乐句终止（每段末小节）——整小节替换保证 4 拍对齐
                is_seg_end = (bar_i == seg_len - 1)
                if is_seg_end:
                    if seg_kind in ("A1", "A2"):
                        # 半终止：动机头 + 尾音落 2 或 5（未解决），1+1+2=4 拍
                        head = (bar_notes[0][0] if bar_notes else pitch_value(1))
                        last = self.rng.choice([pitch_value(2), pitch_value(5)])
                        bar_notes = [(head, 1.0),
                                     (pitch_value(self.end_motif[1]), 1.0),
                                     (last, 2.0)]
                    else:
                        # 全终止：3-2-1 终止式整小节（1+1+2=4 拍）
                        end_m = self.end_motif
                        bar_notes = [(pitch_value(end_m[0]), 1.0),
                                     (pitch_value(end_m[1]), 1.0),
                                     (pitch_value(end_m[2]), 2.0)]
                notes.extend(bar_notes)
        return notes

    # ── 输出 ─────────────────────────────────────────────────

    def to_jianpu(self, notes: list[tuple[int, float]]) -> str:
        """音符 → 简谱（含高低八度记号：̇ 高八度，̲ 低八度）。"""
        parts: list[str] = ["1=C 90 4/4"]
        bar_beats = 0.0
        parts.append("|")
        for value, dur in notes:
            grade, octave = pitch_info(value)
            name = PITCH_NAMES[grade]
            if octave > 0:
                name = f"{name}̇"  # 高八度（上点）
            elif octave < 0:
                name = f"{name}̲"  # 低八度（下划线）
            parts.append(name)
            if dur == 2.0:
                parts.append("-")
            elif dur == 0.5:
                parts.append("_")
            elif dur == 0.25:
                parts.append("__")
            bar_beats += dur
            if abs(bar_beats - 4.0) < 0.01:
                parts.append("|")
                bar_beats = 0.0
        return " ".join(parts)


    # ── v3：12/8 密集流动生成（璃月原谱形态）─────────────────

    def generate_12_8(self, bars: int = 16, motif: list[int] | None = None,
                      jump_rate: float = 0.3) -> list[tuple[int, int, int, float]]:
        """12/8 拍生成：(音级, 升号, 八度偏移, 8分单位时值)。

        每小节 12 个 8 分单位（璃月原谱密度），节奏型从库中选，
        音高由归纳规则推理链填充，小节末终止式 3-2-1。
        """
        base = motif or (self.usable_motifs[0] if self.usable_motifs else [3, 2, 5])
        seg_len = max(1, bars // 4)
        notes: list[tuple[int, int, int, float]] = []
        bar_pos = 0  # 小节内已用单位

        for seg_idx, seg_kind in enumerate(["A1", "A2", "B", "A3"]):
            seg_motif = None
            if seg_kind == "A1":
                seg_motif = list(base)
            elif seg_kind == "A2":
                shift = self.rng.choice([-1, 1])
                seg_motif = [max(1, min(7, m + shift)) for m in base]
            elif seg_kind == "B":
                seg_motif = [max(1, min(7, m + 2)) for m in base]

            for bar_i in range(seg_len):
                is_seg_end = (bar_i == seg_len - 1)
                bar_notes: list[tuple[int, int, int, float]] = []
                if is_seg_end:
                    # 终止式小节：3-2-1（各 1 个 8 分）前补动机
                    end_m = self.end_motif
                    bar_notes = [(end_m[0], False, 1, 1.0),
                                 (end_m[1], False, 1, 1.0),
                                 (end_m[2], False, 1, 2.0)]
                    # 前面补 9 个单位（3 个音 × 3 单位节奏）
                    lead = [(m, False, 1, 1.0) for m in (seg_motif or [3, 2, 5])[:3]]
                    bar_notes = lead + bar_notes
                else:
                    # 节奏型：总和 12 个 8 分单位
                    rhythm = self.rng.choice(RHYTHMS_12_8)
                    pitches: list[int] = []
                    if seg_motif:
                        pitches = list(seg_motif)
                    prev = pitches[-1] if pitches else 3
                    while len(pitches) < len(rhythm):
                        last_step = pitches[-1] - pitches[-2] if len(pitches) > 1 else 0
                        grade = pitches[-1] if pitches else 3
                        # 归纳转移（音级层）
                        counter = self.transitions.get(grade)
                        if counter and self.rng.random() > jump_rate:
                            items = list(counter.items())
                            weights = [c for _, c in items]
                            nxt = self.rng.choices([n for n, _ in items], weights=weights)[0]
                        else:
                            nxt = max(1, min(7, grade + self.rng.choice([-3, -2, 2, 3])))
                        # 跳进补偿
                        if abs(last_step) >= 4:
                            nxt = max(1, min(7, grade - (1 if last_step > 0 else -1)))
                        pitches.append(nxt)
                    bar_notes = [(p, False, 1, d) for p, d in zip(pitches, rhythm, strict=False)]
                notes.extend(bar_notes)
        return notes

    def to_12_8_text(self, notes: list[tuple[int, int, int, float]]) -> str:
        """12/8 音符序列 → 约定格式简谱文本（jianpu_parser 可解析）。"""
        parts: list[str] = ["1=C 12/8", ""]
        bar_units = 0.0
        parts.append("|")
        for grade, sharp, octave, dur in notes:
            mark = "''" if octave == 2 else "'" if octave == 1 else "," if octave == -1 else ""
            name = f"{'#' if sharp else ''}{grade}{mark}"
            parts.append(name)
            if dur == 0.5:
                parts.append("_")
            elif dur == 2.0:
                parts.append("-")
            elif dur >= 3.0:
                parts.extend(["-"] * (int(dur) - 1))
            bar_units += dur
            if abs(bar_units - 12.0) < 0.05:
                parts.append("|")
                bar_units = 0.0
        return " ".join(parts)

    def show_rules(self) -> None:
        print("=== 规则库（归纳产物）===")
        print(f"音高转移: {len(self.transitions)} 条")
        for p in sorted(self.transitions):
            top = self.transitions[p].most_common(2)
            total = sum(self.transitions[p].values())
            print(f"  if {p} → {' '.join(f'{n}({c/total:.0%})' for n, c in top)}")
        print(f"终止式: {self.end_motif}，动机: {self.usable_motifs[:3]}")


def render(notes: list[tuple[int, float]], out_path: Path, bpm: int = 90) -> None:
    """渲染 WAV（支持八度偏移：频率 × 2^octave）。"""
    import numpy as np
    import wave

    sample_rate = 22050
    beat_s = 60.0 / bpm
    base_freq = {1: 261.63, 2: 293.66, 3: 329.63, 4: 349.23,
                 5: 392.00, 6: 440.00, 7: 493.88}
    total_beats = sum(d for _, d in notes) + 2.0
    n_samples = int(total_beats * beat_s * sample_rate)
    audio = np.zeros(n_samples)
    t_cursor = 0.0
    for value, dur in notes:
        grade, octave = pitch_info(value)
        freq = base_freq[grade] * (2 ** octave)
        start = int(t_cursor * beat_s * sample_rate)
        length = int(dur * beat_s * sample_rate)
        if start + length > n_samples:
            length = max(0, n_samples - start)
        t = np.arange(length) / sample_rate
        wave_sig = (np.sin(2 * np.pi * freq * t)
                    + 0.4 * np.sin(2 * np.pi * freq * 2 * t)
                    + 0.15 * np.sin(2 * np.pi * freq * 3 * t))
        envelope = np.exp(-t * 4.0)
        audio[start:start + length] += wave_sig * envelope * 0.3
        t_cursor += dur
    audio = audio / (np.max(np.abs(audio)) + 1e-9)
    data = (audio * 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data.tobytes())
    print(f"WAV 已渲染: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="归纳规则推理生成 v2（AABA 结构）")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--bars", type=int, default=8)
    parser.add_argument("--motif", type=str, default="", help="动机种子（如 '1 2 3'）")
    parser.add_argument("--jump", type=float, default=0.35, help="跳进率旋钮（0-1）")
    parser.add_argument("--wav", type=str, default="output/inferred_v2.wav")
    args = parser.parse_args()

    engine = LearnedRuleEngine(seed=args.seed)
    engine.show_rules()

    motif = [int(x) for x in args.motif.split()] if args.motif else None
    notes = engine.generate(bars=args.bars, motif=motif, jump_rate=args.jump)
    print(f"\n=== 推理生成 v2（{args.bars} 小节 A-A-B-A）===")
    print(f"简谱: {engine.to_jianpu(notes)}")

    out = Path(__file__).resolve().parent / args.wav
    out.parent.mkdir(parents=True, exist_ok=True)
    render(notes, out)


if __name__ == "__main__":
    main()
