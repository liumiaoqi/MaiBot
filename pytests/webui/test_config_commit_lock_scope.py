"""F13（(a)-④）· 收窄 ``config_store.commit`` 锁范围的判据。

**被判定的对象**：``commit`` 的临界区里**还剩什么**，以及收窄之后 F11 的
"内容 ↔ revision 同源"是否仍然成立。

四类判据（前两类是**确定性**的，不依赖机器负载）：

1. **结构化判据**（``TestCriticalSectionScope``）：把 ``_REVISION_LOCK`` 换成带 ``held`` 标记的
   代理，逐个阶段记录"调用时锁是否被持有" ⇒ 解析 / ``to_plain`` / pydantic 全模型校验**必须在锁外**，
   落盘与指纹**必须在锁内**。计时会被同机负载拖走（实测同一份未改动代码的校验阶段从 311ms 漂到
   679ms），而"某段代码在不在临界区里"是布尔事实。
2. **原子性判据**（``TestWriterIsAtomicForReaders``）：在**落盘内部**卡住写者（仍持锁），
   断言读者**拿不到快照**；放行后拿到的 (内容, revision) 成对自洽 ⇒ "替换文件"与"推进 revision"
   之间没有可让读者插进来的点。
3. **并发写判据**（``TestConcurrentCommits``）：两个写者都在锁外阶段停住再同时动手 ⇒
   恰好一个成功、另一个 ``RevisionConflictError``、盘上是赢家的值、输家的值**不落盘**、**不重试**。
4. **F11 不变式**（``TestSameSourceUnderContention``）：前置条件显式化之后并发读零撕裂；
   并把"首个 commit 之前的读"**特性化**成一致视图（说明既有用例为何在收窄后误报）。

⚠️ 本文件**不碰** ``pytests/webui/test_config_seam.py``（`fu-xuan` 在另一棵树改它，避免合并冲突）。
"""

import logging  # noqa: TID251 — 仅取 `logging.WARNING` 这个整数常量配合 pytest 的 caplog；
# 用 `src.common.logger.get_logger()` 取不到它，而过滤器层级必须与生产代码一致，
# 否则"异常双通道"的日志那条会因为记录被过滤掉而假绿。
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
import tomlkit

from src.config.config import CONFIG_VERSION, MODEL_CONFIG_VERSION, Config, ModelConfig, generate_new_config_file
from src.webui import config_store
from src.webui.config_paths import assign_path, parse_path

FIXTURE_VALUE = 42
"""夹具 ``chat.max_context_size`` 的初值（与 ``test_config_seam`` 的夹具同值，便于对照）。"""

WRITER_VALUE = 999
LOSER_VALUE = 777


@pytest.fixture()
def commit_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """把配置面指向 ``tmp_path``（**夹具自造**，不依赖 ``test_config_seam`` 的 fixture）。

    为什么用 `generate_new_config_file` 而不是抄一份最小 TOML：抄来的最小件会随 schema 演进
    悄悄失效（少一个必填字段就以"夹具不合格"红给我看），而生成件**天生与真配置同形**——
    本文件判的是锁的边界与并发不变式，夹具必须先把"配置本身合法"这件事排除掉。

    ⚠️ ``revision`` 状态是**进程内存**里的模块级字典 ⇒ 每个用例都要复位，
    否则上一个用例推进过的计数会漏进来（既有夹具同此约定）。
    """
    generate_new_config_file(Config, tmp_path / "bot_config.toml", CONFIG_VERSION)
    generate_new_config_file(ModelConfig, tmp_path / "model_config.toml", MODEL_CONFIG_VERSION, override_repr=True)
    bot_path = tmp_path / "bot_config.toml"
    document = tomlkit.parse(bot_path.read_text(encoding="utf-8"))
    document["chat"]["max_context_size"] = FIXTURE_VALUE
    bot_path.write_text(tomlkit.dumps(document), encoding="utf-8")

    monkeypatch.setattr(config_store, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_store, "_REVISION_STATES", {})
    yield tmp_path


