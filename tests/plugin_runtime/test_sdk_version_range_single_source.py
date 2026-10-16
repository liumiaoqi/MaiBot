"""`sdk-range-consolidate` 的判据：**一个来源 + 零散落 + 定义自身非空**（2026-10-17）。

## 为什么有这条
同一个概念（宿主支持的 SDK 版本区间）原先有**两套值、两处判定**（v1 `envelope.py` / v2 `servicer.py`）
⇒ 走哪条路径决定被哪套卡。收口后：**数值与判定都只有一处**（`src.common.sdk_version_range`）。

## 三条判据（缺一不算）
- **(乙1) 定义自身非空且可解析** —— 今晚那族教训：只查"消费者对不对"、不查"数据源本身非空"的检查器，
  会在源为空时**静默全过**；
- **(乙2) 零散落** —— 特征值 `"2.99.99"` / `"5.0.0"` 在 `src/` 里**只允许出现在共享模块**（机械扫描）；
- **(乙3) 两代仍**不**合并** —— v1 `[1.0.0, 2.99.99]`（闭）与 v2 `[4.0.0, 5.0.0)`（半开）**必须不同**：
  合并当天 v2 runner 自报的 `4.0.0` 会落在 v1 区间之外 ⇒ v2 全红（见共享模块 docstring）。
"""

from pathlib import Path

from src.common.sdk_version_range import (
    V1_MAX_SDK_VERSION,
    V1_MIN_SDK_VERSION,
    V1_SDK_VERSION_FALLBACK,
    V2_MAX_SDK_VERSION,
    V2_MIN_SDK_VERSION,
    V2_SDK_VERSION_DEFAULT,
    assert_definitions_are_valid,
    parse_version_tuple,
    sdk_version_verdict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_MODULE_NAME = "sdk_version_range.py"
#: 只认**特征值**：1.0.0 / 4.0.0 与协议版本、宿主版本等概念共用字面量，拿来当散落判据会误报。
DISTINCTIVE_LITERALS = ('"2.99.99"', '"5.0.0"')


def test_definitions_are_non_empty_and_parseable() -> None:
    """**(乙1)** 定义自身非空且可解析（导入时已断言一次；这里再显式钉一遍）。"""

    assert_definitions_are_valid()

    for label, value in (
        ("v1 min", V1_MIN_SDK_VERSION),
        ("v1 max", V1_MAX_SDK_VERSION),
        ("v1 fallback", V1_SDK_VERSION_FALLBACK),
        ("v2 min", V2_MIN_SDK_VERSION),
        ("v2 max", V2_MAX_SDK_VERSION),
        ("v2 default", V2_SDK_VERSION_DEFAULT),
    ):
        assert str(value).strip(), f"{label} 为空 —— '抽取型检查'最怕这个"
        assert parse_version_tuple(value), f"{label} 不可解析：{value!r}"


def test_bounds_live_in_exactly_one_place() -> None:
    """**(乙2)** 零散落：特征边界值在 `src/` 里只出现在共享模块。"""

    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        if path.name == SHARED_MODULE_NAME:
            continue
        text = path.read_text(encoding="utf-8")
        if any(literal in text for literal in DISTINCTIVE_LITERALS):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == [], f"这些文件还留着 SDK 区间的字面量（应收敛到 {SHARED_MODULE_NAME}）：{offenders}"


def test_two_generations_stay_distinct() -> None:
    """**(乙3)** 两代区间**必须不同**（收口是"一个来源"，不是"一个数值"）。"""

    assert (V1_MIN_SDK_VERSION, V1_MAX_SDK_VERSION) != (V2_MIN_SDK_VERSION, V2_MAX_SDK_VERSION)
    # v2 runner 的自报默认值必须落在 **v2** 区间内（收口后仍自洽）；若被改成 v1 号段，这条会红
    v2_default = sdk_version_verdict(
        V2_SDK_VERSION_DEFAULT, min_version=V2_MIN_SDK_VERSION, max_version=V2_MAX_SDK_VERSION, half_open=True
    )
    assert v2_default.allowed and not v2_default.out_of_range, v2_default


def test_v2_default_is_out_of_v1_range_by_design() -> None:
    """反证：v2 的自报默认值在 **v1** 区间之外 —— 这就是"不能合并成一套数字"的硬证据。"""

    verdict = sdk_version_verdict(
        V2_SDK_VERSION_DEFAULT, min_version=V1_MIN_SDK_VERSION, max_version=V1_MAX_SDK_VERSION, half_open=False
    )
    assert verdict.out_of_range and not verdict.allowed, verdict
