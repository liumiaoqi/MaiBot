"""插件活体引用计数 — 对标 Linux try_module_get/put。

ZG-15 核心机制：
- PluginState 四态机（LIVE/COMING/GOING/UNFORMED），单向流转 LIVE→GOING→UNFORMED
- PluginRefcount：同步段 try_acquire/release（无 await，单事件循环内无 TOCTOU），
  mark_going 设 GOING 后新 acquire 原子失败，wait_drained 等待在途引用清零
- PluginHandle：acquire() 异步上下文管理器，保证 acquire/release 对称
- 自由线程兼容：Python 3.14 free-threaded 构建下用 threading.Lock 保护

对标 Linux（`kernel/module/main.c:935-960`）：
- try_module_get（检查 live + 原子 inc）→ try_acquire
- module_put（dec + 防下溢 WARN）→ release
- try_stop_module（设 GOING）→ mark_going
- async_synchronize_full + module_wq（等待在途完成）→ wait_drained
"""

import asyncio
import sys
import time
from dataclasses import dataclass, field
from enum import Enum

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.lifecycle.refcount")


class PluginState(str, Enum):
    """插件生命周期状态 — 对标 Linux `enum module_state`。

    单向流转约束：LIVE → GOING → UNFORMED，不可逆。
    - LIVE：正常运行，可 acquire
    - COMING：初始化中（v2 无 on_load 阶段，预留不激活；try_acquire 遇 COMING 行为同 LIVE）
    - GOING：卸载中，新 try_acquire 立即失败
    - UNFORMED：已释放/未构造，不可用
    """

    LIVE = "live"
    COMING = "coming"
    GOING = "going"
    UNFORMED = "unformed"
    ERROR = "error"


@dataclass
class InflightEntry:
    """在途调用追踪条目 — 供 wait_drained 超时诊断（定位哪个 tool 未返回）。"""

    tool_name: str
    acquire_time: float = field(default_factory=time.monotonic)
    runner_id: str = ""


