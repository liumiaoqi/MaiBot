"""插件 SDK 版本区间与握手判定的**单一来源**（2026-10-17 `sdk-range-consolidate` 线）。

## 为什么落在这里
v1（`src/plugin_runtime/`）与 v2（`src/plugin_runtime_v2/`）**互不依赖**，但两边都要回答同一个问题：
"宿主支持哪些 SDK 版本" ⇒ 放进两边都已依赖的 `src/common/`（例如 `src.common.logger`），
**不让任何一代去 import 另一代**，也不留两份会各自漂移的常量。

## ⚠️ 为什么是**两组**区间，而不是一组（下一个人别照直觉合并）
- **v1 `[1.0.0, 2.99.99]`（闭区间）= 今天真实存在的 SDK**：本机实测 `maibot_sdk` **2.13.0**，
  生态插件普遍按 `1.x–1.99.99` 写 ⇒ 它描述**现实**。
- **v2 `[4.0.0, 5.0.0)`（半开）= v2 这一代的自洽闭环**：v2 runner 自报默认 `4.0.0`、
  SDK 声明模型默认下界 `4.0.0` ⇒ 它描述 **v2 给自己定的号段**，不对应任何已安装的 SDK。
⛔ **别把 v1 的区间搬给 v2**：v2 runner 自报 `4.0.0` 会当场落在 `[1.0.0, 2.99.99]` 之外 ⇒ **v2 全红**。
⇒ 本模块给的是"**一个来源**"（一处定义、所有人消费），**不是"一个数值"**。

## 判据根（写在这，免得只看得见号段）
兼容性 = **manifest 可解析 + 所需 API 在位 + 起得来**，**不是号段比较**；
号段只用于 ① **出声（warning）** ② **跨主版本的显式拒绝**（见 `sdk_version_verdict`）。

## 依赖
只用标准库（**不 import logger**）⇒ 两侧调用方各自打自己的日志，本模块只出**结构化判定**。
"""

from typing import NamedTuple

# ── v1：`plugin_runtime/`（闭区间；原 `plugin_runtime/protocol/envelope.py:19-20`）──
V1_MIN_SDK_VERSION = "1.0.0"
V1_MAX_SDK_VERSION = "2.99.99"
#: v1 runner 探测不到本地 SDK 时的**自报兜底值**（原 `runner/rpc_client.py:_get_sdk_version` 的兜底）。
V1_SDK_VERSION_FALLBACK = "1.0.0"

# ── v2：`plugin_runtime_v2/`（半开区间；原 `host/servicer.py:36-37`）──
V2_MIN_SDK_VERSION = "4.0.0"
V2_MAX_SDK_VERSION = "5.0.0"
#: v2 runner 的**自报默认值**（原 `runner/reconnect.py:33` 的硬编码）。
V2_SDK_VERSION_DEFAULT = "4.0.0"


class SDKVersionVerdict(NamedTuple):
    """握手/装载期对"runner 自报的 SDK 版本"的判定结论（结构化，便于两侧映射成各自的协议码）。"""

    kind: str
    """``in_range`` / ``below_floor`` / ``above_ceiling`` / ``unparsable``。"""

    allowed: bool
    """是否放行。``below_floor`` / ``above_ceiling`` 且**同主版本**时仍为 True（出声放行）。"""

    same_major: bool
    """越界时：自报值与**被越过的那个边界**是否同主版本（同主版本 ⇒ 出声放行；跨主版本 ⇒ 拒）。"""

    out_of_range: bool
    """是否越界（含"越界但放行"）。"""

    version: str
    min_version: str
    max_version: str
    half_open: bool

    @property
    def should_warn(self) -> bool:
        """是否需要调用方**具名出声**（越界但放行）。"""

        return self.allowed and self.out_of_range

    def describe(self) -> str:
        """人读的区间描述（自带闭/半开口径，免得两侧各写一套）。"""

        return format_range(self.min_version, self.max_version, half_open=self.half_open)


