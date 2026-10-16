"""日志政策（2026-10-16）回归测试。

对应：路线图 `.shared/decisions/log_policy_roadmap.md` · 调研 `.shared/research/log_policy_1016.md`。

三条稳态消息改成"跃迁 / 去重"之后，本文件守住四件事：
  1. 默认 `file_log_level = INFO`，但**可获取性**没被一刀切掉（白名单 + env 解析）；
  2. 落点锚**数据根**（绝对路径）——否则落点随 CWD 漂，"日志量"永远不可比；
  3. 三条稳态消息各自只出声有限次（taint 首次+恢复 / 心跳不落盘 / 忽略信号只报首次）；
  4. **反向判据**：两条"少但关键"的真失败**不得**被级别或去重吃掉
     （`[SendService] 发送消息失败` ×19 · `可见回复生成成功，但发送失败` ×16）。
"""

import logging
from pathlib import Path

import pytest

from src.common.logger import (
    LOG_DIR,
    LOG_FILE_DEBUG_LOGGERS_ENV,
    FileDebugWhitelistFilter,
    SuppressionFilter,
    file_debug_whitelist,
    load_log_config,
)
from src.common.log_pipeline.ratelimit import RateLimiter
from src.common.runtime_paths import resolve_data_root

APPLY_LEVELS = {logging.DEBUG, logging.INFO, logging.WARNING}


def _record(
    name: str = "test.module",
    level: int = logging.DEBUG,
    msg: str = "boom",
) -> logging.LogRecord:
    """构造受控 LogRecord（TID251 在本目录有显式豁免，见 pyproject ruff 段）。"""
    return logging.LogRecord(name, level, "path.py", 10, msg, (), None)


class _Recorder:
    """替身 logger：只记"谁在什么级别说了什么"，不碰日志管线。"""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def debug(self, msg: str, *args: object) -> None:
        self.lines.append(("debug", msg % args if args else msg))

    def info(self, msg: str, *args: object) -> None:
        self.lines.append(("info", msg % args if args else msg))

    def warning(self, msg: str, *args: object) -> None:
        self.lines.append(("warning", msg % args if args else msg))

    def count(self, needle: str) -> int:
        return sum(1 for _lv, text in self.lines if needle in text)


# ── 1. 级别政策 ────────────────────────────────────────────────────────────


def test_default_file_level_is_info(tmp_path, monkeypatch):
    """默认表（无配置文件时）的 file_log_level 必须是 INFO（政策第一步）。"""
    monkeypatch.chdir(tmp_path)
    assert load_log_config()["file_log_level"] == "INFO"


def test_log_dir_is_absolute_under_data_root():
    """LOG_DIR 必须**绝对**且挂在数据根下 —— 相对路径就是 CWD 漂移本身。"""
    log_dir = Path(LOG_DIR)
    assert log_dir.is_absolute(), "LOG_DIR 不能是相对路径（否则落点随 CWD 漂）"
    assert log_dir.name == "logs"
    assert log_dir.parent == resolve_data_root()


def test_file_filter_suppresses_debug_by_default():
    """默认（白名单为空）：DEBUG 不落盘，INFO 及以上照落。"""
    f = FileDebugWhitelistFilter(logging.INFO, ())
    assert f.filter(_record(level=logging.DEBUG)) is False
    assert f.filter(_record(level=logging.INFO)) is True
    assert f.filter(_record(level=logging.WARNING)) is True
    assert f.filter(_record(level=logging.ERROR)) is True


def test_whitelist_reopens_debug_for_prefix():
    """白名单前缀命中的 logger 仍可落 DEBUG（保"可获取性"的开关）。"""
    f = FileDebugWhitelistFilter(logging.INFO, ("core.tainted_mask", "src.core.watchdog"))
    assert f.filter(_record(name="core.tainted_mask.mark", level=logging.DEBUG)) is True
    assert f.filter(_record(name="src.core.watchdog.runner_health_bridge", level=logging.DEBUG)) is True
    assert f.filter(_record(name="core.other", level=logging.DEBUG)) is False
    # 边界：前缀必须从头匹配（与 ratelimit_whitelist 同口径）
    assert f.filter(_record(name="xcore.tainted_mask", level=logging.DEBUG)) is False


