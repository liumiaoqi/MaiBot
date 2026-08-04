"""TaintMaskAdapter — 实现 TaintedMaskPort，组装 TaintedMask + TaintActionMapper。

适配器层，唯一允许导入污染标记具体类的地方（spec §4.6 规则 2）。
核心通过 TaintedMaskPort Protocol 接口交互，不直接导入本模块。
"""

from typing import Any

from src.common.logger import get_logger
from src.core.protocols import TaintedMaskPort
from src.core.tainted_mask.taint_action_mapper import TaintActionMapper
from src.core.tainted_mask.taint_flag import TaintFlag
from src.core.tainted_mask.tainted_mask import TaintedMask
from src.core.tainted_mask.types import TaintRecord

logger = get_logger("core.adapters.taint_mask")


class TaintMaskAdapter(TaintedMaskPort):
    """污染标记适配器 — 组装 TaintedMask + TaintActionMapper，实现 TaintedMaskPort。

    适配器层唯一入口，核心模块不导入污染标记具体类（spec §4.6 规则 1）。
    """

    def __init__(
        self,
        state_machine_port: Any = None,
        app_config_port: Any = None,
    ) -> None:
        """初始化适配器并加载配置。

        Args:
            state_machine_port: ZG-6 SystemStateMachine（TRIGGER_DEGRADE 动作使用，
                None 时降级为 WARN）
            app_config_port: AppConfigPort（加载 on_taint / warn_limit / preset_mask，
                None 时使用默认值）
        """
        self._state_machine_port = state_machine_port
        self._app_config_port = app_config_port

        on_taint = self._load_on_taint_config()
        warn_limit = self._load_warn_limit_config()
        preset_mask = self._load_preset_mask_config()
        degrade_on_taint_mask = self._load_degrade_on_taint_mask_config()

        self._tainted_mask = TaintedMask(
            on_taint=on_taint,
            warn_limit=warn_limit,
            state_machine_port=state_machine_port,
            preset_mask=preset_mask,
            degrade_on_taint_mask=degrade_on_taint_mask,
        )

    def _load_on_taint_config(self) -> dict[TaintFlag, Any]:
        """从 AppConfigPort 加载 on_taint 映射（design §8.3）。"""
        if self._app_config_port is None:
            return {}
        try:
            config = self._app_config_port.get_taint_on_taint()
            mapper = TaintActionMapper.from_config(config)
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.warning("on_taint 配置加载失败，使用默认（全部 RECORD）", exc_info=True)
            return {}
        return {
            flag: mapper.get_action(flag)
            for flag in TaintFlag
            if mapper.get_action(flag).value != "record"
        }

    def _load_warn_limit_config(self) -> int:
        """从 AppConfigPort 加载 warn_limit（校验 ≥ 0）。"""
        if self._app_config_port is None:
            return 0
        try:
            return max(0, int(self._app_config_port.get_taint_warn_limit()))
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.warning("warn_limit 配置读取失败，使用默认 0", exc_info=True)
            return 0

    def _load_preset_mask_config(self) -> int:
        """从 AppConfigPort 加载 preset_mask。"""
        if self._app_config_port is None:
            return 0
        try:
            return int(self._app_config_port.get_taint_preset_mask())
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.warning("preset_mask 配置读取失败，使用默认 0", exc_info=True)
            return 0

    def _load_degrade_on_taint_mask_config(self) -> int:
        """从 AppConfigPort 加载 degrade_on_taint_mask。"""
        if self._app_config_port is None:
            return 0
        try:
            return int(self._app_config_port.get_degrade_on_taint_mask())
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.warning("degrade_on_taint_mask 配置读取失败，使用默认 0", exc_info=True)
            return 0

    # ── TaintedMaskPort 委托 ─────────────────────────────────────

    def add_taint(self, flag: TaintFlag) -> None:
        self._tainted_mask.add_taint(flag)

    def test_taint(self, flag: TaintFlag) -> bool:
        return self._tainted_mask.test_taint(flag)

    def get_taint(self) -> int:
        return self._tainted_mask.get_taint()

    def print_tainted(self) -> str:
        return self._tainted_mask.print_tainted()

    def print_tainted_verbose(self) -> list[str]:
        return self._tainted_mask.print_tainted_verbose()

    def get_taint_records(self) -> dict[int, TaintRecord]:
        return self._tainted_mask.get_taint_records()

    @property
    def warn_count(self) -> int:
        return self._tainted_mask.warn_count

    def get_degrade_on_taint_mask(self) -> int:
        return self._tainted_mask.get_degrade_on_taint_mask()

    # ── 订阅（外部衔接，如 CrashDump）────────────────────────────

    def subscribe(self, callback: Any) -> int:
        """订阅污染位变化通知（委托 TaintedMask）。"""
        return self._tainted_mask.subscribe(callback)

    def unsubscribe(self, handle: int) -> None:
        """取消订阅（委托 TaintedMask）。"""
        self._tainted_mask.unsubscribe(handle)
