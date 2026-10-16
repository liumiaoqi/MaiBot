"""日志保留（年龄清理）回归测试 —— 2026-10-16 日志路线图段 1。

背景（真故障）：`start_log_cleanup_task()` **全仓零调用** ⇒ 年龄清理从未运行过；
容器 PID 1 只有 1 个线程 · `app_*.log.jsonl` 最老的 53 天 · stdout 无任何清理输出。
本文件守四件事：
  1. **接线**：`initialize_logging()` 必须真的启动保留任务（否则又是"有定义零调用"）；
  2. **只按年龄删主日志**：老的删、新的留、当前文件留；
  3. **反向用例**：`.html/.json/.txt`（158.9 MB 非日志文件，去留待拍板）与
     `dump_*` / `runner_rpc_debug.jsonl` / `usage_*.jsonl` **一个都不许删**，但必须被**统计到**；
  4. **总出声**：删没删都要有一行（旧实现只在删了>0 时打，导致"没跑"与"跑了没删"长得一样）。
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import src.common.logger as logger_mod
from src.common.logger import cleanup_old_logs, start_log_cleanup_task

CLEANUP_DAYS = 30


def _age(path: Path, days: float) -> None:
    """把文件 mtime 调到 N 天前（真实文件 + 真实 mtime，不 mock 时间）。"""
    ts = (datetime.now() - timedelta(days=days)).timestamp()
    os.utime(path, (ts, ts))


def _touch(path: Path, size: int = 64, days: float = 0.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if days:
        _age(path, days)
    return path


def _recorder(monkeypatch) -> list[str]:
    """把保留策略的 logger 换成记录器（只关心"说了什么"）。"""
    lines: list[str] = []

    class _Rec:
        def info(self, msg: str, *args: object) -> None:
            lines.append(msg % args if args else msg)

        def warning(self, msg: str, *args: object) -> None:
            lines.append("WARN " + (msg % args if args else msg))

        def error(self, msg: str, *args: object) -> None:
            lines.append("ERR " + (msg % args if args else msg))

    monkeypatch.setattr(logger_mod, "_cleanup_logger", lambda: _Rec())
    return lines


def _use_tmp_log_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logger_mod, "LOG_DIR", tmp_path)
    monkeypatch.setitem(logger_mod.LOG_CONFIG, "log_cleanup_days", CLEANUP_DAYS)


def test_cleanup_deletes_aged_main_logs_only(tmp_path, monkeypatch):
    """主日志三族：老的删、新的留；报告里的数字要对得上。"""
    _use_tmp_log_dir(monkeypatch, tmp_path)
    old_app = _touch(tmp_path / "app_20260101_000000.log.jsonl", size=1024, days=40)
    new_app = _touch(tmp_path / "app_20261016_000000.log.jsonl", size=2048, days=0)
    old_maibot = _touch(tmp_path / "maibot_20260101_000000.log.jsonl", size=512, days=45)
    old_think = _touch(tmp_path / "think_cycles_2026-01-01.log.jsonl", size=256, days=31)
    # 命名陷阱（本任务实测踩过）：真实产物是 `think_cycles_<date>.log.jsonl`，
    # 少一个 `.log` 的同名文件**不该**被这条规则命中
    decoy_think = _touch(tmp_path / "think_cycles_scratch.jsonl", size=128, days=31)
    boundary = _touch(tmp_path / "app_20260920_000000.log.jsonl", size=100, days=CLEANUP_DAYS - 1)

    report = cleanup_old_logs()

    assert report["cleanup_days"] == CLEANUP_DAYS
    # scanned 只数**被规则命中**的文件：命名不匹配的 decoy 根本不进删除面（这正是要的边界）
    assert report["scanned"] == 5
    assert report["deleted"] == 3, "40/45/31 天的三个该删"
    assert report["freed_bytes"] == 1024 + 512 + 256
    assert report["kept"] == 2, "刚写的与 29 天的都在保留面内"
    assert not old_app.exists() and not old_maibot.exists() and not old_think.exists()
    assert new_app.exists() and boundary.exists() and decoy_think.exists()


def test_non_log_files_are_registered_but_never_deleted(tmp_path, monkeypatch):
    """反向用例：非日志族与调试文件**一个都不许删**，但必须被统计。"""
    _use_tmp_log_dir(monkeypatch, tmp_path)
    protected = [
        _touch(tmp_path / "1782365230610.html", size=4096, days=120),
        _touch(tmp_path / "1782365230610.json", size=2048, days=120),
        _touch(tmp_path / "1782365230610.txt", size=1024, days=120),
        _touch(tmp_path / "dump_20260101_000000_1.log.jsonl", size=512, days=120),
        _touch(tmp_path / "plugin_runtime_debug" / "runner_rpc_debug.jsonl", size=8192, days=120),
        _touch(tmp_path / "usage_20260101.jsonl", size=256, days=120),
    ]
    old_app = _touch(tmp_path / "app_20260101_000000.log.jsonl", size=100, days=120)

    report = cleanup_old_logs()

    assert report["deleted"] == 1, "只有主日志族里的老文件该被删"
    assert not old_app.exists()
    for path in protected:
        assert path.exists(), f"{path.name} 不该被删"
    # 统计面：三类非日志文件要能被看见（数量与字节）
    assert report["register_only"][".html"] == {"files": 1, "bytes": 4096}
    assert report["register_only"][".json"]["files"] >= 1
    assert report["register_only"][".txt"] == {"files": 1, "bytes": 1024}


def test_dry_run_deletes_nothing(tmp_path, monkeypatch):
    """dry_run 只算不删（容器内做只读取证用的就是这条路）。"""
    _use_tmp_log_dir(monkeypatch, tmp_path)
    old_app = _touch(tmp_path / "app_20260101_000000.log.jsonl", size=777, days=99)

    report = cleanup_old_logs(dry_run=True)

    assert report["dry_run"] is True
    assert report["deleted"] == 1
    assert report["freed_bytes"] == 777
    assert old_app.exists(), "dry_run 不许真删"


def test_report_is_audible_even_when_nothing_deleted(tmp_path, monkeypatch):
    """**总出声**：一个都没删时也要有一行（否则"没跑"与"跑了没删"不可区分）。"""
    _use_tmp_log_dir(monkeypatch, tmp_path)
    _touch(tmp_path / "app_20261016_000000.log.jsonl", size=10, days=0)
    lines = _recorder(monkeypatch)

    cleanup_old_logs()

    assert lines, "必须有输出"
    assert any("日志保留" in line and "删除 0 个" in line for line in lines), lines


def test_start_log_cleanup_task_is_idempotent(monkeypatch):
    """重复调用只启动一次（`_cleanup_task_started` 守卫）。"""
    monkeypatch.setattr(logger_mod, "_cleanup_task_started", False)
    monkeypatch.setattr(logger_mod, "cleanup_old_logs", lambda *a, **k: None)  # 线程体别真扫

    assert start_log_cleanup_task(interval_s=3600) is True
    assert start_log_cleanup_task(interval_s=3600) is False


def test_initialize_logging_wires_the_cleanup_task(monkeypatch):
    """**接线回归**：`initialize_logging()` 必须真的拉起保留任务。

    这条是段 1 的核心守卫 —— 修之前 `start_log_cleanup_task` 全仓零调用，
    而"零调用"在测试里**什么都不会红**（没有任何断言指向它）。
    """
    started: list[bool] = []
    monkeypatch.setattr(logger_mod, "_logging_initialized", False)
    monkeypatch.setattr(logger_mod, "start_log_cleanup_task", lambda: started.append(True))

    logger_mod.initialize_logging(verbose=False)

    assert started, "initialize_logging 必须接线日志保留任务（§七：有定义零调用=静默失效）"
