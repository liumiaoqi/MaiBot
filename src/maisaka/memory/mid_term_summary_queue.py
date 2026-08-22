"""ZH1-1a: 异步摘要队列——asyncio.Queue 消费者模式。

设计参考：ZG16-5 scope_audit.py 的 asyncio.Queue 消费者模式
（scope_audit.py:41/106-111/135/168-169/185-210/213-252）。

方案 A（design 4.4）：消费者仅 build+persist 不直接操作 history，
chat_loop_service 下次构建上下文时从持久化表加载摘要 insert 到历史。
"""

import asyncio
import copy
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.common.logger import get_logger
from src.maisaka.context.messages import LLMContextMessage

logger = get_logger("maisaka.mid_term_summary_queue")


def _strip_binary_for_summary(msg: Any) -> Any:
    """剥离 binary_data（摘要只需文本 + 元数据，dsh review P2 性能优化）。"""
    stripped = copy.copy(msg)
    for attr in ("binary_data", "image_data", "emoji_data"):
        if hasattr(stripped, attr):
            setattr(stripped, attr, None)
    return stripped


@dataclass
class SummaryBuildSnapshot:
    """removed_messages 快照（入队深拷贝，解决保存窗口）。

    spec 5.3.1 规则 3 + 5.1.1 规则 9：入队时深拷贝，避免异步 build 期间
    原 removed_messages 被 GC 或修改。
    """
    messages: list[LLMContextMessage]
    session_id: str
    enqueued_at: datetime


class MidTermSummaryQueue:
    """异步摘要队列——asyncio.Queue + 消费者 task。

    设计参考 ZG16-5 scope_audit.py 的 asyncio.Queue 消费者模式。
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[SummaryBuildSnapshot] = asyncio.Queue(maxsize=maxsize)
        self._consumer_task: asyncio.Task | None = None
        self._closed = False

    def start(self) -> None:
        """启动消费者 task。"""
        if self._consumer_task is None:
            self._consumer_task = asyncio.create_task(
                self._consumer_loop(), name="mid_term_summary_consumer",
            )

    def enqueue_summary_build(
        self,
        removed_messages: Sequence[LLMContextMessage],
        session_id: str,
    ) -> None:
        """入队摘要 build（深拷贝 removed_messages + put_nowait）。

        spec 5.3.1 规则 2：入队耗时 < 5ms，不阻塞裁切主流程。
        spec 5.3.1 规则 3：深拷贝解决保存窗口。
        spec 5.3.1 规则 4：队列满丢弃最老 + warning。
        """
        try:
            # dsh review P2：先剥离 binary_data 再深拷贝（摘要只需文本，避免大组件拷贝开销）
            stripped = [_strip_binary_for_summary(msg) for msg in removed_messages]
            snapshot = SummaryBuildSnapshot(
                messages=copy.deepcopy(stripped),
                session_id=session_id,
                enqueued_at=datetime.now(),
            )
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty as exc:
                    # P0-6: 幂等清理出声（debug 防刷屏）（ZG-31）
                    logger.debug("摘要队列 get_nowait 空（幂等）: %s", exc)
                logger.warning("摘要队列已满，丢弃最老条目")
            self._queue.put_nowait(snapshot)
        except Exception as exc:
            logger.warning(f"摘要入队失败: {exc}")
            self._report_escalation(str(exc))

    async def _consumer_loop(self) -> None:
        """异步消费者：出队 → build → persist → 异常捕获 + 继续。

        spec 5.3.1 规则 5：单消费者串行处理。
        spec 5.3.1 规则 6：消费者异常不崩溃（捕获 + error + 上报 + 继续）。
        方案 A（design 4.4）：仅 build+persist，不直接操作 history。
        """
        while True:
            try:
                snapshot = await self._queue.get()
                await self._process_snapshot(snapshot)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"摘要消费者循环异常: {exc}", exc_info=True)
                self._report_escalation(str(exc))

    async def _process_snapshot(self, snapshot: SummaryBuildSnapshot) -> None:
        """处理一条摘要快照：build → persist（方案 A：不直接操作 history）。"""
        from src.maisaka.memory.mid_term import build_mid_term_memory_message
        from src.maisaka.memory.mid_term_persistence import get_mid_term_persistence

        log_prefix = f"[session={snapshot.session_id}] "
        result = await build_mid_term_memory_message(
            snapshot.messages,
            session_id=snapshot.session_id,
            log_prefix=log_prefix,
        )
        if result is None:
            return
        persistence = get_mid_term_persistence()
        if persistence is None:
            logger.warning(f"{log_prefix}持久化服务未初始化，摘要仅内存")
            return
        ok = await persistence.persist_summary_to_db(
            result.message, session_id=snapshot.session_id,
        )
        if ok:
            logger.info(
                f"{log_prefix}摘要生成+持久化成功: "
                f"msg_id={result.message.message_id} "
                f"total_tokens={result.total_tokens}"
            )
        else:
            logger.error(f"{log_prefix}摘要持久化失败，摘要仅内存（下次裁切可恢复）")

    async def close(self) -> None:
        """关闭：取消消费者 + flush 剩余队列（spec 5.3.1 规则 7）。"""
        if self._closed:
            return
        self._closed = True
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
                pass
            except Exception as exc:
                # P0-4: 关闭路径非预期异常出声（ZG-31）
                logger.warning("mid_term_summary_queue consumer 关闭异常: %s", exc, exc_info=True)
        while True:
            try:
                snapshot = self._queue.get_nowait()
                try:
                    await self._process_snapshot(snapshot)
                except Exception as exc:
                    logger.warning(f"关闭 flush 摘要处理失败，跳过: {exc}")
            except asyncio.QueueEmpty:
                break

    def _report_escalation(self, message: str) -> None:
        """上报 error_escalation_port（spec 9.5 静默失效禁令）。"""
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.ERROR, message, component_id="mid_term_summary_queue")


_mid_term_summary_queue: MidTermSummaryQueue | None = None


def init_mid_term_summary_queue(maxsize: int = 1000) -> MidTermSummaryQueue:
    """初始化全局摘要队列 + 启动消费者（@startup_item 触发）。

    maxsize: 队列容量上限，默认 1000（与 MidTermSummaryQueue 构造默认一致），
    队列满时丢弃最老条目（见 enqueue_summary_build）。
    """
    global _mid_term_summary_queue
    queue = MidTermSummaryQueue(maxsize=maxsize)
    queue.start()
    _mid_term_summary_queue = queue
    logger.info("MidTermSummaryQueue 已初始化（消费者已启动）")
    return queue


def get_mid_term_summary_queue() -> MidTermSummaryQueue | None:
    """返回全局单例（未初始化返回 None，调用方跳过入队）。"""
    return _mid_term_summary_queue


async def close_mid_term_summary_queue() -> None:
    """关闭全局摘要队列（main.py 关闭时调用）。"""
    global _mid_term_summary_queue
    if _mid_term_summary_queue is not None:
        await _mid_term_summary_queue.close()
        _mid_term_summary_queue = None
        logger.info("MidTermSummaryQueue 已关闭")