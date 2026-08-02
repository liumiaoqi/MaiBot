"""ZG-7 污染标记 — on_taint 动作映射表管理。

对标 Linux `panic_on_taint` boot 参数（panic.c:1249-1274）：
维护 {TaintFlag: TaintAction} 映射，未列出标志默认 RECORD（spec §2.3.1 规则 1）。
动作执行收敛在 TaintedMask._execute_action 一处（P3-4），本类只负责映射查询与配置加载。
"""

from src.core.tainted_mask.taint_action import TaintAction
from src.core.tainted_mask.taint_flag import TaintFlag


class TaintActionMapper:
    """on_taint 动作映射表 — 查询 + 配置加载。"""

    def __init__(self, mapping: dict[TaintFlag, TaintAction]) -> None:
        """初始化映射表。

        Args:
            mapping: {TaintFlag: TaintAction} 映射（未列出标志默认 RECORD）
        """
        self._mapping: dict[TaintFlag, TaintAction] = dict(mapping)

    def get_action(self, flag: TaintFlag) -> TaintAction:
        """查询标志动作，缺省返回 RECORD（spec §2.3.1 规则 1）。"""
        return self._mapping.get(flag, TaintAction.RECORD)

    @classmethod
    def from_config(cls, config_dict: dict[str, str]) -> "TaintActionMapper":
        """从配置字典构建映射（design §8.3）。

        Args:
            config_dict: {标志名: 动作名}，如 {"TAINT_PORT_BYPASS": "trigger_degrade"}

        Returns:
            TaintActionMapper

        Raises:
            ValueError: key 不在 TaintFlag 枚举名或 value 不在 TaintAction 枚举值中
        """
        mapping: dict[TaintFlag, TaintAction] = {}
        for key, value in (config_dict or {}).items():
            try:
                flag = TaintFlag[key]
            except KeyError:
                raise ValueError(f"非法污染标志名: {key!r}") from None
            try:
                action = TaintAction(value)
            except ValueError:
                raise ValueError(f"非法污染动作值: {value!r}（flag={key}）") from None
            mapping[flag] = action
        return cls(mapping)
