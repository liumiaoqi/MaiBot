"""mini SWA：滑动窗口注意力 + 权重共享 + 角色注入（为 CPU 设计的 1M 架构）。

设计（lmq 2026-08-05）：
1. 滑动窗口注意力（窗口 32）：每 token 只看 32 个邻居——计算量 O(n×32) 线性，
   CPU 上每步一次小矩阵（SIMD 友好）——保留注意力"直接看上下文"的优势
2. 权重共享：同一 Block 重复 4 次——深度 4 的参数成本 = 深度 1
3. 角色注入：Block 内 role 门控向量（逐元素缩放特征）——角色写进架构
4. 缓存友好：1M 参数 int8 = 1MB ≈ 全进 L2

用法：
  uv run python mini_swa.py --train --epochs 3 --character 希儿
  uv run python mini_swa.py --train --epochs 3 --character 希儿 --mix   # A+B：混合语料 + 强正则化
  uv run python mini_swa.py --generate --character 希儿 --prompt "希儿" --len 100
"""

import argparse
import random
import time
from pathlib import Path

import torch

from bpe_tokenizer import BPETokenizer, load_custom_tokens
from prepare_corpus import OUTPUT_DIR as CORPUS_DIR

MODEL_DIR = Path(__file__).resolve().parent / "checkpoints"
VOCAB_DIR = Path(__file__).resolve().parent / "vocab"

D_MODEL = 128
WINDOW = 32
SHARED_REPEAT = 4
SEQUENCE_LEN = 256
BATCH_SIZE = 16
GRAD_CLIP = 1.0
SEED = 42
# 强正则化（B 方案，A+B 重训用）：1M 参数 × 40 万字符仍偏过拟合，
# dropout 0.4 + label smoothing 0.1 + weight_decay 0.1 逼模型学模式而非背数据
DROPOUT = 0.4
WEIGHT_DECAY = 0.1
LABEL_SMOOTHING = 0.1


def corpus_path(character: str, mix: bool = False, dialogue: bool = False) -> Path:
    if dialogue:
        # 对话语料（D 实验）：corpus_dialogue.txt 或 corpus_dialogue_{角色}.txt
        return CORPUS_DIR / f"corpus_dialogue{('_' + character) if character else ''}.txt"
    if character and mix:
        return CORPUS_DIR / f"corpus_mix_{character}.txt"
    if character:
        return CORPUS_DIR / f"corpus_{character}.txt"
    return CORPUS_DIR / "corpus.txt"


class SlidingWindowAttention(torch.nn.Module):
    """滑动窗口注意力：每位置只看前后 window 个邻居。

    实现：逐位置手动窗口（真实 O(n×k)，非掩码伪装）。
    """

    def __init__(self, d_model: int, window: int) -> None:
        super().__init__()
        self.window = window
        self.q_proj = torch.nn.Linear(d_model, d_model)
        self.k_proj = torch.nn.Linear(d_model, d_model)
        self.v_proj = torch.nn.Linear(d_model, d_model)
        self.out_proj = torch.nn.Linear(d_model, d_model)
        self.scale = d_model ** 0.5

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [batch, seq, d] → 同形状（窗口注意力，O(n×window)）。"""
        batch, seq, d = x.shape
        outputs = []
        q_all = self.q_proj(x)
        k_all = self.k_proj(x)
        v_all = self.v_proj(x)
        for i in range(seq):
            lo = max(0, i - self.window)
            hi = min(seq, i + self.window + 1)
            q = q_all[:, i:i + 1]                      # [b, 1, d]
            k = k_all[:, lo:hi]                        # [b, k, d]
            v = v_all[:, lo:hi]                        # [b, k, d]
            scores = (q @ k.transpose(-1, -2)) / self.scale
            attn = torch.softmax(scores, dim=-1)
            outputs.append(self.out_proj(attn @ v))    # [b, 1, d]
        return torch.cat(outputs, dim=1)


class RoleBlock(torch.nn.Module):
    """滑动窗口注意力 + FFN + 角色门控（角色写进架构）。"""

    def __init__(self, d_model: int, window: int) -> None:
        super().__init__()
        self.swa = SlidingWindowAttention(d_model, window)
        self.ffn = torch.nn.Sequential(
            torch.nn.Linear(d_model, d_model * 4),
            torch.nn.ReLU(),
            torch.nn.Linear(d_model * 4, d_model),
            torch.nn.Dropout(DROPOUT),
        )
        self.ln1 = torch.nn.LayerNorm(d_model)
        self.ln2 = torch.nn.LayerNorm(d_model)
        # 角色门控：逐元素决定"哪些特征通路打开"——训练时从角色语料学出
        self.role = torch.nn.Parameter(torch.zeros(d_model))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: [batch, seq, d] → 同形状。"""
        x = self.ln1(x + self.swa(x))
        x = x * torch.sigmoid(self.role).unsqueeze(0).unsqueeze(0)
        x = self.ln2(x + self.ffn(x))
        return x


