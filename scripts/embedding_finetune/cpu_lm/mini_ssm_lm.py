"""CPU 小语言模型：mini SSM（Mamba 精神）字符级语言模型。

架构：Embedding → N×SSMBlock → LayerNorm → 输出头（预测下一个字符）
SSMBlock（极简对角递推）：
    h_t = a ⊙ h_{t-1} + W_in(x_t)     # 对角递推（a 参数化有界 [-1,1]）
    y_t = W_out(tanh(h_t)) + x_t      # 输出 + 残差
    y_t = LayerNorm(y_t)
推理：逐字符 O(1) 递推——CPU 友好（每步一个对角乘加）。

规模（默认 d=192, N=3，~2M 参数，vocab 3460）：
- 嵌入层 3460×192 ≈ 664K
- 3 个 Block：3×(192×192×2 + 192×2) ≈ 222K
- 输出头 192×3460 ≈ 664K

用法：
  uv run python mini_ssm_lm.py --train          # 训练（CPU，~1-2 小时）
  uv run python mini_ssm_lm.py --generate --prompt "希儿" --len 100
  uv run python mini_ssm_lm.py --train --epochs 3 --lr 0.001
"""

import argparse
import json
import random
import time
from pathlib import Path

import torch

from bpe_tokenizer import BPETokenizer, load_custom_tokens
from prepare_corpus import OUTPUT_DIR as CORPUS_DIR

DATA_PATH = CORPUS_DIR / "corpus.txt"
MODEL_DIR = Path(__file__).resolve().parent / "checkpoints"

SEQUENCE_LEN = 256
BATCH_SIZE = 16
D_MODEL = 192
N_LAYERS = 3
DROPOUT = 0.0
GRAD_CLIP = 1.0
SEED = 42


# ── tokenizer（BPE + 手动词元）──────────────────────────────


def build_tokenizer(corpus: str, target_vocab: int = 4000) -> BPETokenizer:
    """构建 BPE tokenizer（手动词元优先）。"""
    return BPETokenizer(corpus, load_custom_tokens(), target_vocab=target_vocab)


# ── mini SSM 架构 ───────────────────────────────────────────


class SSMBlock(torch.nn.Module):
    """对角线性递推块（Mamba 精神极简版）。

    h_t = a ⊙ h_{t-1} + W_in(x_t)
    y_t = LayerNorm(W_out(tanh(h_t)) + x_t)

    a 参数化：a = 2·sigmoid(pa) − 1 ∈ [-1, 1]（有界递推不发散——cpu_arch 教训）
    """

    def __init__(self, d_model: int, dropout: float = 0.2) -> None:
        super().__init__()
        self.w_in = torch.nn.Linear(d_model, d_model)
        self.w_out = torch.nn.Linear(d_model, d_model)
        self.ln = torch.nn.LayerNorm(d_model)
        self.dropout = torch.nn.Dropout(dropout)
        # 对角递推系数（每维度一个，参数化有界）
        self.pa = torch.nn.Parameter(torch.zeros(d_model))

    @property
    def a(self) -> torch.Tensor:
        return 2.0 * torch.sigmoid(self.pa) - 1.0

    def forward(self, x: torch.Tensor, state: torch.Tensor | None = None):
        """处理一个时间步（逐字符递推——生成模式）。

        Args:
            x: [batch, d_model] 当前输入
            state: [batch, d_model] 上一状态（None = 初始零状态）

        Returns:
            (y, new_state)
        """
        if state is None:
            state = torch.zeros_like(x)
        new_state = self.a * state + self.dropout(self.w_in(x))
        y = self.ln(self.dropout(self.w_out(torch.tanh(new_state))) + x)
        return y, new_state

    def forward_seq(self, x_seq: torch.Tensor, state: torch.Tensor | None = None):
        """处理整个序列（训练模式——顺序递推展开，BPTT）。"""
        outputs = []
        h = state
        for t in range(x_seq.shape[1]):
            y, h = self.forward(x_seq[:, t], h)
            outputs.append(y)
        return torch.stack(outputs, dim=1), h


class MiniSSMLM(torch.nn.Module):
    """mini SSM 字符级语言模型：Embedding → N×SSMBlock → LN → 输出头。"""

    def __init__(self, vocab_size: int, d_model: int = D_MODEL, n_layers: int = N_LAYERS) -> None:
        super().__init__()
        self.embed = torch.nn.Embedding(vocab_size, d_model)
        self.blocks = torch.nn.ModuleList([SSMBlock(d_model) for _ in range(n_layers)])
        self.embed_dropout = torch.nn.Dropout(0.2)
        self.ln = torch.nn.LayerNorm(d_model)
        self.head = torch.nn.Linear(d_model, vocab_size)
        self.d_model = d_model

    def forward(self, ids: torch.Tensor, states: list[torch.Tensor] | None = None):
        """训练：输入 id 序列 [batch, seq]，返回 logits [batch, seq, vocab]。"""
        x = self.embed_dropout(self.embed(ids))
        new_states = []
        for idx, block in enumerate(self.blocks):
            x, h = block.forward_seq(x, states[idx] if states else None)
            new_states.append(h)
        logits = self.head(self.ln(x))
        return logits, new_states

    def generate_step(self, token_id: int, states: list[torch.Tensor] | None):
        """生成模式：单步递推（O(1)），返回 (logits, new_states)。"""
        x = self.embed(torch.tensor([[token_id]]))[:, 0]  # [1, d]
        new_states = []
        for idx, block in enumerate(self.blocks):
            x, h = block.forward(x, states[idx] if states else None)
            new_states.append(h)
        logits = self.head(self.ln(x))
        return logits, new_states


