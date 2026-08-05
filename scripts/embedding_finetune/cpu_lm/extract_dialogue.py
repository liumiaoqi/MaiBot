"""台词提取：web_import_tmp 传记 md → 对话语料。

背景（D 实验）：设定文档（corpus_希儿.txt）没有台词——模型学的是文档模板复读。
传记文件（A_memorix web_import_tmp）含真台词（"布洛妮娅姐姐，希儿做到了。"）。

策略：提取引号台词行 + 所在段落上下文 → 对话语料。
输出：data/corpus_dialogue.txt（全部角色）或 corpus_dialogue_{角色}.txt

用法：
  uv run python extract_dialogue.py                # 全部角色对话语料
  uv run python extract_dialogue.py --character 希儿
"""

import re
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "data"

# WSL 与 Windows 双路径
if sys.platform == "win32":
    TMP_ROOT = Path(r"E:\Users\lmq\MaiBot\data\MaiMBot\a-memorix\web_import_tmp")
else:
    TMP_ROOT = Path("/mnt/e/Users/lmq/MaiBot/data/MaiMBot/a-memorix/web_import_tmp")

# 引号台词：双引号 / 「」/ 『』（2-60 字）
_QUOTE = re.compile(r'"[^"\n]{2,60}"|「[^」\n]{2,60}」|『[^』\n]{2,60}』')


def extract(character: str = "") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(TMP_ROOT.rglob("*.md")) if TMP_ROOT.exists() else []
    if not files:
        raise SystemExit(f"传记目录不存在或为空: {TMP_ROOT}")

    if character:
        files = [f for f in files if character in f.stem]
    if not files:
        raise SystemExit(f"未找到含 {character!r} 的传记文件")

    out_path = OUTPUT_DIR / f"corpus_dialogue{('_' + character) if character else ''}.txt"
    paragraphs: list[str] = []
    n_quotes = 0
    total_quote_chars = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if _QUOTE.search(para):
                # 含台词的段落整体保留（台词 + 上下文）
                paragraphs.append(para)
                n_quotes += len(_QUOTE.findall(para))
                total_quote_chars += sum(len(q) for q in _QUOTE.findall(para))

    corpus = "\n\n".join(paragraphs)
    out_path.write_text(corpus, encoding="utf-8")
    print(f"对话语料已生成: {out_path}")
    print(f"来源文件: {len(files)}，含台词段落: {len(paragraphs)}")
    print(f"台词数: {n_quotes} 条，台词字符: {total_quote_chars:,}")
    print(f"语料总字符: {len(corpus):,}")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="传记台词提取")
    parser.add_argument("--character", type=str, default="",
                        help="只提取某角色传记（文件名含角色名）")
    args = parser.parse_args()
    extract(args.character)