def test_whitelist_env_parsing(monkeypatch):
    """env 解析：逗号分隔、去空白、空串/未设 ⇒ 空元组。"""
    monkeypatch.delenv(LOG_FILE_DEBUG_LOGGERS_ENV, raising=False)
    assert file_debug_whitelist() == ()
    monkeypatch.setenv(LOG_FILE_DEBUG_LOGGERS_ENV, "")
    assert file_debug_whitelist() == ()
    monkeypatch.setenv(LOG_FILE_DEBUG_LOGGERS_ENV, " a.b , ,c.d ")
    assert file_debug_whitelist() == ("a.b", "c.d")


def test_whitelist_needs_handler_level_lowered(tmp_path):
    """端到端守住一个坑：**级别门在 `callHandlers`，先于 handler 的 filter**。

    ⇒ "只挂一个白名单 filter、级别门留在 INFO" 的实现是**静默失效**的（DEBUG 收不到）。
    本用例在那种实现上会红 —— 它正是本改动的第一版（实测由 `log_whitelist_probe` 抓出）。
    """
    from src.common.logger import TimestampedFileHandler, file_handler_level

    lg = logging.getLogger("log_policy_level_probe")
    lg.propagate = False
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()

    handler = TimestampedFileHandler(log_dir=tmp_path, max_bytes=1 << 20, backup_count=2)
    lg.addHandler(handler)

    # ① 错法：只挂 filter，级别门留在 INFO ⇒ 记录在 callHandlers 就被挡掉
    handler.setLevel(logging.INFO)
    handler.addFilter(FileDebugWhitelistFilter(logging.INFO, ("log_policy_level_probe",)))
    lg.debug({"event": "SHOULD-NOT-LAND"})

    # ② 对法：白名单非空 ⇒ 级别门降到 DEBUG，交给 filter 收窄
    handler.setLevel(file_handler_level(logging.INFO, ("log_policy_level_probe",)))
    lg.debug({"event": "SHOULD-LAND"})

    handler.close()
    lg.handlers.clear()

    text = "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("app_*.log.jsonl"))
    assert "SHOULD-NOT-LAND" not in text, "级别门留在 INFO 时不该收到 DEBUG（这证明门在工作）"
    assert "SHOULD-LAND" in text, "白名单命中时 DEBUG 必须真落盘（否则白名单是静默无效的）"


# ── 2. 反向判据：真失败不许被吃掉 ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("level", "message"),
    [
        (logging.ERROR, "[SendService] 发送消息失败"),
        (logging.WARNING, "可见回复生成成功，但发送失败"),
    ],
)
def test_real_failures_survive_level_policy(level, message):
    """这两条是"少但缺关键"的真失败：默认 INFO 档下必须照落，不因新政被降级掉。"""
    f = FileDebugWhitelistFilter(logging.INFO, ())
    assert f.filter(_record(name="src.platform_io.send_service", level=level, msg=message)) is True


@pytest.mark.parametrize(
    ("level", "message"),
    [
        (logging.ERROR, "[SendService] 发送消息失败"),
        (logging.WARNING, "可见回复生成成功，但发送失败"),
    ],
)
def test_real_failures_survive_ratelimit(level, message):
    """首次出现必须放行（限流限的是**速率**，不是"这条不许记"）。"""
    rl = RateLimiter(
        window_s=1.0,
        max_events=10,
        apply_levels=APPLY_LEVELS,
        whitelist=(),
        summary_interval_s=1.0,
    )
    assert rl.check(_record(name="src.platform_io.send_service", level=level, msg=message)) is True


# ── 3. 三条稳态消息 ────────────────────────────────────────────────────────


