"""清洗三元组 JSONL 中的 Markdown 格式污染 + 低质量过滤。

处理：
  1. 去掉引用块标记：行首的 "> " 和嵌套的 ">> "
  2. 去掉粗体/斜体标记：**text** → text, *text* → text
  3. 去掉 Markdown 表格分隔行：|---|---|
  4. 去掉水平线：--- / *** / ___
  5. 去掉标题标记：## text → text
  6. 去掉列表标记：- text → text, * text → text
  7. 去掉链接，保留文本：[text](url) → text
  8. 表格行转自然语言：|a|b|c| → a，b，c
  9. 去掉网站前缀：bilibili WIKI - xxx → xxx
  10. 清洗箭头符号：" → " → "："
  11. 压缩连续空行为单个换行
  12. 过滤超长文本（>1000字）
  13. 过滤系统功能描述（"询问消息时间显示功能"等）
  14. 过滤弱 negative（<15字 或 系统标签，训练信号为零）
  15. 去重：同一 negative 出现 >200 次则丢弃该三元组

用法：
  python clean_triplets.py [--input FILE] [--output FILE]
  默认读取 data/train_triplets.jsonl，输出 data/train_triplets_clean.jsonl
"""

import argparse
import json
import re
from pathlib import Path

DEFAULT_INPUT = Path("scripts/embedding_finetune/data/train_triplets.jsonl")
DEFAULT_OUTPUT = Path("scripts/embedding_finetune/data/train_triplets_clean.jsonl")

NOISE_PREFIXES = re.compile(
    r"^(?:bilibili\s+WIKI\s*[-–—]\s*"
    r"|百度百科\s*[-–—]\s*"
    r"|维基百科\s*[-–—]\s*"
    r"|萌娘百科\s*[-–—]\s*"
    r"|Fandom\s*[-–—]\s*"
    r"|Genshin\s+Impact\s+Wiki\s*[-–/]\s*"
    r"|Honkai(?::\s*Star\s*Rail)?\s+Wiki\s*[-–/]\s*"
    r"|HoYoWiki\s*[-–—]\s*"
    r")",
    re.IGNORECASE,
)

URL_PATTERN = re.compile(r'https?://\S+')


SYSTEM_TEXT_PATTERN = re.compile(
    r"^(?:询问|查询|获取|设置|修改|删除|添加|开启|关闭|切换|消息|功能|配置|记录|显示|发送|接收|提醒|准备|晚间|早晨|考试|阅读|晚餐|午餐|早餐|午休|闲聊|问候|互动|进食|补觉|复习|安排|活动|时间).{0,15}$"
)

WEAK_NEG_PATTERN = re.compile(
    r"^(?:发送|接收|询问|查询|获取|设置|修改|删除|添加|开启|关闭|切换|提醒|准备|晚间|早晨|考试|阅读|晚餐|午餐|早餐|午休|闲聊|问候|互动|进食|补觉|复习|安排|活动|时间|消息|功能|配置|记录|显示|观看|发布|简短|近代史).{0,10}$"
)


def clean_markdown(text: str) -> str:
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.lstrip()

        if re.match(r"^>{1,4}", stripped):
            line = re.sub(r"^>{1,4}\s?", "", stripped)

        if re.match(r"^\|[-:\s|]+\|$", line.strip()):
            continue

        if re.match(r"^[-*_]{3,}\s*$", line.strip()):
            continue

        line = re.sub(r"^\#{1,6}\s+", "", line)

        line = re.sub(r"^[\-\*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)

        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"\*(.+?)\*", r"\1", line)

        line = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", line)

        if re.match(r"^\|.+\|$", line.strip()):
            parts = [p.strip() for p in line.strip("|").split("|") if p.strip()]
            line = "，".join(parts)

        line = NOISE_PREFIXES.sub("", line)

        line = URL_PATTERN.sub("", line)

        line = line.replace(" → ", "：").replace("→", "：")

        line = line.strip()
        if not line:
            cleaned.append("")
            continue

        cleaned.append(line)

    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

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

    return text


def is_weak_negative(text: str, anchor_is_short: bool = False) -> bool:
    if WEAK_NEG_PATTERN.match(text):
        return True
    if not anchor_is_short and len(text) < 15:
        return True
    if len(text) < 5:
        return True
    return False


def main(input_path: Path, output_path: Path) -> None:
    total = 0
    cleaned_count = 0
    dropped_count = 0
    drop_reasons = {"too_long": 0, "system": 0, "weak_neg": 0, "neg_repeat": 0}

    print("第一遍：统计 negative 出现频率...")
    neg_counts: dict[str, int] = {}
    with open(input_path, "r", encoding="utf-8") as fin:
        for line in fin:
            triplet = json.loads(line)
            for key in ("anchor", "positive", "negative"):
                triplet[key] = clean_markdown(triplet[key])
            neg = triplet["negative"]
            neg_counts[neg] = neg_counts.get(neg, 0) + 1
    repeat_threshold = 200
    repeated_negs = {k for k, v in neg_counts.items() if v > repeat_threshold}
    print(f"  共 {len(neg_counts)} 种 negative，{len(repeated_negs)} 种出现超过 {repeat_threshold} 次")

    print("第二遍：清洗 + 过滤...")
    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            total += 1
            triplet = json.loads(line)

            changed = False
            for key in ("anchor", "positive", "negative"):
                original = triplet[key]
                cleaned = clean_markdown(original)
                if cleaned != original:
                    changed = True
                    triplet[key] = cleaned

            # 超长文本
            if any(len(triplet[k]) > 1000 for k in ("anchor", "positive", "negative")):
                drop_reasons["too_long"] += 1
                dropped_count += 1
                continue

            # 系统功能描述出现在 anchor/positive
            if any(SYSTEM_TEXT_PATTERN.match(triplet[k]) for k in ("anchor", "positive")):
                drop_reasons["system"] += 1
                dropped_count += 1
                continue

            # 弱 negative（短 anchor 时放宽：只卡系统标签，不卡长度）
            anchor_is_short = len(triplet["anchor"]) <= 100
            if is_weak_negative(triplet["negative"], anchor_is_short):
                drop_reasons["weak_neg"] += 1
                dropped_count += 1
                continue

            # negative 重复过多
            if triplet["negative"] in repeated_negs:
                drop_reasons["neg_repeat"] += 1
                dropped_count += 1
                continue

            if changed:
                cleaned_count += 1
            fout.write(json.dumps(triplet, ensure_ascii=False) + "\n")

            if total % 10000 == 0:
                print(f"  已处理 {total} 条，保留 {total - dropped_count}")

    kept = total - dropped_count
    print(f"完成：共 {total} 条，保留 {kept} 条，丢弃 {dropped_count} 条")
    print(f"  丢弃原因：超长 {drop_reasons['too_long']}，"
          f"系统描述 {drop_reasons['system']}，"
          f"弱negative {drop_reasons['weak_neg']}，"
          f"negative重复 {drop_reasons['neg_repeat']}")
    print(f"输出 → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, dest="input_path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, dest="output_path")
    args = parser.parse_args()
    main(args.input_path, args.output_path)
