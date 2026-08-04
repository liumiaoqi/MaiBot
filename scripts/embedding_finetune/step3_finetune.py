"""Step 3: 微调 bge-large-zh-v1.5 embedding 模型。

使用 sentence-transformers + TripletLoss，在 RTX 5060 上训练。

前置：
  - pip install sentence-transformers[training] torch torchvision --index-url https://download.pytorch.org/whl/cu126
  - step2_build_triplets.py 已生成 train_triplets.jsonl

用法：
  python step3_finetune.py [--triplets FILE] [--base-model NAME] [--epochs N] [--batch-size N] [--output DIR]
"""

import argparse
import json
from pathlib import Path

DEFAULT_TRIPLETS = Path("scripts/embedding_finetune/data/train_triplets.jsonl")
DEFAULT_BASE_MODEL = "BAAI/bge-large-zh-v1.5"
DEFAULT_OUTPUT = Path("scripts/embedding_finetune/finetuned_model")


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
) -> None:
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader

    print(f"加载基础模型: {base_model}")
    model = SentenceTransformer(base_model)

    print(f"加载三元组: {triplets_path}")
    raw = load_triplets(triplets_path)
    print(f"共 {len(raw)} 个三元组")

    train_examples = []
    for t in raw:
        train_examples.append(
            InputExample(
                texts=[t["anchor"], t["positive"], t["negative"]],
            )
        )

    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=batch_size,
    )

    train_loss = losses.TripletLoss(model=model)

    print(f"开始微调: epochs={epochs}, batch_size={batch_size}, warmup={warmup_steps}")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        output_path=str(output_dir),
        show_progress_bar=True,
    )

    print(f"微调完成，模型保存至: {output_dir}")

    test_sentences = ["麦麦今天心情不好", "测试微调后的embedding效果", "群里的黑话yyds"]
    embeddings = model.encode(test_sentences)
    for sent, emb in zip(test_sentences, embeddings, strict=True):
        print(f"  '{sent}' → 向量维度 {len(emb)}, 前5维: {emb[:5].round(4).tolist()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--triplets", type=Path, default=DEFAULT_TRIPLETS, dest="triplets_path")
    parser.add_argument("--base-model", type=str, default=DEFAULT_BASE_MODEL)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--warmup-steps", type=int, default=100)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, dest="output_dir")
    main(**vars(parser.parse_args()))