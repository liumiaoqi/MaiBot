"""输入侧通电 · 前半（0004 转发）的最小用例。

⚠️ **这个文件的第一个用例不是"验收功能"，而是"证明那条分支真的被走到"** ——
在它跑出来之前，`relation_feedback` 分支是**"已落但未验"**（今晚那条：看着接了 ≠ 接了）。

它刻意**不依赖真库/容器**：只用一个最小 stub 过掉 `handle` 开头那两行脚手架
（`await self._kernel.initialize()` 与 `assert self._kernel.metadata_store`），
然后断言两件：

1. **空 `decision` ⇒ 具名拒绝**（而不是静默当成 `neutral` —— "降级可以、静默不行"）；
2. **给了 `decision` ⇒ 真的调到 `record_relation_feedback`，且四个实参逐条对得上**
   （`target→relation_hash` · `decision→action` · `updated_by→actor` · `reason→source_note`）。

第 2 条要的是"**接线**"而不是"**函数存在**"：它断言**参数是从 handle 的既有局部变量传过去的**，
而不是被某处默认值兜掉。
"""

import asyncio
from typing import Any

from src.A_memorix.core.runtime.admin.v5 import V5AdminHandler


class _StubMetadataStore:
    """最小 stub —— **但两个用例对它的要求不同，要分开看**：

    · 用例 1（具名拒绝）在触碰 `metadata_store` **之前**就返回 ⇒ 那时它确实什么都不用实现；
    · 用例 2/3 会让流程**走完分支** ⇒ 会调到 `record_v5_operation` ⇒ 这里**必须有它**。

    ⚠️ 教训（本轮实测）：stub 按"能过断言"写到最小 ⇒ 用例 2 会红；
    而**红的原因在脚手架、不在产品** —— 判据是"**红在哪一层**"，不是"红没红"。
    """

    def __init__(self) -> None:
        self.ops: list[dict[str, Any]] = []

    def record_v5_operation(self, **kwargs: Any) -> dict[str, Any]:
        self.ops.append(kwargs)
        return {"operation_id": "stub-op"}


class _RecordingV5MemoryService:
    """记录调用实参的假服务（验证"接线"而不是"函数存在"）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record_relation_feedback(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"success": True}


class _StubKernel:
    def __init__(self) -> None:
        self.metadata_store = _StubMetadataStore()
        self._v5_memory_service = _RecordingV5MemoryService()

    async def initialize(self) -> None:
        return None


def test_relation_feedback_without_decision_is_a_named_refusal() -> None:
    """⭐ 证明分支被走到：空 `decision` ⇒ 具名拒绝（不是静默 neutral、也不是掉进 fall-through）。"""

    handler = V5AdminHandler(_StubKernel())

    result = asyncio.run(handler.handle("relation_feedback", target="h1"))

    assert result["success"] is False, f"空 decision 被放过了：{result}"
    assert "decision" in result["error"], f"拒绝理由没点名 decision：{result}"
    # 反向自检：若这条分支没被走到，未知 action 会掉进末尾 fall-through
    # ⇒ 那里会先调 `_resolve_relation_hashes`（stub 没有它）⇒ 抛 AttributeError 而不是返回本结果。
    assert "relation_hash" not in str(result), "像是被当成别的动作处理了"


def test_relation_feedback_passes_handle_locals_straight_through() -> None:
    """接线断言：四个实参**由 handle 的既有局部变量**直通（不是被默认值兜掉）。"""

    kernel = _StubKernel()
    handler = V5AdminHandler(kernel)

    asyncio.run(
        handler.handle(
            "relation_feedback",
            target="hash-abc",
            decision="raise",
            updated_by="刘妙奇",
            reason="今晚聊得好",
        )
    )

    calls = kernel._v5_memory_service.calls
    assert len(calls) == 1, f"应当恰好调一次 record_relation_feedback，实际 {len(calls)}"
    assert calls[0]["relation_hash"] == "hash-abc", calls[0]
    assert calls[0]["action"] == "raise", calls[0]
    assert calls[0]["actor"] == "刘妙奇", calls[0]
    assert calls[0]["source_note"] == "今晚聊得好", calls[0]

    # 留痕断言 —— 这是 (乙) 第一条（`memory_v5_operations` 0→≥1）在**纯测试**里的落点：
    # 真库那条靠"表从没被写过"，这里靠"桩从没被调过"，两处同形。
    ops = kernel.metadata_store.ops
    assert len(ops) == 1, f"应当恰好留痕一次，实际 {len(ops)}"
    assert ops[0]["action"] == "relation_feedback", ops[0]
    # ⚠️ `resolved_hashes` 是**必填**（`metadata_store.py:1311`，无默认）⇒ 这条同时锁住"传了它"
    assert ops[0]["resolved_hashes"] == ["hash-abc"], ops[0]


def test_empty_decision_does_not_silently_become_neutral() -> None:
    """**证红用**：空 `decision` **不得**被当成 `neutral` 送进去（`neutral` 只留痕不动值 ⇒ 静默无害更危险）。"""

    kernel = _StubKernel()
    handler = V5AdminHandler(kernel)

    asyncio.run(handler.handle("relation_feedback", target="h1", decision="   "))

    assert kernel._v5_memory_service.calls == [], (
        "空白 decision 被当成一次真实动作送进去了 —— 这正是'静默把没传当 neutral'"
    )
