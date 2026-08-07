"""OOMHandler — OOM 处理引擎，对标 Linux oom_kill + oom_reaper + oom_lock。

单锁串行 + 受害者选择 + oom_group 整组杀除 + 异步处置 + under_oom 计数。
oom_lock 在异步处置派发之前释放（ADR-04：锁内无 I/O）。
"""


import asyncio
from src.common.logger import get_logger
import time
import uuid
from collections import deque
from typing import Any, Callable, Optional

from src.core.error_escalation.types import ErrorLevel
from src.core.resource_limit.types import (
    OOMAction,
    OOMDecision,
    OOMDecisionRecord,
    ResourceDimension,
)

logger = get_logger(__name__)

_OOM_LOCK_TIMEOUT = 5.0
_REAP_MAX_ATTEMPTS = 10
_REAP_RETRY_INTERVAL = 0.5
_OOM_HISTORY_MAXLEN = 100


class OOMHandler:
    """OOM 处理引擎，对应 design §3.4。"""

    def __init__(
        self,
        resource_counter: Any = None,
        config_manager: Any = None,
        event_bus: Any = None,
        service_manager: Any = None,
        kill_callback: Optional[Callable[[str], bool]] = None,
    ):
        self._oom_lock = asyncio.Lock()
        self._oom_history: deque[OOMDecisionRecord] = deque(maxlen=_OOM_HISTORY_MAXLEN)
        self._reap_tasks: dict[str, asyncio.Task] = {}
        self._counter = resource_counter
        self._config = config_manager
        self._event_bus = event_bus
        self._service_manager = service_manager
        self._kill_callback = kill_callback

    async def trigger_oom(
        self,
        trigger_plugin_id: str,
        dimension: ResourceDimension,
        usage: int,
        limit: int,
    ) -> Optional[OOMDecision]:
        """触发 OOM 处理，对应 design §3.4.3。

        单锁串行，oom_lock 超时 5s 放弃。
        锁内仅纯内存操作（选受害者/计数/决策/历史），所有 await
        （事件发布/故障上报）在锁释放后执行（ADR-04：锁内无 I/O，
        CX 审查 P3 修正——原 emit/report 在锁内 await，慢回调可
        持锁超过 5s 获取超时导致并发 OOM 被丢弃）。
        """
        try:
            await asyncio.wait_for(self._oom_lock.acquire(), timeout=_OOM_LOCK_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("OOM 锁获取超时 %.1fs，放弃当前 OOM", _OOM_LOCK_TIMEOUT)
            return None

        victim = None
        group_targets: list[Any] = []
        decision: Optional[OOMDecision] = None
        record: Optional[OOMDecisionRecord] = None
        unresolved = False

        try:
            # 选受害者（纯内存）
            victim = self._select_victim(dimension)
            if victim is None:
                logger.warning("OOM 无可用受害者（全受保护或树空）")
                unresolved = True
            else:
                # 查找 oom_group 根
                group_targets = self._find_oom_group_targets(victim)
                # under_oom 计数递增
                self._increment_under_oom_chain(victim)

                # 生成决策
                decision_id = str(uuid.uuid4())
                decision_time = time.monotonic()
                action = OOMAction.KILL
                decision = OOMDecision(
                    decision_id=decision_id,
                    victim_plugin_id=victim.plugin_id,
                    victim_group=[t.plugin_id for t in group_targets],
                    action=action,
                    decision_time=decision_time,
                )

                # 记录决策到历史
                record = OOMDecisionRecord(
                    decision_id=decision_id,
                    victim_plugin_id=victim.plugin_id,
                    victim_group=[t.plugin_id for t in group_targets],
                    action=action,
                    decision_time=decision_time,
                    trigger_plugin_id=trigger_plugin_id,
                    trigger_dimension=dimension,
                    trigger_usage=usage,
                    trigger_limit=limit,
                    reap_attempts=0,
                    reap_success=False,
                )
                self._oom_history.append(record)
        finally:
            # oom_lock 在异步处置派发之前释放（ADR-04：锁内无 I/O）
            self._oom_lock.release()

        # ── 锁外：所有 await（CX 审查 P3 修正）──────────────────

        if unresolved:
            # 无可用受害者：上报 FATAL（OOM 无法处置）+ 锁外发布事件后返回
            self._report_oom(
                ErrorLevel.FATAL,
                "OOM 无可用受害者（全受保护或树空），系统资源无法回收",
                component_id=None,
            )
            if self._event_bus:
                try:
                    await self._event_bus.emit("resource.oom_unresolvable", {
                        "trigger_plugin_id": trigger_plugin_id,
                        "dimension": dimension.value,
                        "usage": usage,
                        "limit": limit,
                    })
                except Exception as e:
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, '发布 oom_unresolvable 事件失败', exception=e)
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.error("发布 oom_unresolvable 事件失败: %s", e)
            return None

        # 发布 OOM 事件
        if self._event_bus and decision is not None and victim is not None:
            try:
                await self._event_bus.emit("resource.oom", {
                    "decision_id": decision.decision_id,
                    "victim": decision.victim_plugin_id,
                    "group": decision.victim_group,
                    "action": decision.action.value,
                    "trigger_plugin_id": trigger_plugin_id,
                    "trigger_dimension": dimension.value,
                })
            except Exception as e:
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, '发布 OOM 事件失败', exception=e)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.error("发布 OOM 事件失败: %s", e)

        # 故障上报
        if self._service_manager and decision is not None:
            try:
                await self._service_manager.report_external_fault(
                    decision.victim_plugin_id,
                    "resource_oom",
                    f"dimension={dimension.value}, usage={usage}, limit={limit}",
                )
            except Exception as e:
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, '故障上报失败，OOM 流程继续', exception=e)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.error("故障上报失败，OOM 流程继续: %s", e)

        # ZG-14 接入（design §1.1.2）：KILL 处置前上报 CRITICAL。
        # 代码当前仅 KILL 路径（OOMAction.DEGRADE 未启用），KILL 前按
        # 烈度上报 CRITICAL；DEGRADE 路径启用后在其前补 report(WARN)。
        if decision is not None and victim is not None:
            self._report_oom(
                ErrorLevel.CRITICAL,
                "OOM 触发 KILL 处置",
                component_id=decision.victim_plugin_id,
            )

        # 异步处置（oom_lock 已释放）
        if decision is not None and record is not None:
            task = asyncio.create_task(
                self._reap_worker(group_targets, decision.decision_id, record)
            )
            self._reap_tasks[decision.decision_id] = task

        return decision

    def _report_oom(self, level: ErrorLevel, message: str, *, component_id: Optional[str]) -> None:
        """经 registry 获取 ZG-14 Port 上报（未注入跳过，不影响原 OOM 处置）。

        通过 Protocol + 运行时注入获取，不直接导入 ZG-14 具体类
        （spec §5.7.1 规则 9）；上报失败仅记日志不影响原处置。
        """
        try:
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                port.report(level, message, component_id=component_id)
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, 'ZG-14 上报失败，OOM 处置继续', exception=e)
            logger.warning("ZG-14 上报失败，OOM 处置继续: %s", e)

    def _select_victim(self, dimension: ResourceDimension) -> Optional[Any]:
        """选受害者：跳过 usage < min 的硬保护插件，选资源消耗最大者。"""
        if self._counter is None or self._config is None:
            return None

        candidates = self._counter.all_nodes()
        if not candidates:
            return None

        best = None
        best_usage = -1

        for node in candidates:
            # 跳过硬保护插件
            min_val = self._config.get_min(node.plugin_id, dimension)
            current_usage = node.usage.get(dimension, 0)
            if current_usage < min_val:
                continue

            if current_usage > best_usage:
                best = node
                best_usage = current_usage

        return best

    def _find_oom_group_targets(self, victim: Any) -> list[Any]:
        """查找 oom_group 根，返回处置范围。"""
        if self._config is None:
            return [victim]

        # 沿父链查找 oom_group=true 祖先
        group_root = None
        current = victim
        while current is not None:
            if self._config.is_oom_group(current.plugin_id):
                group_root = current
                break
            current = getattr(current, "parent", None)

        if group_root is None:
            return [victim]

        # 收集子树全部插件
        targets: list[Any] = []
        self._collect_subtree(group_root, targets)
        return targets

    def _collect_subtree(self, node: Any, targets: list[Any]) -> None:
        """收集子树全部插件。"""
        targets.append(node)
        for child in getattr(node, "children", []):
            self._collect_subtree(child, targets)

    def _increment_under_oom_chain(self, node: Any) -> None:
        """OOM 触发时受害者及所有祖先的 under_oom 计数 +1。"""
        current = node
        while current is not None:
            current.increment_under_oom()
            current = getattr(current, "parent", None)

    def _decrement_under_oom_chain(self, node: Any) -> None:
        """处置成功后递减 under_oom 计数。"""
        current = node
        while current is not None:
            current.decrement_under_oom()
            current = getattr(current, "parent", None)

    async def _reap_worker(
        self, targets: list[Any], decision_id: str, record: OOMDecisionRecord
    ) -> None:
        """异步处置 Worker，对应 design §3.4.5。

        oom_lock 释放后异步下发杀除指令。
        处置失败时重试，最多 10 次，每次间隔 0.5s。
        """
        success = False
        attempts = 0

        for attempt in range(_REAP_MAX_ATTEMPTS):
            attempts = attempt + 1
            all_killed = True

            for target in targets:
                try:
                    if self._kill_callback:
                        killed = self._kill_callback(target.plugin_id)
                        if not killed:
                            all_killed = False
                            logger.warning(
                                "OOM 杀除失败: %s (尝试 %d/%d)",
                                target.plugin_id,
                                attempts,
                                _REAP_MAX_ATTEMPTS,
                            )
                except Exception as e:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, 'OOM 杀除异常', exception=e)
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    all_killed = False
                    logger.error("OOM 杀除异常: %s -> %s", target.plugin_id, e)

            if all_killed:
                success = True
                break

            if attempt < _REAP_MAX_ATTEMPTS - 1:
                await asyncio.sleep(_REAP_RETRY_INTERVAL)

        if success:
            # 处置成功，递减 under_oom
            for target in targets:
                self._decrement_under_oom_chain(target)
            logger.info("OOM 处置成功: %s (尝试 %d 次)", decision_id, attempts)
        else:
            logger.error(
                "OOM 处置重试耗尽: %s (%d 次)", decision_id, _REAP_MAX_ATTEMPTS
            )

        # 更新历史记录
        updated = OOMDecisionRecord(
            decision_id=record.decision_id,
            victim_plugin_id=record.victim_plugin_id,
            victim_group=record.victim_group,
            action=record.action,
            decision_time=record.decision_time,
            trigger_plugin_id=record.trigger_plugin_id,
            trigger_dimension=record.trigger_dimension,
            trigger_usage=record.trigger_usage,
            trigger_limit=record.trigger_limit,
            reap_attempts=attempts,
            reap_success=success,
        )
        # 替换历史中的记录
        for i, r in enumerate(self._oom_history):
            if r.decision_id == decision_id:
                self._oom_history[i] = updated
                break

        self._reap_tasks.pop(decision_id, None)

    def get_oom_history(self, limit: int = 100) -> list[OOMDecisionRecord]:
        """查询 OOM 决策历史。"""
        return list(self._oom_history)[-limit:]