# ── 数据加载 ────────────────────────────────────────────────


def load_data(tokenizer: BPETokenizer) -> torch.Tensor:
    """语料 → id 张量（训练序列切片用）。"""
    corpus = DATA_PATH.read_text(encoding="utf-8")
    ids = tokenizer.encode(corpus)
    return torch.tensor(ids, dtype=torch.long)


def make_batches(ids: torch.Tensor, seq_len: int, batch_size: int, seed: int) -> list[torch.Tensor]:
    """切块成 (batch, seq) 训练批。"""
    rng = random.Random(seed)
    n_chunks = ids.numel() // seq_len
    chunks = ids[: n_chunks * seq_len].view(n_chunks, seq_len)
    rng.shuffle(chunks)
    return [chunks[i:i + batch_size] for i in range(0, n_chunks, batch_size)]


# ── 训练 ─────────────────────────────────────────────────────


def train(epochs: int, lr: float, d_model: int, n_layers: int) -> None:
    """CPU 训练 mini SSM 语言模型。"""
    torch.manual_seed(SEED)
    corpus = DATA_PATH.read_text(encoding="utf-8")
    tokenizer = build_tokenizer(corpus)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tokenizer.save(MODEL_DIR / "tokenizer.json")

    model = MiniSSMLM(tokenizer.vocab_size, d_model, n_layers)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"模型参数: {n_params:,}（vocab={tokenizer.vocab_size}, d={d_model}, layers={n_layers}）")
    print(f"语料: {len(corpus):,} 字符")

    ids = load_data(tokenizer)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    criterion = torch.nn.CrossEntropyLoss()
    start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        batches = make_batches(ids, SEQUENCE_LEN, BATCH_SIZE, SEED + epoch)
        total_loss = 0.0
        n_steps = 0
        for batch in batches:
            optimizer.zero_grad()
            logits, _ = model(batch)
            loss = criterion(logits.reshape(-1, tokenizer.vocab_size), batch.reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            optimizer.step()
            total_loss += loss.item()
            n_steps += 1
        avg_loss = total_loss / n_steps
        elapsed = time.perf_counter() - start
        # 抽样生成看一眼效果
        sample = generate(model, tokenizer, "希儿", 60, temperature=0.8)
        print(f"epoch {epoch}/{epochs}  loss={avg_loss:.4f}  用时 {elapsed:.0f}s")
        print(f"  生成: {sample!r}")

    checkpoint = MODEL_DIR / f"mini_ssm_lm_d{d_model}_l{n_layers}.pt"
    torch.save({"state_dict": model.state_dict(), "d_model": d_model,
                "n_layers": n_layers, "vocab_size": tokenizer.vocab_size}, checkpoint)
    print(f"模型已保存: {checkpoint}")


# ── 生成 ─────────────────────────────────────────────────────


@torch.no_grad()
def generate(model: MiniSSMLM, tokenizer: BPETokenizer, prompt: str,
             length: int, temperature: float = 0.8) -> str:
    """从 prompt 逐字符递推生成（O(n) CPU 友好）。"""
    model.eval()
    ids = tokenizer.encode(prompt)
    if not ids:
        ids = [tokenizer.stoi.get("。", 0)]
    states: list[torch.Tensor] | None = None
    # 先递推 prompt
    for tid in ids:
        _, states = model.generate_step(tid, states)
    # 逐字符生成
    generated = list(ids)
    for _ in range(length):
        logits, states = model.generate_step(generated[-1], states)
        logits = logits / temperature
        # top-k 采样：只从概率最高的 k 个 token 里抽（防高频卡死）
        top_k = 30
        top_logits, top_indices = torch.topk(logits, top_k)
        probs = torch.softmax(top_logits, dim=-1)
        chosen = torch.multinomial(probs, 1).item()
        generated.append(top_indices[0, chosen].item())
    return tokenizer.decode(generated)


def main() -> None:
    """训练或生成。"""
    parser = argparse.ArgumentParser(description="mini SSM 字符级语言模型（CPU 友好）")
    parser.add_argument("--train", action="store_true", help="训练模式")
    parser.add_argument("--epochs", type=int, default=3, help="训练轮数（默认 3）")
    parser.add_argument("--lr", type=float, default=0.001, help="学习率")
    parser.add_argument("--d-model", type=int, default=D_MODEL, help="隐藏维度")
    parser.add_argument("--layers", type=int, default=N_LAYERS, help="SSM 块数")
    parser.add_argument("--generate", action="store_true", help="生成模式")
    parser.add_argument("--prompt", type=str, default="希儿", help="生成起始文本")
    parser.add_argument("--len", type=int, default=200, help="生成字符数")
    parser.add_argument("--temp", type=float, default=0.8, help="采样温度")
    args = parser.parse_args()

    if args.train:
        train(args.epochs, args.lr, args.d_model, args.layers)
    elif args.generate:
        tokenizer = BPETokenizer.load(MODEL_DIR / "tokenizer.json")
        checkpoint = MODEL_DIR / f"mini_ssm_lm_d{args.d_model}_l{args.layers}.pt"
        if not checkpoint.exists():
            raise SystemExit(f"模型不存在: {checkpoint}——先跑 --train")
        model = MiniSSMLM(tokenizer.vocab_size, args.d_model, args.layers)
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state["state_dict"])
        print(generate(model, tokenizer, args.prompt, args.len, args.temp))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
