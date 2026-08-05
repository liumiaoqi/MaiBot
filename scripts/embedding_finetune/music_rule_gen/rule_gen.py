"""音乐规则生成器 — 简谱数值创作（无数据、无神经网络）。

设计（lmq 2026-08-06，用户认知）：
- 音乐是数值结构不是统计结构：音高 = 数值（音程 = 差），时值 = 分数（比例 = 算术）
- "能直接计算为什么要通过概率计算"——简谱不该 token 化，该直接算
- 规则即风格：风格统一性来自生成规则（同套规则 = 同风格），不来自数据
- 每个参数是旋钮：调式/走向/动机/音程跳跃/节奏密度——拧参数直接改变旋律性格

生成流程（纯计算，无模型）：
  调式(音阶数值集合) + 和弦走向(每小节和弦) + 动机种子(2-4 音符)
  → 逐小节：小节首尾锚定和弦音，中间音阶内数值游走（音程约束）
  → 节奏：时值组合填满小节（算术）
  → 动机发展：重复 → 变奏 → 对比
  → 输出：简谱文本 + numpy 渲染 WAV

用法：
  uv run python rule_gen.py                          # 默认曲
  uv run python rule_gen.py --scale major --chords I-V-vi-IV --seed 42
  uv run python rule_gen.py --motif "3 5 6 5"        # 用户给动机种子
"""

import argparse
import random
from pathlib import Path

import numpy as np

# ── 调式：音阶 = 音级数字集合（简谱 1-7，1 为主音）─────────────────
# 注意：minor 与 major 音阶数字相同，区别在特征音权重（旋律色彩）

SCALES = {
    "major": [1, 2, 3, 4, 5, 6, 7],        # 自然大调
    "minor": [1, 2, 3, 4, 5, 6, 7],        # 自然小调
    "pentatonic": [1, 2, 3, 5, 6],         # 五声音阶（4/7 禁用）
    "minor_penta": [1, 3, 4, 5, 7],        # 小调五声（2/6 禁用）
}

# 特征音权重（游走时倾向）：大调明亮（1/4/5 主音功能），小调忧郁（3/6/7）
SCALE_FLAVOR = {
    "major": [1, 4, 5],
    "minor": [3, 6, 7],
    "pentatonic": [1, 2, 3, 5, 6],
    "minor_penta": [1, 3, 4, 5, 7],
}

# ── 和弦走向模板：每小节一个和弦（音级数字）───────────────────────

CHORD_PROGRESSIONS = {
    "I-V-vi-IV": [1, 5, 6, 4],             # 流行经典
    "I-vi-IV-V": [1, 6, 4, 5],             # 50s 进行
    "ii-V-I": [2, 5, 1],                   # 爵士基本
    "I-IV-V": [1, 4, 5],                   # 蓝调基础
    "I-V-vi-iii-IV": [1, 5, 6, 3, 4],      # 五和弦流行
}

# 和弦 = 音阶内三度堆叠（简谱音级）：1 → 1-3-5（大三和弦）
CHORD_TONES = {1: [1, 3, 5], 2: [2, 4, 6], 3: [3, 5, 7], 4: [4, 6, 1],
               5: [5, 7, 2], 6: [6, 1, 3], 7: [7, 2, 4]}

# 时值（以四分音符 = 1 拍）
DURATIONS = [0.25, 0.5, 0.5, 1.0, 1.0, 2.0]


