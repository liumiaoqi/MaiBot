"""T14 SessionLifecyclePort 扩展测试 — 会话回调订阅 + 关联任务查询。"""

import asyncio

import pytest

from src.core.adapters.chat_manager_adapter import ChatManagerAdapter


class _Dummy:
    def __init__(self) -> None:
        self.sessions: dict[str, object] = {}
        self._new: list[str] = []

    def list_session_ids(self) -> list[str]:
        return list(self.sessions)

    def get(self, session_id: str) -> object:
        return self.sessions.get(session_id)


class _FakeLifecycle:
    def __init__(self, store: _Dummy) -> None:
        self._store = store
        self._counter = 0

    async def get_or_create_session(
        self, platform: str, user_id: str = "", group_id: str = None, account_id: str = None, scope: str = None
    ) -> object:
        # 同 user_id 已存在会话时复用（模拟"get"语义）
        for sid in self._store.sessions:
            if sid.startswith(f"sess-{user_id}"):
                return type("Session", (), {"session_id": sid})()
        self._counter += 1
        session_id = f"sess-{user_id}-{self._counter}"
        self._store.sessions[session_id] = object()
        return type("Session", (), {"session_id": session_id})()


def _make_adapter() -> ChatManagerAdapter:
    store = _Dummy()
    adapter = ChatManagerAdapter(
        routing_service=object(),
        session_store=store,
        message_registry=object(),
        name_cache=object(),
        resolver=object(),
        session_lifecycle=_FakeLifecycle(store),
    )
    return adapter


class TestSessionCreatedSubscription:
    @pytest.mark.asyncio
    async def test_created_notify_on_new_session(self) -> None:
        """新建会话时通知订阅者（spec §7.8 会话生命周期通知）。"""
        adapter = _make_adapter()
        created: list[str] = []
        adapter.subscribe_session_created(lambda sid: created.append(sid))
        await adapter.get_or_create_session_id(platform="qq", user_id="u1")
        assert created == [f"sess-u1-1"]

    @pytest.mark.asyncio
    async def test_existing_session_no_notify(self) -> None:
        """已存在会话（get 命中）不触发创建通知。"""
        adapter = _make_adapter()
        created: list[str] = []
        adapter.subscribe_session_created(lambda sid: created.append(sid))
        await adapter.get_or_create_session_id(platform="qq", user_id="u1")
        await adapter.get_or_create_session_id(platform="qq", user_id="u1")
        assert created == [f"sess-u1-1"]  # 第二次复用，不通知

    def test_subscribe_destroyed_registration(self) -> None:
        """销毁回调注册机制就位（MaiBot 会话常驻，触发点待销毁功能接入）。"""
        adapter = _make_adapter()
        destroyed: list[str] = []

        def handler(session_id: str) -> None:
            destroyed.append(session_id)

        adapter.subscribe_session_destroyed(handler)
        assert len(adapter._session_destroyed_subscribers) == 1


class TestSessionTasks:
    @pytest.mark.asyncio
    async def test_register_and_list(self) -> None:
        """注册会话任务后可查询（致命扩散目标）。"""
        adapter = _make_adapter()

        async def worker() -> None:
            await asyncio.sleep(3600)

        task = asyncio.create_task(worker())
        adapter.register_session_task("s1", task)
        tasks = await adapter.list_session_async_tasks("s1")
        assert tasks == [task]
        task.cancel()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_task_auto_removed_on_done(self) -> None:
        """任务完成自动从注册表移除。"""
        adapter = _make_adapter()

        async def worker() -> None:
            await asyncio.sleep(0)

        task = asyncio.create_task(worker())
        adapter.register_session_task("s1", task)
        await asyncio.sleep(0.05)  # 等任务完成 + done callback
        assert await adapter.list_session_async_tasks("s1") == []

    @pytest.mark.asyncio
    async def test_unknown_session_empty(self) -> None:
        adapter = _make_adapter()
        assert await adapter.list_session_async_tasks("nope") == []

    @pytest.mark.asyncio
    async def test_no_duplicate_registration(self) -> None:
        adapter = _make_adapter()

        async def worker() -> None:
            await asyncio.sleep(3600)

        task = asyncio.create_task(worker())
        adapter.register_session_task("s1", task)
        adapter.register_session_task("s1", task)
        assert len(await adapter.list_session_async_tasks("s1")) == 1
        task.cancel()
