"""简谱解析器 — 按符号约定解析手动修改的乐谱（liyue_jianpu.txt 等）。

约定（全键盘可输入）：
- 1-7 音高（12/8 拍下 = 1 个 8 分音符基本单位）
- 1' 高八度 / 1'' 高两个八度 / 1, 低八度
- 1_ 时值减半（16 分）；1__ 时值再减半（32 分）
- . 或 · 附点（×1.5）；- 延长一拍（+1 基本单位，可多个）
- #4 升号（升高半音）
- ( ... ) 弧线（tie 同音合并时值 / slur 连奏标记，v1 忽略）
- 0 休止（时值同音符规则）
- ^ / tr 装饰音（时值不延长，v1 忽略）
- | || 小节线；1=E 转调（v1 支持：解析后音级不变，渲染按调内）
- 空格/换行/注释行/小节编号 (n) 忽略

用法：
  uv run python jianpu_parser.py --file output/liyue_jianpu.txt --section part1
  uv run python jianpu_parser.py --file output/liyue_jianpu.txt --section part1 --wav output/liyue_part1.wav
"""

import argparse
import re
from pathlib import Path

import numpy as np

# 12/8 拍：♩=336，以 8 分音符为一拍记 → 8 分音符 = 336/分
# （之前按四分 336 渲染快了一倍——用户反馈"节奏非常快"修正）
EIGHTH_BPM = 336
EIGHTH_S = 60.0 / EIGHTH_BPM

# 简谱 1=C，中音区 1 = C4
BASE_FREQ = {1: 261.63, 2: 293.66, 3: 329.63, 4: 349.23,
             5: 392.00, 6: 440.00, 7: 493.88}
SHARP_RATIO = 2 ** (1 / 12)  # 升半音


def parse_notes(text: str) -> list[tuple[int, bool, int, float]]:
    """解析简谱文本 → (音级, 升号, 八度偏移, 8 分单位时值) 序列。

    八度偏移：'' = +2，' = +1，无 = 0（中音区），, = -1。
    音级 0 = 休止。弧线 v1 忽略（tie 时值合并后续版本）。
    """
    notes: list[tuple[int, bool, int, float]] = []
    # token 正则：可选 # 前缀 + 数字/0 + 可选八度标记 + 可选下划线 + 可选附点 + 可选延长
    token_re = re.compile(
        r"(#)?([1-7]|0)((?:'''|''|'|,)?)(_+)?(\.|·)?(-+)?")
    for match in token_re.finditer(text):
        sharp, digit, octave_mark, half, dot, extend = match.groups()
        grade = int(digit)
        octave = 0
        if octave_mark == "'''":
            octave = 3
        elif octave_mark == "''":
            octave = 2
        elif octave_mark == "'":
            octave = 1
        elif octave_mark == ",":
            octave = -1
        dur = 1.0
        if half:
            dur *= 0.5 ** len(half)
        if dot:
            dur *= 1.5
        if extend:
            dur += len(extend)
        notes.append((grade, bool(sharp), octave, dur))
    return notes


def pitch_freq(grade: int, sharp: bool, octave: int) -> float:
    """音级 + 升号 + 八度偏移 → 频率（Hz）。"""
    if grade == 0:
        return 0.0
    freq = BASE_FREQ[grade] * (2 ** octave)
    if sharp:
        freq *= SHARP_RATIO
    return freq


