"""
核心事件总线

面向最终架构的事件系统：
- 内部 handler 直接注册 async callable
- IPC 插件通过 plugin_runtime 桥接
- 不依赖任何插件基类

ZG-4：统一 Vote 投票语义 + robust（BAD 触发逆序回滚）/ nofail 模式。
对标 Linux notifier chain（include/linux/notifier.h:185-209）。
"""

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from src.common.logger import get_logger
from src.core.types import EventType, MaiMessages
from src.core.vote import DuplicatePriorityError, Vote, VoteHistory, VoteResult

logger = get_logger("event_bus")

# Handler 签名：接收 MaiMessages，返回旧 (continue, modified) 或新 VoteResult
EventHandler = Callable[
    [Optional[MaiMessages]],
    Coroutine[Any, Any, Tuple[bool, Optional[MaiMessages]] | VoteResult],
]


@dataclass
class HandlerInfo:
    """handler 内省信息（NFR-ZG4-MNT-02）。"""

    name: str
    weight: int
    intercept: bool
    has_on_rollback: bool


class EventBus:
    """核心事件总线

    支持两种 handler：
    - 拦截型（intercept=True）：同步顺序执行，可修改消息、可中断流程、
      可返回 Vote 参与投票与 robust 回滚
    - 非拦截型（intercept=False）：异步并发执行，fire-and-forget，
      不参与投票与回滚

    handler 是纯 async callable，不需要继承任何基类。
    """

    def __init__(
        self,
        rollback_timeout: float = 5.0,
        vote_history_capacity: int = 100,
    ):
        # event_type -> [handler entry]
        self._handlers: Dict[EventType | str, List[_HandlerEntry]] = {}
        self._running_tasks: Dict[str, List[asyncio.Task]] = {}
        # event_type -> 投票历史环形缓冲（内省）
        self._history: Dict[EventType | str, VoteHistory] = {}

        # 回滚单个 on_rollback 超时（秒）；装配期可经 configure() 注入
        self._rollback_timeout = rollback_timeout

        # 预注册所有内置事件类型
        for event in EventType:
            self._handlers[event] = []
            self._history[event] = VoteHistory(vote_history_capacity)

    def configure(
        self,
        rollback_timeout: float | None = None,
        vote_history_capacity: int | None = None,
    ) -> None:
        """装配期注入配置（幂等，未注入项保持当前值/默认值）。

        模块级单例 import 时配置尚未加载（AGENTS.md 踩坑 #1），
        由 main.py 装配点调用（NFR-ZG4-CMP-04：核心不碰 config_manager）。
        """
        if rollback_timeout is not None:
            self._rollback_timeout = rollback_timeout
        if vote_history_capacity is not None:
            for history in self._history.values():
                history._capacity = max(1, vote_history_capacity)  # noqa: SLF001 — 同模块共享类

    def subscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
        name: str,
        weight: int = 0,
        intercept: bool = False,
        on_rollback: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        unique_priority: bool = False,
    ) -> None:
        """注册事件 handler

        Args:
            event_type: 事件类型
            handler: async callable，签名 (Optional[MaiMessages]) -> (bool, msg) 或 VoteResult
            name: handler 标识名
            weight: 权重，越大越先执行
            intercept: 是否为拦截型（同步执行，可中断流程、参与投票与回滚）
            on_rollback: 仅 intercept=True 有效，供 robust 模式逆序调用；
                intercept=False 提供则忽略并告警
            unique_priority: True 时同 weight 重复注册抛 DuplicatePriorityError
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
            self._history[event_type] = VoteHistory(self._history_capacity())

        if unique_priority:
            for entry in self._handlers[event_type]:
                if entry.weight == weight:
                    raise DuplicatePriorityError(weight, entry.name)

        if on_rollback is not None and not intercept:
            logger.warning("非拦截型 handler %s 提供 on_rollback 被忽略（仅拦截型参与回滚）", name)
            on_rollback = None

        entry = _HandlerEntry(
            handler=handler, name=name, weight=weight,
            intercept=intercept, on_rollback=on_rollback,
        )
        self._handlers[event_type].append(entry)
        self._handlers[event_type].sort(key=lambda e: e.weight, reverse=True)
        logger.debug(f"注册事件 handler: {name} -> {event_type} (weight={weight}, intercept={intercept})")

    def unsubscribe(self, event_type: EventType | str, name: str) -> bool:
        """取消注册事件 handler"""
        handlers = self._handlers.get(event_type, [])
        for i, entry in enumerate(handlers):
            if entry.name == name:
                del handlers[i]
                logger.debug(f"取消注册事件 handler: {name} <- {event_type}")
                return True
        return False

    async def emit(
        self,
        event_type: EventType | str,
        message: Optional[MaiMessages] = None,
        robust: bool = False,
        nofail: bool = False,
    ) -> VoteResult:
        """触发事件

        按权重顺序执行所有 handler：
        - 拦截型 handler 同步执行，可修改消息和中断流程
        - 非拦截型 handler 异步 fire-and-forget（不参与投票与回滚）

        Args:
            event_type: 事件类型
            message: 事件消息（可选）
            robust: True 时拦截型返回 BAD 触发已执行者逆序回滚（与 nofail 互斥）
            nofail: True 时遍历到底不停止，异常/BAD 记告警（与 robust 互斥）

        Returns:
            VoteResult（final_vote.is_stop 对应旧 continue_flag=False，
            向后兼容：不传 robust/nofail 时行为与旧版一致）
        """
        if robust and nofail:
            raise ValueError("robust 与 nofail 互斥，不能同时启用")

        handlers = self._handlers.get(event_type, [])
        if not handlers:
            result = VoteResult(final_vote=Vote.OK)
            self._record(event_type, result)
            return result

        current_message = message.deepcopy() if message else None
        intercept_handlers: List[_HandlerEntry] = [e for e in handlers if e.intercept]
        async_handlers: List[_HandlerEntry] = [e for e in handlers if not e.intercept]

        executed: List[_HandlerEntry] = []  # 已执行拦截型（robust 回滚用）
        failures: List[Tuple[str, BaseException | str]] = []
        final_vote = Vote.OK
        vetoer: Optional[str] = None
        reason: Optional[BaseException | str] = None
        rolled_back = False
        chain_stopped = False

        for entry in intercept_handlers:
            try:
                result = entry.handler(current_message)
                if asyncio.iscoroutine(result):
                    result = await result
                vote, cb_reason, modified = self._parse_handler_result(result)
                if modified is not None:
                    current_message = modified

                if vote is Vote.BAD:
                    bad_reason: BaseException | str = (
                        cb_reason if cb_reason is not None else "BAD without reason"
                    )
                    if cb_reason is None:
                        logger.warning(
                            "拦截型 handler %s 返回 BAD 未携带原因，降级为默认字符串", entry.name
                        )
                    if nofail:
                        # nofail：BAD 记录告警，继续遍历到底（spec 5.5.1-1b）
                        failures.append((entry.name, bad_reason))
                        final_vote = Vote.BAD
                        vetoer = entry.name
                        continue
                    final_vote = Vote.BAD
                    vetoer = entry.name
                    reason = bad_reason
                    chain_stopped = True
                    if robust:
                        # 逆序回滚已执行拦截型（不回滚触发 BAD 者本身）
                        rolled_back = True
                        for done in reversed(executed):
                            await self._rollback_one(done)
                    break
                if vote is Vote.STOP:
                    # 干净中止：不回滚（design.md §2.2 偏离）
                    final_vote = Vote.STOP
                    vetoer = entry.name
                    chain_stopped = True
                    break
                executed.append(entry)
            except Exception as e:
                logger.error(f"拦截型 handler {entry.name} 执行异常: {e}", exc_info=True)
                if nofail:
                    failures.append((entry.name, e))

        # BAD（普通/robust）或 STOP 停止链后，非拦截型不 fire（原 continue_flag 守卫）
        if not chain_stopped:
            for entry in async_handlers:
                async_message = current_message.deepcopy() if current_message else None
                self._fire_and_forget(entry, event_type, async_message)

        # 桥接到 IPC 插件运行时（逻辑不变，ZG-4 不变更桥接）。
        # nofail 遍历到底后桥接照常；STOP/BAD 停止链后桥接不执行（原守卫）。
        continue_flag = nofail or not final_vote.is_stop
        bridge_ran = continue_flag  # 桥接是否实际执行（False 时桥接直接返回）
        continue_flag, current_message = await self._bridge_to_ipc_runtime(
            event_type, continue_flag, current_message
        )
        if bridge_ran and not continue_flag:
            # 桥接中断（桥接实际执行且返回 False）：final_vote 降级 STOP
            # （vetoer=ipc_bridge，P1 决策；链内 STOP/BAD 的 vetoer 不被覆盖）
            final_vote = Vote.STOP
            vetoer = "ipc_bridge"
            reason = None

        # nofail 无 BAD 时 final_vote 为 DONE（spec 5.5.2-1 聚合规则）
        if nofail and final_vote is Vote.OK:
            final_vote = Vote.DONE

        result = VoteResult(
            final_vote=final_vote,
            vetoer=vetoer,
            reason=reason,
            modified_message=current_message,
            rolled_back=rolled_back,
            failures=failures,
        )
        self._record(event_type, result)
        return result

    async def cancel_handler_tasks(self, handler_name: str) -> None:
        """取消某个 handler 的所有运行中任务"""
        tasks = self._running_tasks.pop(handler_name, [])
        if remaining := [t for t in tasks if not t.done()]:
            for t in remaining:
                t.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)
            logger.info(f"已取消 handler {handler_name} 的 {len(remaining)} 个任务")

    # --- 内省（NFR-ZG4-MNT-02）---

    def get_handler_list(self, event_type: EventType | str) -> List[HandlerInfo]:
        """返回链上 handler（含 name/weight/intercept/has_on_rollback）。"""
        return [
            HandlerInfo(
                name=e.name,
                weight=e.weight,
                intercept=e.intercept,
                has_on_rollback=e.on_rollback is not None,
            )
            for e in self._handlers.get(event_type, [])
        ]

    def get_vote_history(self, event_type: EventType | str) -> List[VoteResult]:
        """返回最近 N 次投票结果。"""
        history = self._history.get(event_type)
        return history.get_all() if history else []

    # --- 内部方法 ---

    def _record(self, event_type: EventType | str, result: VoteResult) -> None:
        """记录投票历史（内省）。"""
        history = self._history.get(event_type)
        if history:
            history.append(result)

    def _history_capacity(self) -> int:
        """当前环形缓冲容量（configure 注入后反映新值）。"""
        for history in self._history.values():
            return history._capacity  # noqa: SLF001 — 同模块共享类
        return 100

    @staticmethod
    def _parse_handler_result(
        result: Tuple[bool, Optional[MaiMessages]] | VoteResult,
    ) -> Tuple[Vote, BaseException | str | None, Optional[MaiMessages]]:
        """解析 handler 返回值：旧 (continue_flag, msg) 或新 VoteResult。

        旧签名映射（design §4.5）：
        - (True, msg) → Vote.OK + modified_message=msg
        - (False, msg) → Vote.STOP（默认映射，不触发回滚，向后兼容）
        """
        if isinstance(result, VoteResult):
            return result.final_vote, result.reason, result.modified_message
        continue_flag, modified = result
        vote = Vote.OK if continue_flag else Vote.STOP
        return vote, None, modified

    def _fire_and_forget(
        self,
        entry: "_HandlerEntry",
        event_type: EventType | str,
        message: Optional[MaiMessages],
    ) -> None:
        """创建异步任务执行非拦截型 handler。"""
        try:
            task = asyncio.create_task(entry.handler(message))
            task.set_name(entry.name)
            task.add_done_callback(lambda t: self._task_done_callback(t, entry.name))
            self._running_tasks.setdefault(entry.name, []).append(task)
        except Exception as e:
            logger.error(f"创建 handler 任务 {entry.name} 失败: {e}", exc_info=True)

    def _task_done_callback(self, task: asyncio.Task, handler_name: str) -> None:
        """异步任务完成回调"""
        try:
            if task.cancelled():
                return
            if exc := task.exception():
                logger.error(f"handler {handler_name} 异步任务异常: {exc}")
                return
            result = task.result()
            if isinstance(result, VoteResult) and result.final_vote is Vote.BAD:
                # 非拦截型不参与投票：BAD 被忽略，仅告警（spec 5.3.1-5）
                logger.warning("非拦截型 handler %s 返回 BAD 被忽略（不参与投票）", handler_name)
        except Exception as exc:
            logger.debug("清理异步任务异常: %s", exc)
            pass
        finally:
            task_list = self._running_tasks.get(handler_name, [])
            with contextlib.suppress(ValueError):
                task_list.remove(task)

    async def _rollback_one(self, entry: "_HandlerEntry") -> None:
        """对单个已执行拦截型调 on_rollback（None 时 no-op），best-effort。"""
        if entry.on_rollback is None:
            return
        try:
            result = entry.on_rollback()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=self._rollback_timeout)
        except Exception:
            logger.exception("事件回滚异常（handler %s），回滚继续", entry.name)

    async def _bridge_to_ipc_runtime(
        self,
        event_type: EventType | str,
        continue_flag: bool,
        message: Optional[MaiMessages],
    ) -> Tuple[bool, Optional[MaiMessages]]:
        """将事件桥接到 IPC 插件运行时"""
        if not continue_flag:
            return continue_flag, message

        try:
            from src.plugin_runtime.integration import get_plugin_runtime_manager

            prm = get_plugin_runtime_manager()
            if not prm.is_running:
                return continue_flag, message

            event_value = event_type.value if isinstance(event_type, EventType) else str(event_type)
            message_dict = message.to_transport_dict() if message else None

            new_continue, modified_dict = await prm.bridge_event(
                event_type_value=event_value,
                message_dict=message_dict,
            )
            if not new_continue:
                continue_flag = False
            if modified_dict is not None and message is not None:
                message = self._apply_ipc_message_update(message, modified_dict)
        except Exception as e:
            logger.warning(f"桥接事件到 IPC 运行时失败: {e}")

        return continue_flag, message

    @staticmethod
    def _apply_ipc_message_update(message: MaiMessages, modified_dict: Dict[str, Any]) -> MaiMessages:
        """将 IPC 返回的消息字典回写到当前 MaiMessages。"""
        return message.apply_transport_update(modified_dict)


class _HandlerEntry:
    """内部 handler 条目"""

    __slots__ = ("handler", "name", "weight", "intercept", "on_rollback")

    def __init__(
        self,
        handler: EventHandler,
        name: str,
        weight: int,
        intercept: bool,
        on_rollback: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
    ):
        self.handler = handler
        self.name = name
        self.weight = weight
        self.intercept = intercept
        self.on_rollback = on_rollback


# 全局单例
event_bus = EventBus()
