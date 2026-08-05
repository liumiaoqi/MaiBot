"""第三层：填词小网络——从"next-token 生成"退到"模板空位选择"。

设计（lmq 2026-08-06，预装+学习认知的最终形态）：
- 状态机 + 模板 = 预装结构（不学）
- 网络只学：状态 + 上下文 → 动作槽位候选打分（窄任务分类）
- 训练数据：台词自动标注（状态机标状态 + 台词内候选动作词），
  样本不完美但教"情境 → 动作偏好"足够

架构（极小）：
  context 词 id（8 个，pad）+ state id
  → Embedding(32) mean + state Embedding(8)
  → Linear(64) ReLU → Linear(n_actions) → 候选打分

参数：vocab 2000 × 32 = 64K + MLP ~8K ≈ 70K

用法：
  uv run python filler_net.py --train        # 构建数据 + 训练 + 存 checkpoint
  uv run python filler_net.py --eval         # 加载网络对比随机/查表填词
"""

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

import torch

from bpe_tokenizer import BPETokenizer, _WORD_PATTERN
from hierarchical_engine import STATES, HierarchicalEngine, segment

DATA_DIR = Path(__file__).resolve().parent / "data"
CKPT_DIR = Path(__file__).resolve().parent / "checkpoints"

CONTEXT_LEN = 8
D_EMB = 32
D_HID = 64
SEED = 42

# 停用词（不参与动作候选）
_STOP = set("的了她是在想要今天我去来来很也都有没有不会吗呢吧啊什么这那")
_PUNCT_ONLY = re.compile(r"^[^\w一-鿿]+$")


def extract_quotes() -> list[str]:
    """希儿台词：对话语料 + 设定文档里的引号内容。"""
    texts = []
    for name in ["corpus_dialogue_希儿.txt", "corpus_希儿.txt"]:
        p = DATA_DIR / name
        if p.exists():
            texts.append(p.read_text(encoding="utf-8"))
    return re.findall(r'"([^"\n]{2,60})"', "\n".join(texts))


# 手工动作词表（台词观察总结——自动提取会混入名词/网络语）
ACTION_TABLE = [
    # 依赖
    "陪着", "等着", "做到", "相信", "不会离开", "在一起", "保护", "看海",
    "约定", "回来", "永远",
    # 战斗
    "战斗", "反击", "守护", "伤害", "欺负", "放过", "靠近", "打败", "小心",
    # 温柔
    "喜欢", "不会放手", "一直", "温柔",
    # 警戒/日常
    "危险", "是谁", "出去走走", "去看看", "想想", "走走",
]


def build_candidates(quotes: list[str], engine: HierarchicalEngine) -> list[str]:
    """候选动作词：手工动作表 + 状态动作域（去重，~40 词）。"""
    candidates: list[str] = []
    for a in ACTION_TABLE:
        if a not in candidates:
            candidates.append(a)
    for s in STATES.values():
        for a in s["actions"]:
            if a not in candidates:
                candidates.append(a)
    return candidates


def build_dataset(quotes: list[str], engine: HierarchicalEngine,
                  candidates: list[str]) -> list[tuple[int, list[int], int, str, str]]:
    """(state_id, context_ids, action_id, 台词, 动作) —— 自动标注。"""
    state_names = list(STATES)
    tokenizer = BPETokenizer.load(CKPT_DIR / "tokenizer_swa_希儿.json")
    stoi = {w: i for i, w in enumerate(tokenizer.vocab)}
    samples = []
    for q in quotes:
        # 否定台词跳过（"不会再伤害任何人"会标出反义动作——网络学到"受伤→伤害"）
        if re.search(r"不会|不要|不再|别|没有|不许", q):
            continue
        words = segment(q, engine.seg_vocab)
        # 状态标注：台词含状态关键词
        state = engine.match_state(q)
        # 动作标注：台词里最后一个候选动作词
        hit = [w for w in words if w in candidates]
        if not hit:
            continue
        action = hit[-1]
        # 上下文：动作词之前的词（取最后 CONTEXT_LEN 个）
        idx = words.index(action) if action in words else len(words) - 1
        ctx_words = [w for w in words[:idx] if w not in _STOP][-CONTEXT_LEN:]
        ctx_ids = [stoi.get(w, 0) for w in ctx_words]
        ctx_ids = [0] * (CONTEXT_LEN - len(ctx_ids)) + ctx_ids  # 左 pad
        samples.append((state_names.index(state), ctx_ids,
                        candidates.index(action), q, action))
    return samples


