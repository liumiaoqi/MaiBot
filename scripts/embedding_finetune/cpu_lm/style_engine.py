"""角色风格引擎：词库 + n-gram 统计表 + 句式模板（无神经网络）。

方向（lmq 2026-08-05，8 个神经网络实验全部失败的收敛结论）：
- next-token 生成在 <1M 参数 × 30 万字符上必然复读/黑洞
- 规则引擎不"学"——把语料统计直接存成查表，把句式直接写成模板
- 契合"本地+API 混合架构"：API 决定说什么（意图/起始词），本地决定怎么按角色说

组成：
1. 词库：角色手动词（vocab/role_{角色}.txt，可手动编辑）
2. n-gram 表：2-gram + 3-gram 频次（从语料直接数，零训练）
3. 生成：seed → 3-gram 优先 → 2-gram 回退 → 词库兜底 → 句号/叹号/省略号收尾

用法：
  uv run python style_engine.py --build --character 希儿          # 建词库 + n-gram
  uv run python style_engine.py --generate --seed 布洛妮娅 --len 15
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from bpe_tokenizer import _WORD_PATTERN
from prepare_corpus import OUTPUT_DIR as CORPUS_DIR

VOCAB_DIR = Path(__file__).resolve().parent / "vocab"
ENGINE_DIR = Path(__file__).resolve().parent / "engines"

# 句尾标点（句子结束信号）
_END_PUNCT = "。！？…~！？．"
# 纯标点 token（生成时不能当候选词，只能句尾）
_PUNCT_ONLY = re.compile(r"^[^\w一-鿿]+$")

TEMPLATES = [
    # 模板（第二版扩展）：{word} 填词库词
    ("布洛妮娅", "布洛妮娅姐姐，{action}。"),
    ("姐姐", "姐姐，{action}。"),
]


def clean_text(text: str) -> str:
    """清洗：去舞台指示（笑）、引号包裹、markdown 引用符。"""
    text = re.sub(r"[（(][^）)]{1,8}[）)]", "", text)   # （笑）（叹气）等
    text = re.sub(r'["""「」『』]', "", text)           # 引号包裹
    text = re.sub(r"(?m)^>\s*", "", text)              # 引用行
    return text


def corpus_sources(character: str) -> list[Path]:
    """台词语料优先，设定文档补充（台词结构更接近角色风格）。"""
    dialogue = CORPUS_DIR / f"corpus_dialogue_{character}.txt"
    setting = CORPUS_DIR / f"corpus_{character}.txt"
    sources = []
    if dialogue.exists():
        sources.append(dialogue)
    if setting.exists():
        sources.append(setting)
    return sources


def build_vocab(character: str, text: str, top_n: int = 300) -> list[str]:
    """角色词库：台词高频词 + 手动词元（custom_tokens.txt）合并，可手动编辑。"""
    words = _WORD_PATTERN.findall(text)
    freq = Counter(words)
    # 词库排除纯标点
    top = [w for w, _ in freq.most_common(top_n * 2) if not re.fullmatch(r"[^\w一-鿿]", w)]
    top = top[:top_n]
    custom = []
    custom_path = VOCAB_DIR / "custom_tokens.txt"
    if custom_path.exists():
        custom = [line.strip() for line in custom_path.read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.strip().startswith("#")]
    vocab = list(dict.fromkeys([*custom, *top]))[:top_n]
    return vocab


