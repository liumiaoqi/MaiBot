"""对比评估：纯希儿（无正则化）vs 混合语料+强正则化（A+B）。

用法：
  uv run python compare_generation.py

对比维度：
- 同 prompt 生成质量（多样 vs 复读）
- 温度 0.7 / 1.0 / 1.3 采样行为
- 复读率指标：生成文本 unique 字符比例
"""

import sys
from pathlib import Path

import torch

import mini_swa
from bpe_tokenizer import BPETokenizer

MODEL_DIR = Path(__file__).resolve().parent / "checkpoints"

MODELS = [
    ("纯希儿（16.9万，无正则化）", "希儿", False),
    ("混合+强正则（40.6万，A+B）", "希儿", True),
]

PROMPTS = ["希儿", "希儿说", "我想要", "今天"]

TEMPERATURES = [0.7, 1.0, 1.3]


def repeat_score(text: str) -> float:
    """简单复读率：unique 字符比例（越低越复读）。"""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return len(set(chars)) / len(chars)


def load_model(character: str, mix: bool):
    suffix = "_mix" if mix else ""
    tokenizer = BPETokenizer.load(MODEL_DIR / f"tokenizer_swa_{character}{suffix}.json")
    model = mini_swa.MiniSWALM(tokenizer.vocab_size)
    checkpoint = MODEL_DIR / f"mini_swa_{character}{suffix}.pt"
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(state["state_dict"])
    model.eval()
    return model, tokenizer


def main() -> None:
    print("=" * 70)
    for name, character, mix in MODELS:
        model, tokenizer = load_model(character, mix)
        print(f"\n## {name}  (vocab={tokenizer.vocab_size})")
        for prompt in PROMPTS:
            for temp in TEMPERATURES:
                text = mini_swa.generate(model, tokenizer, prompt, 60, temp)
                score = repeat_score(text)
                flag = "✅多样" if score > 0.45 else "⚠️复读"
                print(f"  [{prompt!r} t={temp}] {flag}({score:.2f}) {text[:80]!r}")


if __name__ == "__main__":
    main()
