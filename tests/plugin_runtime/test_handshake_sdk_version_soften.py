"""第 3 道闸门（v1 **握手期** SDK 版本检查）的判据 —— 2026-10-17 `version-floor-soften` 线。

## 为什么有这条
`src/plugin_runtime/host/rpc_server.py` 的握手校验原本把"runner 自报 `sdk_version` 不在宿主支持区间
`[MIN_SDK_VERSION, MAX_SDK_VERSION]`"直接当**拒握手**依据（= 把**号段**当兼容判据）。
lmq 裁：**我们根本没法用版本号定兼容性**（我们的号段与生态脱节）
⇒ 判据改成分主版本：**同主版本**越界 ⇒ **具名 warning + 放行**；**跨主版本** ⇒ **仍拒**；
不可解析 ⇒ fail-closed（`SDK_VERSION_UNPARSABLE`）。

## 判据根（写在代码注释里，也写在这）
兼容性 = **manifest 可解析 + 所需 API 在位 + 起得来**，不是号段比较。

## 覆盖边界（如实）
本文件只测**判定函数** `_sdk_version_verdict` —— 它决定"放行 / 拒"，也就是那道门的**闸芯**；
**没有**起真连接去跑 `check_hello` 的收发帧路径（那一层不在本文件覆盖内）。
"""

from src.plugin_runtime.host.rpc_server import _sdk_version_verdict


def test_in_range_passes_silently(caplog) -> None:
    """区间内 ⇒ 放行且**不出声**（别把正常态也弄成噪声）。"""

    with caplog.at_level("WARNING"):
        assert _sdk_version_verdict("2.50.0") is None

    # `at_level("WARNING")` 之下捕获到的记录**都在 warning 及以上** ⇒ 空 = 没出声
    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_same_major_over_ceiling_is_named_but_allowed(caplog) -> None:
    """**（甲）同主版本越上界 ⇒ 具名 warning + 放行**（本线的核心改动）。

    取 `2.150.0`：与上界 `2.99.99` **同主版本**、但比较上更大。
    """

    with caplog.at_level("WARNING"):
        assert _sdk_version_verdict("2.150.0") is None

    messages = [r.getMessage() for r in caplog.records]
    assert any("2.150.0" in m and "兼容模式" in m for m in messages), f"没有具名 warning：{messages}"


def test_cross_major_over_ceiling_is_rejected() -> None:
    """**（乙）跨主版本越上界 ⇒ 仍拒**（显式不兼容，不是按号段猜）。"""

    reason = _sdk_version_verdict("3.0.0")
    assert reason is not None and reason.startswith("SDK_VERSION_MISMATCH"), reason


def test_cross_major_below_floor_is_rejected() -> None:
    """低于下界且**跨主版本** ⇒ 也拒（同上：显式不兼容）。"""

    reason = _sdk_version_verdict("0.9.0")
    assert reason is not None and reason.startswith("SDK_VERSION_MISMATCH"), reason


def test_unparsable_is_fail_closed() -> None:
    """不可解析 ⇒ fail-closed（"声明了但不可判"不许当通过）。"""

    reason = _sdk_version_verdict("not-a-version")
    assert reason is not None and reason.startswith("SDK_VERSION_UNPARSABLE"), reason
