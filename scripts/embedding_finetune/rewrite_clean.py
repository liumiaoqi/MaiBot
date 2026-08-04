"""对已人工审核的 train_triplets_clean.jsonl 做二次清洗。

基于人工审核发现的问题，对已清洗文件做补充清洗（不重新跑全量）：
  1. 去掉网站前缀残留（HoYoWiki、Fandom Wiki、Genshin Impact Wiki 等）
  2. 去掉行内 URL（https://...）
  3. 统一引号：英文直引号 → 中文弯引号（交替配对）
  4. 清洗箭头符号：→ → ：
  5. 追加 custom_triplets.jsonl（表情/人名私货）

用法：
  python rewrite_clean.py [--input FILE] [--custom FILE] [--output FILE]
  默认读取 data/train_triplets_clean.jsonl + data/custom_triplets.jsonl
  输出 data/train_triplets_final.jsonl
"""

import argparse
import json
import re
from pathlib import Path

DEFAULT_INPUT = Path("scripts/embedding_finetune/data/train_triplets_clean.jsonl")
DEFAULT_CUSTOM = Path("scripts/embedding_finetune/data/custom_triplets.jsonl")
DEFAULT_OUTPUT = Path("scripts/embedding_finetune/data/train_triplets_final.jsonl")

NOISE_PREFIXES = re.compile(
    r"(?:HoYoWiki\s*[-–—]\s*"
    r"|Fandom\s+Wiki\s*[-–—]\s*"
    r"|Genshin\s+Impact\s+Wiki\s*[-–/]\s*"
    r"|Honkai(?::\s*Star\s*Rail)?\s+Wiki\s*[-–/]\s*"
    r"|bilibili\s+WIKI\s*[-–—]\s*"
    r"|百度百科\s*[-–—]\s*"
    r"|萌娘百科\s*[-–—]\s*"
    r")",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r'https?://\S+')


def clean_text(text: str) -> str:
    text = NOISE_PREFIXES.sub("", text)
    text = URL_PATTERN.sub("", text)
    text = text.replace(" → ", "：").replace("→", "：")

    text = text.replace("'", '\u2018').replace("'", '\u2019')
    result = []
    open_quote = True
    for c in text:
        if c == '"':
            result.append('\u201c' if open_quote else '\u201d')
            open_quote = not open_quote
        else:
            result.append(c)
    text = ''.join(result)

    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text


def main(input_path: Path, custom_path: Path, output_path: Path) -> None:
    total = 0
    cleaned_count = 0

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            total += 1
            triplet = json.loads(line)

            changed = False
            for key in ("anchor", "positive", "negative"):
                original = triplet[key]
                cleaned = clean_text(original)
                if cleaned != original:
                    changed = True
                    triplet[key] = cleaned

            if changed:
                cleaned_count += 1
            fout.write(json.dumps(triplet, ensure_ascii=False) + "\n")

    custom_count = 0
    if custom_path.exists():
        with open(custom_path, "r", encoding="utf-8") as fcustom, \
             open(output_path, "a", encoding="utf-8") as fout:
            for line in fcustom:
                line = line.strip()
                if not line:
                    continue
                triplet = json.loads(line)
                for key in ("anchor", "positive", "negative"):
                    triplet[key] = clean_text(triplet[key])
                fout.write(json.dumps(triplet, ensure_ascii=False) + "\n")
                custom_count += 1

    print(f"处理 {total} 条，清洗 {cleaned_count} 条，追加私货 {custom_count} 条")
    print(f"总计 {total + custom_count} 条 → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, dest="input_path")
    parser.add_argument("--custom", type=Path, default=DEFAULT_CUSTOM, dest="custom_path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, dest="output_path")
    args = parser.parse_args()
    main(args.input_path, args.custom_path, args.output_path)