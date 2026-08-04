"""展示将用于训练的文本数据 + 长度统计。"""
import csv
from pathlib import Path

d = Path("scripts/embedding_finetune/data")

# paragraphs
with open(d / "paragraphs.csv", "r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
lengths = [len(r["content"]) for r in rows if r.get("content")]
print(f"=== paragraphs.content ({len(lengths)} 条) ===")
print(f"  最短: {min(lengths)}字  最长: {max(lengths)}字  平均: {sum(lengths)//len(lengths)}字")
print(f"  >500字: {sum(1 for length in lengths if length > 500)}条  >200字: {sum(1 for length in lengths if length > 200)}条  <=20字: {sum(1 for length in lengths if length <= 20)}条")
by_len = sorted(enumerate(rows), key=lambda x: len(x[1].get("content", "")), reverse=True)
print("\n  最长5条（web_import 的整篇文档被存成了单条段落）:")
for idx, r in by_len[:5]:
    c = r["content"][:80].replace("\n", " ")
    src = r.get("source", "")[:25]
    print(f"    [{idx}] ({len(r['content'])}字) src={src} | {c}...")
print("\n  典型短条（人物事实/聊天摘要）:")
for idx, r in by_len[-5:]:
    c = r["content"][:80].replace("\n", " ")
    print(f"    [{idx}] ({len(r['content'])}字) {c}")

# episodes
with open(d / "episodes.csv", "r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
lengths = [len(r["summary"]) for r in rows if r.get("summary")]
print(f"\n=== episodes.summary ({len(lengths)} 条) ===")
print(f"  最短: {min(lengths)}字  最长: {max(lengths)}字  平均: {sum(lengths)//len(lengths)}字")
print("  样本:")
for r in rows[:5]:
    t = r.get("title", "")[:30]
    s = r.get("summary", "")[:60].replace("\n", " ")
    print(f"    {t} | {s}")

# relations
with open(d / "relations.csv", "r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
print(f"\n=== relations ({len(rows)} 条) ===")
print("  样本:")
for r in rows[:10]:
    print(f"    {r['subject']} -{r['predicate']}-> {r['object']}  conf={r.get('confidence','')}")

# person_profiles
with open(d / "person_profiles.csv", "r", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
lengths = [len(r["profile_text"]) for r in rows if r.get("profile_text")]
print(f"\n=== person_profiles.profile_text ({len(lengths)} 条) ===")
print(f"  最短: {min(lengths)}字  最长: {max(lengths)}字  平均: {sum(lengths)//len(lengths)}字")