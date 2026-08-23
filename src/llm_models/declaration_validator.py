"""声明校验器 — 启动时校验全部 @model_requirement 声明（ZG-12）。

对标 Linux driver probe：驱动声明的需求无法满足 → 设备可见地不可用，
不假装驱动了设备。

分类语义（错误码驱动验证的静态侧）：
- satisfied：声明可满足
- fast_fail：critical 声明不可满足 → 拒绝启动（配置写错，炸得响比假装能用好）
- degraded：非 critical 声明不可满足 → 告警 + 组件降级
"""

from dataclasses import dataclass, field

from src.common.logger import get_logger
from src.llm_models.model_requirement import DeclarationError, get_all_declarations
from src.llm_models.model_registry import ModelRegistry

logger = get_logger("llm_models.declaration_validator")

STATUS_PASSED = "passed"
STATUS_FAST_FAIL = "fast_fail"
STATUS_DEGRADED = "degraded"


@dataclass(slots=True)
class ValidationItem:
    """单条声明的校验结果。"""

    component_name: str
    status: str
    required_capabilities: frozenset[str] = frozenset()
    resolved_model: str = ""
    detail: str = ""


@dataclass(slots=True)
class ValidationReport:
    """全部声明的校验报告。"""

    status: str = STATUS_PASSED
    items: list[ValidationItem] = field(default_factory=list)

    @property
    def fast_fail_components(self) -> list[str]:
        return [item.component_name for item in self.items if item.status == STATUS_FAST_FAIL]

    @property
    def degraded_components(self) -> list[str]:
        return [item.component_name for item in self.items if item.status == STATUS_DEGRADED]


class DeclarationValidator:
    """声明校验器 — 遍历全局声明表，逐项按能力解析并分类。"""

    def validate_all_declarations(self, registry: ModelRegistry) -> ValidationReport:
        """校验全部声明。

        静态校验只做注册表结构完整性（category/name 引用在注册表内存在）；
        服务商相关的（模型名对不对/参数支不支持）交给错误码驱动（调用时验证）。

        Args:
            registry: 已 build_index 的模型注册表

        Returns:
            ValidationReport：status=passed / fast_fail / degraded
        """
        report = ValidationReport()
        for component_name, declaration in get_all_declarations().items():
            prefer = declaration.defaults.prefer if declaration.defaults else ()
            try:
                resolved = registry.query_by_capability(
                    declaration.capabilities,
                    prefer=prefer,
                )
            except DeclarationError as exc:
                item = ValidationItem(
                    component_name=component_name,
                    status=STATUS_FAST_FAIL if declaration.critical else STATUS_DEGRADED,
                    required_capabilities=declaration.capabilities,
                    detail=str(exc),
                )
                report.items.append(item)
                if declaration.critical:
                    logger.warning(f"声明校验 fast_fail: component={component_name}, error={exc}")
                    report.status = STATUS_FAST_FAIL
                elif report.status != STATUS_FAST_FAIL:
                    logger.warning(f"声明校验 degraded: component={component_name}, error={exc}")
                    report.status = STATUS_DEGRADED
                continue

            report.items.append(ValidationItem(
                component_name=component_name,
                status=STATUS_PASSED,
                required_capabilities=declaration.capabilities,
                resolved_model=f"({resolved.category}, {resolved.name})",
            ))
        return report