class PluginRefcount:
    """插件活体引用计数器 — 对标 try_module_get/put。

    单事件循环内同步检查 + inc/dec 无锁；free-threaded 构建下用 threading.Lock。
    线程模型声明（CX 审查 P1）：**所有状态访问限定在同一事件循环线程**——
    acquire/release/mark_going 由 asyncio 任务调用；同步 handler 的 worker
    线程不得直接触碰 refcount（其生命周期经 done callback 回事件循环处理）。
    在此前提下标准分支无 TOCTOU，Lock 分支仅作 free-threaded 兜底。
    """

    # 自由线程检测结果（类级缓存，避免每次实例化都查）
    _free_threaded: bool | None = None

    def __init__(self, plugin_id: str) -> None:
        self._plugin_id = plugin_id
        self._state: PluginState = PluginState.LIVE
        self._refcount: int = 0
        self._zero_event: asyncio.Event = asyncio.Event()
        self._zero_event.set()  # 初始 refcount==0，已触发
        self._inflight_entries: list[InflightEntry] = []
        if PluginRefcount._free_threaded is None:
            PluginRefcount._free_threaded = self._detect_free_threaded()
        self._lock = __import__("threading").Lock() if PluginRefcount._free_threaded else None

    @staticmethod
    def _detect_free_threaded() -> bool:
        """检测 Python 是否 free-threaded 构建（无 GIL 时同步段非原子）。"""
        checker = getattr(sys, "_is_gil_enabled", None)
        if checker is None:
            return False
        free = not checker()
        if free:
            logger.warning(
                "检测到 Python free-threaded 构建——PluginRefcount 启用 threading.Lock 保护"
            )
        return free

    # ── acquire/release（同步段，无 await）────────────────────────

    def try_acquire(self, tool_name: str = "", runner_id: str = "") -> bool:
        """对标 try_module_get：检查非 GOING + 递增 refcnt。

        同步段（无 await）——asyncio 单线程下"检查 + inc"无交错窗口。
        失败（GOING）时返回 False，调用方应拒绝执行。

        Args:
            tool_name: 在途调用的工具名（超时诊断用）
            runner_id: 所属 Runner 标识（超时诊断用）

        Returns:
            True 若成功 acquire（state 非 GOING 且已 inc）；False 若 GOING 中。
        """
        if self._lock is not None:
            with self._lock:
                return self._try_acquire_locked(tool_name, runner_id)
        return self._try_acquire_locked(tool_name, runner_id)

    def _try_acquire_locked(self, tool_name: str, runner_id: str) -> bool:
        # CX 审查 P1：UNFORMED 是终态——仅 LIVE/COMING 允许 acquire
        if self._state != PluginState.LIVE and self._state != PluginState.COMING:
            return False
        # LIVE/COMING：inc（同步，无交错窗口）
        self._refcount += 1
        self._zero_event.clear()  # refcount > 0，清零事件未触发
        if tool_name:
            self._inflight_entries.append(InflightEntry(tool_name=tool_name, runner_id=runner_id))
        logger.debug(
            "PluginRefcount acquire: plugin=%s refcount=%d state=%s",
            self._plugin_id, self._refcount, self._state,
        )
        return True

    def release(self) -> None:
        """对标 module_put：dec refcnt + 唤醒等待者。

        下溢（refcount<=0 多 put 少 get）输出 WARNING，对标 WARN_ON(ret < 0)。
        """
        if self._lock is not None:
            with self._lock:
                self._release_locked()
        else:
            self._release_locked()

    def _release_locked(self) -> None:
        if self._refcount <= 0:
            logger.warning(
                "PluginRefcount 下溢: plugin=%s refcount=%d",
                self._plugin_id, self._refcount,
            )
            return
        self._refcount -= 1
        if self._inflight_entries:
            self._inflight_entries.pop()  # 后进先出移除（O(1)）
        if self._refcount == 0:
            self._zero_event.set()  # 唤醒卸载等待者
        logger.debug(
            "PluginRefcount release: plugin=%s refcount=%d state=%s",
            self._plugin_id, self._refcount, self._state,
        )

    # ── 卸载侧（GOING 设置 + 排空等待）──────────────────────────

    def mark_going(self) -> bool:
        """对标 try_stop_module：设 GOING，若有在途引用则返回 False。

        Returns:
            True 若 refcount==0 可立即卸载；
            False 若有在途引用（调用方应 await wait_drained）。
        """
        if self._lock is not None:
            with self._lock:
                return self._mark_going_locked()
        return self._mark_going_locked()

    def _mark_going_locked(self) -> bool:
        # CX 审查 P1：UNFORMED/ERROR 是终态——禁止回退
        if self._state in (PluginState.UNFORMED, PluginState.ERROR):
            return False
        if self._state == PluginState.GOING:
            return self._refcount == 0
        self._state = PluginState.GOING
        logger.info("PluginRefcount mark_going: plugin=%s refcount=%d", self._plugin_id, self._refcount)
        return self._refcount == 0

    async def wait_drained(self, timeout_s: float | None = None) -> bool:
        """对标 async_synchronize_full + module_wq：等待在途引用清零。

        Returns:
            True 若清零；False 若超时（输出 ERROR 日志含在途详情）。
        """
        if self._refcount == 0:
            return True
        try:
            await asyncio.wait_for(self._zero_event.wait(), timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            inflight = ", ".join(f"{e.tool_name}({time.monotonic() - e.acquire_time:.1f}s)"
                                 for e in self._inflight_entries) or "无"
            logger.error(
                "PluginRefcount 排空超时: plugin=%s refcount=%d timeout=%ss 在途=%s",
                self._plugin_id, self._refcount, timeout_s, inflight,
            )
            return False

    def mark_unformed(self) -> None:
        """卸载完成后设 UNFORMED（对标 free_module 的 state 转换）。"""
        self._state = PluginState.UNFORMED

    def mark_error(self) -> None:
        """on_load 失败时设 ERROR——终态，try_acquire 拒新，不可恢复。"""
        self._state = PluginState.ERROR
        logger.warning(
            "PluginRefcount mark_error: plugin=%s refcount=%d",
            self._plugin_id, self._refcount,
        )

    # ── 只读属性 ────────────────────────────────────────────────

    @property
    def state(self) -> PluginState:
        return self._state

    @property
    def refcount(self) -> int:
        return self._refcount

    @property
    def inflight_entries(self) -> list[InflightEntry]:
        return list(self._inflight_entries)


class PluginHandle:
    """插件活体句柄 — 提供 acquire() 上下文管理器。

    使用方式：
        async with handle.acquire() as h:
            if h is None:
                return error("PLUGIN_GOING")
            result = await h.some_tool(args)
    """

    def __init__(self, plugin: object, refcount: PluginRefcount) -> None:
        self._plugin = plugin
        self._refcount = refcount

    @property
    def plugin(self) -> object:
        return self._plugin

    @property
    def refcount(self) -> PluginRefcount:
        return self._refcount

    def acquire(self, tool_name: str = "", runner_id: str = ""):
        """async 上下文管理器：__aenter__ 调 try_acquire，__aexit__ 调 release。"""
        return _PluginAcquire(self, tool_name, runner_id)


class _PluginAcquire:
    """acquire 上下文管理器的内部实现（async context manager）。"""

    def __init__(self, handle: PluginHandle, tool_name: str, runner_id: str) -> None:
        self._handle = handle
        self._tool_name = tool_name
        self._runner_id = runner_id
        self._acquired = False

    async def __aenter__(self):
        self._acquired = self._handle._refcount.try_acquire(
            tool_name=self._tool_name, runner_id=self._runner_id,
        )
        if not self._acquired:
            return None  # GOING 中，调用方收 None 拒绝
        return self._handle._plugin

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._acquired:
            self._handle._refcount.release()
