"""看门狗配置 — 启动时传入，运行时不可变。"""


from dataclasses import dataclass


@dataclass(frozen=True)
class WatchdogConfig:
    """看门狗配置，所有字段有默认值。

    touch_interval_s: touch 刷新间隔（上限 1s）
    check_interval_s: 检测判定间隔（上限 5s）
    mild_threshold_s: 轻度卡顿阈值，距上次 touch 超过此值记轻度卡顿
    severe_threshold_s: 严重阻塞阈值，距上次 touch 超过此值记严重阻塞
    consecutive_report_threshold: 连续超时上报阈值 N，连续 N 次严重阻塞才上报
    cooldown_s: 冷却窗口，同一异常源在冷却内不重复上报
    v1_poll_interval_s: V1 旁路轮询间隔，与 V1 健康检查间隔对齐
    v2_diff_interval_s: V2 状态 diff 轮询间隔，与检测间隔对齐
    """

    touch_interval_s: float = 1.0
    check_interval_s: float = 5.0
    mild_threshold_s: float = 3.0
    severe_threshold_s: float = 10.0
    consecutive_report_threshold: int = 2
    cooldown_s: float = 30.0
    v1_poll_interval_s: float = 10.0
    v2_diff_interval_s: float = 5.0

    def __post_init__(self) -> None:
        if self.severe_threshold_s <= self.mild_threshold_s:
            raise ValueError(
                f"severe_threshold_s ({self.severe_threshold_s}) 必须大于 mild_threshold_s ({self.mild_threshold_s})"
            )
        if self.touch_interval_s <= 0:
            raise ValueError(f"touch_interval_s 必须为正数，当前 {self.touch_interval_s}")
        if self.check_interval_s <= 0:
            raise ValueError(f"check_interval_s 必须为正数，当前 {self.check_interval_s}")
        if self.mild_threshold_s <= 0:
            raise ValueError(f"mild_threshold_s 必须为正数，当前 {self.mild_threshold_s}")
        if self.severe_threshold_s <= 0:
            raise ValueError(f"severe_threshold_s 必须为正数，当前 {self.severe_threshold_s}")
        if self.cooldown_s <= 0:
            raise ValueError(f"cooldown_s 必须为正数，当前 {self.cooldown_s}")
        if self.v1_poll_interval_s <= 0:
            raise ValueError(f"v1_poll_interval_s 必须为正数，当前 {self.v1_poll_interval_s}")
        if self.v2_diff_interval_s <= 0:
            raise ValueError(f"v2_diff_interval_s 必须为正数，当前 {self.v2_diff_interval_s}")
        if self.consecutive_report_threshold < 1:
            raise ValueError(
                f"consecutive_report_threshold 必须 >= 1，当前 {self.consecutive_report_threshold}"
            )