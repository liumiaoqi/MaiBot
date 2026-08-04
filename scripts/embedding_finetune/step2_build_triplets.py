"""Step 2: 用阿里 API embedding 计算向量，按余弦相似度自动构造三元组。

策略：
  - positive: 与 anchor 余弦相似度 Top-K 近邻（语义相近）
  - negative: 与 anchor 余弦相似度 Bottom-K 远邻（语义不同）
  - 同时加入同 source 段落对为 positive（同来源的段落语义相关）

输出：train_triplets.jsonl，每行 {"anchor": ..., "positive": ..., "negative": ...}

用法：
  python step2_build_triplets.py [--data DIR] [--out FILE] [--top-k N] [--bottom-k N]

需要：阿里 API embedding 已配置（读取 docker-config/mmc/model_config.toml）
"""

import argparse
import json
import csv
import math
import random
from pathlib import Path
from collections import defaultdict

DEFAULT_DATA = Path("scripts/embedding_finetune/data")
DEFAULT_OUT = Path("scripts/embedding_finetune/data/train_triplets.jsonl")
DOCKER_MODEL_CONFIG = Path("docker-config/mmc/model_config.toml")


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


def load_paragraphs(data_dir: Path) -> list[dict]:
    texts = []
    with open(data_dir / "paragraphs.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            content = row["content"].strip()
            if len(content) >= 4:
                texts.append({"text": content, "source": row["source"], "hash": row["hash"]})

    with open(data_dir / "episodes.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            summary = row["summary"].strip()
            if len(summary) >= 4:
                texts.append({"text": summary, "source": "episode", "hash": row["episode_id"]})
            title = row["title"].strip()
            if len(title) >= 4:
                texts.append({"text": title, "source": "episode_title", "hash": row["episode_id"]})

    return texts


def encode_with_api(texts: list[str], api_key: str, base_url: str, model_id: str) -> list[list[float]]:
    """用阿里 API 批量编码。"""
    import urllib.request
    import urllib.error

    url = f"{base_url.rstrip('/')}/embeddings"
    all_embeddings = []
    batch_size = 16
    max_input_len = 8000

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        truncated = [t[:max_input_len] for t in batch]
        payload = json.dumps({
            "model": model_id,
            "input": truncated,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            indexed = {d["index"]: d["embedding"] for d in result["data"]}
            for j in range(len(batch)):
                all_embeddings.append(indexed[j])
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:300]
            print(f"  批次 {i//batch_size} 失败 (HTTP {e.code}): {error_body}")
            for _ in range(len(batch)):
                all_embeddings.append([0.0] * 1024)

        done = i + len(batch)
        if done % 500 == 0 or done == len(texts):
            print(f"  已编码 {done}/{len(texts)} 条")

    return all_embeddings


def build_triplets(
    texts: list[dict],
    embeddings: list[list[float]],
    top_k: int,
    bottom_k: int,
) -> list[dict]:
    by_source = defaultdict(list)
    for i, t in enumerate(texts):
        by_source[t["source"]].append(i)

    triplets = []

    for i in range(len(texts)):
        sims = []
        for j in range(len(texts)):
            if i == j:
                continue
            sims.append((j, cosine_sim(embeddings[i], embeddings[j])))

        sims.sort(key=lambda x: x[1], reverse=True)

        positives = [j for j, _ in sims[:top_k]]
        negatives = [j for j, _ in sims[-bottom_k:]]

        same_source = [j for j in by_source[texts[i]["source"]] if j != i]
        if same_source:
            positives.extend(random.sample(same_source, min(3, len(same_source))))

        for p in positives:
            for n in negatives:
                triplets.append({
                    "anchor": texts[i]["text"],
                    "positive": texts[p]["text"],
                    "negative": texts[n]["text"],
                })

    return triplets


def main(data_dir: Path, out_path: Path, top_k: int, bottom_k: int, api_key: str, base_url: str, model_id: str) -> None:
    print("加载文本数据...")
    texts = load_paragraphs(data_dir)
    print(f"共 {len(texts)} 条文本")

    print("计算 embedding（阿里 API）...")
    embeddings = encode_with_api([t["text"] for t in texts], api_key, base_url, model_id)
    print(f"获得 {len(embeddings)} 个向量")

    print("构造三元组...")
    triplets = build_triplets(texts, embeddings, top_k, bottom_k)
    random.shuffle(triplets)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for t in triplets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"写入 {len(triplets)} 个三元组 → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, dest="data_dir")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, dest="out_path")
    parser.add_argument("--top-k", type=int, default=3, dest="top_k", help="每个 anchor 取 Top-K 近邻为 positive")
    parser.add_argument("--bottom-k", type=int, default=3, dest="bottom_k", help="每个 anchor 取 Bottom-K 远邻为 negative")
    parser.add_argument("--api-key", type=str, required=True, help="阿里百炼 API Key")
    parser.add_argument("--base-url", type=str, default="https://dashscope.aliyuncs.com/compatible-mode/v1", help="阿里百炼 API Base URL")
    parser.add_argument("--model-id", type=str, default="qwen3.7-text-embedding", help="阿里 embedding 模型 ID")
    args = parser.parse_args()
    main(args.data_dir, args.out_path, args.top_k, args.bottom_k, args.api_key, args.base_url, args.model_id)