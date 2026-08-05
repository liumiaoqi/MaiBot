"""受限词库分析：希儿语料的 token 频率分布与覆盖度 + 词库文件生成。

受限词库实验（R 实验）的前提分析：
- 角色语料高频 token 有哪些（top-N 长什么样）
- N 个词能覆盖语料多少比例（覆盖度曲线）
- 生成词库文件 vocab/restricted_希儿.txt（--write 时）供 mini_swa --restrict 使用

用法：
  uv run python analyze_vocab.py                # 只分析
  uv run python analyze_vocab.py --write 400    # 分析 + 写 top-400 词库文件
"""

import argparse
from collections import Counter
from pathlib import Path

from bpe_tokenizer import BPETokenizer, load_custom_tokens
from prepare_corpus import OUTPUT_DIR as CORPUS_DIR

CORPUS = CORPUS_DIR / "corpus_希儿.txt"
VOCAB_DIR = Path(__file__).resolve().parent / "vocab"


def main(top_n: int | None = None, dialogue: bool = False) -> None:
    corpus_path = CORPUS_DIR / "corpus_dialogue.txt" if dialogue else CORPUS
    corpus = corpus_path.read_text(encoding="utf-8")
    tokenizer = BPETokenizer(corpus, load_custom_tokens(), target_vocab=4000)
    ids = tokenizer.encode(corpus)
    n_tokens = len(ids)
    print(f"语料: {len(corpus):,} 字符 → {n_tokens:,} token（平均 {n_tokens / len(corpus):.2f} 字/token）")

    freq = Counter(ids)
    print(f"不同 token 数: {len(freq)}（vocab 上限 {tokenizer.vocab_size}）")

    # 覆盖率曲线
    print("\n=== 覆盖率（top-N token 覆盖语料比例）===")
    ranked = freq.most_common()
    for n in [50, 100, 200, 300, 400, 500, 800, 1000, 2000]:
        covered = sum(c for _, c in ranked[:n])
        print(f"  top {n:>5}: {covered / n_tokens:6.1%}")

    # top 300 词长什么样
    print("\n=== top 300 token（受限词库候选）===")
    for i, (tid, count) in enumerate(ranked[:300]):
        token = tokenizer.decode([tid])
        print(f"{token}\t{count}", end="\n" if (i + 1) % 5 == 0 else "  |  ")

    # 写词库文件
    if top_n:
        custom = load_custom_tokens()
        kept = [tokenizer.decode([tid]) for tid, _ in ranked[:top_n]]
        # 手动词元合并进去（去重、不丢角色词）
        kept = list(dict.fromkeys([*custom, *kept]))[:top_n]
        name = "dialogue" if dialogue else "希儿"
        out = VOCAB_DIR / f"restricted_{name}.txt"
        VOCAB_DIR.mkdir(parents=True, exist_ok=True)
        lines = [f"# 希儿受限词库（top-{len(kept)}，手动词元优先）— 覆盖率 {sum(c for _, c in ranked[:top_n]) / n_tokens:.1%}", *kept]
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n词库已写入: {out}（{len(kept)} 词，覆盖率 {sum(c for _, c in ranked[:top_n]) / n_tokens:.1%}）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="受限词库分析")
    parser.add_argument("--write", type=int, default=0,
                        help="写 top-N 词库文件到 vocab/restricted_{希儿|dialogue}.txt")
    parser.add_argument("--dialogue", action="store_true",
                        help="分析对话语料（corpus_dialogue.txt，D 实验）")
    args = parser.parse_args()
    main(args.write or None, args.dialogue)


if __name__ == "__main__":
    main()
