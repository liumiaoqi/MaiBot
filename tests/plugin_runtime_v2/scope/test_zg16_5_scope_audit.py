"""ZG16-5: ScopeAuditRecorder 审计记录器测试。

覆盖 Tier 1 触发审计、参数脱敏、JSON Lines 格式、best-effort 不阻断、
队列满丢弃、初始化失败降级、close 清理、全局单例。
"""

import asyncio
import json
from unittest.mock import patch

import pytest

from src.plugin_runtime_v2.scope.scope_audit import (
    ScopeAuditRecorder,
    close_scope_audit_recorder,
    get_scope_audit_recorder,
    init_scope_audit_recorder,
)


@pytest.fixture
def log_path(tmp_path):
    """审计日志路径（tmp_path 下）。"""
    return str(tmp_path / "audit.log")


@pytest.fixture
async def recorder(log_path):
    """创建带消费者任务的 ScopeAuditRecorder，测试后自动关闭。"""
    rec = ScopeAuditRecorder(log_path=log_path)
    rec._consumer_task = asyncio.create_task(rec._consumer_loop())
    try:
        yield rec
    finally:
        await rec.close()


async def _wait_consumer():
    """让消费者任务处理队列中的条目。"""
    await asyncio.sleep(0.05)


def _read_log(log_path):
    """读取日志文件所有行，返回 list[dict]。"""
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


class TestTier1TriggersAudit:
    """Tier 1 触发审计。"""

    async def test_tier1_triggers_audit(self, recorder, log_path):
        await recorder.record(
            plugin_id="X", scope="system:execute:cli", params={},
        )
        await _wait_consumer()
        entries = _read_log(log_path)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry["plugin_id"] == "X"
        assert entry["scope"] == "system:execute:cli"


