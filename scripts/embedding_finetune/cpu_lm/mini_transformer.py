"""对照实验：mini Transformer（同规模级）vs mini SSM。

问题：SSM 架构是否不适合极小模型？
方法：同语料、同训练设置（epochs/lr/seq_len/batch），
Transformer（d=128, l=2，~1.4M 参数）vs SSM（d=128, l=2，~1.1M 参数）。

对比：
- loss 曲线（收敛速度）
- 生成样本（同 prompt）
- 生成耗时（Transformer 无 KV 缓存重算 vs SSM O(n) 递推）

用法：
  uv run python mini_transformer.py --train --epochs 2
  uv run python mini_transformer.py --generate --prompt "希儿" --len 100
"""

import argparse
import random
import time
from pathlib import Path

import torch

from bpe_tokenizer import BPETokenizer
from mini_ssm_lm import (
    DATA_PATH,
    MODEL_DIR,
    BATCH_SIZE,
    SEQUENCE_LEN,
    GRAD_CLIP,
    build_tokenizer,
)

CORPUS_DIR = DATA_PATH.parent


def corpus_path(mix: bool) -> Path:
    if mix:
        return CORPUS_DIR / f"corpus_mix_{MIX_CHARACTER}.txt"
    return DATA_PATH

D_MODEL = 128
N_LAYERS = 2
N_HEADS = 2
FFN_SCALE = 4
# 强正则化（与 mini_swa 的 A+B 设置一致，只差架构做对照）
DROPOUT = 0.4
WEIGHT_DECAY = 0.1
LABEL_SMOOTHING = 0.1
MIX_CHARACTER = "希儿"  # --mix 时用 corpus_mix_{角色}.txt（与 SWA 同语料）


def device() -> torch.device:
    """自动选 GPU（GPU 架构用 GPU 跑，与 CPU 架构各用各的硬件）。"""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


