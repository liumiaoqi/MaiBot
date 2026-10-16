"""F3 探针：同会话连续两轮请求体的 **token 级 LCP（首个分歧位置）** + 变化源归因。

为什么需要它（问题形式化见 `.shared/research/2026-10/llm_cache_context_1016.md` §F1/F3）：
服务端 prefix cache 的收益由 **first-variation position**（首个分歧位置）决定——分歧越靠前，
能复用的前缀越短；分歧在**系统提示里**时（早期变化）等于全量重算。
本模块只做**客户端可算**的这一半：不需要服务端配合，也不需要真实调用模型。

三种用法：
1. 库里调用：`first_divergence(a, b)` / `summarize(pairs)` / `early_variation_violations(pairs)`
2. 命令行（语料模式）：`python -m tests.unit.prompt_cache.lcp_probe <请求快照目录>`
3. 命令行（合成模式，证红用）：`python -m tests.unit.prompt_cache.lcp_probe --demo`

口径与近似（如实声明）：
- 请求体被规范化成**有序段**（`system` / `tools` / `msg[i]`），段序即请求体顺序；
- "token 级"用本仓自己的估算器（`src/maisaka/context/token_estimator.py::estimate_text`）把
  **公共前缀的字符数**折算成 token 数；字符级 LCP 与 token 级 LCP 单调一致，折算误差来自估算器本身；
- 变化源归类是**模式判定**（时间戳/uuid/计数/文本），只给"最可能的类别"，不当结论用。
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

# ── 变化源模式（只用于"给变化源起个名字"，不是判据） ──
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("timestamp.iso", re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")),
    ("timestamp.clock", re.compile(r"\b\d{2}:\d{2}:\d{2}\b")),
    ("timestamp.date", re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}")),
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("hex_id", re.compile(r"\b[0-9a-f]{16,}\b", re.I)),
    ("long_number", re.compile(r"\b\d{9,}\b")),
)

PROVIDER_CACHE_BLOCK_TOKENS = 64
"""本家（DeepSeek）的缓存块粒度，据 dsh 的 e2e（`packages/core/agent-loop/tests/
request-cache.e2e.ts:24-25`：system prompt 要足够长以跨过供应商的 cache-block granularity）
—— **可以硬编码**（单厂商对齐 DeepSeek，依据 `AGENTS.md §八.3`）。

**可证伪措辞**：若**实测**（从 usage 的 `prompt_cache_hit_tokens` / `cached_tokens` 反推）
与 64 对不上 ⇒ **复核这个数**。不是因为"它会变"，而是因为**观测与断言要对得上**。