class MiniSWALM(torch.nn.Module):
    """mini SWA 语言模型：Embedding + 共享 Block×repeat + LN + 输出头。"""

    def __init__(self, vocab_size: int, d_model: int = D_MODEL,
                 window: int = WINDOW, shared_repeat: int = SHARED_REPEAT,
                 max_seq: int = SEQUENCE_LEN) -> None:
        super().__init__()
        self.embed = torch.nn.Embedding(vocab_size, d_model)
        self.pos = torch.nn.Embedding(max_seq, d_model)
        self.embed_dropout = torch.nn.Dropout(DROPOUT)
        self.block = RoleBlock(d_model, window)  # 共享块（重复用）
        self.shared_repeat = shared_repeat
        self.ln = torch.nn.LayerNorm(d_model)
        self.head = torch.nn.Linear(d_model, vocab_size)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        """ids: [batch, seq] → logits [batch, seq, vocab]（共享块重复 forward）。"""
        seq_len = ids.shape[1]
        positions = torch.arange(seq_len, device=ids.device).unsqueeze(0)
        x = self.embed_dropout(self.embed(ids) + self.pos(positions))
        for _ in range(self.shared_repeat):
            x = self.block(x)
        return self.head(self.ln(x))


def build_tokenizer(character: str, target_vocab: int = 4000, mix: bool = False,
                    dialogue: bool = False) -> BPETokenizer:
    corpus = corpus_path(character, mix, dialogue).read_text(encoding="utf-8")
    return BPETokenizer(corpus, load_custom_tokens(), target_vocab=target_vocab)


def load_data(tokenizer: BPETokenizer, character: str, mix: bool = False,
              restrict: bool = False, dialogue: bool = False) -> torch.Tensor:
    corpus = corpus_path(character, mix, dialogue).read_text(encoding="utf-8")
    if restrict:
        ids = tokenizer.encode_restricted(corpus)  # 词库外一律 <unk>
    else:
        ids = tokenizer.encode(corpus)
    return torch.tensor(ids, dtype=torch.long)


def load_restricted_vocab(character: str, dialogue: bool = False) -> list[str]:
    """加载受限词库文件（analyze_vocab.py --write 生成，可手动编辑增删词）。"""
    name = "dialogue" if dialogue and not character else (character or "希儿")
    path = VOCAB_DIR / f"restricted_{name}.txt"
    if not path.exists():
        raise SystemExit(f"受限词库不存在，先跑 analyze_vocab.py --write 400: {path}")
    tokens = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tokens.append(line)
    return tokens


def make_batches(ids: torch.Tensor, seq_len: int, batch_size: int, seed: int) -> list[torch.Tensor]:
    rng = random.Random(seed)
    n_chunks = ids.numel() // seq_len
    chunks = ids[: n_chunks * seq_len].view(n_chunks, seq_len)
    rng.shuffle(chunks)
    return [chunks[i:i + batch_size] for i in range(0, n_chunks, batch_size)]


@torch.no_grad()
def generate(model: MiniSWALM, tokenizer: BPETokenizer, prompt: str,
             length: int, temperature: float = 1.0, top_k: int = 30,
             restrict: bool = False) -> str:
    """逐字符生成（每步窗口内重算——O(n×k) 线性）。"""
    model.eval()
    if restrict:
        ids = tokenizer.encode_restricted(prompt)
    else:
        ids = tokenizer.encode(prompt)
    if not ids:
        ids = [0]
    generated = list(ids)
    for _ in range(length):
        seq = torch.tensor([generated[-SEQUENCE_LEN:]], dtype=torch.long)
        logits = model(seq)[0, -1] / temperature
        top_logits, top_indices = torch.topk(logits, top_k)
        probs = torch.softmax(top_logits, dim=-1)
        chosen = torch.multinomial(probs, 1).item()
        generated.append(top_indices[chosen].item())
    return tokenizer.decode(generated)