def render(notes: list[tuple[int, bool, int, float]], out_path: Path,
           octave_shift: int = 0) -> None:
    """渲染 WAV（钢琴音色：正弦+谐波+指数包络）。"""
    sample_rate = 22050
    total_dur = sum(d for _, _, _, d in notes) * EIGHTH_S + 1.0
    n_samples = int(total_dur * sample_rate)
    audio = np.zeros(n_samples)
    t_cursor = 0.0
    t_units = 0.0  # 小节内累积 8 分单位（力度动态用）
    for grade, sharp, octave, dur in notes:
        freq = pitch_freq(grade, sharp, octave + octave_shift)
        length = int(dur * EIGHTH_S * sample_rate)
        start = int(t_cursor * sample_rate)
        if freq <= 0:  # 休止
            t_cursor += dur * EIGHTH_S
            t_units += dur
            continue
        # 小节边界呼吸：每 12 个 8 分（1 小节）起点前加 1/4 拍停顿（乐句感）
        if 0 < (t_units % 12.0) < 0.05:
            start += int(0.5 * EIGHTH_S * sample_rate)
        # 力度动态（用户反馈"音量缺少起伏"）：
        # 1. 节拍重音：12/8 每组三连音第一拍（每 3 个 8 分）强
        strong_beat = (t_units % 3.0) < 0.05 or (t_units % 3.0) > 2.95
        dyn = 1.25 if strong_beat else 0.85
        # 2. 音高加权：高音稍强、低音稍弱
        pitch_amp = 0.85 + 0.12 * (grade / 7.0) + 0.1 * (octave + octave_shift)
        amp = 0.12 * dyn * pitch_amp
        if start + length > n_samples:
            length = max(0, n_samples - start)
        # 每音短 22%：音符间留明显呼吸间隙（用户反馈"急促没停顿"）
        length = int(length * 0.78)
        t = np.arange(length) / sample_rate
        # 柔和音色：弱谐波 + 中速衰减（收尾快=音符分明）
        wave = (np.sin(2 * np.pi * freq * t)
                + 0.2 * np.sin(2 * np.pi * freq * 2 * t)
                + 0.06 * np.sin(2 * np.pi * freq * 3 * t))
        envelope = np.exp(-t * 3.0)
        audio[start:start + length] += wave * envelope * amp
        t_cursor += dur * EIGHTH_S
        t_units += dur
    peak = np.max(np.abs(audio)) + 1e-9
    audio = audio / peak * 0.5  # 半幅：整体音量明显降低
    data = (audio * 32767).astype(np.int16)
    import wave

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data.tobytes())
    print(f"WAV 已渲染: {out_path}")


def extract_section(text: str, section: str) -> str:
    """提取指定章节的代码块内容（part1/part2/part3）。"""
    headers = {"part1": "第 1-41 小节", "part2": "第 45-85 小节", "part3": "第 89-125 小节"}
    for h in headers.values():
        pass
    lines = text.split("\n")
    out: list[str] = []
    in_block = False
    capture = False
    for line in lines:
        if line.strip().startswith("```"):
            if capture:  # 块结束
                break
            in_block = not in_block
            continue
        if in_block and section == "part1" and "1=C 12/8" in line:
            capture = True
        if capture and in_block:
            # 跳过元信息行（调号/拍号/速度/转调）与空行
            stripped = line.strip()
            if stripped and "=" not in stripped and not re.match(r"^[0-9=♩/ ]+$", stripped):
                out.append(line)
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="简谱解析渲染")
    parser.add_argument("--file", type=str, default="output/liyue_jianpu.txt")
    parser.add_argument("--section", type=str, default="part1", choices=["part1", "part2", "part3"])
    parser.add_argument("--wav", type=str, default="")
    parser.add_argument("--bpm", type=int, default=EIGHTH_BPM, help="8 分音符速度（默认 336）")
    parser.add_argument("--octave-shift", type=int, default=0,
                        help="整体八度偏移（负=降八度，如 -1 试听音区）")

    args = parser.parse_args()

    path = Path(__file__).resolve().parent / args.file
    text = path.read_text(encoding="utf-8")
    section_text = extract_section(text, args.section)
    if not section_text.strip():
        raise SystemExit(f"未找到章节 {args.section}")

    global EIGHTH_S
    EIGHTH_S = 60.0 / args.bpm
    notes = parse_notes(section_text)
    total_units = sum(n[3] for n in notes)
    print(f"解析音符: {len(notes)} 个，总时长 {total_units:.1f} 个 8 分"
          f"（{total_units * EIGHTH_S:.1f}s @ 8分={args.bpm}/分）")
    # 预览前 40 个（含八度/升号标记）
    def fmt(n):
        g, sharp, octv, d = n
        if g == 0:
            return f"0{'_' if d < 1 else ''}"
        mark = {3: "'''", 2: "''", 1: "'", -1: ","}.get(octv, "")
        return f"{'#' if sharp else ''}{g}{mark}{'_' if d < 1 else ''}"
    preview = " ".join(fmt(n) for n in notes[:40])
    print(f"预览: {preview}")

    if args.wav:
        render(notes, Path(__file__).resolve().parent / args.wav,
               octave_shift=args.octave_shift)


if __name__ == "__main__":
    main()
