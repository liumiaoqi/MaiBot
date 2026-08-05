"""分层风格引擎：状态机（推理）+ 句式模板（预装）+ n-gram 填词（查表）。

设计（lmq 2026-08-06，基于"预装 vs 从零"认知）：
- 人类学语言 = 进化预装 + 后天校准；随机初始化神经网络 = 从零 → 8 实验失败
- 解法：给机器预装结构，网络/查表只做局部"填充"
- 三层：
  1. 状态机（手写规则）：意图/关键词 → 角色状态（依赖/战斗/温柔/日常）
  2. 句式模板（预装词库 + 台词句式）：每个状态一组模板，{槽位}待填
  3. 填词（n-gram 条件分布查表）：模板上下文词 → 最高频候选

"推理"= 状态机选择（确定性、可解释）；"生成"= 模板 + 查表（不会复读/黑洞，
因为输出空间 = 模板结构 × 词库候选，不是自由 next-token）。

用法：
  uv run python hierarchical_engine.py --reply "布洛妮娅她受伤了"   # 关键词 → 状态 → 回复
  uv run python hierarchical_engine.py --intent combat              # 直接指定意图
  uv run python hierarchical_engine.py --demo                       # 多种输入演示
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

from bpe_tokenizer import _WORD_PATTERN

ENGINE_DIR = Path(__file__).resolve().parent / "engines"

_END_PUNCT = "。！？…~"
_PUNCT_ONLY = re.compile(r"^[^\w一-鿿]+$")

# 角色名词库（填 {name} 槽位）——希儿的关系网络
NAMES = ["布洛妮娅", "姐姐", "希儿", "Veliona", "琪亚娜", "芽衣", "可可利亚"]


def segment(text: str, vocab: set[str], max_word: int = 4) -> list[str]:
    """词库最长匹配分词：连续中文串按词库词切，最长 max_word 字，单字兜底。

    原因：_WORD_PATTERN 把连续汉字串切成一个块（无标点分隔），
    {word} 槽位需要真"词"粒度——用词库做最长匹配（不引外部依赖）。"""
    out: list[str] = []
    i = 0
    while i < len(text):
        matched = False
        for end in range(min(len(text), i + max_word), i, -1):
            if text[i:end] in vocab:
                out.append(text[i:end])
                i = end
                matched = True
                break
        if not matched:
            out.append(text[i])
            i += 1
    return out

# ── 状态机：意图/关键词 → 状态 → 模板组 + 动作域 ────────────────
STATES = {
    "依赖": {
        "keywords": ["布洛妮娅", "姐姐", "她", "他", "受伤", "疼", "病", "哭了"],
        "actions": ["陪着", "做到", "等着", "相信", "不会离开"],
        "templates": [
            "布洛妮娅姐姐，{action}。",
            "姐姐……{action}。",
            "布洛妮娅姐姐，希儿{action}。",
        ],
    },
    "战斗": {
        "keywords": ["战斗", "敌人", "打", "欺负", "伤害", "杀", "碰", "抢", "追"],
        "actions": ["不会放过", "保护", "战斗", "守护", "反击"],
        "templates": [
            "哼。{action}！",
            "别过来——{action}！",
            "{name}，希儿不会让任何人{action}的。",
        ],
    },
    "温柔": {
        "keywords": ["守护", "保护", "想要", "永远", "一起", "爱"],
        "actions": ["守护", "保护", "相信", "陪着", "一直在一起"],
        "templates": [
            "希儿会{action}的。",
            "{name}，希儿会{action}的。",
            "希儿想要{action}。",
        ],
    },
    "警戒": {
        "keywords": ["谁", "什么", "奇怪", "危险", "小心"],
        "actions": ["是谁", "有危险", "小心", "交给我"],
        "templates": [
            "嗯？{action}……",
            "小心——{action}！",
            "希儿感觉到了，{action}。",
        ],
    },
    "日常": {
        "keywords": [],
        "actions": ["去看看", "一起去", "想想", "出去走走", "等着"],
        "templates": [
            "{word}……{action}。",
            "今天{word}，{action}。",
        ],
    },
}


class HierarchicalEngine:
    """分层引擎：意图 → 状态 → 模板 → 填词。"""

    def __init__(self, character: str = "希儿") -> None:
        self.character = character
        # 分词词库：角色词库 + 角色名 + n-gram 表全部词（最长匹配）
        vocab_path = Path(__file__).resolve().parent / "vocab" / f"role_{character}.txt"
        self.seg_vocab = set(NAMES)
        if vocab_path.exists():
            self.seg_vocab.update(
                line.strip() for line in vocab_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#"))
        path = ENGINE_DIR / f"style_{character}.json"
        if not path.exists():
            raise SystemExit(f"n-gram 表不存在，先跑 style_engine.py --build: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.bigram: dict[str, dict[str, int]] = payload["bigram"]
        self.trigram: dict[tuple[str, str], dict[str, int]] = {
            tuple(k.split("")): v for k, v in payload["trigram"].items()
        }
        self.high_freq: list[str] = payload["high_freq"]
        # BPE tokenizer 的 vocab 补进分词词库（merges 已把高频组合合并成 token，
        # "下层区""今天"这类词在 vocab 里，最长匹配就能切出来）
        tok_path = Path(__file__).resolve().parent / "checkpoints" / f"tokenizer_swa_{character}.json"
        if tok_path.exists():
            payload = json.loads(tok_path.read_text(encoding="utf-8"))
            for w in payload.get("vocab", []):
                if w and w != "<unk>" and len(w) > 1:
                    self.seg_vocab.add(w)
        for w in self.bigram:
            self.seg_vocab.add(w)
            self.seg_vocab.update(self.bigram[w])
        self.seg_vocab.discard(" ")  # 过滤空白

    # ── 状态机 ────────────────────────────────────────────────────

    def match_state(self, intent: str, context: str = "") -> str:
        """意图/上下文关键词 → 状态名（首个命中的状态）。"""
        text = f"{intent} {context}"
        for state, spec in STATES.items():
            if any(kw in text for kw in spec["keywords"]):
                return state
        return "日常"

    # ── 填词（n-gram 条件分布查表）──────────────────────────────

    def _fill_action(self, state: str, context_words: list[str]) -> str:
        """{action} 槽位：状态动作域优先（语义约束），n-gram 条件分布补充，
        两者都没有才随机。"""
        actions = STATES[state]["actions"]
        # 1) 上下文词在动作域里 → 直接用
        for w in context_words:
            if w in actions:
                return w
        # 2) n-gram 条件分布 top（跟模板上下文相关）
        if len(context_words) >= 2:
            cand = self.trigram.get((context_words[-2], context_words[-1]))
            if cand:
                top = self._top_word(cand)
                if top and top not in NAMES:
                    return top
        if context_words:
            cand = self.bigram.get(context_words[-1])
            if cand:
                top = self._top_word(cand)
                if top and top not in NAMES:
                    return top
        # 3) 状态动作域随机
        return random.choice(actions)

    def _fill_word(self, context_words: list[str]) -> str:
        """{word} 槽位：优先输入里的实词（非标点非角色名），n-gram 查表补充，
        兜底状态相关词（避免高频词漂移）。"""
        for w in reversed(context_words):
            if (not _PUNCT_ONLY.match(w) and w not in NAMES
                    and w not in "的了她是在想要今天我去来"):
                return w
        return "下层区"

    def _top_word(self, candidates: dict[str, int]) -> str | None:
        """候选最高频实词（跳过纯标点）。"""
        for w, _ in sorted(candidates.items(), key=lambda x: -x[1]):
            if not _PUNCT_ONLY.match(w) and w not in "的了她是在":
                return w
        return None

    # ── 生成 ─────────────────────────────────────────────────────

    def reply(self, intent: str, context: str = "", seed: int | None = None) -> str:
        """完整流程：状态机 → 模板 → 填词 → 角色回复。"""
        rng = random.Random(seed)
        state = self.match_state(intent, context)
        templates = STATES[state]["templates"]
        template = templates[rng.randrange(len(templates))]
        return self._fill(template, state, intent, context)

    def _fill(self, template: str, state: str, intent: str, context: str) -> str:
        """模板槽位填充。"""
        context_words = segment(f"{intent} {context}", self.seg_vocab)
        out = template
        # {action} 槽位
        if "{action}" in out:
            out = out.replace("{action}", self._fill_action(state, context_words), 1)
        # {name} 槽位：状态相关的角色名（依赖态 → 布洛妮娅）
        if "{name}" in out:
            name = "布洛妮娅" if state == "依赖" and "布洛妮娅" in context_words else \
                   (context_words[0] if context_words and context_words[0] in NAMES else "希儿")
            out = out.replace("{name}", name, 1)
        # {word} 槽位
        if "{word}" in out:
            out = out.replace("{word}", self._fill_word(context_words), 1)
        return out


def demo() -> None:
    engine = HierarchicalEngine()
    cases = [
        ("布洛妮娅姐姐受伤了", "她需要我"),
        ("敌人来了", ""),
        ("我想守护你", ""),
        ("今天去下层区吧", ""),
        ("小心！", ""),
        ("布洛妮娅回来了", "我等你很久了"),
    ]
    print("=== 分层引擎 demo（意图 → 状态 → 回复）===")
    for intent, context in cases:
        state = engine.match_state(intent, context)
        reply = engine.reply(intent, context)
        print(f"  输入: {intent!r} {context!r}  →  [{state}] {reply}")


def main() -> None:
    parser = argparse.ArgumentParser(description="分层风格引擎（状态机 + 模板 + 填词）")
    parser.add_argument("--reply", type=str, default="", help="输入对话（关键词 → 状态 → 回复）")
    parser.add_argument("--context", type=str, default="", help="上下文补充")
    parser.add_argument("--intent", type=str, default="", help="直接指定意图关键词")
    parser.add_argument("--demo", action="store_true", help="多输入演示")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.reply or args.intent:
        engine = HierarchicalEngine()
        intent = args.intent or args.reply
        state = engine.match_state(intent, args.context)
        print(f"[{state}] {engine.reply(intent, args.context)}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
