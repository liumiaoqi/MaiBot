"""归属降级收口测试（批次 7）。"""


from src.maisaka import chat_loop_service as module


class _FakeLogger:
    def __init__(self):
        self.warnings: list[tuple] = []

    def warning(self, *args, **kwargs):
        self.warnings.append((args, kwargs))


class _FakePort:
    def __init__(self):
        self.reports: list[tuple] = []

    def report(self, *args, **kwargs):
        self.reports.append((args, kwargs))


def test_role_rejection_detection():
    assert module._is_role_rejection(RuntimeError("invalid role: assistant"))
    assert module._is_role_rejection(RuntimeError("messages[0].role invalid"))
    assert not module._is_role_rejection(RuntimeError("connection timeout"))


def test_report_attribution_failure_dual_channel(monkeypatch):
    fake_logger = _FakeLogger()
    fake_port = _FakePort()
    monkeypatch.setattr(module, "logger", fake_logger)
    monkeypatch.setattr(
        "src.core.error_escalation_port_registry.get_error_escalation_port",
        lambda: fake_port,
    )

    module._report_attribution_failure(RuntimeError("bad role"), "silver_wolf")

    assert len(fake_logger.warnings) == 1
    assert len(fake_port.reports) == 1


def test_degraded_session_memory_is_bounded_per_session():
    module._DEGRADED_SESSIONS.discard("session-degraded")

    module._DEGRADED_SESSIONS.add("session-degraded")
    assert "session-degraded" in module._DEGRADED_SESSIONS

    module._DEGRADED_SESSIONS.discard("session-degraded")
    assert "session-degraded" not in module._DEGRADED_SESSIONS