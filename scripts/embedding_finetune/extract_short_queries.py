"""提取对话类短文本语料，作为 embedding 微调的 query 侧样本。

来源：episodes.csv（summary/title）、paragraphs.csv（source=chat_summary/person_fact）
过滤：只剔纯表情/纯符号/重复，保留含文字的表情文本
输出：short_queries.jsonl，每行 {"text": ..., "source": ...}

用法：
  python extract_short_queries.py [--data DIR] [--out FILE]
"""

import argparse
import csv
import json
import re
from pathlib import Path

DEFAULT_DATA = Path("scripts/embedding_finetune/data")
DEFAULT_OUT = Path("scripts/embedding_finetune/data/short_queries.jsonl")


def has_chinese_or_letter(text: str) -> bool:
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
    has_letter = any(c.isalpha() for c in text)
    return has_cjk or has_letter


def is_pure_emoji(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return not has_chinese_or_letter(stripped)


def normalize_quotes(text: str) -> str:
    text = text.replace('"', '\u201c').replace('"', '\u201d')
    text = text.replace("'", '\u2018').replace("'", '\u2019')
    return text


def is_garbage(text: str) -> bool:
    if len(text.strip()) < 2:
        return True
    if is_pure_emoji(text):
        return True
    if re.match(r'^[\s\d\.\,\-\+\*\/\=\(\)\[\]]+$', text.strip()):
        return True
    return False


def main(data_dir: Path, out_path: Path) -> None:
    texts = []

    with open(data_dir / "episodes.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for field in ("summary", "title"):
                val = row.get(field, "").strip()
                val = normalize_quotes(val)
                if val and not is_garbage(val) and len(val) <= 100:
                    texts.append({"text": val, "source": f"episode_{field}"})

    with open(data_dir / "paragraphs.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source = row.get("source", "")
            if source not in ("chat_summary", "person_fact"):
                continue
            content = row["content"].strip()
            content = normalize_quotes(content)
            if content and not is_garbage(content) and len(content) <= 100:
                texts.append({"text": content, "source": source})

    seen = set()
    unique = []
    for item in texts:
        if item["text"] not in seen:
            seen.add(item["text"])
            unique.append(item)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for item in unique:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"提取 {len(texts)} 条短文本，去重后 {len(unique)} 条")
    print(f"输出 → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, dest="data_dir")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, dest="out_path")
    args = parser.parse_args()
    main(args.data_dir, args.out_path)