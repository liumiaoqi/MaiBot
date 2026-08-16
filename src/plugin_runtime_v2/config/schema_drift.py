"""ZG16-6a: 配置 schema 声明键 vs 实际键漂移检测。

设计参考：dsh shell-env 声明-实际漂移检测 `shell/shell-env/src/index.ts:152-176`。
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from src.common.logger import get_logger
from src.core.error_escalation_port_registry import get_error_escalation_port

logger = get_logger("plugin_runtime_v2.config.schema_drift")


@dataclass(frozen=True)
class DriftResult:
    """schema 漂移检测结果。"""

    plugin_id: str
    extra_keys: list[str] = field(default_factory=list)  # 实际有但 schema 未声明
    missing_keys: list[str] = field(default_factory=list)  # schema 声明必填但实际缺失
    type_mismatches: list[dict] = field(default_factory=list)  # {key, expected_type, actual_type}


class SchemaDriftDetector:
    """配置 schema 声明键 vs 实际键漂移检测。

    设计参考 dsh shell-env 声明-实际漂移检测
    `shell/shell-env/src/index.ts:152-176`。
    """

    @classmethod
    def detect(
        cls,
        plugin_id: str,
        config: dict,
        schema: type[BaseModel] | None,
    ) -> DriftResult | None:
        """检测 schema 漂移。schema 为 None → 跳过（返回 None）。"""
        if schema is None:
            return None  # 未注册 schema，跳过（spec 5.2.3 场景 1）
        try:
            schema_fields = schema.model_fields  # pydantic v2
            extra_keys = [k for k in config if k not in schema_fields]
            missing_keys = [
                name for name, f in schema_fields.items()
                if f.is_required() and name not in config
            ]
            type_mismatches = cls._check_types(config, schema, schema_fields)
            if not extra_keys and not missing_keys and not type_mismatches:
                return None
            result = DriftResult(plugin_id, extra_keys, missing_keys, type_mismatches)
            cls._emit_drift_alert(plugin_id, result)
            return result
        except Exception as e:
            # schema 本身定义错误 → 跳过检测 + warning（spec 5.5.3 场景 3）
            logger.warning(f"schema 漂移检测失败，跳过: {e}")
            return None

    @classmethod
    def _check_types(cls, config, schema, schema_fields) -> list[dict]:
        """检查类型不匹配。"""
        mismatches = []
        for name, f in schema_fields.items():
            if name in config:
                try:
                    schema(**{
                        k: v for k, v in config.items() if k in schema_fields
                    })
                except ValidationError:
                    mismatches.append({
                        "key": name,
                        "expected_type": str(f.annotation),
                        "actual_type": type(config[name]).__name__,
                    })
                    break  # 一个类型错误即可，避免重复报
        return mismatches

    @classmethod
    def _emit_drift_alert(cls, plugin_id: str, drift: DriftResult) -> None:
        """漂移告警上报：logger + error_escalation_port。"""
        if drift.extra_keys:
            logger.warning(f"插件 {plugin_id} 配置多余键: {drift.extra_keys}")
        if drift.missing_keys:
            logger.error(f"插件 {plugin_id} 配置缺失必填键: {drift.missing_keys}")
        if drift.type_mismatches:
            logger.error(f"插件 {plugin_id} 配置类型不匹配: {drift.type_mismatches}")
        port = get_error_escalation_port()
        if port is not None:
            port.report(
                level="WARNING" if drift.extra_keys else "ERROR",
                message=f"插件 {plugin_id} 配置 schema 漂移: {drift}",
                component_id=plugin_id,
            )