def test_taint_logs_first_and_recovery_only(monkeypatch):
    """taint 未就绪：N 次调用只出声 1 条；恢复时再 1 条并带上累计次数。"""
    import src.core.taint_mask_port_registry as registry
    import src.core.tainted_mask.mark as mark_mod
    from src.core.tainted_mask.taint_flag import TaintFlag

    def _not_ready():
        raise RuntimeError("TaintedMaskPort 未注册")

    rec = _Recorder()
    monkeypatch.setattr(mark_mod, "logger", rec)
    monkeypatch.setattr(mark_mod, "_not_ready_logged", False)
    monkeypatch.setattr(mark_mod, "_skipped_count", 0)
    monkeypatch.setattr(registry, "get_taint_mask_port", _not_ready)

    for _ in range(50):
        mark_mod.mark_taint(TaintFlag.TAINT_WARN)

    assert rec.count("taint registry 未就绪") == 1, "稳态只许出声一次"
    assert mark_mod.taint_skip_stats() == {"not_ready_logged": True, "skipped": 50}

    class _Port:
        def add_taint(self, flag) -> None:
            return None

    monkeypatch.setattr(registry, "get_taint_mask_port", lambda: _Port())
    mark_mod.mark_taint(TaintFlag.TAINT_WARN)

    assert rec.count("taint registry 已就绪") == 1, "降级→就绪要出声（跃迁）"
    assert "50" in [t for _lv, t in rec.lines if "已就绪" in t][0], "恢复那条要带上被跳过的次数"
    assert mark_mod.taint_skip_stats() == {"not_ready_logged": False, "skipped": 0}


def test_suppression_filter_marks_warning_once_per_record(monkeypatch):
    """同一 record 经 root + 多个 handler 的 filter 时，mark_taint 只该被调用一次。"""
    import src.core.tainted_mask.mark as mark_mod

    calls: list[object] = []
    monkeypatch.setattr(mark_mod, "mark_taint", lambda flag: calls.append(flag))

    f = SuppressionFilter()
    record = _record(level=logging.WARNING, msg="一次 WARNING")
    for _ in range(4):  # 模拟 root + 3 个 handler
        f.filter(record)

    assert len(calls) == 1, "同一条 record 只判一次（否则 taint 噪声 ×3~4）"


async def test_health_check_does_not_write_heartbeat_event(monkeypatch):
    """runner 心跳不再写诊断事件；卡住的 inflight 现场仍由 _dump_inflight_debug 保留。"""
    from src.plugin_runtime.protocol.envelope import Envelope, MessageType
    from src.plugin_runtime.runner.runner_main import PluginRunner

    class _Loader:
        @staticmethod
        def list_plugins() -> list:
            return []

    runner = PluginRunner.__new__(PluginRunner)
    runner._inflight_rpcs = {}
    runner._start_time = 0.0
    runner._runner_group = "test"
    runner._plugin_dirs = []
    runner._loader = _Loader()

    written: list[str] = []

    async def _fake_write(event: str, payload: dict) -> None:
        written.append(event)

    monkeypatch.setattr(runner, "_write_debug_event", _fake_write)

    env = Envelope(request_id=1, message_type=MessageType.REQUEST, method="health")
    await runner._handle_health(env)

    assert written == [], "心跳不得逐次落盘（实测容器里它占 131,793 行）"


async def test_ignored_recovery_signal_logged_once_then_summarized(monkeypatch):
    """未预期的恢复信号：每 runner 只报 1 条 WARNING，其余计数，注销时汇总。"""
    import src.core.watchdog.runner_health_bridge as bridge_mod
    from src.core.watchdog.runner_health_bridge import RunnerHealthBridge
    from src.core.watchdog.types import DetectionSource, RunnerBridgeStatus

    async def _noop_cb(_event: object) -> None:
        return None

    bridge = RunnerHealthBridge.__new__(RunnerHealthBridge)
    bridge._config = None
    bridge._main_loop = None
    bridge._report_callback = _noop_cb
    bridge._bridge_status = {
        "r1": RunnerBridgeStatus(
            runner_id="r1",
            component_id="c1",
            last_detection_source=DetectionSource.HEARTBEAT,
            last_consecutive_failures=0,
            cooldown_until=0.0,
            total_report_count=0,
            last_report_time=0.0,
            is_recovering=False,
        )
    }
    bridge._v1_supervisors = {}
    bridge._v2_supervisors = {}
    bridge._last_restart_count = {}
    bridge._poll_tasks = {}
    bridge._skip_warning_logged = set()
    bridge._ignored_recovery_logged = set()
    bridge._ignored_recovery_counts = {}

    rec = _Recorder()
    monkeypatch.setattr(bridge_mod, "logger", rec)

    for _ in range(30):
        await bridge._on_runner_recovered("r1")

    assert rec.count("未预期的恢复信号") == 1, "稳态只许出声一次"
    assert bridge._ignored_recovery_counts["r1"] == 30, "次数要留下（否则丢了量级）"

    bridge.unregister_runner("r1")
    assert rec.count("累计忽略 30 次") == 1, "注销时要把累计次数一次说清"
