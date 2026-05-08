"""
使用方法
python .\scripts\reproduce_maisaka_memory_growth.py --messages 100 --batch-size 50 --sessions 100 --session-batch-size 50 --payload-size 1024 --session-payload-size 1024

"""


from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import argparse
import asyncio
import gc
import inspect
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class PayloadMessage:

    __slots__ = ("message_id", "timestamp", "payload")

    def __init__(self, message_id: str, payload_size: int) -> None:
        self.message_id = message_id
        self.timestamp = SimpleNamespace(timestamp=lambda: time.time())
        self.payload = bytearray(payload_size)


@dataclass
class FakeRuntime:
    payload: bytearray
    stopped: bool = False

    async def stop(self) -> None:
        self.stopped = True

    def prune_runtime_caches(self) -> None:
        return None


def _bool_cn(value: bool) -> str:
    return "是" if value else "否"


def _build_maisaka_runtime_stub(max_cache_size: int) -> Any:
    from src.learners.expression_learner import ExpressionLearner
    from src.maisaka.runtime import MaisakaHeartFlowChatting

    runtime = object.__new__(MaisakaHeartFlowChatting)
    runtime._running = False
    runtime._last_message_received_at = 0.0
    runtime._last_processed_index = 0
    runtime._message_cache_max_size = max_cache_size
    runtime.message_cache = []
    runtime._message_received_at_by_id = {}
    runtime._source_messages_by_id = {}
    runtime.history_loop = []
    runtime.log_prefix = "[memory-repro]"
    runtime._expression_learner = ExpressionLearner("memory-repro-session")
    runtime._enable_expression_learning = False
    runtime._enable_jargon_learning = False
    runtime._agent_state = "idle"
    runtime._STATE_RUNNING = "running"
    runtime._reply_latency_measurement_started_at = None
    runtime._message_debounce_required = False
    runtime._update_message_trigger_state = lambda message: None
    runtime._is_reply_effect_tracking_enabled = lambda: False
    return runtime


def _mark_expression_learner_consumed(runtime: Any) -> None:
    learner = runtime._expression_learner
    if hasattr(learner, "set_processed_message_cache_index"):
        learner.set_processed_message_cache_index(len(runtime.message_cache))
        return
    if hasattr(learner, "_last_processed_index"):
        learner._last_processed_index = len(runtime.message_cache)


async def _maybe_call_runtime_prune(runtime: Any) -> bool:
    prune_runtime_caches = getattr(runtime, "prune_runtime_caches", None)
    if not callable(prune_runtime_caches):
        return False

    result = prune_runtime_caches()
    if inspect.isawaitable(result):
        await result
    return True


async def probe_maisaka_message_cache(args: argparse.Namespace) -> bool:
    from src.maisaka.runtime import MaisakaHeartFlowChatting

    runtime = _build_maisaka_runtime_stub(args.max_cache_size)
    print("[Maisaka 消息缓存]")
    print("批次,累计注册消息数,缓存消息数,原始消息映射数,已处理下标,MB")

    for index in range(args.messages):
        message = PayloadMessage(f"m{index}", args.payload_size)
        await MaisakaHeartFlowChatting.register_message(runtime, message)
        if (index + 1) % args.batch_size != 0:
            continue

        MaisakaHeartFlowChatting._collect_pending_messages(runtime)
        if args.call_prune:
            _mark_expression_learner_consumed(runtime)
            await _maybe_call_runtime_prune(runtime)
        gc.collect()

        retained_payload = sum(len(message.payload) for message in runtime.message_cache)
        print(
            f"{(index + 1) // args.batch_size},"
            f"{index + 1},"
            f"{len(runtime.message_cache)},"
            f"{len(runtime._source_messages_by_id)},"
            f"{runtime._last_processed_index},"
            f"{retained_payload / 1024 / 1024:.2f}"
        )

    issue_observed = len(runtime.message_cache) > args.max_cache_size
    print(f"是否观察到无界增长={_bool_cn(issue_observed)}")
    return issue_observed


async def probe_heartflow_session_registry(args: argparse.Namespace) -> bool:
    from src.chat.heart_flow.heartflow_manager import HeartflowManager

    manager = HeartflowManager()
    print("\n[Heartflow 会话注册表]")
    print("批次,累计会话数,注册表长度,锁数量,MB")

    for index in range(args.sessions):
        session_id = f"session-{index}"
        runtime = FakeRuntime(bytearray(args.session_payload_size))
        manager.heartflow_chat_list[session_id] = runtime
        manager._chat_create_locks[session_id] = None
        if hasattr(manager, "_last_access_at"):
            manager._last_access_at[session_id] = 100.0

        if (index + 1) % args.session_batch_size != 0:
            continue

        retained_payload = sum(len(runtime.payload) for runtime in manager.heartflow_chat_list.values())
        print(
            f"{(index + 1) // args.session_batch_size},"
            f"{index + 1},"
            f"{len(manager.heartflow_chat_list)},"
            f"{len(manager._chat_create_locks)},"
            f"{retained_payload / 1024 / 1024:.2f}"
        )

    if args.call_cleanup:
        cleanup_idle_chats = getattr(manager, "cleanup_idle_chats", None)
        if callable(cleanup_idle_chats):
            cleanup_now = 100.0 + (6 * 60 * 60) + 1.0
            await cleanup_idle_chats(now=cleanup_now)

    issue_observed = len(manager.heartflow_chat_list) == args.sessions
    print(f"剩余会话数={len(manager.heartflow_chat_list)}")
    print(f"是否观察到会话未释放={_bool_cn(issue_observed)}")
    return issue_observed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="复现")
    parser.add_argument("--messages", type=int, default=6000)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--payload-size", type=int, default=16 * 1024)
    parser.add_argument("--max-cache-size", type=int, default=200)
    parser.add_argument("--sessions", type=int, default=3000)
    parser.add_argument("--session-batch-size", type=int, default=500)
    parser.add_argument("--session-payload-size", type=int, default=32 * 1024)
    parser.add_argument(
        "--call-prune",
        action="store_true",
        help="每个消息批次结束后，如运行时提供裁剪hook则主动调用",
    )
    parser.add_argument(
        "--call-cleanup",
        action="store_true",
        help="填充会话注册表后，如 HeartflowManager 提供清理方法则主动调用",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    message_issue = await probe_maisaka_message_cache(args)
    session_issue = await probe_heartflow_session_registry(args)
    print("\n[汇总]")
    print(f"消息缓存问题是否复现={_bool_cn(message_issue)}")
    print(f"会话注册表问题是否复现={_bool_cn(session_issue)}")


if __name__ == "__main__":
    asyncio.run(main())