**对账判据（尚未实现，留作下一步）**：拿同一会话的**同刻**两组数——① 本探针算出的
`prefix_tokens`（客户端口径）② 服务端上报的缓存命中 token（读账口径）——差值应落在
**一个缓存块以内**（`abs(prefix_tokens - cache_read_tokens) < PROVIDER_CACHE_BLOCK_TOKENS`）。
对不上即说明"我们以为的前缀"与"服务端实际复用的前缀"不是同一段（格式差异 / 块对齐 /
漏看变化源）。⇒ **这条现在只是断言，还没有对账数据**。
"""


@dataclass(frozen=True)
class Segment:
    """请求体里的一个有序段（顺序即请求体顺序）。"""

    label: str
    text: str


@dataclass(frozen=True)
class Divergence:
    """一次两轮对照的分歧画像。"""

    first_diff_chars: int
    """公共前缀的字符数（0 = 第一个字符就不同）。"""
    prefix_tokens: int
    """公共前缀折算的 token 数 = 服务端理论上能命中缓存的量。"""
    segment_label: str
    """首个分歧落在哪一段（`system` / `tools` / `msg[i]` / `""`=完全相同）。"""
    segment_index: int
    """该段在请求体里的序号（0 基）——越靠前越毒。"""
    offset_in_segment: int
    """段内字符偏移。"""
    total_tokens: int
    """后一轮请求体的总 token 估算。"""
    change_class: str
    """变化源模式判定（`timestamp.iso` / `uuid` / `text` …）。"""
    samples: tuple[str, str] = ()
    """两侧在分歧处的片段（截断 60 字符），用于人工核对。"""

    @property
    def recompute_tokens(self) -> int:
        """分歧点之后需要重算的 token（= 缓存省不下来的部分）。"""
        return max(0, self.total_tokens - self.prefix_tokens)

    @property
    def hit_ratio(self) -> float:
        """理论上限意义上的前缀命中率（prefix_tokens / total_tokens）。"""
        return self.prefix_tokens / self.total_tokens if self.total_tokens else 0.0


def _estimate_tokens(text: str) -> int:
    """用本仓估算器折算 token；估算器不可用时退化为"每 2 字符 1 token"（如实标注）。"""
    if not text:
        return 0
    try:
        from src.maisaka.context.token_estimator import estimate_text

        return int(estimate_text(text))
    except Exception:
        return max(1, len(text) // 2)


def _classify(left: str, right: str) -> str:
    """给变化源起个名字：时间戳类 → id 类 → 顺序类 → 内容类（四类，真数据上要能分开）。"""
    for name, pattern in _PATTERNS:
        if pattern.search(left) or pattern.search(right):
            return name
    if len(left) == len(right) and left != right:
        differing = [index for index, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
        # 等长且**只有数字位不同** ⇒ 时间戳/计数/ID 一类（`22:00:00` vs `22:00:07` 这种）
        if differing and all(left[index].isdigit() and right[index].isdigit() for index in differing):
            return "numeric_value"
        # 字符多集相同、次序不同 ⇒ **集合顺序类**（工具表/清单重排）
        if sorted(left) == sorted(right):
            return "set_order"
        return "same_length_content"
    return "content"


def first_divergence(previous: Sequence[Segment], current: Sequence[Segment]) -> Divergence:
    """两轮请求体对照：算出公共前缀长度、首个分歧段、变化源类别。"""
    # 段级：找出第一对"标签相同但内容不同"或"标签不同"的段
    segment_label = ""
    segment_index = -1
    offset_in_segment = 0
    left_sample = ""
    right_sample = ""
    chars_before = 0

    for index, (prev_seg, curr_seg) in enumerate(zip(previous, current, strict=False)):
        if prev_seg.label != curr_seg.label or prev_seg.text != curr_seg.text:
            segment_label = curr_seg.label
            segment_index = index
            left_text, right_text = prev_seg.text, curr_seg.text
            # 段内：逐字符找首个不同
            limit = min(len(left_text), len(right_text))
            offset = limit
            for position in range(limit):
                if left_text[position] != right_text[position]:
                    offset = position
                    break
            offset_in_segment = offset
            left_sample = left_text[max(0, offset - 20) : offset + 40]
            right_sample = right_text[max(0, offset - 20) : offset + 40]
            break
        chars_before += len(curr_seg.text)
    else:
        # 公共段全同：差异在**长度**上——最常见的就是"尾部追加了一条消息"
        if len(current) > len(previous):
            segment_index = len(previous)
            segment_label = current[segment_index].label
            offset_in_segment = 0
            right_sample = current[segment_index].text[:60]
        elif len(current) < len(previous):
            segment_index = len(current)
            segment_label = f"-{previous[segment_index].label}"
            offset_in_segment = 0
            left_sample = previous[segment_index].text[:60]

    if segment_index < 0:
        # 完全一致（或前一段是另一段的前缀）
        chars_before = sum(len(seg.text) for seg in current)
        first_diff_chars = chars_before
    else:
        first_diff_chars = chars_before + offset_in_segment

    total_text = "".join(seg.text for seg in current)
    prefix_text = total_text[:first_diff_chars]
    return Divergence(
        first_diff_chars=first_diff_chars,
        prefix_tokens=_estimate_tokens(prefix_text),
        segment_label=segment_label,
        segment_index=segment_index,
        offset_in_segment=offset_in_segment,
        total_tokens=_estimate_tokens(total_text),
        change_class="identical" if segment_index < 0 else _classify(left_sample, right_sample),
        samples=(left_sample, right_sample),
    )


def early_variation_violations(
    pairs: Iterable[tuple[Sequence[Segment], Sequence[Segment]]],
    *,
    protected_prefix_labels: Sequence[str] = ("system", "tools"),
) -> list[str]:
    """**闸**：受保护前缀段（默认 system/tools）里出现变化 ⇒ 报违规。

    这是本探针唯一"判好坏"的地方：前缀段必须逐字节稳定。
    """
    violations: list[str] = []
    for index, (previous, current) in enumerate(pairs):
        divergence = first_divergence(previous, current)
        if divergence.segment_label and divergence.segment_label in protected_prefix_labels:
            violations.append(
                f"第 {index} 对：首个分歧落在受保护前缀段 `{divergence.segment_label}`"
                f"（段内偏移 {divergence.offset_in_segment}，变化源疑似 {divergence.change_class}）"
                f" ⇒ 前缀命中率理论上限 {divergence.hit_ratio:.1%}，需重算 {divergence.recompute_tokens} token"
            )
    return violations


def summarize(pairs: Sequence[tuple[Sequence[Segment], Sequence[Segment]]]) -> str:
    """跑一次给"首分歧位置 + 变化源 top-k"的可读报告。"""
    lines: list[str] = []
    lines.append(f"对照轮数: {len(pairs)}")
    sources: dict[str, int] = {}
    per_pair: list[Divergence] = []
    for index, (previous, current) in enumerate(pairs):
        divergence = first_divergence(previous, current)
        per_pair.append(divergence)
        sources[divergence.change_class] = sources.get(divergence.change_class, 0) + 1
        lines.append(
            f"[{index}] 首分歧 token≈{divergence.prefix_tokens} / 总≈{divergence.total_tokens}"
            f" | 段={divergence.segment_label or '-'}(#{divergence.segment_index})"
            f" | 变化源={divergence.change_class}"
            f" | 需重算≈{divergence.recompute_tokens} token | 前缀命中上限≈{divergence.hit_ratio:.1%}"
        )
        if divergence.samples[0] or divergence.samples[1]:
            lines.append(f"      左: {divergence.samples[0]!r}")
            lines.append(f"      右: {divergence.samples[1]!r}")

    ranked = sorted(sources.items(), key=lambda item: (-item[1], item[0]))
    lines.append("")
    lines.append("变化源 top-k（按出现次数）:")
    for name, count in ranked:
        lines.append(f"  - {name}: {count}")

    worst = min(per_pair, key=lambda item: item.prefix_tokens, default=None)
    if worst is not None:
        lines.append("")
        lines.append(
            f"最毒的一处：段 `{worst.segment_label or '-'}` 段内偏移 {worst.offset_in_segment}"
            f"（变化源 {worst.change_class}）——分歧越靠前，重算越多"
        )

    lines.append("")
    lines.append(f"缓存块粒度：{PROVIDER_CACHE_BLOCK_TOKENS} token/块（本家 DeepSeek 粒度，据 dsh e2e）")
    zero_block = [index for index, item in enumerate(per_pair) if reusable_blocks(item.prefix_tokens) == 0]
    if zero_block:
        lines.append(
            f"  ⚠️ {len(zero_block)} 对连一个完整缓存块都凑不满（前缀 < {PROVIDER_CACHE_BLOCK_TOKENS} token "
            f"就分歧）⇒ 这些请求的缓存收益为 0（不是『变少』）：{zero_block}"
        )
    else:
        lines.append(f"  最小可复用块数：{min((reusable_blocks(item.prefix_tokens) for item in per_pair), default=0)}")
    return "\n".join(lines)


def reusable_blocks(prefix_tokens: int, *, block_tokens: int = PROVIDER_CACHE_BLOCK_TOKENS) -> int:
    """存活前缀能凑出几个**完整**缓存块（不足一块 ⇒ 服务端无从复用，收益为 0）。"""
    if prefix_tokens <= 0:
        return 0
    return prefix_tokens // block_tokens


# ── 语料模式：读请求快照（形状容错；真机语料未在本机验证） ──


def _message_text(message: Any) -> str:
    """把一条消息压成文本（容忍 str / list-of-blocks / 带 tool_calls 的形状）。"""
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return str(message)
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
    elif content is not None:
        parts.append(str(content))
    for key in ("tool_calls", "tool_call_id", "name", "role"):
        if message.get(key) is not None:
            parts.append(f"{key}={message.get(key)}")
    return "\n".join(parts)


def segments_from_snapshot(payload: dict[str, Any]) -> list[Segment]:
    """把一份请求快照变成有序段。"""
    segments: list[Segment] = []
    system_prompt = payload.get("system_prompt") or payload.get("system")
    if system_prompt:
        segments.append(Segment("system", str(system_prompt)))
    tools = payload.get("tools") or payload.get("tool_options")
    if tools:
        segments.append(Segment("tools", json.dumps(tools, ensure_ascii=False, default=str, sort_keys=False)))
    messages = payload.get("messages") or []
    for index, message in enumerate(messages):
        role = message.get("role") if isinstance(message, dict) else ""
        segments.append(Segment(f"msg[{index}]:{role}", _message_text(message)))
    return segments


_GENERIC_KINDS = frozenset({"", "response", "request", "default", "unknown"})
"""粗默认值——**不是任务名**：2026-10-16 实测语料里 `request_kind` 24/24 全是 `"response"`
⇒ 按它分组等于没分组（跨任务配对被当成 0% 前缀，属 artifact）。"""


def _strip_dynamic(text: str) -> str:
    """去掉动态值（数字串/长十六进制）——它们每轮都变，留在签名里会把同一任务切成多组。"""
    return re.sub(r"[0-9a-fA-F]{6,}|\d+", "#", text)


def _tool_names(tools: Any) -> list[str]:
    """工具名集合（有无/几个/叫什么——区分"带工具的大请求"与"主对话"的关键字段）。"""
    names: list[str] = []
    if isinstance(tools, list):
        for item in tools:
            if not isinstance(item, dict):
                continue
            function = item.get("function")
            name = item.get("name") or (function.get("name") if isinstance(function, dict) else None)
            if name:
                names.append(str(name))
    return sorted(names)


def _head_text(payload: dict[str, Any], segments: Sequence[Segment]) -> str:
    """任务头部文本：优先 `system_prompt`，为空则退**最长段**（通常是系统/人设/指令块）。"""
    system_prompt = str(payload.get("system_prompt") or "").strip()
    if system_prompt:
        return system_prompt
    return max((segment.text.strip() for segment in segments), key=len, default="")


def group_key(payload: dict[str, Any], segments: Sequence[Segment]) -> str:
    """分组键：**组合可见字段**，且**可读**（每行本身就是"这组是什么任务"的判据）。

    组成（照 lead 2026-10-16 的建议）：
      ① 任务头部前若干行，**去动态值**（数字/长 hex → `#`）；
      ② **工具名集合**（有无/几个/前三个名字）；
      ③ **前 3 条消息的 role 序列**。
    另：`request_kind` 只在不属粗默认值时才用（见 `_GENERIC_KINDS`）。
    """
    kind = str(payload.get("request_kind") or "").strip()
    if kind.lower() not in _GENERIC_KINDS:
        return f"kind:{kind}"

    head = _strip_dynamic("\n".join(_head_text(payload, segments).splitlines()[:3]))[:80].replace("\n", "⏎")
    names = _tool_names(payload.get("tools"))
    tools_part = f"{len(names)}[{','.join(names[:3])}]" if names else "0"
    roles = ",".join(str((m or {}).get("role", "")) for m in (payload.get("messages") or [])[:3])
    return f"head:{head} | tools:{tools_part} | roles:{roles}"


def group_pairs_from_snapshot_dir(directory: Path) -> dict[str, list[tuple[list[Segment], list[Segment]]]]:
    """**先按任务分组、组内再配相邻轮** —— 跨任务的 LCP 没有意义（2026-10-16 真数据实测教训）。"""
    grouped: dict[str, list[list[Segment]]] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        segments = segments_from_snapshot(payload)
        grouped.setdefault(group_key(payload, segments), []).append(segments)

    return {key: list(zip(group, group[1:], strict=False)) for key, group in grouped.items()}


def pairs_from_snapshot_dir(directory: Path) -> list[tuple[list[Segment], list[Segment]]]:
    """组内相邻轮拉平（保留旧接口；分组信息用 `group_pairs_from_snapshot_dir`）。"""
    grouped = group_pairs_from_snapshot_dir(directory)
    return [pair for group in grouped.values() for pair in group]


# ── 合成模式（证红用）：前缀里塞了每轮变化的值 ──


def demo_pairs() -> list[tuple[list[Segment], list[Segment]]]:
    """一对合成对照：唯一差异是 **system 段里的时间戳**（典型早期变化）。"""
    base = [
        Segment("system", "你是麦麦。当前时间：{ts}。请自然回复。"),
        Segment("tools", '[{"name": "send_text"}]'),
        Segment("msg[0]:user", "在吗"),
    ]
    previous = [Segment(seg.label, seg.text.replace("{ts}", "2026-10-16 22:00:00")) for seg in base]
    current = [Segment(seg.label, seg.text.replace("{ts}", "2026-10-16 22:00:07")) for seg in base]
    return [(previous, current)]


def demo_clean_pairs() -> list[tuple[list[Segment], list[Segment]]]:
    """一对**干净**对照：差异只在尾部（新增一条 user 消息）——前缀全稳。"""
    prefix = [Segment("system", "你是麦麦。请自然回复。"), Segment("tools", '[{"name": "send_text"}]')]
    previous = prefix + [Segment("msg[0]:user", "在吗")]
    current = prefix + [Segment("msg[0]:user", "在吗"), Segment("msg[1]:assistant", "在的")]
    return [(previous, current)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提示前缀 token 级 LCP 探针（首分歧位置 + 变化源 top-k）")
    parser.add_argument("snapshot_dir", nargs="?", help="请求快照目录（*.json，按文件名排序当连续两轮）")
    parser.add_argument("--demo", action="store_true", help="用合成的『前缀塞变化值』样本跑一遍（证红）")
    parser.add_argument("--clean", action="store_true", help="用合成的『干净样本』跑一遍（对照组）")
    args = parser.parse_args(argv)

    if args.demo:
        pairs = demo_pairs()
    elif args.clean:
        pairs = demo_clean_pairs()
    elif args.snapshot_dir:
        grouped = group_pairs_from_snapshot_dir(Path(args.snapshot_dir))
        pairs = [pair for group in grouped.values() for pair in group]
        print(f"按任务分组: {len(grouped)} 组（跨任务不配对）")
        for key, group in sorted(grouped.items(), key=lambda item: -len(item[1])):
            print(f"  - {key}: {len(group)} 对")
    else:
        parser.error("给一个快照目录，或用 --demo / --clean")

    print(summarize(pairs))
    violations = early_variation_violations(pairs)
    print("")
    print(f"受保护前缀段违规: {len(violations)}")
    for item in violations:
        print(f"  ✗ {item}")
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover - 命令行入口
    raise SystemExit(main())
