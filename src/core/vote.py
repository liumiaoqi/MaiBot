"""统一投票语义 — 对标 Linux NOTIFY_DONE/OK/STOP/BAD。

EventBus 与 NotifierChain 共享此模块，统一投票语义与 robust 回滚触发条件。
对标 include/linux/notifier.h:185-209（notifier.h 返回值宏 + errno 编解码）。

仅依赖 core 基础类型（src.core.types.MaiMessages），不依赖组件具体类，
满足 NFR-ZG4-CMP-04 微内核约束。
"""

from dataclasses import dataclass, field
from enum import IntEnum

from src.core.types import MaiMessages


class Vote(IntEnum):
    """统一投票枚举 — 对标 Linux NOTIFY_*。

    值与 Linux 完全一致（便于对照源码排障）：
    - DONE/OK 不设置 STOP_MASK（0x8000），继续遍历
    - STOP/BAD 设置 STOP_MASK，停止遍历；区别在是否触发回滚
    """

    DONE = 0x0000  # 不关心，继续
    OK = 0x0001  # 满意，继续
    STOP = 0x8001  # 正常停止，无错误，不触发回滚
    BAD = 0x8002  # 否决+错误，停止链，触发 robust 回滚

    @property
    def is_stop(self) -> bool:
        """停止判定 — 对标 NOTIFY_STOP_MASK (0x8000)。

        STOP 与 BAD 返回 True（停止后续遍历），DONE 与 OK 返回 False。
        """
        return bool(self & 0x8000)

    @property
    def triggers_rollback(self) -> bool:
        """是否触发 robust 回滚 — 仅 BAD。

        MaiBot 偏离 Linux：Linux 在 STOP_MASK 上回滚（含 STOP），
        MaiBot 只在 BAD 上回滚（见 design.md §2.2，有意偏离防照源码改回）。
        """
        return self is Vote.BAD


@dataclass
class VoteResult:
    """链遍历结束后的聚合结果。

    Attributes:
        final_vote: 最终 Vote（无停止时为 DONE/OK，被停止时为 STOP/BAD）
        vetoer: 否决者标识（handler name），仅 STOP/BAD 时有值
        reason: 否决原因（异常对象或字符串），仅 BAD 时有值
        modified_message: 拦截型链累积修改消息（EventBus 专属），无修改时为 None
        rolled_back: 是否触发了 robust 回滚（仅 robust 模式 + BAD 时为 True）
        failures: nofail 模式下所有失败记录列表（普通/robust 模式为空）
    """

    final_vote: Vote
    vetoer: str | None = None
    reason: BaseException | str | None = None
    modified_message: MaiMessages | None = None
    rolled_back: bool = False
    failures: list[tuple[str, BaseException | str]] = field(default_factory=list)

    @property
    def is_vetoed(self) -> bool:
        """是否被否决（STOP 或 BAD）。"""
        return self.final_vote.is_stop

    @property
    def is_bad(self) -> bool:
        """是否被 BAD 否决（出错中止）。"""
        return self.final_vote is Vote.BAD

    def serialize_reason(self) -> str:
        """序列化 reason 为字符串（日志/WebUI 用）。

        异常对象降级为 "类名: repr"，不丢失诊断信息（spec 5.1.3-2 兜底）。
        """
        if self.reason is None:
            return ""
        if isinstance(self.reason, BaseException):
            return f"{type(self.reason).__name__}: {self.reason!r}"
        return str(self.reason)


class VoteHistory:
    """投票历史环形缓冲 — 内省用（NFR-ZG4-MNT-02），EventBus/NotifierChain 共享。"""

    def __init__(self, capacity: int = 100) -> None:
        self._capacity = max(1, capacity)
        self._records: list[VoteResult] = []

    def append(self, result: VoteResult) -> None:
        """追加记录，超容量淘汰最早。"""
        self._records.append(result)
        if len(self._records) > self._capacity:
            self._records = self._records[-self._capacity:]

    def get_all(self) -> list[VoteResult]:
        return list(self._records)


class DuplicatePriorityError(Exception):
    """unique_priority 启用时同优先级重复注册。

    对标 Linux atomic_notifier_chain_register_unique_prio。
    含已有 handler 标识与冲突优先级，便于排障。
    """

    def __init__(self, priority: int, existing_name: str) -> None:
        self.priority = priority
        self.existing_name = existing_name
        super().__init__(
            f"优先级 {priority} 已被 handler '{existing_name}' 占用（unique_priority 启用）"
        )
