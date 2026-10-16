"""F3 探针的判据用例。

判据门①要求"探针证红"：合成一份**前缀里塞了变化值**的请求体 ⇒ 断言必须红。
做法：把负样本写成 `xfail(strict=True)` 的用例——它**必须失败**（= 闸能红），
若哪天探针不再检出这种病，它会变成 XPASS ⇒ strict 下判为失败（防探针退化）。
想直接看红：`uv run pytest tests/unit/prompt_cache/test_lcp_probe.py -k dirty --runxfail`
"""

import json
from pathlib import Path

import pytest

from tests.unit.prompt_cache.lcp_probe import (
    demo_clean_pairs,
    demo_pairs,
    early_variation_violations,
    first_divergence,
    main,
    segments_from_snapshot,
    summarize,
)


def test_clean_pair_has_no_early_variation() -> None:
    """对照组：差异只在尾部（新增一条消息）⇒ 受保护前缀段零违规。"""
    assert early_variation_violations(demo_clean_pairs()) == []


def test_clean_pair_prefix_hit_cap_is_high() -> None:
    """对照组的前缀命中上限应当很高（分歧在尾部）。"""
    divergence = first_divergence(*demo_clean_pairs()[0])
    assert divergence.segment_label.startswith("msg[1]"), divergence.segment_label
    assert divergence.hit_ratio > 0.5, divergence.hit_ratio


def test_probe_locates_divergence_inside_system_segment() -> None:
    """正样本：时间戳在 system 段 ⇒ 首个分歧必须落在 `system`，且偏移恰好是时间戳起点。"""
    previous, current = demo_pairs()[0]
    divergence = first_divergence(previous, current)

    assert divergence.segment_label == "system"
    assert divergence.segment_index == 0
    # 首分歧落在**时间戳内部**（秒数末位），不是时间戳起点——这正是"前缀被打碎"的位置
    assert divergence.offset_in_segment > previous[0].text.index("2026-")
    assert "22:00:0" in divergence.samples[0] and "22:00:0" in divergence.samples[1]
    assert divergence.change_class.startswith("timestamp")


def test_early_change_destroys_prefix_hit_cap() -> None:
    """早期变化 ⇒ 前缀只剩"时间戳之前"那一点点（真正的判据是 prefix_tokens 绝对量）。

    注：合成样本很短，比例不会极端；真实系统提示有几千 token 时，14 token 的前缀等于全废。
    """
    divergence = first_divergence(*demo_pairs()[0])
    assert divergence.prefix_tokens < 20, divergence.prefix_tokens
    assert divergence.hit_ratio < 0.5, f"前缀命中上限 {divergence.hit_ratio:.1%} 不该这么高"
    assert divergence.recompute_tokens > 0


def test_summarize_reports_first_divergence_and_sources() -> None:
    """可复算报告的三个必备输出：首分歧位置、变化源 top-k、最毒一处。"""
    text = summarize(demo_pairs() + demo_clean_pairs())
    assert "首分歧 token≈" in text
    assert "变化源 top-k" in text
    assert "timestamp" in text
    assert "最毒的一处" in text


def test_cli_exit_code_is_the_gate() -> None:
    """命令行的退出码即闸：脏样本 1、干净样本 0（可直接接进 CI/巡检）。"""
    assert main(["--demo"]) == 1
    assert main(["--clean"]) == 0


def test_snapshot_loader_tolerates_shapes() -> None:
    """语料模式的形状容错：system / tools / messages（含 list-of-blocks）都要能读。"""
    payload = {
        "system_prompt": "你是麦麦",
        "tools": [{"name": "send_text"}],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "在吗"}]},
            {"role": "assistant", "content": "在的", "name": "bot"},
        ],
    }
    segments = segments_from_snapshot(payload)
    assert [seg.label for seg in segments] == ["system", "tools", "msg[0]:user", "msg[1]:assistant"]
    assert "在吗" in segments[2].text


def test_snapshot_dir_mode_is_reproducible(tmp_path: Path) -> None:
    """复算命令的语料模式：同任务两份相邻快照 ⇒ 报告首分歧（system 里塞了时间戳）。

    夹具带 `request_kind`（**新语料的正常形状**）。没有它时探针只能按内容签名兜底分组，而
    "最长段里含变化值"会把同一任务切成两组（2026-10-16 实测撞到）⇒ 结论：新语料必须带
    `request_kind`，兜底签名只是老语料的应急手段。
    """
    for index, stamp in enumerate(("2026-10-16T22:00:00", "2026-10-16T22:00:07")):
        (tmp_path / f"{index:03d}.json").write_text(
            json.dumps(
                {
                    "request_kind": "maisaka.replyer",
                    "system_prompt": f"当前时间 {stamp}",
                    "messages": [{"role": "user", "content": "在吗"}],
                }
            ),
            encoding="utf-8",
        )
    assert main([str(tmp_path)]) == 1


@pytest.mark.xfail(strict=True, reason="负样本：证明闸能红——system 段里塞了每轮变化的时间戳")
def test_dirty_pair_is_flagged(  # noqa: D103 - 负样本，意图写在 xfail reason 与文件头
) -> None:
    """**证红**：这份合成请求体的前缀段里有变化值 ⇒ "受保护前缀段零违规"这条断言必须失败。"""
    assert early_variation_violations(demo_pairs()) == []
