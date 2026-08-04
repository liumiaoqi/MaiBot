"""组件模型需求声明与解析数据模型（ZG-12 组件自治）。

组件自治模型配置的核心数据类：
- ModelEntry：注册表中单个模型的条目（能力声明 + 采样参数默认值）
- ResolutionOptions / ResolvedModel / EffectiveResolution：需求解析链路的数据载体
- ComponentDeclaration：@model_requirement 声明的结构化表示
- DeclarationError：声明不可满足的结构化错误（错误信息指向根因）
- model_requirement：组件自治声明装饰器（与 ZG-10 @startup_item 同哲学）
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")

DECLARATION_SOURCE = "declaration"
DEFAULT_SOURCE = "default"
OPTIONS_SOURCE = "options"


@dataclass(frozen=True, slots=True)
class ModelEntry:
    """注册表中的模型条目 — 能力声明 + 采样参数默认值。

    字段语义：
    - category：能力域粗分（llm / embedding / voice），仅用于组织分组，能力筛选以 capabilities 为准
    - capabilities：模型能力标签集（text_generation / tool_calling / vision / embedding / voice）
    - context_window：模型最大上下文窗口（token 数）——ZG-16 动态策略预留
    - temperature / max_tokens：该模型的默认采样参数（适配器按 capability 翻译）
    """

    category: str
    name: str
    model_identifier: str
    api_provider: str
    capabilities: frozenset[str] = frozenset()
    context_window: int = 0
    price_in: float = 0.0
    price_out: float = 0.0
    cache: bool = False
    temperature: float = 0.3
    max_tokens: int = 4096
    force_stream_mode: bool = False
    extra_params: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        """(category, name) 组合唯一键。"""
        return (self.category, self.name)


@dataclass(frozen=True, slots=True)
class ResolutionOptions:
    """调用点级解析选项 — 覆盖注册表默认采样参数。"""

    prefer: tuple[tuple[str, str], ...] = ()
    """偏好模型列表（(category, name) 元组序列），按顺序优先"""

    temperature: float | None = None
    max_tokens: int | None = None
    selection_strategy: str = "balance"
    hard_timeout: float = 240.0
    slow_threshold: float = 15.0


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """需求解析结果 — 选定的模型 + 生效采样参数。"""

    category: str
    name: str
    model_identifier: str
    api_provider: str
    capabilities: frozenset[str] = frozenset()
    temperature: float = 0.3
    max_tokens: int = 4096
    selection_strategy: str = "balance"
    hard_timeout: float = 240.0
    slow_threshold: float = 15.0
    source: str = DEFAULT_SOURCE
    """解析来源：declaration / default / options"""
    fallback_candidates: tuple[str, ...] = ()
    """同能力 fallback 候选（模型 name 序列，不含已选模型）"""

    @property
    def key(self) -> tuple[str, str]:
        return (self.category, self.name)


@dataclass(frozen=True, slots=True)
class EffectiveResolution:
    """组件的生效解析结果 — 含参数来源追踪。"""

    component_name: str
    capabilities: frozenset[str] = frozenset()
    resolved_model: ResolvedModel | None = None
    param_sources: dict[str, str] = field(default_factory=dict)
    """参数名 → 来源（declaration / default / options）"""
    fallback_candidates: tuple[str, ...] = ()
    status: str = "satisfied"
    """satisfied / fast_fail / degraded"""


@dataclass(frozen=True, slots=True)
class ComponentDeclaration:
    """@model_requirement 声明的结构化表示。"""

    component_name: str
    capabilities: frozenset[str]
    defaults: ResolutionOptions | None = None
    critical: bool = True
    fallback_chain: tuple[str, ...] = ()
    """声明级 fallback 链（模型 name 序列，优先于同能力筛选）"""


@dataclass(frozen=True, slots=True)
class DeclarationError(Exception):
    """声明不可满足的结构化错误 — 错误信息指向根因。"""

    message: str
    component_name: str = ""
    required_capabilities: frozenset[str] = frozenset()
    category: str = ""
    name: str = ""

    def __str__(self) -> str:
        parts = []
        if self.component_name:
            parts.append(f"组件 {self.component_name}")
        if self.category and self.name:
            parts.append(f"模型 ({self.category}, {self.name})")
        elif self.required_capabilities:
            parts.append(f"能力 {sorted(self.required_capabilities)}")
        parts.append(self.message)
        return " ".join(parts)


# ── 全局声明表与装饰器 ──────────────────────────────────────────

_DECLARATIONS: dict[str, ComponentDeclaration] = {}
"""全局声明表：component_name → ComponentDeclaration（@model_requirement 注册）"""


def get_all_declarations() -> dict[str, ComponentDeclaration]:
    """返回全部声明的副本（只读视图）。"""
    return dict(_DECLARATIONS)


def clear_declarations() -> None:
    """清空全局声明表（测试用）。"""
    _DECLARATIONS.clear()


def model_requirement(
    capabilities: Sequence[str],
    *,
    defaults: ResolutionOptions | None = None,
    critical: bool = True,
    fallback_chain: Sequence[str] = (),
) -> Callable[[type[T]], type[T]]:
    """组件自治模型需求声明装饰器 — 与 ZG-10 @startup_item 同哲学。

    在类上附加 `_model_requirement: ComponentDeclaration` 属性，
    并注册到全局声明表 _DECLARATIONS（key = 类名）。

    Args:
        capabilities: 所需能力标签列表（如 ["text_generation", "tool_calling"]）
        defaults: 采样参数默认值覆盖（温度/长度/超时等）
        critical: 声明不可满足时是否拒绝启动（True=fast-fail；False=降级）
        fallback_chain: 声明级 fallback 链（模型 name 序列，优先于同能力筛选）

    Example:
        @model_requirement(capabilities=["text_generation", "tool_calling"], critical=True)
        class ThinkingOrgan: ...
    """

    def decorator(cls: type[T]) -> type[T]:
        declaration = ComponentDeclaration(
            component_name=cls.__name__,
            capabilities=frozenset(capabilities),
            defaults=defaults,
            critical=critical,
            fallback_chain=tuple(fallback_chain),
        )
        cls._model_requirement = declaration  # type: ignore[attr-defined]
        _DECLARATIONS[cls.__name__] = declaration
        return cls

    return decorator