def parse_version_tuple(version: str) -> tuple[int, ...]:
    """把版本串解析成可比较的整数元组；空/不可解析 ⇒ 返回空元组（**不抛**，由调用方 fail-closed）。

    ``1.2.3`` ⇒ ``(1, 2, 3)``；``2.99`` ⇒ ``(2, 99)``；``x`` / ``""`` ⇒ ``()``。
    """

    parts = [part for part in str(version or "").strip().split(".") if part != ""]
    if not parts:
        return ()
    try:
        return tuple(int(part) for part in parts)
    except (TypeError, ValueError):
        return ()


def format_range(min_version: str, max_version: str, *, half_open: bool) -> str:
    """区间的人读形态：闭区间 ``[a, b]`` / 半开 ``[a, b)``。"""

    return f"[{min_version}, {max_version}{')' if half_open else ']'}"


def sdk_version_verdict(
    version: str,
    *,
    min_version: str,
    max_version: str,
    half_open: bool = False,
) -> SDKVersionVerdict:
    """判定"自报的 SDK 版本"相对支持区间的结论（**两侧共用这一处**）。

    规则（与"号段不作兼容判据"一致）：
    - 区间内 ⇒ ``in_range``、放行、不出声；
    - **越界但同主版本** ⇒ 放行但 ``should_warn``（调用方**具名出声**）；
    - **越界且跨主版本** ⇒ 不放行（这是"显式声明的不兼容"）；
    - **不可解析** ⇒ 不放行（fail-closed："声明了但不可判"不许当通过）。

    ``half_open``：v1 用闭区间（``min <= v <= max``），v2 用半开（``min <= v < max``）。
    """

    current = parse_version_tuple(version)
    floor = parse_version_tuple(min_version)
    ceiling = parse_version_tuple(max_version)
    if not current or not floor or not ceiling:
        return SDKVersionVerdict(
            "unparsable", False, False, False, str(version or ""), min_version, max_version, half_open
        )

    in_range = floor <= current < ceiling if half_open else floor <= current <= ceiling
    if in_range:
        return SDKVersionVerdict(
            "in_range", True, False, False, version, min_version, max_version, half_open
        )

    below = current < floor
    boundary = floor if below else ceiling
    same_major = current[0] == boundary[0]
    return SDKVersionVerdict(
        "below_floor" if below else "above_ceiling",
        same_major,  # 同主版本 ⇒ 放行；跨主版本 ⇒ 不放行
        same_major,
        True,
        version,
        min_version,
        max_version,
        half_open,
    )


def assert_definitions_are_valid() -> None:
    """**定义自己必须非空且可解析**（抽取型检查的前置断言）。

    今晚那族教训：只查"消费者对不对"、不查"数据源本身非空"的检查器，会在源为空时**静默全过**。
    这里在**模块导入时**就断言 ⇒ 常量被改坏时**立刻出声**，而不是让四道门各自拿空值判。
    """

    pairs = (
        ("v1", V1_MIN_SDK_VERSION, V1_MAX_SDK_VERSION, False),
        ("v2", V2_MIN_SDK_VERSION, V2_MAX_SDK_VERSION, True),
    )
    for label, floor, ceiling, half_open in pairs:
        if not str(floor).strip() or not str(ceiling).strip():
            raise ValueError(f"SDK 区间定义为空（{label}）：min={floor!r} max={ceiling!r}")
        floor_parts = parse_version_tuple(floor)
        ceiling_parts = parse_version_tuple(ceiling)
        if not floor_parts or not ceiling_parts:
            raise ValueError(f"SDK 区间定义不可解析（{label}）：min={floor!r} max={ceiling!r}")
        if floor_parts > ceiling_parts or (half_open and floor_parts == ceiling_parts):
            raise ValueError(f"SDK 区间定义非法（{label} {format_range(floor, ceiling, half_open=half_open)}）")
    for label, fallback in (("v1 fallback", V1_SDK_VERSION_FALLBACK), ("v2 default", V2_SDK_VERSION_DEFAULT)):
        if not parse_version_tuple(fallback):
            raise ValueError(f"{label} 不可解析：{fallback!r}")


assert_definitions_are_valid()
