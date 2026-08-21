"""N3 模块健康检查 — 系统做对没做对。

契约：HealthCheck Protocol + HealthResult + HealthStatus。
模板：BaseHealthCheck（内置超时 + 异常降级）——补齐 Spring Boot Actuator 关键缺陷。
聚合：悲观策略 DOWN > DEGRADED > UP > UNKNOWN。
巡检：HealthService 定时后台 task（30-60s）+ 启动全量自检 + WebUI 按需查缓存。

设计参考：
- Spring Boot Actuator HealthIndicator（公开源码知识）
- 定时巡检为 MaiBot 原创（超越 Actuator——常驻进程主动巡检）
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class HealthStatus(IntEnum):
    """健康状态枚举 — 悲观聚合用 IntEnum（值越小越严重）。"""

    DOWN = 0  # 宕机：不能服务
    DEGRADED = 1  # 降级：半死半活但还能服务
    UP = 2  # 正常
    UNKNOWN = 3  # 未知：未检查或检查器未注册


@dataclass(frozen=True)
class HealthResult:
    """单次健康检查结果。"""

    status: HealthStatus
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.name.lower(),
            "details": self.details,
            "timestamp": self.timestamp,
        }


@runtime_checkable
class HealthCheck(Protocol):
    """健康检查协议 — 异步返回 HealthResult。"""

    name: str

    async def check(self) -> HealthResult: ...


class BaseHealthCheck:
    """模板基类：只写 _do_check，自动处理异常 + 超时降级。

    补齐 Spring Boot Actuator 关键缺陷：内置超时 + 异常统一降级。
    """

    timeout: float = 5.0

    def __init__(self, name: str, timeout: float | None = None) -> None:
        self.name = name
        if timeout is not None:
            self.timeout = timeout

    async def check(self) -> HealthResult:
        """模板方法：超时 + 异常降级，子类只实现 _do_check。"""
        try:
            return await asyncio.wait_for(self._do_check(), timeout=self.timeout)
        except asyncio.TimeoutError:
            return HealthResult(
                HealthStatus.DOWN,
                {"reason": "timeout", "timeout": self.timeout},
            )
        except Exception as exc:
            return HealthResult(
                HealthStatus.DOWN,
                {"error": str(exc), "type": exc.__class__.__name__},
            )

    async def _do_check(self) -> HealthResult:
        """子类实现具体检查逻辑。"""
        raise NotImplementedError


def aggregate_pessimistic(results: dict[str, HealthResult]) -> HealthResult:
    """悲观聚合器：取最严重状态（DOWN > DEGRADED > UP > UNKNOWN）。

    IntEnum 值越小越严重，min() 即悲观聚合。
    UNKNOWN 单独处理：全 UNKNOWN 才返回 UNKNOWN，否则取最严重非 UNKNOWN。
    """
    if not results:
        return HealthResult(HealthStatus.UNKNOWN, {"reason": "no checks registered"})

    statuses = [r.status for r in results.values()]
    non_unknown = [s for s in statuses if s != HealthStatus.UNKNOWN]

    if not non_unknown:
        return HealthResult(HealthStatus.UNKNOWN, {"checks": len(results)})

    worst = min(non_unknown)  # IntEnum 悲观聚合
    return HealthResult(
        worst,
        {
            "checks": {name: r.to_dict() for name, r in results.items()},
            "summary": {
                "up": sum(1 for s in statuses if s == HealthStatus.UP),
                "degraded": sum(1 for s in statuses if s == HealthStatus.DEGRADED),
                "down": sum(1 for s in statuses if s == HealthStatus.DOWN),
                "unknown": sum(1 for s in statuses if s == HealthStatus.UNKNOWN),
            },
        },
    )


class HealthService:
    """健康检查服务 — 注册检查器 + 定时巡检 + 缓存 + 聚合。

    线程安全：单线程 asyncio 语境。
    """

    def __init__(self, *, check_interval: float = 30.0) -> None:
        self._checks: dict[str, HealthCheck] = {}
        self._cache: dict[str, HealthResult] = {}
        self._check_interval = check_interval
        self._periodic_task: asyncio.Task | None = None

    def register(self, check: HealthCheck) -> Callable[[], None]:
        """注册健康检查器，返回 disposer。"""
        if check.name in self._checks:
            raise ValueError(f"健康检查器名称重复: {check.name}")
        self._checks[check.name] = check
        logger.debug("健康检查器已注册: %s", check.name)

        def disposer() -> None:
            self._checks.pop(check.name, None)
            self._cache.pop(check.name, None)

        return disposer

    async def check_all(self) -> dict[str, HealthResult]:
        """全量自检 — 并发执行所有检查器，更新缓存。"""
        if not self._checks:
            return {}
        results = await asyncio.gather(
            *(check.check() for check in self._checks.values()),
            return_exceptions=False,
        )
        for name, result in zip(self._checks.keys(), results, strict=True):
            self._cache[name] = result
        return dict(self._cache)

    async def check_one(self, name: str) -> HealthResult:
        """单个检查 — 更新缓存。"""
        check = self._checks.get(name)
        if check is None:
            return HealthResult(HealthStatus.UNKNOWN, {"reason": "check not registered"})
        result = await check.check()
        self._cache[name] = result
        return result

    async def get_health(self) -> HealthResult:
        """获取聚合健康状态（用缓存，不触发检查）。"""
        return aggregate_pessimistic(self._cache)

    async def get_health_detail(self) -> dict[str, Any]:
        """获取详细健康状态（含各检查器结果）。"""
        agg = await self.get_health()
        return {
            "status": agg.status.name.lower(),
            "details": agg.details,
            "timestamp": agg.timestamp,
        }

    async def start_periodic_check(self) -> None:
        """启动定时巡检后台任务。"""
        if self._periodic_task is not None and not self._periodic_task.done():
            logger.warning("定时巡检已在运行，忽略重复启动")
            return

        # 启动时立即全量自检一次
        await self.check_all()

        async def _loop() -> None:
            while True:
                await asyncio.sleep(self._check_interval)
                await self.check_all()

        self._periodic_task = asyncio.create_task(_loop())
        logger.info("健康巡检已启动，间隔 %.0fs", self._check_interval)

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
    def registered_names(self) -> list[str]:
        return list(self._checks.keys())


# ───────────────────────────── 全局单例 ─────────────────────────────


_service: HealthService | None = None


def get_health_service() -> HealthService:
    """获取全局健康检查服务单例。"""
    global _service
    if _service is None:
        _service = HealthService()
    return _service


def reset_health_service() -> None:
    """重置全局服务（测试用）。"""
    global _service
    _service = None