def train(character: str, epochs: int, lr: float, mix: bool, restrict: bool,
          dialogue: bool) -> None:
    torch.manual_seed(SEED)
    tokenizer = build_tokenizer(character, mix=mix, dialogue=dialogue)
    if restrict:
        tokenizer.restrict(load_restricted_vocab(character, dialogue))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"{'_dialogue' if dialogue else ''}{'_mix' if mix else ''}{'_r' if restrict else ''}"
    tokenizer.save(MODEL_DIR / f"tokenizer_swa_{character}{suffix}.json")

    model = MiniSWALM(tokenizer.vocab_size)
    n_params = sum(p.numel() for p in model.parameters())
    corpus = corpus_path(character, mix, dialogue).read_text(encoding="utf-8")
    print(f"[SWA] 角色={character}{'（对话语料）' if dialogue else ''}"
          f"{'（混合语料）' if mix else ''}{'【受限词库】' if restrict else ''} "
          f"参数: {n_params:,}（vocab={tokenizer.vocab_size}, "
          f"d={D_MODEL}, 窗口={WINDOW}, 共享×{SHARED_REPEAT}）")
    print(f"[SWA] 语料: {len(corpus):,} 字符")
    print(f"[SWA] 正则化: dropout={DROPOUT} weight_decay={WEIGHT_DECAY} label_smoothing={LABEL_SMOOTHING}")

    ids = load_data(tokenizer, character, mix, restrict, dialogue)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
    criterion = torch.nn.CrossEntropyLoss(label_smoothing=LABEL_SMOOTHING)
    start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        batches = make_batches(ids, SEQUENCE_LEN, BATCH_SIZE, SEED + epoch)
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
        sample = generate(model, tokenizer, character, 80, temperature=1.0)
        print(f"[SWA] epoch {epoch}/{epochs}  loss={avg_loss:.4f}  用时 {elapsed:.0f}s")
        print(f"  生成: {sample!r}")

    checkpoint = MODEL_DIR / f"mini_swa_{character}{suffix}.pt"
    torch.save({"state_dict": model.state_dict()}, checkpoint)
    print(f"[SWA] 模型已保存: {checkpoint}")


def main() -> None:
    parser = argparse.ArgumentParser(description="mini SWA（滑动窗口 + 角色注入）")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--character", type=str, default="希儿", help="角色名（语料过滤 + 角色注入）")
    parser.add_argument("--mix", action="store_true",
                        help="用混合语料 corpus_mix_{角色}.txt（A+B 方案）")
    parser.add_argument("--restrict", action="store_true",
                        help="受限词库模式：vocab/restricted_{角色|dialogue}.txt，词库外一律 <unk>（R/D 实验）")
    parser.add_argument("--dialogue", action="store_true",
                        help="对话语料：corpus_dialogue.txt（D 实验——台词 vs 设定文档）")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--prompt", type=str, default="")
    parser.add_argument("--len", type=int, default=120)
    parser.add_argument("--temp", type=float, default=1.0)
    args = parser.parse_args()

    if args.train:
        train(args.character, args.epochs, args.lr, args.mix, args.restrict, args.dialogue)
    elif args.generate:
        suffix = f"{'_dialogue' if args.dialogue else ''}{'_mix' if args.mix else ''}{'_r' if args.restrict else ''}"
        tokenizer = BPETokenizer.load(MODEL_DIR / f"tokenizer_swa_{args.character}{suffix}.json")
        model = MiniSWALM(tokenizer.vocab_size)
        checkpoint = MODEL_DIR / f"mini_swa_{args.character}{suffix}.pt"
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state["state_dict"])
        prompt = args.prompt or (args.character or "她")
        print(generate(model, tokenizer, prompt, args.len, args.temp, restrict=args.restrict))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
