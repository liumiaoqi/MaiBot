"""T22 性能测试 — 控制消息入队热路径（spec §4.1 性能 2：单次入队 ≤ 30μs）。

⚠️ 测量口径（2026-10-17 改，**看的不是"一遍跑多快"，是"稳定落在哪"**）
    判据 = **中位**；**max 是早警，不参与判定但长期越界要报**。
    为什么：本成员原先报"均值 × 单次" ⇒ 在**未被压稳的进程**里会被
    **冷进程 / 页缓存首触 / CPU 频率爬升**抬高（实测冷首轮 36.02µs vs 其后 23.10µs，
    同刻跨度曾达 **2.10×**），该方差**至少一部分是自造的**。
    ⇒ 现在固定为 **预热一轮（数值打印）+ 丢弃首个计时轮 + 正式 N=5 轮**，
    每轮一个均值，取**中位**判 30µs；min/max 一并打印当作早警。
    残余窗口（**如实记**）：此法只消掉"自造的"那一半（预热/爬升）；
    **短时争用那一半仍在**（哨兵实测：并发一跑，本例中位可从 ~20µs 抬到 38–51µs）
    ⇒ 本成员**仍可能偶发**，只是**不再是自造的**。
"""

import statistics
import threading
import time

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.types import ControlMessageKind

# 性能阈值（spec §4.1 性能 2）
ENQUEUE_BUDGET_US = 30.0
# 采样次数（去抖动）：每个计时轮内部的操作次数
SAMPLES = 2000
# 正式计时轮数（判据取这些轮的中位）
ROUNDS = 5
# 正式段前丢弃的计时轮数（预热轮之外）——冷进程残压不止一轮
DISCARD_ROUNDS = 1
# 队列节点上限：对齐生产量级（spec §5.8.1 规则 5）。
# 依据 `src/core/control_message/two_level_pending.py:27-28`：私有 256 / 共享 1024。
# ⚠️ 参数面对不上（如实记）：生产是**两级各一个上限**，本测试只有一个 `max_nodes`
# ⇒ 只能对齐其中一级，取 **256 = `ControlMessagePending` 的默认值 + 私有队列上限**，
# 理由：生产入队多数走私有队列（`send_to_session`，会话不存在才降级共享），
# 且同胞成员 `tests/perf/control_message/test_perf_dequeue.py:32` 已取 256。
# ⚠️ 该上限**决定走哪条分支**（实测）：100000 时 2000 次入队不溢出（队列长到 ~2001，只有去重分支）；
# 256/1024 时队列很快到顶 ⇒ 溢出的实时消息**每条都要 `_find_eviction_target` 全队列扫一遍后拒收**。
# ⇒ **本 KPI 的绝对值 =「队列上限 × 队列算法」的合成，不是"代码贵不贵"的单独度量**；
# 换上限 = **换仪器** ⇒ 旧数字与新数字不可比、必须重记基线。
QUEUE_MAX_NODES = 256


def _info() -> dict[str, object]:
    return {"source": "perf", "payload": {"n": 1}, "timestamp": 1.0, "trace_id": "perf"}


def _run_round(samples: int = SAMPLES) -> float:
    """跑一轮完整 enqueue 序列（**每对入队后按生产消费点排空**），返回单次入队均值（µs）。

    预热轮与计时轮**走同一函数** ⇒ 预热数字与计时的数字同一口径、可直接比。
    每轮用**新队列**：队列状态（节点数）也是方差源，不给下一轮留残留。

    ⚠️ 出队比例 = **每个入队对之后排空到 None**。依据是生产消费点本身为"排空式"：
    `src/chat/message_receive/bot.py:371-376` 是 `while True: dequeue_next(...)` 直到 None，
    而消费点 = **每条入站用户消息一次**（`bot.py:796`）⇒ 生产队列**每个消费点都回到空**，
    不是"远小于 cap"，而是**常态归零**。本形态下队列长度只在 0→2 间摆动 ⇒
    既到不了上限、也走不到溢出拒收（`_find_eviction_target` 全队列扫描）。
    ⚠️ 计时口径未变：**只计 enqueue** —— dequeue 落在两拍之间的计时盲区，不进分子。
    ⚠️ 偏差面（如实记）：排空同时把位图清零 ⇒ 本形态**走不到去重分支**
    （`pending_queue.py:72-83` 的 `del node_list[i]`）。该面由同胞成员
    `test_dedup_hot_path` 覆盖（它本就只用 2 节点队列，已是生产形态）。
    """
    q = ControlMessagePending(
        kind_registry=ControlMessageKindRegistry(), max_nodes=QUEUE_MAX_NODES
    )

    total_s = 0.0
    for _ in range(samples):
        # 入队单独计时（不含 dequeue，避免混合开销）
        t0 = time.perf_counter()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        t1 = time.perf_counter()
        total_s += t1 - t0

        # 生产消费点：排空到 None（与 bot.py:372-376 同形）
        while q.dequeue(0, 0) is not None:
            pass

    return total_s / (samples * 2) * 1e6


