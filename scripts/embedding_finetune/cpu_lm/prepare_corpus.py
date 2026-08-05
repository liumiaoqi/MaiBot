"""CPU 小语言模型：语料准备——md 资料 → 纯文本语料。

来源：~/整理崩坏星穹铁道资料/（人格设定/表达风格/世界观 md 文档）
输出：data/corpus.txt（清洗后的纯文本，UTF-8）
      data/corpus_{角色}.txt（单角色提取）
      data/corpus_mix_{角色}.txt（单角色 + 补充语料混合，A+B 用）

清洗规则：
- 去掉 Markdown 语法（# 标题、| 表格、- 列表符号、** 强调）
- 去掉代码块
- 压缩连续空行
"""

import re
import sys
from pathlib import Path

# WSL 与 Windows 双路径（uv.exe 在 Windows 侧跑，路径是 E:\ 风格）
if sys.platform == "win32":
    CORPUS_ROOT = Path(r"E:\Users\lmq\整理崩坏星穹铁道资料")
else:
    CORPUS_ROOT = Path("/mnt/e/Users/lmq/整理崩坏星穹铁道资料")
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_PATH = OUTPUT_DIR / "corpus.txt"

# Markdown 行级语法
_MD_PATTERNS = [
    (re.compile(r"^#{1,6}\s*"), ""),          # 标题
    (re.compile(r"^\s*[-*+]\s+"), ""),        # 无序列表
    (re.compile(r"^\s*\d+[.、)]\s*"), ""),    # 有序列表
    (re.compile(r"^\s*\|.*\|\s*$"), ""),      # 表格行
    (re.compile(r"^\s*>+\s*"), ""),           # 引用
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),  # 粗体
    (re.compile(r"\*([^*]+)\*"), r"\1"),      # 斜体
    (re.compile(r"`([^`]+)`"), r"\1"),        # 行内代码
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),  # 图片
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),  # 链接
]


def clean_markdown(text: str) -> str:
    """按行清洗 Markdown 文本。"""
    lines: list[str] = []
    in_code_block = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        for pattern, replacement in _MD_PATTERNS:
            line = pattern.sub(replacement, line)
        line = line.strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def build_corpus() -> int:
    """扫描全部 md，清洗后合并成语料，返回字符数。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CORPUS_ROOT.exists():
        raise SystemExit(f"语料目录不存在: {CORPUS_ROOT}")

    md_files = sorted(CORPUS_ROOT.rglob("*.md"))
    if not md_files:
        raise SystemExit(f"未找到 md 文件: {CORPUS_ROOT}")

    chunks: list[str] = []
    total_chars = 0
    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cleaned = clean_markdown(text)
        if len(cleaned) < 50:  # 跳过过短文件（设定模板等）
            continue
        chunks.append(cleaned)
        total_chars += len(cleaned)

    corpus = "\n\n".join(chunks)
    # 压缩连续空行
    corpus = re.sub(r"\n{3,}", "\n\n", corpus)

    OUTPUT_PATH.write_text(corpus, encoding="utf-8")
    print(f"语料已生成: {OUTPUT_PATH}")
    print(f"来源文件: {len(md_files)} 个 md，有效 {len(chunks)} 个")
    print(f"总字符数: {len(corpus)}")
    # 字符集统计（tokenizer 参考）
    chars = sorted(set(corpus))
    print(f"字符集大小: {len(chars)}")
    return len(corpus)


def build_mixed_corpus(character: str, extra_path: str) -> Path:
    """混合语料（A+B）：单角色语料 + 补充语料（资本论等），加量 + 多样化。

    混合动机（1M 参数 × 17.4 万字符 = 过拟合复读）：
    - 加量：补充语料把总量推到 50 万级，参数/语料比不再差一个数量级
    - 多样化：跨风格文本稀释同质语料，强正则化才能学到"模式"而非背数据
    输出：data/corpus_mix_{character}.txt
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    character_path = OUTPUT_DIR / f"corpus_{character}.txt"
    extra = Path(extra_path)
    if not character_path.exists():
        raise SystemExit(f"单角色语料不存在，先跑 --character {character}: {character_path}")
    if not extra.exists():
        raise SystemExit(f"补充语料不存在: {extra}")

    base = character_path.read_text(encoding="utf-8")
    supplement = extra.read_text(encoding="utf-8")
    corpus = f"{base}\n\n{supplement}"
    corpus = re.sub(r"\n{3,}", "\n\n", corpus)

    out_path = OUTPUT_DIR / f"corpus_mix_{character}.txt"
    out_path.write_text(corpus, encoding="utf-8")
    print(f"混合语料已生成: {out_path}")
    print(f"基础（{character}）: {len(base):,} 字符 + 补充（{extra.name}）: {len(supplement):,} 字符")
    print(f"总字符数: {len(corpus):,}")
    return out_path


def build_character_corpus(character: str) -> Path:
    """提取单一角色语料：文件名含角色名 或 段落含角色名。

    段落级过滤避免混入其他角色（只保留提到该角色的段落）。
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"corpus_{character}.txt"

    md_files = sorted(CORPUS_ROOT.rglob("*.md"))
    chunks: list[str] = []
    for path in md_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cleaned = clean_markdown(text)
        if len(cleaned) < 50:
            continue
        # 文件名命中（角色专属文档）→ 整篇保留
        if character in path.stem:
            chunks.append(cleaned)
            continue
        # 否则段落级过滤：只保留含角色名的段落
        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        kept = [p for p in paragraphs if character in p]
        if kept:
            chunks.append("\n\n".join(kept))

    corpus = "\n\n".join(chunks)
    corpus = re.sub(r"\n{3,}", "\n\n", corpus)
    out_path.write_text(corpus, encoding="utf-8")
    print(f"单角色语料已生成: {out_path}")
    print(f"来源文件: {len(md_files)} 个 md，命中段落文件: {len(chunks)} 个")
    print(f"总字符数: {len(corpus)}")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="语料准备")
    parser.add_argument("--character", type=str, default="",
                        help="提取单一角色语料（文件名或段落含角色名）")
    parser.add_argument("--mix", type=str, default="",
                        help="混合补充语料路径（如 data/资本论.txt），输出 corpus_mix_{角色}.txt")
    args = parser.parse_args()
    if args.mix:
        build_mixed_corpus(args.character, args.mix)
    elif args.character:
        build_character_corpus(args.character)
    else:
        build_corpus()
