"""错误升级梯 — 现有错误枚举统一映射器（ZG-14）。

14 个现有枚举值（8 个枚举类型）到 ErrorLevel 的只读映射表 + 4 个
冲突消解（spec §5.6.1）。映射为只读查表，禁止修改现有枚举值
（spec §5.6.1 规则 6/8）；标志缺失按保守原则映射 FATAL（spec
§5.6.3 异常场景 2，确保错误不被低估）。
"""

from src.common.logger import get_logger
from src.core.error_escalation.types import ErrorLevel
from src.core.resource_limit.types import OOMAction, PressureLevel
from src.core.service_manager.types import RecoveryAction, ServiceState
from src.core.startup.types import ComponentStatus
from src.core.tainted_mask.taint_action import TaintAction
from src.core.watchdog.types import BlockSeverity

logger = get_logger("error_escalation.mapper")


class EnumLevelMapper:
    """现有枚举 → ErrorLevel 只读映射 + 冲突消解。

    冲突消解标志（kwargs）：
    - storm_protection: bool — ServiceState.FAULT_MANUAL / RecoveryAction.MANUAL_RESTART
      True（风暴保护场景）→ CRITICAL；False/缺失 → FATAL（保守）
    - critical: bool — ComponentStatus.FAILED True → CRITICAL；False → ERROR
    - diffuse_scope: str — "single"（单会话扩散）→ CRITICAL；"global"（全扩散）→ FATAL。
      注（P2-1）：映射对象为扩散范围状态值 single/global，非 FatalDiffuser
      类本身（该类是扩散器引擎，无枚举值可映射）
    """

    # 无冲突枚举的静态映射表
    _STATIC_MAP: dict[type, dict[object, ErrorLevel]] = {
        TaintAction: {
            TaintAction.WARN: ErrorLevel.WARN,
            TaintAction.TRIGGER_DEGRADE: ErrorLevel.ERROR,
        },
        OOMAction: {
            OOMAction.DEGRADE: ErrorLevel.ERROR,
            OOMAction.KILL: ErrorLevel.CRITICAL,
        },
        ServiceState: {
            ServiceState.FAULT: ErrorLevel.ERROR,
            ServiceState.DEGRADED: ErrorLevel.WARN,
        },
        BlockSeverity: {
            BlockSeverity.MILD_LAG: ErrorLevel.WARN,
            BlockSeverity.SEVERE_BLOCK: ErrorLevel.ERROR,
        },
        PressureLevel: {
            PressureLevel.MEDIUM: ErrorLevel.WARN,
            PressureLevel.CRITICAL: ErrorLevel.CRITICAL,
        },
    }

    # 冲突消解枚举的映射函数（标志缺失按保守原则 FATAL，spec §5.6.3 异常场景 2）
    def _map_service_state_fault_manual(self, flags: dict[str, object]) -> ErrorLevel:
        if flags.get("storm_protection") is True:
            return ErrorLevel.CRITICAL
        return ErrorLevel.FATAL  # 保守（全扩散/停机场景）

    def _map_component_status_failed(self, flags: dict[str, object]) -> ErrorLevel:
        if flags.get("critical") is True:
            return ErrorLevel.CRITICAL
        return ErrorLevel.ERROR

    def _map_recovery_manual_restart(self, flags: dict[str, object]) -> ErrorLevel:
        if flags.get("storm_protection") is True:
            return ErrorLevel.CRITICAL
        return ErrorLevel.FATAL  # 保守（人工标记场景）

    def _map_diffuse_scope(self, flags: dict[str, object]) -> ErrorLevel:
        scope = flags.get("diffuse_scope")
        if scope == "global":
            return ErrorLevel.FATAL
        if scope == "single":
            return ErrorLevel.CRITICAL
        logger.warning(
            "ERROR_MAP_FLAG_MISSING: FatalDiffuser 扩散范围标志缺失（diffuse_scope=%r），按保守 FATAL 映射",
            scope,
        )
        return ErrorLevel.FATAL

    def map(self, value: object, **flags: object) -> ErrorLevel:
        """映射现有枚举/状态值到 ErrorLevel。

        Args:
            value: 现有枚举值（TaintAction / OOMAction / ServiceState /
                ComponentStatus / RecoveryAction / BlockSeverity /
                PressureLevel）或扩散范围状态值（"single"/"global"，P2-1）
            flags: 冲突消解上下文标志（storm_protection / critical / diffuse_scope）

        Returns:
            ErrorLevel；未知枚举按 WARN 兜底（spec §5.6.3 异常场景 1）
        """
        # 冲突消解枚举（4 个）
        if value is ServiceState.FAULT_MANUAL:
            return self._map_service_state_fault_manual(flags)
        if value is ComponentStatus.FAILED:
            return self._map_component_status_failed(flags)
        if value is RecoveryAction.MANUAL_RESTART:
            return self._map_recovery_manual_restart(flags)
        # FatalDiffuser 扩散范围状态（single/global，非类本身——P2-1 修复）
        if value == "single" or value == "global":
            return self._map_diffuse_scope(flags)

        # 静态映射表查表
        for enum_type, table in self._STATIC_MAP.items():
            if isinstance(value, enum_type) and value in table:
                return table[value]

        # 未知枚举兜底（spec §5.6.3 异常场景 1）
        logger.warning("ERROR_MAP_UNKNOWN: 未收录的枚举 %r，按 WARN 兜底", value)
        return ErrorLevel.WARN

    def get_mapping_table(self) -> dict[str, dict[str, str]]:
        """返回可查询映射表（14 枚举项 → ErrorLevel + 消解说明）。

        供运维与测试验证映射正确性（spec §5.6.1 规则 7）。
        """
        table: dict[str, dict[str, str]] = {}
        for enum_type, mapping in self._STATIC_MAP.items():
            for enum_value, level in mapping.items():
                table[f"{enum_type.__name__}.{enum_value.name}"] = {
                    "default": level.value,
                    "resolve": "无冲突",
                }
        # 冲突消解 4 项（P2-1：FatalDiffuser 项标注映射对象为扩散范围状态）
        table["ServiceState.FAULT_MANUAL"] = {
            "default": ErrorLevel.FATAL.value,
            "resolve": "storm_protection=True→critical；False/缺失→fatal（保守）",
        }
        table["ComponentStatus.FAILED"] = {
            "default": ErrorLevel.ERROR.value,
            "resolve": "critical=True→critical；False→error",
        }
        table["RecoveryAction.MANUAL_RESTART"] = {
            "default": ErrorLevel.FATAL.value,
            "resolve": "storm_protection=True→critical；False/缺失→fatal（保守）",
        }
        table["FatalDiffuser(diffuse_scope)"] = {
            "default": ErrorLevel.CRITICAL.value,
            "resolve": "single→critical；global→fatal；缺失→fatal（保守）。映射对象为扩散范围状态值 single/global，非 FatalDiffuser 类本身",
        }
        return table


# 模块级单例（纯查表无状态，供 adapter/escalator 复用）
default_mapper = EnumLevelMapper()

__all__ = ["EnumLevelMapper", "default_mapper"]
