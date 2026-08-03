"""MF-P2-004 验收：WriteLockManager 节点级写入锁。

对应 tasks.md 5.1：并发写入同一概念节点串行执行；超时抛 WriteLockTimeoutError；
release 后锁可复用。
"""

import asyncio

import pytest

from src.A_memorix.core.concept_graph.write_lock_manager import (
    WriteLockManager,
    WriteLockTimeoutError,
)


async def test_acquire_and_release() -> None:
    manager = WriteLockManager()
    token = await manager.acquire(["a", "b"], timeout=1.0)
    assert token.concept_ids == ("a", "b")
    manager.release(token)
    # 释放后可再次获取
    token2 = await manager.acquire(["a"], timeout=1.0)
    manager.release(token2)


async def test_concurrent_writes_serialize() -> None:
    """并发写同一节点串行执行（互斥）。"""
    manager = WriteLockManager()
    active = 0
    max_active = 0
    done = asyncio.Event()

    async def writer() -> None:
        nonlocal active, max_active
        token = await manager.acquire(["shared"], timeout=2.0)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        manager.release(token)
        done.set()

    writers = [asyncio.create_task(writer()) for _ in range(3)]
    await asyncio.gather(*writers)
    assert max_active == 1  # 任意时刻只有一个写入者


async def test_acquire_timeout_raises() -> None:
    """锁被占用时超时抛 WriteLockTimeoutError。"""
    manager = WriteLockManager()
    token = await manager.acquire(["a"], timeout=5.0)
    try:
        with pytest.raises(WriteLockTimeoutError):
            await manager.acquire(["a"], timeout=0.1)
    finally:
        manager.release(token)


async def test_acquire_timeout_releases_held_locks() -> None:
    """部分获取后超时：已持有的锁被释放（不泄漏）。"""
    manager = WriteLockManager()
    token_b = await manager.acquire(["b"], timeout=5.0)  # 占用 b
    try:
        with pytest.raises(WriteLockTimeoutError):
            # acquire(["a","b"]) 按序先获取 a，卡在 b → 超时
            await manager.acquire(["a", "b"], timeout=0.2)
        # a 的锁未被泄漏：可重新获取（b 仍被占用）
        token_a = await manager.acquire(["a"], timeout=0.5)
        manager.release(token_a)
    finally:
        manager.release(token_b)


async def test_duplicate_ids_deduplicated() -> None:
    manager = WriteLockManager()
    token = await manager.acquire(["a", "a", "b"], timeout=1.0)
    assert token.concept_ids == ("a", "b")
    manager.release(token)
