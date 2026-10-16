"""防回归巡检（cache-guardrails，2026-10-16）——**不进生产代码、不改提示词**。

**下一个人在动提示词前先跑这一条**：

    uv run python -m tests.unit.prompt_cache.cache_guardrails <语料目录>

三条抓手（对应 `.shared/research/2026-10/llm_cache_context_1016.md` §7.6）：
① **绊线**：**按组**报首分歧位置与"前缀段违规"——跨组拼盘会复现 artifact（2026-10-16 实测教训：
   `tools` 段 0% 那 5 处全是跨任务配对的假阳性）；
② **结构提示**：报"**变量样文本之后还有指令样文本**"的组——⛔ **只提示、不判决**：
   判"可切"必须走 §7.4 的**模拟预测**（净位移能提升多少），否则会像"收益分"一样骗人（丽塔就是反例）；
③ **判据口径**：本脚本只提供**位置事实**（首分歧 token / 段 / 变化源），用于给既有
   `theoretical_prompt_cache_hit_*` 补"分歧在哪里"，**不是**另加一列命中率。

**证红方式（留档）**：

    uv run pytest tests/unit/prompt_cache/test_cache_guardrails.py -k guardrail_red --runxfail

（合成"变量插在稳定段之前"的语料 ⇒ 必须报违规；常态跑里该用例是 `xfail(strict=True)`，
即"必须红"被永久锁住——探针一旦不再检出，strict 会让它变成失败。）
"""

import argparse
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from tests.unit.prompt_cache.lcp_probe import (
    Segment,
    early_variation_violations,
    first_divergence,
    group_key,
    segments_from_snapshot,
)

# "变量样"文本：这些标记之后的正文通常逐轮变化
_VARIABLE_MARKERS = (
    "对话内容：",
    "用户：",
    "目标用户发言",
    "用户原始发言",
    "机器人回复",
    "当前时间",
    "当前情绪",
)
# "指令样"文本：这些词通常出现在**稳定指令**里
_INSTRUCTION_HINT = re.compile(r"(^|\n)\s*(请|判断|不要|最多|只|注意|输出|严格)")
_JSON_HINT = re.compile(r"JSON|json")


@dataclass
class GroupReport:
    """一个任务组的位置事实 + 两类提示（**没有"可切"字段**——判决权不在这里）。"""

    key: str
    requests: int
    pairs: int
    prefix_min: int = 0
    prefix_median: float = 0.0
    prefix_max: int = 0
    cap_median: float = 0.0
    diverge_segments: tuple[str, ...] = ()
    violations: list[str] = field(default_factory=list)
    structure_warnings: list[str] = field(default_factory=list)


def _group_segments(directory: Path) -> dict[str, list[list[Segment]]]:
    groups: dict[str, list[list[Segment]]] = {}
    for path in sorted(directory.glob("*.json")):
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        segments = segments_from_snapshot(payload)
        groups.setdefault(group_key(payload, segments), []).append(segments)
    return groups


def structure_hints(segments: Sequence[Segment]) -> list[str]:
    """**只提示**：变量样文本之后是否还有指令样文本（丽塔那种形态）。

    返回人话提示；**不返回任何"可切/不可切"的判定**——判决要靠 §7.4 的模拟预测。
    """
    hints: list[str] = []
    for segment in segments:
        text = segment.text
        first_variable = min(
            (text.find(marker) for marker in _VARIABLE_MARKERS if text.find(marker) >= 0),
            default=-1,
        )
        if first_variable < 0:
            continue
        tail = text[first_variable:]
        after = [match.start() for match in _INSTRUCTION_HINT.finditer(tail)]
        if after or _JSON_HINT.search(tail):
            count = len(after) + (1 if _JSON_HINT.search(tail) else 0)
            hints.append(
                f"段 `{segment.label}`：变量样文本之后还有 {count} 处指令样文本"
                f"（⚠️ 仅提示：这类形态可能把稳定指令挤到变量之后；**是否可切须先跑 §7.4 模拟**）"
            )
            break
    return hints


def audit_corpus(directory: Path) -> list[GroupReport]:
    """按组巡检：位置事实 + 前缀段违规（**绊线**）+ 结构提示。"""
    reports: list[GroupReport] = []
    for key, seglist in sorted(_group_segments(directory).items(), key=lambda item: -len(item[1])):
        pairs = list(zip(seglist, seglist[1:], strict=False))
        divergences = [first_divergence(a, b) for a, b in pairs]
        prefixes = [item.prefix_tokens for item in divergences]
        report = GroupReport(
            key=key,
            requests=len(seglist),
            pairs=len(pairs),
            prefix_min=min(prefixes, default=0),
            prefix_median=statistics.median(prefixes) if prefixes else 0.0,
            prefix_max=max(prefixes, default=0),
            cap_median=round(
                statistics.median([item.hit_ratio for item in divergences]) * 100, 1
            )
            if divergences
            else 0.0,
            diverge_segments=tuple(sorted({item.segment_label or "(相同)" for item in divergences})),
            violations=early_variation_violations(pairs),
            structure_warnings=structure_hints(seglist[0]) if seglist else [],
        )
        reports.append(report)
    return reports


def render(reports: Sequence[GroupReport]) -> str:
    lines = ["按任务分组巡检（跨组不配对）："]
    for report in reports:
        lines.append(
            f"\n- {report.key[:66]}"
            f"\n  请求 {report.requests} · 对 {report.pairs} · 首分歧 token {report.prefix_min}/{report.prefix_median}/{report.prefix_max}"
            f" · 命中上限中位 {report.cap_median}%"
            f"\n  分歧落点段: {', '.join(report.diverge_segments) or '—'}"
        )
        for warning in report.structure_warnings:
            lines.append(f"  [提示] {warning}")
        for violation in report.violations:
            lines.append(f"  [违规] {violation}")
    total = sum(len(report.violations) for report in reports)
    lines.append(f"\n前缀段违规合计: {total}（0 = 没有『变量插在稳定段之前』这类病）")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="缓存前缀防回归巡检（按组）")
    parser.add_argument("corpus_dir", help="语料目录（*.json，含 request_kind 或按内容签名分组）")
    args = parser.parse_args(argv)
    reports = audit_corpus(Path(args.corpus_dir))
    print(render(reports))
    return 1 if sum(len(report.violations) for report in reports) else 0


if __name__ == "__main__":  # pragma: no cover - 命令行入口
    raise SystemExit(main())
