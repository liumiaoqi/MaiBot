"""Step 3b: 基于 train_triplets_final.jsonl 微调 bge-large-zh-v1.5。

与 step3 的区别：
  - 默认读取 train_triplets_final.jsonl（清洗+私货后的最终版）
  - 短 anchor（≤100字）自动加 query instruction（bge 官方推荐）

用法：
  python step3b_finetune.py [--triplets FILE] [--base-model NAME] [--epochs N] [--batch-size N] [--output DIR]
"""

import argparse
import json
from pathlib import Path

DEFAULT_TRIPLETS = Path("scripts/embedding_finetune/data/train_triplets_final.jsonl")
DEFAULT_BASE_MODEL = "BAAI/bge-large-zh-v1.5"
DEFAULT_OUTPUT = Path("scripts/embedding_finetune/output/v1")

QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def load_triplets(path: Path) -> list[dict]:
    triplets = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                triplets.append(json.loads(line))
    return triplets


def main(
    triplets_path: Path,
    base_model: str,
    epochs: int,
    batch_size: int,
    output_dir: Path,
    warmup_steps: int,
    fp16: bool = False,
    max_seq_length: int = 512,
) -> None:
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader

    print(f"加载基础模型: {base_model}")
    model = SentenceTransformer(base_model)
    if max_seq_length and 0 < max_seq_length < 512:
        model.max_seq_length = max_seq_length
        print(f"序列长度限制: {max_seq_length}（长文本截断，计算量减半）")

    print(f"加载三元组: {triplets_path}")
    raw = load_triplets(triplets_path)
    print(f"共 {len(raw)} 个三元组")

    train_examples = []
    for t in raw:
        anchor = t["anchor"]
        if len(anchor) <= 100:
            anchor = QUERY_INSTRUCTION + anchor
        train_examples.append(
            InputExample(
                texts=[anchor, t["positive"], t["negative"]],
            )
        )

    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=batch_size,
    )

    train_loss = losses.TripletLoss(model=model)

    print(f"开始微调: epochs={epochs}, batch_size={batch_size}, warmup={warmup_steps}, fp16={fp16}")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        output_path=str(output_dir),
        show_progress_bar=True,
        use_amp=fp16,  # sentence-transformers 3.x：fp16 改名为 use_amp
    )

    print(f"微调完成，模型保存至: {output_dir}")

    # 一致性验证：query 侧加 instruction + L2 normalize（与 step4 部署行为一致）
    import numpy as np

    test_sentences = ["麦麦今天心情不好", "测试微调后的embedding效果", "群里的黑话yyds"]
    embeddings = model.encode([QUERY_INSTRUCTION + s for s in test_sentences])
    norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-12)
    for sent, emb in zip(test_sentences, embeddings, strict=True):
        print(f"  '{sent}' -> 向量维度 {len(emb)}, 前5维: {emb[:5].round(4).tolist()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--triplets", type=Path, default=DEFAULT_TRIPLETS, dest="triplets_path")
    parser.add_argument("--base-model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--warmup-steps", type=int, default=100)
    parser.add_argument("--fp16", action="store_true", help="fp16 混合精度（Tensor Core 加速，RTX 50 系必需）")
    parser.add_argument("--max-seq-length", type=int, default=512, dest="max_seq_length")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, dest="output_dir")
    main(**vars(parser.parse_args()))