def build(character: str) -> None:
    """构建词库 + n-gram 表，存到 engines/。"""
    sources = corpus_sources(character)
    if not sources:
        raise SystemExit(f"找不到语料: {sources}")
    raw_original = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    # 台词提取必须在清洗（删引号）之前
    dialogue_words = _WORD_PATTERN.findall(
        "".join(re.findall(r'"([^"]{2,60})"', raw_original)))
    raw = clean_text(raw_original)

    # 台词加权：引号内台词 ×3（角色风格的主信号），叙述 ×1（词频补充）
    all_words = _WORD_PATTERN.findall(raw)
    words = all_words + dialogue_words * 2  # 台词本身已含在 all_words，再加 2 份
    print(f"[引擎] 语料: {' + '.join(p.name for p in sources)} → {len(raw):,} 字符 / "
          f"{len(all_words):,} 词（台词 {len(dialogue_words):,} 词 ×3 加权）")

    # 词库
    vocab = build_vocab(character, raw)
    VOCAB_DIR.mkdir(parents=True, exist_ok=True)
    role_vocab_path = VOCAB_DIR / f"role_{character}.txt"
    role_vocab_path.write_text(
        f"# {character} 角色词库（style_engine 用，可手动编辑增删词）\n" + "\n".join(vocab),
        encoding="utf-8")
    print(f"[引擎] 词库: {len(vocab)} 词 → {role_vocab_path}")

    # n-gram 统计 → 条件分布（前文 → Counter(候选词)）
    bigram: Counter = Counter(zip(words, words[1:], strict=False))
    trigram: Counter = Counter(
        (words[i], words[i + 1], words[i + 2]) for i in range(len(words) - 2)
    )
    # 2-gram 条件分布：w1 → {w2: count}
    b2: dict[str, dict[str, int]] = {}
    for (a, b), c in bigram.items():
        if c >= 2:  # 低频对没统计意义
            b2.setdefault(a, {})[b] = c
    # 3-gram 条件分布：(w1, w2) → {w3: count}
    t3: dict[tuple[str, str], dict[str, int]] = {}
    for (a, b, c), n in trigram.items():
        if n >= 2:
            t3.setdefault((a, b), {})[c] = n

    ENGINE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "character": character,
        "bigram": {a: b for a, b in b2.items()},
        "trigram": {f"{a}{b}": c for (a, b), c in t3.items()},
        "high_freq": [w for w, _ in Counter(words).most_common(50)],
    }
    out = ENGINE_DIR / f"style_{character}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"[引擎] n-gram: 2-gram {len(b2):,} 条件 / 3-gram {len(t3):,} 条件 → {out}")


class StyleEngine:
    """加载构建产物，按角色风格生成。"""

    def __init__(self, character: str) -> None:
        self.character = character
        path = ENGINE_DIR / f"style_{character}.json"
        if not path.exists():
            raise SystemExit(f"引擎未构建，先跑 --build: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.bigram: dict[str, dict[str, int]] = payload["bigram"]
        self.trigram: dict[tuple[str, str], dict[str, int]] = {
            tuple(k.split("")): v for k, v in payload["trigram"].items()
        }
        self.high_freq: list[str] = payload["high_freq"]

    def _pick(self, candidates: dict[str, int], temperature: float, rng: random.Random) -> str:
        if temperature <= 0:
            return max(candidates, key=candidates.get)
        items = list(candidates.items())
        weights = [c ** (1 / temperature) for _, c in items]
        return rng.choices([w for w, _ in items], weights=weights)[0]

    def generate(self, seed: str, length: int = 12, temperature: float = 0.0) -> str:
        """seed → 查表游走 → 句尾收束。

        temperature=0 取最高频（确定性），>0 按频率加权采样。
        """
        rng = random.Random()
        words = _WORD_PATTERN.findall(seed) or [seed]
        out = list(words)
        while len(out) < length:
            # 候选：3-gram（两词历史）→ 2-gram（一词历史）→ 高频词兜底
            hist2 = (out[-2], out[-1]) if len(out) >= 2 else None
            candidates = self.trigram.get(hist2) if hist2 else None
            if not candidates:
                candidates = self.bigram.get(out[-1])
            if not candidates:
                out.append(self.high_freq[rng.randrange(min(len(self.high_freq), 10))])
                continue
            # 过滤纯标点候选（只能句尾出现，不能当正文词）
            candidates = {w: c for w, c in candidates.items()
                          if not _PUNCT_ONLY.match(w) or w[-1] in _END_PUNCT}
            if not candidates:
                out.append(self.high_freq[rng.randrange(min(len(self.high_freq), 10))])
                continue
            nxt = self._pick(candidates, temperature, rng)
            out.append(nxt)
            # 句尾收束
            if nxt and nxt[-1] in _END_PUNCT and len(out) >= 4:
                break
        return "".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="角色风格引擎（n-gram + 词库，无神经网络）")
    parser.add_argument("--build", action="store_true", help="构建词库 + n-gram 表")
    parser.add_argument("--character", type=str, default="希儿")
    parser.add_argument("--generate", action="store_true", help="生成角色风格句子")
    parser.add_argument("--seed", type=str, default="布洛妮娅", help="起始词（模拟 API 转译的意图）")
    parser.add_argument("--len", type=int, default=12, help="最大词数")
    parser.add_argument("--temp", type=float, default=0.0, help="0=确定性最高频，>0 加权采样")
    args = parser.parse_args()

    if args.build:
        build(args.character)
    elif args.generate:
        engine = StyleEngine(args.character)
        print(engine.generate(args.seed, args.len, args.temp))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