class MiniTransformerBlock(torch.nn.Module):
    """单层：多头自注意力 + FFN + LayerNorm + 残差。"""

    def __init__(self, d_model: int, n_heads: int) -> None:
        super().__init__()
        self.attn = torch.nn.MultiheadAttention(
            d_model, n_heads, batch_first=True, dropout=DROPOUT
        )
        self.ln1 = torch.nn.LayerNorm(d_model)
        self.ffn = torch.nn.Sequential(
            torch.nn.Linear(d_model, d_model * FFN_SCALE),
            torch.nn.ReLU(),
            torch.nn.Linear(d_model * FFN_SCALE, d_model),
            torch.nn.Dropout(DROPOUT),
        )
        self.ln2 = torch.nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [batch, seq, d] → 同形状。"""
        attn_out, _ = self.attn(x, x, x)
        x = self.ln1(x + attn_out)
        x = self.ln2(x + self.ffn(x))
        return x


class MiniTransformerLM(torch.nn.Module):
    """mini Transformer：Embedding + 位置编码 + N×Block + LN + 输出头。"""

    def __init__(self, vocab_size: int, d_model: int = D_MODEL,
                 n_layers: int = N_LAYERS, n_heads: int = N_HEADS,
                 max_seq: int = SEQUENCE_LEN) -> None:
        super().__init__()
        self.embed = torch.nn.Embedding(vocab_size, d_model)
        self.pos = torch.nn.Embedding(max_seq, d_model)
        self.embed_dropout = torch.nn.Dropout(DROPOUT)
        self.blocks = torch.nn.ModuleList(
            [MiniTransformerBlock(d_model, n_heads) for _ in range(n_layers)]
        )
        self.ln = torch.nn.LayerNorm(d_model)
        self.head = torch.nn.Linear(d_model, vocab_size)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        """ids: [batch, seq] → logits [batch, seq, vocab]。"""
        seq_len = ids.shape[1]
        positions = torch.arange(seq_len, device=ids.device).unsqueeze(0)
        x = self.embed_dropout(self.embed(ids) + self.pos(positions))
        for block in self.blocks:
            x = block(x)
        return self.head(self.ln(x))


# ── 训练（与 mini_ssm_lm 同设置）────────────────────────────


def load_data(tokenizer: BPETokenizer, mix: bool = False) -> torch.Tensor:
    corpus = corpus_path(mix).read_text(encoding="utf-8")
    ids = tokenizer.encode(corpus)
    return torch.tensor(ids, dtype=torch.long)


def make_batches(ids: torch.Tensor, seq_len: int, batch_size: int, seed: int) -> list[torch.Tensor]:
    rng = random.Random(seed)
    n_chunks = ids.numel() // seq_len
    chunks = ids[: n_chunks * seq_len].view(n_chunks, seq_len)
    rng.shuffle(chunks)
    return [chunks[i:i + batch_size] for i in range(0, n_chunks, batch_size)]


@torch.no_grad()
def generate(model: MiniTransformerLM, tokenizer: BPETokenizer, prompt: str,
             length: int, temperature: float = 1.0, top_k: int = 30) -> str:
    """逐字符生成（无 KV 缓存——每步重算全历史，O(n²) 注意力）。"""
    model.eval()
    dev = device()
    model = model.to(dev)
    ids = tokenizer.encode(prompt)
    if not ids:
        ids = [0]
    generated = list(ids)
    for _ in range(length):
        seq = torch.tensor([generated[-SEQUENCE_LEN:]], dtype=torch.long, device=dev)
        logits = model(seq)[0, -1] / temperature
        top_logits, top_indices = torch.topk(logits, top_k)
        probs = torch.softmax(top_logits, dim=-1)
        chosen = torch.multinomial(probs, 1).item()
        generated.append(top_indices[chosen].item())
    return tokenizer.decode(generated)


def train(epochs: int, lr: float, mix: bool) -> None:
    torch.manual_seed(42)
    corpus = corpus_path(mix).read_text(encoding="utf-8")
    tokenizer = build_tokenizer(corpus)
    suffix = "_mix" if mix else ""
    tokenizer.save(MODEL_DIR / f"tokenizer_transformer{suffix}.json")

    model = MiniTransformerLM(tokenizer.vocab_size)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[Transformer] {'混合语料（A+B 对照）' if mix else '全量语料'} 参数: {n_params:,}"
          f"（vocab={tokenizer.vocab_size}, d={D_MODEL}, layers={N_LAYERS}, heads={N_HEADS}）")
    print(f"[Transformer] 语料: {len(corpus):,} 字符")
    print(f"[Transformer] 正则化: dropout={DROPOUT} weight_decay={WEIGHT_DECAY} label_smoothing={LABEL_SMOOTHING}")
    print(f"[Transformer] 设备: {device()}")

    ids = load_data(tokenizer, mix)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
    criterion = torch.nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    start = time.perf_counter()
    model = model.to(device())
    ids = ids.to(device())

    for epoch in range(1, epochs + 1):
        batches = make_batches(ids, SEQUENCE_LEN, BATCH_SIZE, 42 + epoch)
        total_loss = 0.0
        n_steps = 0
        for batch in batches:
            optimizer.zero_grad()
            logits = model(batch)
            loss = criterion(logits.reshape(-1, tokenizer.vocab_size), batch.reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimizer.step()
            total_loss += loss.item()
            n_steps += 1
        avg_loss = total_loss / n_steps
        elapsed = time.perf_counter() - start
        sample = generate(model, tokenizer, "希儿", 80, temperature=1.0)
        print(f"[Transformer] epoch {epoch}/{epochs}  loss={avg_loss:.4f}  用时 {elapsed:.0f}s")
        print(f"  生成: {sample!r}")

    checkpoint = MODEL_DIR / f"mini_transformer_d128_l2{suffix}.pt"
    torch.save({"state_dict": model.state_dict()}, checkpoint)
    print(f"[Transformer] 模型已保存: {checkpoint}")


def main() -> None:
    parser = argparse.ArgumentParser(description="mini Transformer（对照实验）")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--mix", action="store_true",
                        help="混合语料 corpus_mix_希儿.txt + 强正则化（GPU 架构对照，同 SWA A+B 设置）")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--prompt", type=str, default="希儿")
    parser.add_argument("--len", type=int, default=100)
    parser.add_argument("--temp", type=float, default=1.0)
    args = parser.parse_args()

    if args.train:
        train(args.epochs, args.lr, args.mix)
    elif args.generate:
        suffix = "_mix" if args.mix else ""
        tokenizer = BPETokenizer.load(MODEL_DIR / f"tokenizer_transformer{suffix}.json")
        model = MiniTransformerLM(tokenizer.vocab_size)
        checkpoint = MODEL_DIR / f"mini_transformer_d128_l2{suffix}.pt"
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state["state_dict"])
        print(generate(model, tokenizer, args.prompt, args.len, args.temp))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
