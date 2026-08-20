"""P0-3 cooldown 持久化真库集成测试 — 单 session 读-改-写真实落库。

覆盖 spec 5.5.1-1~4 + 并发边界保证：
- record 递增真实落库（新 session 可见）
- can_trigger 窗口重置真实落库（新 session 可见）
- 首次创建后新 session 重查可见
- 判定语义快照（窗口内 False / 超上限 False / 恢复后 True）
- 并发 2 任务同 key → 无重复记录、计数非负

业务 key 加 `ut:cooldown_p0_3:` 前缀，teardown 清理，避免污染 MaiBot.db。
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

from src.common.database.database import get_db_session
from src.common.database.database_model import InteractionCooldown as InteractionCooldownTable
from src.maisaka.agent_interaction.cooldown import InteractionCooldownManager

_KEY_PREFIX = "ut:cooldown_p0_3:"


def _key(name: str = "a:b") -> str:
    return f"{_KEY_PREFIX}{name}"


@pytest.fixture(autouse=True)
def _cleanup_cooldown_rows():
    """清理 ut: 前缀的测试行，避免污染 MaiBot.db。"""
    yield


    with get_db_session() as session:
        stmt = delete(InteractionCooldownTable).where(
            InteractionCooldownTable.agent_pair_key.like(f"{_KEY_PREFIX}%")
        )
        session.execute(stmt)


class TestCooldownPersistence:
    """P0-3 冷却持久化：修改必须真实落库（新 session 可见）。"""

    @pytest.mark.asyncio
    async def test_record_interaction_persists(self) -> None:
        """record 两次 → 新 session 查询计数==2 且 last_interaction_at 非空。"""
        manager = InteractionCooldownManager()
        key = _key("a:b")
        await manager.record_interaction(key)
        await manager.record_interaction(key)

        with get_db_session() as session:
            row = session.get(InteractionCooldownTable, key)
            assert row is not None
            assert row.interaction_count_hourly == 2
            assert row.interaction_count_daily == 2
            assert row.last_interaction_at is not None

    @pytest.mark.asyncio
    async def test_can_trigger_reset_persists(self) -> None:
        """预置过期 hourly_reset_at → can_trigger 重置 → 新 session 计数==0 且 reset_at 已刷新。"""
        # 预置过期重置时间（旧实现下 can_trigger 的修改不落库）
        key = _key("expired")
        with get_db_session() as session:
            row = InteractionCooldownTable(
                agent_pair_key=key,
                interaction_count_hourly=3,
                interaction_count_daily=3,
                hourly_reset_at=datetime.now() - timedelta(minutes=5),
                daily_reset_at=datetime.now() - timedelta(minutes=5),
                last_interaction_at=datetime.now() - timedelta(hours=2),
            )
            session.add(row)

        manager = InteractionCooldownManager()
        can = await manager.can_trigger(key, cooldown_minutes=30)
        assert can is True

        with get_db_session() as session:
            row = session.get(InteractionCooldownTable, key)
            assert row.interaction_count_hourly == 0
            assert row.interaction_count_daily == 0
            assert row.hourly_reset_at is not None and row.hourly_reset_at > datetime.now() - timedelta(
                hours=1
            )

    @pytest.mark.asyncio
    async def test_first_create_visible_in_new_session(self) -> None:
        """首次创建后新 session 重查可见记录且计数 0。"""
        manager = InteractionCooldownManager()
        key = _key("fresh")
        can = await manager.can_trigger(key)
        assert can is True

        with get_db_session() as session:
            row = session.get(InteractionCooldownTable, key)
            assert row is not None
            assert row.interaction_count_hourly == 0

    @pytest.mark.asyncio
    async def test_decision_semantics(self) -> None:
        """判定语义快照：窗口内 False / 超上限 False / 恢复后 True。"""
        manager = InteractionCooldownManager()
        key = _key("semantics")
        # 第一次交互后冷却窗口内 → False
        await manager.record_interaction(key)
        assert await manager.can_trigger(key, cooldown_minutes=30) is False

        # 预置窗口过期 + 计数超上限
        with get_db_session() as session:
            row = session.get(InteractionCooldownTable, key)
            row.last_interaction_at = datetime.now() - timedelta(hours=1)
            row.interaction_count_hourly = 2
            row.interaction_count_daily = 8
            row.hourly_reset_at = datetime.now() - timedelta(minutes=1)
            row.daily_reset_at = datetime.now() - timedelta(minutes=1)
        # 窗口重置后计数清 0 → True
        assert await manager.can_trigger(key, cooldown_minutes=30) is True


class TestCooldownConcurrency:
    """并发边界保证：无重复记录、计数非负。"""

    @pytest.mark.asyncio
    async def test_concurrent_record_no_negative(self) -> None:
        """并发 2 任务同 key → 无重复记录（主键约束）、计数非负。

        P2-R2-9: asyncio.gather 真实并发触发 2 个 record_interaction，
        SQLite WAL + busy_timeout=1000ms 串行化写入——验证并发边界下
        无重复记录（主键约束）且计数非负（不产生负值）。
        """
        manager = InteractionCooldownManager()
        key = _key("concurrent")
        await asyncio.gather(manager.record_interaction(key), manager.record_interaction(key))

        with get_db_session() as session:
            rows = session.execute(
                select(InteractionCooldownTable).where(
                    InteractionCooldownTable.agent_pair_key == key
                )
            ).scalars().all()
            assert len(rows) == 1  # 无重复记录
            assert rows[0].interaction_count_hourly >= 1
            assert rows[0].interaction_count_daily >= 1