class TestPerfEnqueue:
    def test_enqueue_hot_path(self) -> None:
        """单次入队 ≤ 30μs（标准消息，位图 + 链表尾插）——判据 = N=5 的中位数。

        ⚠️ **该成员测的是一条尚未接线的路径**（2026-10-17 接线审计）：被计的 `ControlMessagePending.enqueue` 在生产里只有一条来路 —— `adapter.send()`（`control_message_adapter.py:196` / `:198` → `two_level_pending.py:95` / `:101`），
        而 `ControlMessagePort.send()` 在 `src/` 中**零生产调用点**：唯二投递方 `main.py:607`（看门狗超时）与 `escalator.py:519`（FATAL 扩散）**都走 `force_send`**，
        而 `force_enqueue` 绕开 `enqueue()` 直接 append（`two_level_pending.py:150-152`）⇒ **本成员的绝对值 = 该路径接上生产之前的已知上界**，
        不是"生产热路径的当前开销"。⚠️ 连带：`_run_round` 里"依据生产消费点排空"的前提（`bot.py:371-376`）也被
        `bot.py:360-361` 的 `get_control_message_global_enabled()`（默认 `False`，`official_configs.py:7542`）挡在门外 ⇒ **排空形态是设计的，不是实测的**。
        """
        # 预热**一整轮**（走同一函数），数值打印：让人看见"一次预热把值压到哪"
        warm_us = _run_round()
        # 冷进程残压不止一轮 ⇒ 正式段前再丢一轮（两级形态；依据见模块 docstring 与 §八）
        dropped_us = [_run_round() for _ in range(DISCARD_ROUNDS)]
        print(
            f"\n预热轮（已丢弃）: {warm_us:.2f}μs"
            + (" ｜ 再弃计时轮: " + ", ".join(f"{d:.2f}" for d in dropped_us) + "μs" if dropped_us else "")
        )

        # 正式段：N 轮，每轮一个均值 ⇒ 取中位判 30µs，min/max 仅备查（早警）
        threads_before = threading.active_count()
        rounds_us = [_run_round() for _ in range(ROUNDS)]
        threads_after = threading.active_count()
        print("正式轮逐轮: " + ", ".join(f"{r:.2f}" for r in rounds_us))
        median = statistics.median(rounds_us)
        mn = min(rounds_us)
        mx = max(rounds_us)
        # 同时刻并发线程数：>1 说明有别的活在同刻跑（哨兵/它测）⇒ 读数字时要连它一起看
        print(f"同时刻并发线程数: {threads_before} → {threads_after}")
        print(
            f"入队中位: {median:.2f}μs"
            f"（n={len(rounds_us)}, min {mn:.2f}, max {mx:.2f}，"
            f"预算 {ENQUEUE_BUDGET_US}μs；预热 {warm_us:.2f}μs）"
        )
        assert median <= ENQUEUE_BUDGET_US

    def test_dedup_hot_path(self) -> None:
        """标准消息去重入队 ≤ 30μs（位图命中 + payload 更新 + 移至尾部）。"""
        registry = ControlMessageKindRegistry()
        q = ControlMessagePending(kind_registry=registry, max_nodes=QUEUE_MAX_NODES)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info())

        start = time.perf_counter()
        for _ in range(SAMPLES):
            q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / SAMPLES * 1e6
        print(f"\n去重入队均值: {per_op_us:.2f}μs（预算 {ENQUEUE_BUDGET_US}μs）")
        assert per_op_us <= ENQUEUE_BUDGET_US

    def test_throughput_5000_per_sec(self) -> None:
        """投递频率 ≥ 5000 次/秒（spec §4.1 性能 6：单次 ≤ 200μs 等效）。"""
        registry = ControlMessageKindRegistry()
        q = ControlMessagePending(kind_registry=registry, max_nodes=QUEUE_MAX_NODES)

        start = time.perf_counter()
        for _ in range(SAMPLES):
            q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        elapsed = time.perf_counter() - start
        rate = SAMPLES / elapsed
        print(f"\n入队吞吐: {rate:.0f} 次/秒（要求 ≥ 5000）")
        assert rate >= 5000
