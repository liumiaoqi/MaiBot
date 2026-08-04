"""启动项声明层 — 装饰器 + 全局收集器。

迁移批次中，启动项以 @startup_item 装饰器声明，由 _StartupItemRegistry
在模块导入期收集，StartupOrchestrator 启动时一次性 drain 消费。
"""


from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .types import StartupPhase
from src.core.service_manager.types import DependencyKind


StartupInitFn = Callable[[], Awaitable[None]]
"""启动项初始化函数类型：无参数、返回协程。"""


@dataclass(frozen=True)
class StartupItemDesc:
    """启动项声明描述。

    init_fn 无参数，通过闭包或实例属性获取依赖，与 StartupComponent 的约定一致。
    """

    name: str
    phase: StartupPhase
    init_fn: StartupInitFn
    critical: bool = False
    depends_on: list[str] = field(default_factory=list)
    dependency_kind: dict[str, DependencyKind] = field(default_factory=dict)
    core_readiness_flag: str = ""
    order: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("startup item name 不能为空")
        if self.core_readiness_flag and not self.critical:
            raise ValueError(
                f"startup item {self.name!r} 声明了 core_readiness_flag 但 critical=False"
            )


class _StartupItemRegistry:
    """全局启动项声明收集器（单例）。

    register 负责名称唯一性校验；drain 一次性消费全部声明并清空内部存储。
    _running 为 True 时（编排已开始）禁止继续注册。
    """

    _instance: "_StartupItemRegistry | None" = None

    def __new__(cls) -> "_StartupItemRegistry":
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._items: dict[str, StartupItemDesc] = {}
            instance._running: bool = False
            cls._instance = instance
        return cls._instance

    def register(self, desc: StartupItemDesc) -> None:
        """注册启动项声明。

        名称重复抛 ValueError；编排已开始（_running=True）抛 RuntimeError。
        """
        if self._running:
            raise RuntimeError("启动编排已开始，禁止在运行期注册启动项")
        if desc.name in self._items:
            raise ValueError(f"启动项名称重复注册: {desc.name}")
        self._items[desc.name] = desc

    def drain(self) -> dict[str, StartupItemDesc]:
        """一次性取出全部已注册声明并清空内部存储。"""
        items = self._items
        self._items = {}
        return items


_registry = _StartupItemRegistry()


def startup_item(
    *,
    name: str,
    phase: StartupPhase,
    critical: bool = False,
    depends_on: list[str] | None = None,
    dependency_kind: dict[str, DependencyKind] | None = None,
    core_readiness_flag: str = "",
    order: int = 0,
) -> Callable[[StartupInitFn], StartupInitFn]:
    """注册 async 启动项声明的装饰器。

    装饰后返回原函数，不改变函数行为。缺少 name 或 phase 时由
    关键字参数签名直接抛出 TypeError。
    """

    def decorator(init_fn: StartupInitFn) -> StartupInitFn:
        _registry.register(
            StartupItemDesc(
                name=name,
                phase=phase,
                init_fn=init_fn,
                critical=critical,
                depends_on=depends_on if depends_on is not None else [],
                dependency_kind=dependency_kind if dependency_kind is not None else {},
                core_readiness_flag=core_readiness_flag,
                order=order,
            )
        )
        return init_fn

    return decorator
