"""防回归巡检的判据用例（cache-guardrails）。

三条硬要求各有对应用例：
① **按组**（跨组拼盘会复现 artifact）；
② **证红留档**：合成"变量插在稳定段之前" ⇒ 必须报违规（`xfail(strict=True)` 锁住"必须红"）；
③ **结构检查只提示、不判决**：模块里**不存在**"可切"字段/函数（判决权归 §7.4 的模拟预测）。
"""

import json
from pathlib import Path

import pytest

from tests.unit.prompt_cache.cache_guardrails import audit_corpus, main


def _write_corpus(directory: Path, payloads: list[dict]) -> None:
    for index, payload in enumerate(payloads):
        (directory / f"{index:03d}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )


def _bad_corpus(directory: Path) -> None:
    """变量（时间戳）插在**稳定段（system）里** ⇒ 典型"变量插在稳定段之前"。"""
    _write_corpus(
        directory,
        [
            {
                "request_kind": "maisaka.replyer",
                "system_prompt": f"你是麦麦。当前时间：{stamp}。请自然回复。",
                "messages": [{"role": "user", "content": "在吗"}],
            }
            for stamp in ("2026-10-16T23:00:00", "2026-10-16T23:00:07")
        ],
    )


def _good_corpus(directory: Path) -> None:
    """变量只在**尾部**（新增一条消息）⇒ 前缀全稳。"""
    _write_corpus(
        directory,
        [
            {
                "request_kind": "maisaka.replyer",
                "system_prompt": "你是麦麦。请自然回复。",
                "messages": messages,
            }
            for messages in (
                [{"role": "user", "content": "在吗"}],
                [{"role": "user", "content": "在吗"}, {"role": "assistant", "content": "在的"}],
            )
        ],
    )


def _rita_shaped_corpus(directory: Path) -> None:
    """丽塔形态：稳定人设在前 → 变量 → **变量之后还有指令样文本**（只该报提示）。"""
    body = (
        "你是丽塔。客厅的守护者，优雅而敏锐\n\n你正在观察客厅里的对话。\n\n"
        "对话内容：\n用户：打算几点睡\n\n可能感兴趣的角色：\n1. 银狼\n\n"
        "判断哪些角色会自然想插话。最多选2个，只返回JSON数组。"
    )
    _write_corpus(
        directory,
        [
            {"request_kind": "maisaka.rita", "system_prompt": body, "messages": [{"role": "user", "content": turn}]}
            for turn in ("打算几点睡", "两点吧")
        ],
    )


def test_audit_reports_every_group_separately(tmp_path: Path) -> None:
    """① 按组：两个不同任务必须分成两组，且组数 = 2（跨组不配对）。"""
    _write_corpus(
        tmp_path,
        [
            {"request_kind": "k1", "system_prompt": "A 任务", "messages": [{"role": "user", "content": "1"}]},
            {"request_kind": "k1", "system_prompt": "A 任务", "messages": [{"role": "user", "content": "2"}]},
            {"request_kind": "k2", "system_prompt": "B 任务", "messages": [{"role": "user", "content": "1"}]},
            {"request_kind": "k2", "system_prompt": "B 任务", "messages": [{"role": "user", "content": "2"}]},
        ],
    )
    reports = audit_corpus(tmp_path)
    assert len(reports) == 2
    assert all(report.pairs == 1 for report in reports)


def test_good_corpus_has_no_violation(tmp_path: Path) -> None:
    """对照组：变量在尾部 ⇒ 绊线不报。"""
    _good_corpus(tmp_path)
    assert sum(len(report.violations) for report in audit_corpus(tmp_path)) == 0
    assert main([str(tmp_path)]) == 0


@pytest.mark.xfail(strict=True, reason="证红留档：变量插在稳定段之前必须报违规")
def test_guardrail_red(tmp_path: Path) -> None:
    """② **证红**：合成"变量插在稳定段之前" ⇒ "零违规"这条断言必须失败。

    直看红：`uv run pytest tests/unit/prompt_cache/test_cache_guardrails.py -k guardrail_red --runxfail`
    """
    _bad_corpus(tmp_path)
    assert sum(len(report.violations) for report in audit_corpus(tmp_path)) == 0


def test_guardrail_detects_early_variation(tmp_path: Path) -> None:
    """② 的反面（常态绿）：同一份合成语料，巡检**确实**报出违规，且退出码为 1。"""
    _bad_corpus(tmp_path)
    reports = audit_corpus(tmp_path)
    assert sum(len(report.violations) for report in reports) >= 1
    assert main([str(tmp_path)]) == 1


def test_structure_hint_warns_on_rita_shape(tmp_path: Path) -> None:
    """③ 丽塔形态 ⇒ 报"变量之后还有指令样文本"的**提示**（且提示里写明"仅提示"、不许判决）。"""
    _rita_shaped_corpus(tmp_path)
    reports = audit_corpus(tmp_path)
    assert reports and reports[0].structure_warnings, "丽塔形态必须报提示"
    assert "仅提示" in reports[0].structure_warnings[0], "提示里必须写明'仅提示'，不许给判决"


def test_module_has_no_cuttable_verdict() -> None:
    """③ **检查器只做提示、不做判决**：模块里不存在"可切"字段或函数。"""
    import tests.unit.prompt_cache.cache_guardrails as guardrails

    from tests.unit.prompt_cache.cache_guardrails import GroupReport

    assert not hasattr(GroupReport, "cuttable")
    assert not any("cuttable" in name for name in dir(guardrails))
    assert not any("verdict" in name for name in dir(guardrails))
