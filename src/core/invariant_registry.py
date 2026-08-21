"""N2 运行时不变量注册表 — 运行时关系守卫。

每个模块自声明不变量（installer），注册表统一检查。
对标 dsh InvariantRegistry（index.ts:136-197）。

约束：
- 只读内存状态（dict/list/属性）
- 禁 IO / 禁重算 / 禁网络请求
- <0.1ms CPU（启动毫秒级 + 定时微秒级）
"""

import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class InvariantError(Exception):
    """不变量违反 — 运行时关系不成立。"""


@runtime_checkable
class InvariantInstaller(Protocol):
    """不变量安装器协议 — 接收 fail 回调，检查不变量。

    installer 应只读内存状态，发现违反时调 fail(msg)。
    """

    def __call__(self, fail: Callable[[str], None]) -> None: ...


@dataclass(frozen=True)
class InvariantDesc:
    """不变量声明描述。"""

    name: str  # 模块名，如 "maisaka.replyer"
    installer: InvariantInstaller
    source_module: str = ""  # 注册者所在模块（防"注册别人名字"）


@dataclass
class InvariantViolation:
    """单次违反记录。"""

    name: str
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"name": self.name, "message": self.message, "timestamp": self.timestamp}


class InvariantRegistry:
    """不变量注册表 — 注册 + 统一检查 + 定时巡检。

    线程安全：单线程 asyncio 语境，register/verify_all 在事件循环里调用。
    """

    def __init__(
        self,
        *,
        enabled_modules: list[str] | None = None,
        disabled_modules: list[str] | None = None,
    ) -> None:
        self._items: dict[str, InvariantDesc] = {}
        self._enabled = set(enabled_modules) if enabled_modules is not None else None
        self._disabled = set(disabled_modules or [])
        self._periodic_task: asyncio.Task | None = None
        self._last_violations: list[InvariantViolation] = []

    def register(self, desc: InvariantDesc) -> Callable[[], None]:
        """注册不变量，返回 disposer（注销函数）。

        名称重复抛 ValueError。
        """
        if desc.name in self._items:
            raise ValueError(f"不变量名称重复注册: {desc.name}")
        self._items[desc.name] = desc
        logger.debug("不变量已注册: %s (source=%s)", desc.name, desc.source_module)

        def disposer() -> None:
            self._items.pop(desc.name, None)

        return disposer

    def is_enabled(self, name: str) -> bool:
        """检查某不变量是否启用（受 enabled/disabled 配置开关控制）。"""
        if name in self._disabled:
            return False
        if self._enabled is not None and name not in self._enabled:
            return False
        return True

    def verify_all(self) -> list[InvariantViolation]:
        """同步检查所有启用的不变量，返回违反列表。

        installer 内部异常捕获为违反（不应抛异常，应调 fail）。
        """
        violations: list[InvariantViolation] = []
        for name, desc in self._items.items():
            if not self.is_enabled(name):
                continue
            try:
                desc.installer(self._make_fail(name, violations))
            except InvariantError as exc:
                violations.append(InvariantViolation(name, str(exc)))
            except Exception as exc:
                # installer 不应抛异常，捕获为违反 + 记日志
                logger.warning("不变量 installer 异常: %s: %s", name, exc, exc_info=True)
                violations.append(InvariantViolation(name, f"installer 异常: {exc}"))
        self._last_violations = violations
        return violations

    def _make_fail(self, name: str, violations: list[InvariantViolation]) -> Callable[[str], None]:
        """构造 fail 回调。"""

        def fail(message: str) -> None:
            violations.append(InvariantViolation(name, message))

        return fail

    async def start_periodic_check(self, interval: float = 300.0) -> None:
        """启动定时巡检后台任务（默认 5 分钟一次）。"""
        if self._periodic_task is not None and not self._periodic_task.done():
            logger.warning("定时巡检已在运行，忽略重复启动")
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(interval)
                violations = self.verify_all()
                if violations:
                    for v in violations:
                        logger.warning("不变量违反: %s: %s", v.name, v.message)

        self._periodic_task = asyncio.create_task(_loop())
        logger.info("不变量定时巡检已启动，间隔 %.0fs", interval)

    async def stop_periodic_check(self) -> None:
        """停止定时巡检。"""
        if self._periodic_task is None:
            return
        self._periodic_task.cancel()
        try:
            await self._periodic_task
        except asyncio.CancelledError:
            pass
        self._periodic_task = None

    @property
    def last_violations(self) -> list[InvariantViolation]:
        """最近一次 verify_all 的违反列表。"""
        return self._last_violations

    @property
    def registered_names(self) -> list[str]:
        """已注册不变量名列表。"""
        return list(self._items.keys())


# ───────────────────────────── 全局单例 ─────────────────────────────

_registry: InvariantRegistry | None = None


def get_invariant_registry() -> InvariantRegistry:
    """获取全局不变量注册表单例。"""
    global _registry
    if _registry is None:
        _registry = InvariantRegistry()
    return _registry


def reset_invariant_registry() -> None:
    """重置全局注册表（测试用）。"""
    global _registry
    _registry = None


# ───────────────────────────── 装饰器 ─────────────────────────────


def invariant(
    name: str,
    *,
    registry: InvariantRegistry | None = None,
) -> Callable[[InvariantInstaller], InvariantInstaller]:
    """注册运行时不变量的装饰器。

    参数：
        name: 模块名，如 "maisaka.replyer"（防"注册别人名字"）
        registry: 目标注册表（默认全局单例）

    用法：
        @invariant("maisaka.replyer")
        def check_replyer(fail):
            if last_generation is not None and not last_generation.response_text:
                fail("last_generation 非空但 response_text 为空")
    """

    def decorator(installer: InvariantInstaller) -> InvariantInstaller:
        reg = registry if registry is not None else get_invariant_registry()
        source_module = sys._getframe(1).f_globals.get("__name__", "")
        disposer = reg.register(InvariantDesc(name=name, installer=installer, source_module=source_module))
        # 挂载 disposer 到 installer 便于测试清理
        setattr(installer, "_disposer", disposer)
        return installer

    return decorator