class RuleGen:
    """简谱规则生成器：调式 + 和弦 + 数值游走 + 节奏算术 + 动机发展。"""

    def __init__(self, scale: str = "major", progression: str = "I-V-vi-IV",
                 bpm: int = 100, seed: int | None = None) -> None:
        self.scale_name = scale
        self.scale = SCALES[scale]
        self.progression = CHORD_PROGRESSIONS[progression]
        self.progression_name = progression
        self.bpm = bpm
        self.rng = random.Random(seed)

    # ── 旋律生成（数值游走）─────────────────────────────────────

    def _pick_chord_tone(self, chord: int) -> int:
        """和弦音（锚点）：和弦音级 + 八度归一。"""
        tones = CHORD_TONES[chord]
        return self.rng.choice(tones)

    def _walk(self, prev: int, chord: int, max_step: int = 3) -> int:
        """音阶内数值游走：步长 ≤ max_step，约束在调式音阶内（旋钮生效）。"""
        candidates = [d for d in range(-max_step, max_step + 1) if d != 0]
        step = self.rng.choice(candidates)
        nxt = prev + step
        # 归一回到 1-7 循环域
        while nxt < 1:
            nxt += 7
        while nxt > 7:
            nxt -= 7
        # 调式约束：五声音阶禁用 4/7（拉回最近音阶音）
        if nxt not in self.scale:
            nxt = min(self.scale, key=lambda s: abs(s - nxt))
        # 特征音倾向（大调主音功能 / 小调忧郁色彩）
        if self.rng.random() < 0.3 and nxt not in SCALE_FLAVOR[self.scale_name]:
            nxt = self.rng.choice(SCALE_FLAVOR[self.scale_name])
        # 和声骨架：50% 概率落回当前和弦音
        if nxt not in CHORD_TONES[chord] and self.rng.random() < 0.5:
            return self._pick_chord_tone(chord)
        return nxt

    def _fill_measures(self, beats_per_bar: int = 4) -> list[tuple[int, float]]:
        """逐小节生成：首尾锚定和弦音，中间数值游走；节奏算术填满小节。"""
        notes: list[tuple[int, float]] = []
        for bar_idx, chord in enumerate(self.progression):
            bar: list[tuple[int, float]] = []
            bar_duration = 0.0
            first_note = self._pick_chord_tone(chord)
            bar.append((first_note, 0.0))
            prev = first_note
            # 动机种子（第一小节即用）或动机发展（后续小节）
            motif = self._motif_for_bar(bar_idx, first_note)
            if motif and bar_idx == 0:
                # 用户动机种子：直接铺进第一小节
                bar = []
                for i, m in enumerate(motif):
                    if bar_duration >= beats_per_bar - 1.0:
                        break
                    dur = self.rng.choice([0.5, 1.0])
                    bar.append((m, dur))
                    bar_duration += dur
                    prev = m
            while bar_duration < beats_per_bar - 1.0:
                dur = self.rng.choice(DURATIONS)
                if bar_duration + dur > beats_per_bar - 1.0:
                    break
                if motif and len(bar) < len(motif) + 1:
                    note = motif[len(bar) - 1]
                else:
                    note = self._walk(prev, chord)
                bar.append((note, dur))
                bar_duration += dur
                prev = note
            # 小节末锚定回和弦音
            last = self._pick_chord_tone(chord)
            remaining = beats_per_bar - bar_duration
            bar.append((last, max(remaining, 0.5)))
            notes.extend(bar)
        return notes

    # ── 动机发展：重复 → 变奏 → 对比 ───────────────────────────

    def _motif_for_bar(self, bar_idx: int, first_note: int) -> list[int] | None:
        # 用户给动机种子：第一小节用动机，后续重复/变奏/对比
        if not hasattr(self, "_base_motif"):
            return None  # 无动机：第一小节自由
        base = self._base_motif
        if bar_idx == 0:
            return base  # 动机种子铺第一小节
        if bar_idx % 3 == 1:
            return base  # 重复
        if bar_idx % 3 == 2:
            # 变奏：音程缩放（±1 或 ±2 度）
            shift = self.rng.choice([-2, -1, 1, 2])
            return [max(1, min(7, n + shift)) for n in base]
        return None  # 对比（自由）

    # ── 输出 ────────────────────────────────────────────────────

    def generate(self, motif: str = "", bars: int | None = None) -> list[tuple[int, float]]:
        """生成旋律（音符, 时值）序列。"""
        if motif:
            self._base_motif = [int(x) for x in motif.split() if x.isdigit()]
        if bars is None:
            bars = len(self.progression)
        # 重复走向填满小节数
        prog = [self.progression[i % len(self.progression)] for i in range(bars)]
        self.progression = prog
        return self._fill_measures()

    def to_jianpu(self, notes: list[tuple[int, float]]) -> str:
        """音符序列 → 简谱文本（固定 4/4 拍号）。"""
        parts: list[str] = []
        bar_count = 0.0
        parts.append(f"1=C {self.bpm} 4/4")
        parts.append("|")
        for note, dur in notes:
            if note == 0:
                parts.append("0")
            else:
                parts.append(str(note))
            # 时值 → 简谱标记：1 拍裸数字，2 拍加 -, 0.5 拍下划线
            if dur == 2.0:
                parts.append("-")
            elif dur == 0.5:
                parts.append("_")
            elif dur == 0.25:
                parts.append("__")
            bar_count += dur
            if abs(bar_count - 4.0) < 0.01:
                parts.append("|")
                bar_count = 0.0
        return " ".join(parts)

    # ── 渲染（numpy 钢琴音色，复用 lab 思路）────────────────────

    def render_wav(self, notes: list[tuple[int, float]], out_path: Path,
                   sample_rate: int = 22050) -> None:
        """渲染为 WAV：正弦 + 谐波 + 指数包络（钢琴感）。"""
        beat_s = 60.0 / self.bpm
        # 简谱 1 = C4（261.63Hz），音级 → 频率
        freq_table = {1: 261.63, 2: 293.66, 3: 329.63, 4: 349.23,
                      5: 392.00, 6: 440.00, 7: 493.88}
        total_beats = sum(d for _, d in notes) + 2.0
        n_samples = int(total_beats * beat_s * sample_rate)
        audio = np.zeros(n_samples)
        t_cursor = 0.0
        for note, dur in notes:
            if note == 0:
                t_cursor += dur
                continue
            freq = freq_table.get(note, 261.63)
            start = int(t_cursor * beat_s * sample_rate)
            length = int(dur * beat_s * sample_rate)
            if start + length > n_samples:
                length = max(0, n_samples - start)
            t = np.arange(length) / sample_rate
            # 基波 + 二次/三次谐波 + 指数衰减包络
            wave = (np.sin(2 * np.pi * freq * t)
                    + 0.4 * np.sin(2 * np.pi * freq * 2 * t)
                    + 0.15 * np.sin(2 * np.pi * freq * 3 * t))
            envelope = np.exp(-t * 4.0)
            audio[start:start + length] += wave * envelope * 0.3
            t_cursor += dur
        # 归一化 + 写 WAV
        audio = audio / (np.max(np.abs(audio)) + 1e-9)
        data = (audio * 32767).astype(np.int16)
        import wave

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(data.tobytes())
        print(f"WAV 已渲染: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="简谱规则生成器（数值创作，无模型）")
    parser.add_argument("--scale", type=str, default="major",
                        choices=list(SCALES), help="调式旋钮")
    parser.add_argument("--chords", type=str, default="I-V-vi-IV",
                        choices=list(CHORD_PROGRESSIONS), help="和弦走向旋钮")
    parser.add_argument("--bpm", type=int, default=100, help="速度旋钮")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--motif", type=str, default="", help="动机种子（如 '3 5 6 5'）")
    parser.add_argument("--bars", type=int, default=None, help="小节数")
    parser.add_argument("--wav", type=str, default="output/melody.wav", help="WAV 输出路径")
    args = parser.parse_args()

    gen = RuleGen(scale=args.scale, progression=args.chords,
                  bpm=args.bpm, seed=args.seed)
    notes = gen.generate(motif=args.motif, bars=args.bars)
    jianpu = gen.to_jianpu(notes)
    print(f"[{gen.scale_name} | {gen.progression_name} | {gen.bpm}bpm]")
    print(f"  简谱: {jianpu}")
    out = Path(__file__).resolve().parent / args.wav
    out.parent.mkdir(parents=True, exist_ok=True)
    gen.render_wav(notes, out)
    print(f"  音符数: {len(notes)}")


if __name__ == "__main__":
    main()