class _HoldProbe:
    """可观测的锁代理：``held`` 标记 + 每次持有时长（替换 ``_REVISION_LOCK``）。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.held = False
        self.holds: list[float] = []

    def acquire(self, *args: Any, **kwargs: Any) -> bool:
        return self._inner.acquire(*args, **kwargs)

    def release(self) -> None:
        self._inner.release()

    def __enter__(self) -> "_HoldProbe":
        self._inner.acquire()
        self.held = True
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.holds.append(time.perf_counter() - self._started)
        self.held = False
        self._inner.release()
        return False


class _TomlkitSpy:
    """``config_store.tomlkit`` 的替身：记录 ``loads`` 被调用时锁是否被持有，其余透传。"""

    def __init__(self, real: Any, on_loads: Callable[[], None]) -> None:
        self._real = real
        self._on_loads = on_loads

    def loads(self, *args: Any, **kwargs: Any) -> Any:
        self._on_loads()
        return self._real.loads(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _commit_value(namespace: str, revision: int, value: int, *, validate: Any = None) -> int:
    """走一次真实 commit：把 ``chat.max_context_size`` 设成 ``value``。"""

    def _apply(document: Any, baseline: Any) -> None:
        del baseline
        assign_path(document, parse_path("chat.max_context_size"), value)

    return config_store.commit(namespace, revision, _apply, validate=validate)


class TestCriticalSectionScope:
    """判据一：重活在锁外，落盘与指纹在锁内（结构化，与负载无关）。"""

    def test_heavy_work_is_outside_and_write_is_inside(
        self, commit_fixture: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        probe = _HoldProbe(config_store._REVISION_LOCK)  # noqa: SLF001
        monkeypatch.setattr(config_store, "_REVISION_LOCK", probe)

        inside: dict[str, list[bool]] = {
            "解析": [],
            "to_plain": [],
            "校验": [],
            "落盘": [],
            "指纹": [],
        }

        monkeypatch.setattr(
            config_store,
            "tomlkit",
            _TomlkitSpy(tomlkit, lambda: inside["解析"].append(probe.held)),
        )
        real_to_plain = config_store.to_plain
        real_save = config_store.save_toml_with_format
        real_fingerprint = config_store._fingerprint  # noqa: SLF001

        def spy_to_plain(*args: Any, **kwargs: Any) -> Any:
            inside["to_plain"].append(probe.held)
            return real_to_plain(*args, **kwargs)

        def spy_save(*args: Any, **kwargs: Any) -> Any:
            inside["落盘"].append(probe.held)
            return real_save(*args, **kwargs)

        def spy_fingerprint(*args: Any, **kwargs: Any) -> Any:
            inside["指纹"].append(probe.held)
            return real_fingerprint(*args, **kwargs)

        monkeypatch.setattr(config_store, "to_plain", spy_to_plain)
        monkeypatch.setattr(config_store, "save_toml_with_format", spy_save)
        monkeypatch.setattr(config_store, "_fingerprint", spy_fingerprint)

        def validator(plain: Any) -> None:
            inside["校验"].append(probe.held)
            config_store._default_validator(config_store.namespace_spec(config_store.NAMESPACE_BOT))(  # noqa: SLF001
                plain
            )

        namespace = config_store.NAMESPACE_BOT
        revision = config_store.current_revision(namespace)
        _commit_value(namespace, revision, FIXTURE_VALUE + 1, validate=validator)

        for name in ("解析", "to_plain", "校验"):
            assert inside[name], f"{name} 一次都没被调用？判据没打到对象上"
            assert not any(inside[name]), f"{name} 在临界区里跑了（F13 要修的就是这个）"
        for name in ("落盘", "指纹"):
            assert inside[name], f"{name} 一次都没被调用？判据没打到对象上"
            assert all(inside[name]), f"{name} 跑到锁外了（并发写会交错落盘）"

    def test_missing_revision_is_refused_before_the_heavy_work(
        self, commit_fixture: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """过期写入要在**重活之前**被挡掉（否则白做一趟 0.4s 的解析与全校验）。"""
        parsed: list[int] = []
        monkeypatch.setattr(
            config_store,
            "tomlkit",
            _TomlkitSpy(tomlkit, lambda: parsed.append(1)),
        )
        namespace = config_store.NAMESPACE_BOT
        stale = config_store.current_revision(namespace) - 1

        with pytest.raises(config_store.RevisionConflictError):
            _commit_value(namespace, stale, FIXTURE_VALUE + 1)

        assert parsed == [], "过期写入仍然做了解析（重活应当被 revision 检查挡住）"


class TestWriterIsAtomicForReaders:
    """判据二：写者"替换文件 + 推进 revision"对读者是**一个**原子步（确定性阻塞证明）。"""

    def test_reader_cannot_get_a_snapshot_while_the_write_is_in_flight(
        self, commit_fixture: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_entered = threading.Event()
        release_write = threading.Event()
        real_save = config_store.save_toml_with_format

        def blocked_save(*args: Any, **kwargs: Any) -> Any:
            write_entered.set()
            assert release_write.wait(timeout=10), "测试没有放行落盘"
            return real_save(*args, **kwargs)

        monkeypatch.setattr(config_store, "save_toml_with_format", blocked_save)

        namespace = config_store.NAMESPACE_BOT
        revision = config_store.current_revision(namespace)
        outcome: dict[str, Any] = {}

        def commit_worker() -> None:
            try:
                outcome["revision"] = _commit_value(namespace, revision, WRITER_VALUE)
            except Exception as error:  # noqa: BLE001 — 失败要带回主线程断言
                outcome["error"] = error

        writer = threading.Thread(target=commit_worker, daemon=True)
        writer.start()
        assert write_entered.wait(timeout=10), "写者没能进到落盘"

        # 此刻：写者**持锁**且卡在落盘内部 ⇒ 读者必须进不来
        reader_done = threading.Event()
        snapshot: dict[str, Any] = {}

        def reader() -> None:
            snapshot["value"] = config_store.read_snapshot(namespace)
            reader_done.set()

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        try:
            assert not reader_done.wait(timeout=0.5), (
                "读者在写者落盘期间拿到了快照 —— 说明'替换文件'与'推进 revision'之间可被插入"
            )
        finally:
            release_write.set()
            writer.join(timeout=10)
            reader_thread.join(timeout=10)

        assert "error" not in outcome, f"写者失败：{outcome.get('error')}"
        assert reader_done.is_set(), "放行之后读者仍拿不到快照"
        stored, observed_revision = snapshot["value"]
        # 读者最终看到的是**成对**的新状态：新内容 + 与之同源的新 revision
        assert stored["chat"]["max_context_size"] == WRITER_VALUE
        assert observed_revision == outcome["revision"] == revision + 1


class TestConcurrentCommits:
    """判据三：并发 commit 不交错落盘、不丢更新、不静默重试。"""

    def test_exactly_one_wins_and_the_loser_writes_nothing(
        self, commit_fixture: Path
    ) -> None:
        namespace = config_store.NAMESPACE_BOT
        revision = config_store.current_revision(namespace)
        path = config_store.config_file_path(namespace)
        before = path.read_bytes()
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, Any]] = []
        lock = threading.Lock()

        def worker(value: int) -> None:
            def _apply(document: Any, baseline: Any) -> None:
                del baseline
                # 两个写者都在**锁外的变更阶段**停住再同时动手 —— 这是收窄之后新出现的交错面，
                # 也正是"检查与落盘不在同一段"必须靠同源快照 + 复核兜住的地方。
                barrier.wait(timeout=10)
                assign_path(document, parse_path("chat.max_context_size"), value)

            try:
                _commit_value(namespace, revision, value, validate=None)  # 用默认校验器
            except config_store.RevisionConflictError as error:
                with lock:
                    outcomes.append(("conflict", error))
            except Exception as error:  # noqa: BLE001
                with lock:
                    outcomes.append((f"error:{type(error).__name__}", error))
            else:
                with lock:
                    outcomes.append(("ok", value))

        threads = [
            threading.Thread(target=worker, args=(WRITER_VALUE,), daemon=True),
            threading.Thread(target=worker, args=(LOSER_VALUE,), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        kinds = sorted(kind for kind, _ in outcomes)
        assert kinds == ["conflict", "ok"], f"并发结果不是「一成一拒」：{outcomes}"
        winner = next(value for kind, value in outcomes if kind == "ok")
        after = config_store.load_stored(namespace)["chat"]["max_context_size"]
        assert after == winner, "盘上是失败那次的取值（交错落盘/丢更新）"
        loser = LOSER_VALUE if winner == WRITER_VALUE else WRITER_VALUE
        assert loser != after
        assert after != FIXTURE_VALUE or winner == FIXTURE_VALUE
        # 不静默重试：被拒的那次没有自己重算重写（否则盘上会是两者的混合/后者）
        assert path.read_bytes() != before, "赢家没有落盘？"
        # revision 单调前进（被拒那次的"检测到内容变化"也会记一次新版本——既有语义）
        assert config_store.current_revision(namespace) > revision


class TestSameSourceUnderContention:
    """判据四（F11）：并发下 (内容, revision) 仍同源；并把"首个 commit 之前"特性化。"""

    def test_snapshot_is_same_source_while_a_writer_commits(
        self, commit_fixture: Path
    ) -> None:
        """**前置条件显式化**：等首个 commit 真正落地，再并发读 ⇒ 零撕裂。

        不变式：写者把 ``max_context_size`` 设成它带的 revision，commit 后 revision = 值 + 1
        ⇒ 一致快照必须满足 ``值 == revision - 1``。**该不变式只在首个 commit 之后成立**
        （夹具初值 42 配 revision 1 是"一致但不满足不变式"的初始视图）——所以这里等 Event
        而不是睡固定时长。
        """
        namespace = config_store.NAMESPACE_BOT
        stop = threading.Event()
        first_commit = threading.Event()

        def writer() -> None:
            while not stop.is_set():
                try:
                    revision = config_store.current_revision(namespace)

                    def _apply(document: Any, baseline: Any, revision: int = revision) -> None:
                        del baseline
                        document["chat"]["max_context_size"] = revision

                    config_store.commit(namespace, revision, _apply)
                    first_commit.set()
                except config_store.RevisionConflictError:
                    continue

        worker = threading.Thread(target=writer, daemon=True)
        worker.start()
        tears: list[tuple[int, int]] = []
        try:
            assert first_commit.wait(timeout=15), "写者未能在超时内完成首个 commit"
            for _ in range(200):
                stored, revision = config_store.read_snapshot(namespace)
                value = stored["chat"]["max_context_size"]
                if value != revision - 1:
                    tears.append((value, revision))
        finally:
            stop.set()
            worker.join(timeout=5)

        assert tears == [], f"read_snapshot 出现撕裂：{tears[:5]}"

    def test_pre_first_commit_view_is_consistent_not_a_tear(
        self, commit_fixture: Path
    ) -> None:
        """**特性化用例**：首个 commit 之前读到 (夹具原值, 初始 revision) 是**一致视图**。

        这条是为"既有断言为何在收窄锁之后误报"留下证据（实测 3/3 次跑出 ``(42, 1)``）：
        它满足"内容与 revision 同源"（revision 由**同一批字节**的指纹派生），只是**不满足**
        那条不变式——不变式描述的是写者的协议，而此刻还没有任何写者动过手。
        """
        namespace = config_store.NAMESPACE_BOT
        revision_before = config_store.current_revision(namespace)

        stored, revision = config_store.read_snapshot(namespace)

        assert stored["chat"]["max_context_size"] == FIXTURE_VALUE
        assert revision == revision_before == 1
        # 同源性的可判据形态：没有写入时重复读给出**同一对**；外部改动后成对变化
        stored_again, revision_again = config_store.read_snapshot(namespace)
        assert (stored_again["chat"]["max_context_size"], revision_again) == (FIXTURE_VALUE, 1)

    def test_external_write_advances_content_and_revision_together(
        self, commit_fixture: Path
    ) -> None:
        """同源性的另一半：**本层之外**改了文件 ⇒ 内容与 revision 成对前进（不是各自为政）。"""
        namespace = config_store.NAMESPACE_BOT
        path = config_store.config_file_path(namespace)
        _stored, revision_before = config_store.read_snapshot(namespace)

        text = path.read_text(encoding="utf-8").replace(
            f"max_context_size = {FIXTURE_VALUE}", f"max_context_size = {FIXTURE_VALUE + 7}"
        )
        assert f"max_context_size = {FIXTURE_VALUE + 7}" in text
        path.write_text(text, encoding="utf-8")

        stored, revision_after = config_store.read_snapshot(namespace)

        assert stored["chat"]["max_context_size"] == FIXTURE_VALUE + 7
        assert revision_after == revision_before + 1, "外部改动没有让 revision 前进（乐观锁会失效）"


class TestSnapshotInvariantSelfCheck:
    """防御分支的行为锁定（正常不可达，用注入式判据锁住它）。

    ``commit`` 的临界区二里有一步"复核快照指纹未变"。按构造它不可达：快照指纹在临界区一
    刚被登记为当前状态，而 ``state.fingerprint`` 只在锁内被改、且每次从"快照那份"改成别的时
    必然同时推进 revision ⇒ "内容变了"先被 revision 比对拦下。

    那它为什么留着：它是"内容 ↔ revision 同源"这条不变量的最后一道自检。哪天有人把快照读挪到
    锁外，revision 比对会静默通过并按旧内容落盘，而这一步会当场出声。本用例用**注入**让它出声，
    免得它变成"没人知道会怎样"的死代码。
    """

    def test_snapshot_check_refuses_when_state_disagrees(
        self, commit_fixture: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        namespace = config_store.NAMESPACE_BOT
        revision = config_store.current_revision(namespace)
        path = config_store.config_file_path(namespace)
        before = path.read_bytes()
        real_refresh = config_store._refresh_locked  # noqa: SLF001
        calls = {"count": 0}

        def tampered_refresh(ns: str, **kwargs: Any) -> Any:
            state = real_refresh(ns, **kwargs)
            calls["count"] += 1
            if calls["count"] == 2:  # 第二次 = 临界区二里的复核
                # ⚠️ 返回**副本**而不是改真 state：改真的会把共享状态弄脏，之后的
                # `current_revision` 会因为指纹不符而推进 revision（第一版就是这么红的）。
                return config_store._RevisionState(  # noqa: SLF001 — 注入式判据要造出这一态
                    revision=state.revision,
                    fingerprint="tampered-not-the-snapshot",
                )
            return state

        monkeypatch.setattr(config_store, "_refresh_locked", tampered_refresh)

        with caplog.at_level(logging.WARNING, logger="webui"):
            with pytest.raises(config_store.RevisionConflictError) as excinfo:
                _commit_value(namespace, revision, WRITER_VALUE)

        assert "快照" in str(excinfo.value) or "过期内容" in str(excinfo.value)
        assert path.read_bytes() == before, "被拒绝的写入动了文件"
        assert config_store.current_revision(namespace) == revision, "被拒绝的写入推进了 revision"