class FillerNet(torch.nn.Module):
    """填词网络：state + context → 候选动作打分。"""

    def __init__(self, vocab_size: int, n_states: int, n_actions: int) -> None:
        super().__init__()
        self.emb = torch.nn.Embedding(vocab_size, D_EMB)
        self.state_emb = torch.nn.Embedding(n_states, 8)
        self.fc1 = torch.nn.Linear(D_EMB + 8, D_HID)
        self.fc2 = torch.nn.Linear(D_HID, n_actions)

    def forward(self, ctx_ids: torch.Tensor, state_id: torch.Tensor) -> torch.Tensor:
        x = self.emb(ctx_ids).mean(dim=1)
        s = self.state_emb(state_id)
        h = torch.relu(self.fc1(torch.cat([x, s], dim=-1)))
        return self.fc2(h)


def train(epochs: int = 200) -> None:
    torch.manual_seed(SEED)
    engine = HierarchicalEngine()
    quotes = extract_quotes()
    candidates = build_candidates(quotes, engine)
    samples = build_dataset(quotes, engine, candidates)
    print(f"[filler] 台词 {len(quotes)} 条 → 标注样本 {len(samples)} 条，候选动作 {len(candidates)} 个")

    tokenizer = BPETokenizer.load(CKPT_DIR / "tokenizer_swa_希儿.json")
    model = FillerNet(tokenizer.vocab_size, len(STATES), len(candidates))
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[filler] 网络参数: {n_params:,}（vocab={tokenizer.vocab_size}, 状态={len(STATES)}, 动作候选={len(candidates)}）")

    ctx = torch.tensor([s[1] for s in samples], dtype=torch.long)
    st = torch.tensor([s[0] for s in samples], dtype=torch.long)
    act = torch.tensor([s[2] for s in samples], dtype=torch.long)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.005, weight_decay=0.01)
    criterion = torch.nn.CrossEntropyLoss()

    for epoch in range(1, epochs + 1):
        optimizer.zero_grad()
        logits = model(ctx, st)
        loss = criterion(logits, act)
        loss.backward()
        optimizer.step()
        if epoch % 50 == 0:
            acc = (logits.argmax(-1) == act).float().mean().item()
            print(f"[filler] epoch {epoch}: loss={loss.item():.3f}  acc={acc:.2f}")

    checkpoint = CKPT_DIR / "filler_net.pt"
    torch.save({
        "state_dict": model.state_dict(),
        "candidates": candidates,
        "vocab": tokenizer.vocab,
    }, checkpoint)
    print(f"[filler] 已保存: {checkpoint}")


def eval_net() -> None:
    """对比：网络填词 vs 状态动作域随机。"""
    engine = HierarchicalEngine()
    checkpoint = torch.load(CKPT_DIR / "filler_net.pt", map_location="cpu", weights_only=True)
    candidates = checkpoint["candidates"]
    model = FillerNet(len(checkpoint["vocab"]), len(STATES), len(candidates))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    stoi = {w: i for i, w in enumerate(checkpoint["vocab"])}
    state_names = list(STATES)

    print("=== 网络填词（state → 候选 top3）===")
    for state in state_names:
        ctx = [1, 1, 1, 1, 1, 1, 1, 1]  # 全 pad（无上下文）
        with torch.no_grad():
            logits = model(torch.tensor([ctx], dtype=torch.long),
                           torch.tensor([state_names.index(state)], dtype=torch.long))
        top = logits[0].topk(3)
        picks = [candidates[i] for i in top.indices.tolist()]
        print(f"  [{state}] {' | '.join(picks)}")

    print("\n=== 情境推理（输入台词 → 网络 vs 原引擎）===")
    for q in ["布洛妮娅姐姐，希儿想和你去看海", "有敌人包围了我们",
              "我想永远和你在一起", "那是什么声音"]:
        words = segment(q, engine.seg_vocab)
        ctx_words = [w for w in words if w not in _STOP][-CONTEXT_LEN:]
        ctx_ids = [stoi.get(w, 0) for w in ctx_words]
        ctx_ids = [0] * (CONTEXT_LEN - len(ctx_ids)) + ctx_ids
        state = engine.match_state(q)
        with torch.no_grad():
            logits = model(torch.tensor([ctx_ids], dtype=torch.long),
                           torch.tensor([state_names.index(state)], dtype=torch.long))
        top = logits[0].topk(3)
        picks = [candidates[i] for i in top.indices.tolist()]
        print(f"  {q!r} → [{state}] 网络: {' | '.join(picks)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="填词小网络（第三层）")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--eval", action="store_true")
    args = parser.parse_args()
    if args.train:
        train()
    elif args.eval:
        eval_net()
    else:
        parser.print_help()