class TestParamDesensitization:
    """参数脱敏。"""

    def test_desensitize_token(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"token": "abc123"}, rec._sensitive_names)
        assert result["token"] == "***"

    def test_desensitize_password(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"password": "xyz"}, rec._sensitive_names)
        assert result["password"] == "***"

    def test_desensitize_secret(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"secret": "top"}, rec._sensitive_names)
        assert result["secret"] == "***"

    def test_desensitize_api_key(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"api_key": "k123"}, rec._sensitive_names)
        assert result["api_key"] == "***"

    def test_file_path_desensitized(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"path": "/etc/passwd"}, rec._sensitive_names)
        assert result["path"] == "<file>"

    def test_file_path_windows_desensitized(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"path": "C:\\Users\\data"}, rec._sensitive_names)
        assert result["path"] == "<file>"

    def test_non_sensitive_value_preserved(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params(
            {"cmd": "ls -la", "timeout": 30}, rec._sensitive_names,
        )
        assert result["cmd"] == "ls -la"
        assert result["timeout"] == 30

    def test_complex_type_dict(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"data": {"a": 1}}, rec._sensitive_names)
        assert result["data"] == "<dict>"

    def test_complex_type_list(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        result = rec._desensitize_params({"items": [1, 2]}, rec._sensitive_names)
        assert result["items"] == "<list>"

    async def test_desensitize_in_record(self, recorder, log_path):
        """record 中参数被脱敏后写入日志。"""
        await recorder.record(
            plugin_id="P", scope="system:execute:cli",
            params={"token": "secret_val", "cmd": "ls"},
        )
        await _wait_consumer()
        entries = _read_log(log_path)
        assert entries[0]["param_summary"]["token"] == "***"
        assert entries[0]["param_summary"]["cmd"] == "ls"


class TestDesensitizeFailure:
    """脱敏异常处理。"""

    def test_desensitize_failure(self, log_path):
        """异常 params → param_summary = {"<desensitize_failed>": True}。"""
        rec = ScopeAuditRecorder(log_path=log_path)

        # 构造一个会在 _desensitize_params 中抛异常的 params
        # 使用一个 items() 会抛异常的自定义对象
        class BadDict:
            def items(self):
                raise RuntimeError("bad")

        result = rec._desensitize_params(BadDict(), rec._sensitive_names)  # type: ignore
        assert result == {"<desensitize_failed>": True}


class TestAsyncNonBlocking:
    """异步不阻塞。"""

    async def test_record_returns_quickly(self, recorder):
        """record 应快速返回（入队即返回）。"""
        start = asyncio.get_event_loop().time()
        await recorder.record(plugin_id="X", scope="system:execute:cli", params={})
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1  # 100ms 内返回


class TestJsonLinesFormat:
    """JSON Lines 格式。"""

    async def test_json_lines_format(self, recorder, log_path):
        await recorder.record(plugin_id="A", scope="system:execute:cli", params={})
        await recorder.record(plugin_id="B", scope="network:fetch:url", params={})
        await _wait_consumer()
        # 每行是合法 JSON
        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            if line.strip():
                data = json.loads(line)
                assert "plugin_id" in data
                assert "timestamp" in data
                assert "scope" in data
                assert "param_summary" in data


class TestAuditNotBlocking:
    """审计 best-effort 不阻断操作。"""

    async def test_record_crash_does_not_raise(self, log_path):
        """record 内部异常不向外抛。"""
        rec = ScopeAuditRecorder(log_path=log_path)
        # 模拟入队异常
        with patch.object(rec._queue, "put_nowait", side_effect=RuntimeError("boom")):
            # 不应抛异常
            await rec.record(plugin_id="X", scope="system:execute:cli", params={})


class TestQueueFull:
    """队列满时丢弃最老条目。"""

    async def test_queue_full_drops_oldest(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        # 填满队列
        for i in range(rec._queue.maxsize):
            rec._queue.put_nowait({"plugin_id": f"old_{i}"})
        assert rec._queue.full()
        # 再入一条 → 应丢弃最老 + 成功入队
        await rec.record(plugin_id="new", scope="system:execute:cli", params={})
        assert rec._queue.full()
        # 队列中应含 new 条目
        found_new = False
        while not rec._queue.empty():
            entry = rec._queue.get_nowait()
            if entry.get("plugin_id") == "new":
                found_new = True
        assert found_new


class TestInitFailure:
    """初始化失败降级。"""

    def test_init_failure_degrades(self, tmp_path):
        """坏日志路径 → 降级为仅 error_escalation 上报。"""
        # 使用一个无法创建的路径（将文件名作为目录）
        bad_path = str(tmp_path / "is_a_file" / "audit.log")
        # 先创建 is_a_file 为文件，导致子路径无法创建
        (tmp_path / "is_a_file").write_text("x", encoding="utf-8")
        rec = ScopeAuditRecorder(log_path=bad_path)
        assert rec._handler_disabled is True
        assert rec._handler is None


class TestClose:
    """close 清理。"""

    async def test_close_flushes_and_closes(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        rec._consumer_task = asyncio.create_task(rec._consumer_loop())
        # 入队一条
        await rec.record(plugin_id="X", scope="system:execute:cli", params={})
        await _wait_consumer()
        await rec.close()
        # close 后 handler 已关闭
        assert rec._closed is True

    async def test_close_idempotent(self, log_path):
        rec = ScopeAuditRecorder(log_path=log_path)
        rec._consumer_task = asyncio.create_task(rec._consumer_loop())
        await rec.close()
        # 二次 close 不报错
        await rec.close()

    async def test_close_flushes_remaining(self, log_path):
        """close 时 flush 队列中剩余条目。"""
        rec = ScopeAuditRecorder(log_path=log_path)
        # 不启动消费者，直接入队
        await rec.record(plugin_id="X", scope="system:execute:cli", params={})
        # close 应 flush 剩余条目到文件
        await rec.close()
        entries = _read_log(log_path)
        assert len(entries) >= 1
        assert entries[0]["plugin_id"] == "X"


class TestGlobalSingleton:
    """全局单例。"""

    def test_get_returns_none_before_init(self):
        """init 前 get 返回 None。"""
        # 注意：其他测试可能已 init，此处用 mock 确保干净状态
        with patch("src.plugin_runtime_v2.scope.scope_audit._scope_audit_recorder", None):
            assert get_scope_audit_recorder() is None

    async def test_get_returns_instance_after_init(self, log_path):
        """init 后 get 返回实例。"""
        rec = init_scope_audit_recorder(
            log_path=log_path,
            max_size_mb=10,
            backup_count=5,
            sensitive_param_names=["token", "password"],
        )
        try:
            assert get_scope_audit_recorder() is rec
        finally:
            await close_scope_audit_recorder()

    async def test_close_sets_none(self, log_path):
        """close 后 get 返回 None。"""
        init_scope_audit_recorder(
            log_path=log_path,
            max_size_mb=10,
            backup_count=5,
            sensitive_param_names=["token"],
        )
        await close_scope_audit_recorder()
        assert get_scope_audit_recorder() is None


class TestLogRotation:
    """RotatingFileHandler 轮转测试（P1 修复验证）。"""

    async def test_rotation_creates_backup(self, tmp_path):
        """写入超过 maxBytes → 产生 .1 备份文件。"""
        log_path = str(tmp_path / "audit.log")
        # max_size_mb=1 → maxBytes=1MB，但我们用更小的值加速测试
        rec = ScopeAuditRecorder(
            log_path=log_path,
            max_size_mb=1,
            backup_count=3,
        )
        # 手动设置 maxBytes 为很小的值以触发轮转
        if rec._handler is not None:
            rec._handler.maxBytes = 200  # 200 bytes，几条日志就超
        rec._consumer_task = asyncio.create_task(rec._consumer_loop())
        try:
            # 写入足够多的条目触发轮转
            for i in range(20):
                await rec.record(
                    plugin_id=f"plugin_{i}",
                    scope="system:execute:cli",
                    params={"cmd": f"command_{i}_with_some_padding_to_fill_space"},
                )
            await _wait_consumer()
            # 应产生 .1 备份文件
            backup_path = tmp_path / "audit.log.1"
            assert backup_path.exists(), "轮转应产生 .1 备份文件"
        finally:
            await rec.close()

    async def test_rotation_backup_count_limit(self, tmp_path):
        """轮转备份数不超过 backup_count。"""
        log_path = str(tmp_path / "audit.log")
        rec = ScopeAuditRecorder(
            log_path=log_path,
            max_size_mb=1,
            backup_count=2,
        )
        if rec._handler is not None:
            rec._handler.maxBytes = 100
        rec._consumer_task = asyncio.create_task(rec._consumer_loop())
        try:
            for i in range(50):
                await rec.record(
                    plugin_id=f"p_{i}",
                    scope="system:execute:cli",
                    params={"x": f"val_{i}_padding"},
                )
            await _wait_consumer()
            # backup_count=2 → 最多 .1 和 .2，不应有 .3
            assert (tmp_path / "audit.log.1").exists()
            assert (tmp_path / "audit.log.2").exists()
            assert not (tmp_path / "audit.log.3").exists()
        finally:
            await rec.close()

    def test_write_with_rotation_method(self, tmp_path):
        """_write_with_rotation 方法正确触发轮转。"""
        log_path = str(tmp_path / "audit.log")
        rec = ScopeAuditRecorder(log_path=log_path, max_size_mb=1, backup_count=3)
        if rec._handler is not None:
            rec._handler.maxBytes = 50  # 50 bytes
        # 写入超过 maxBytes 的数据
        for i in range(10):
            rec._write_with_rotation(f'{{"id": {i}, "data": "padding_xxxxxx"}}\n')
        # 应产生备份
        assert (tmp_path / "audit.log.1").exists()
        if rec._handler is not None:
            rec._handler.close()