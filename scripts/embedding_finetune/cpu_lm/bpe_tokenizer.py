"""mini BPE tokenizer（支持手动自定义词元）。

流程：
1. 自定义词元（vocab/custom_tokens.txt，每行一个——用户手动划分的角色词）
2. 字符集（语料中全部字符）
3. BPE 合并：词内统计相邻 token 对频率，反复合并最高频对
   （中文按连续串切词——词内 BPE，标准做法）

自定义词元优先（最长匹配）——"希儿"等角色词不会被 BPE 拆散。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

VOCAB_DIR = Path(__file__).resolve().parent / "vocab"
CUSTOM_TOKENS_PATH = VOCAB_DIR / "custom_tokens.txt"

# 切词正则：中文连续串 / 英文单词 / 数字 / 单个标点
_WORD_PATTERN = re.compile(r"[一-鿿]+|[A-Za-z]+|\d+|[^\sA-Za-z0-9一-鿿]")


class BPETokenizer:
    """字符 BPE tokenizer：自定义词元优先 + 词内字节对合并。"""

    def __init__(self, corpus: str, custom_tokens: List[str] | None = None,
                 target_vocab: int = 4000) -> None:
        self.custom_tokens = [t for t in (custom_tokens or []) if t]
        # 初始 vocab：自定义词元 + 字符集
        chars = sorted(set(corpus))
        self.vocab: List[str] = [*self.custom_tokens, *chars]
        self.stoi: Dict[str, int] = {t: i for i, t in enumerate(self.vocab)}
        self.merges: List[Tuple[str, str]] = []
        self._train_merges(corpus, target_vocab)

    # ── BPE 训练 ─────────────────────────────────────────────

    def _train_merges(self, corpus: str, target_vocab: int) -> None:
        """反复合并词内最高频相邻对，直到 vocab 达到目标（增量更新）。

        优化（v2）：词预切分成 token 序列（不重复切分），
        对频率用 Counter 增量维护——每次合并只更新受影响词的贡献，
        不全量重建（v1 全量扫描 + replace 是慢的根源）。
        """
        from collections import Counter

        words = _WORD_PATTERN.findall(corpus)
        freq_map: Dict[str, int] = {}
        for word in words:
            freq_map[word] = freq_map.get(word, 0) + 1
        # 词 → (token 序列, 频次)——预切分一次
        word_list: List[Tuple[List[str], int]] = [
            (self._split_word(word), freq) for word, freq in freq_map.items()
        ]

        pair_counter: Counter = Counter()
        for tokens, freq in word_list:
            for pair in zip(tokens, tokens[1:], strict=False):
                pair_counter[pair] += freq

        while len(self.vocab) < target_vocab and pair_counter:
            (a, b), count = pair_counter.most_common(1)[0]
            if count < 2:  # 低频对不再合并
                break
            merged = a + b
            self.merges.append((a, b))
            self.vocab.append(merged)
            self.stoi[merged] = len(self.vocab) - 1

            # 增量更新：只处理包含 (a,b) 的词
            for i, (tokens, freq) in enumerate(word_list):
                # 一次性替换该词内全部 (a,b) 相邻对
                new_tokens: List[str] = []
                j = 0
                changed = False
                while j < len(tokens):
                    if j + 1 < len(tokens) and tokens[j] == a and tokens[j + 1] == b:
                        new_tokens.append(merged)
                        j += 2
                        changed = True
                    else:
                        new_tokens.append(tokens[j])
                        j += 1
                if changed:
                    # 旧对贡献全减，新对贡献全加
                    for pair in zip(tokens, tokens[1:], strict=False):
                        pair_counter[pair] -= freq
                    for pair in zip(new_tokens, new_tokens[1:], strict=False):
                        pair_counter[pair] += freq
                    word_list[i] = (new_tokens, freq)

            # 清理零/负计数
            pair_counter = Counter(
                {k: v for k, v in pair_counter.items() if v > 0}
            )

    def _split_word(self, word: str) -> List[str]:
        """把词切成 token 序列（先自定义词元最长匹配，再字符）。"""
        tokens: List[str] = []
        i = 0
        while i < len(word):
            matched = None
            for custom in sorted(self.custom_tokens, key=len, reverse=True):
                if word.startswith(custom, i):
                    matched = custom
                    break
            if matched:
                tokens.append(matched)
                i += len(matched)
            else:
                tokens.append(word[i])
                i += 1
        return tokens

    def _bpe_split(self, word: str) -> List[str]:
        """应用 merges 把词切分成 BPE token（encode 用）。"""
        symbols = self._split_word(word)
        while len(symbols) > 1:
            pair_idx = None
            for idx in range(len(symbols) - 1):
                if (symbols[idx], symbols[idx + 1]) in self.merges:
                    pair_idx = idx
                    break
            if pair_idx is None:
                break
            symbols = (symbols[:pair_idx]
                       + [symbols[pair_idx] + symbols[pair_idx + 1]]
                       + symbols[pair_idx + 2:])
        return symbols

    # ── 编码/解码 ────────────────────────────────────────────

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    def encode(self, text: str) -> List[int]:
        """文本 → id 序列（自定义词元优先 + BPE）。"""
        ids: List[int] = []
        for word in _WORD_PATTERN.findall(text):
            for token in self._bpe_split(word):
                tid = self.stoi.get(token)
                if tid is None:
                    # 未知 token：按字符拆
                    for ch in token:
                        tid = self.stoi.get(ch)
                        if tid is not None:
                            ids.append(tid)
                    continue
                ids.append(tid)
        return ids

    def restrict(self, keep_tokens: List[str], fallback_chars: bool = True) -> None:
        """受限词库化：只保留 keep_tokens 内的词元 + <unk>（id 0），
        encode_restricted 时词库外的 token 映射 <unk>。

        fallback_chars=True 时额外保留语料全部单字符（字符回退）——
        OOV 词拆成字符后每个字符都在库内，覆盖率 100%，无 <unk> 黑洞。
        <unk> 仍保留作绝对兜底（非汉字/罕见字符）。
        """
        kept = [t for t in keep_tokens if t in self.stoi]
        if fallback_chars:
            # 全部单字符补进词库（覆盖长尾：低频词 → 单字拼，无 <unk> 黑洞）
            chars = sorted(t for t in self.vocab if len(t) == 1)
            kept = list(dict.fromkeys([*kept, *chars]))
        self.vocab = ["<unk>", *kept]
        self.stoi = {t: i for i, t in enumerate(self.vocab)}
        self.merges = []  # 受限模式不再做 BPE 合并（词库已定）

    def encode_restricted(self, text: str) -> List[int]:
        """受限编码：词库内 token 保留，词库外拆成单字符（字符在库内），
        字符也不在则 <unk>（id 0）。"""
        ids: List[int] = []
        for word in _WORD_PATTERN.findall(text):
            for token in self._split_word(word):
                tid = self.stoi.get(token)
                if tid is not None:
                    ids.append(tid)
                    continue
                # 字符回退：token 拆成单字符逐个查库
                for ch in token:
                    cid = self.stoi.get(ch)
                    ids.append(cid if cid is not None else 0)
        return ids

    def decode(self, ids: List[int]) -> str:
        """id 序列 → 文本。"""
        return "".join(self.vocab[idx] if idx < len(self.vocab) else "" for idx in ids)

    def save(self, path: Path) -> None:
        """保存 tokenizer 状态（vocab + merges + 自定义词元）。"""
        payload = {
            "vocab": self.vocab,
            "merges": [list(m) for m in self.merges],
            "custom_tokens": self.custom_tokens,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "BPETokenizer":
        """从保存状态重建（无需 corpus）。"""
        payload = json.loads(path.read_text(encoding="utf-8"))
        tok = cls.__new__(cls)
        tok.vocab = payload["vocab"]
        tok.merges = [tuple(m) for m in payload["merges"]]
        tok.custom_tokens = payload["custom_tokens"]
        tok.stoi = {t: i for i, t in enumerate(tok.vocab)}
        return tok


def load_custom_tokens() -> List[str]:
    """读取手动词元文件（每行一个，忽略空行和 # 注释）。"""
    if not CUSTOM_TOKENS_PATH.exists():
        VOCAB_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_TOKENS_PATH.write_text(
            "# 手动词元：每行一个（角色名/专有名词），优先匹配不被 BPE 拆散\n"
            "# 示例：\n# 希儿\n# 星穹列车\n",
            encoding="utf-8",
        )
        return []
    tokens = []
    for line in CUSTOM_TOKENS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tokens.append(line)
    return tokens
