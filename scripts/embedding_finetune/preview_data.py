"""快速预览导出的数据样本。"""
import csv
from pathlib import Path

data_dir = Path("scripts/embedding_finetune/data")

for name in ["paragraphs", "episodes", "relations", "person_profiles"]:
    path = data_dir / f"{name}.csv"
    if not path.exists():
        continue
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"=== {name}.csv ({len(rows)} 行) ===")
    print(f"  列: {list(rows[0].keys())}")
    if name == "paragraphs":
        for i in [0, 100, 500, 2000]:
            if i < len(rows):
                r = rows[i]
                src = str(r.get("source", ""))[:30]
                cnt = str(r.get("content", ""))[:60]
                print(f"  [{i}] src={src} | {cnt}")
    elif name == "episodes":
        for i in [0, 10, 50]:
            if i < len(rows):
                r = rows[i]
                t = str(r.get("title", ""))[:40]
                s = str(r.get("summary", ""))[:60]
                print(f"  [{i}] {t} | {s}")
    elif name == "relations":
        for i in range(min(5, len(rows))):
            r = rows[i]
            subj = r.get("subject", "")
            pred = r.get("predicate", "")
            obj = r.get("object", "")
            conf = r.get("confidence", "")
            print(f"  [{i}] {subj} -{pred}-> {obj}  conf={conf}")
    elif name == "person_profiles":
        for i in [0, 50, 200]:
            if i < len(rows):
                r = rows[i]
                p = str(r.get("person_id", ""))[:20]
                t = str(r.get("profile_text", ""))[:80]
                print(f"  [{i}] person={p} | {t}")
    print()