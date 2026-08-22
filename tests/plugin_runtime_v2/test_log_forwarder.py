"""LogForwarder 单元测试 — 日志转发 + P1-15 stop cancel 无 await。

覆盖：
- 构造与默认状态
- start 创建读取任务（stdout/stderr/两者皆无）
- stop 取消任务，P1-15: stop 是 async 但只 cancel 不 await task
- _read_stream 行为：ANSI 转义码剥离、空行跳过、BrokenPipeError/ValueError 静默
- _ANSI_RE 正则行为
"""

import asyncio
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.plugin_runtime_v2.host.log_forwarder import LogForwarder, _ANSI_RE


class TestLogForwarderConstruct:
    """构造与默认状态。"""

    def test_init_stores_params(self):
        proc = MagicMock(spec=subprocess.Popen)
        fwd = LogForwarder(proc, "r1")
        assert fwd._process is proc
        assert fwd._runner_id == "r1"
        assert fwd._tasks == []


class TestLogForwarderStart:
    """start 创建读取任务。"""

    @pytest.mark.asyncio
    async def test_start_no_streams(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.stdout = None
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        assert len(fwd._tasks) == 0
        await fwd.stop()

    @pytest.mark.asyncio
    async def test_start_stdout_only(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.stdout = MagicMock()
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        assert len(fwd._tasks) == 1
        await fwd.stop()

    @pytest.mark.asyncio
    async def test_start_both_streams(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        assert len(fwd._tasks) == 2
        await fwd.stop()


class TestLogForwarderStop:
    """stop 行为 + P1-15 cancel 无 await。"""

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks_no_await(self):
        """P1-15: stop cancel 后无 await——task 被 cancel 但 stop 不等待完成。"""
        proc = MagicMock(spec=subprocess.Popen)
        # readline 阻塞（永不返回的 Future 模拟）
        proc.stdout = MagicMock()
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        tasks = list(fwd._tasks)
        assert len(tasks) == 1
        # stop 应快速返回（不 await 阻塞的 task）
        await fwd.stop()
        assert len(fwd._tasks) == 0
        # task 被 cancel
        assert tasks[0].cancelled() or tasks[0].cancelling() >= 1
        # 清理 task 避免警告
        try:
            await tasks[0]
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_empty(self):
        """无任务时 stop 不抛异常。"""
        proc = MagicMock(spec=subprocess.Popen)
        proc.stdout = None
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        """重复 stop 不抛异常。"""
        proc = MagicMock(spec=subprocess.Popen)
        proc.stdout = MagicMock()
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        await fwd.stop()
        await fwd.stop()  # 再次 stop 不抛


class TestLogForwarderReadStream:
    """_read_stream 行为：ANSI 剥离、空行、异常处理。"""

    @pytest.mark.asyncio
    async def test_reads_and_strips_ansi(self):
        """读取行并剥离 ANSI 转义码，空行跳过。"""
        proc = MagicMock(spec=subprocess.Popen)
        mock_stdout = MagicMock()
        # 带 ANSI 转义码的行 + 空行 + 结束
        mock_stdout.readline.side_effect = [
            b"\x1b[32mgreen text\x1b[0m\n",
            b"\n",  # 空行（rstrip 后为空，跳过）
            b"",  # EOF
        ]
        proc.stdout = mock_stdout
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        with patch("src.plugin_runtime_v2.host.log_forwarder.logger.info") as mock_log:
            await fwd.start()
            await asyncio.sleep(0.1)
            await fwd.stop()
            # 应只记录一行（空行跳过），且 ANSI 已剥离
            calls = [str(c) for c in mock_log.call_args_list]
            assert any("green text" in c for c in calls)
            assert not any("\x1b" in c for c in calls)

    @pytest.mark.asyncio
    async def test_broken_pipe_silent(self):
        """BrokenPipeError 静默处理（pipe 正常关闭）。"""
        proc = MagicMock(spec=subprocess.Popen)
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = BrokenPipeError()
        proc.stdout = mock_stdout
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        await asyncio.sleep(0.1)
        await fwd.stop()  # 不抛异常

    @pytest.mark.asyncio
    async def test_value_error_silent(self):
        """ValueError 静默处理。"""
        proc = MagicMock(spec=subprocess.Popen)
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = ValueError()
        proc.stdout = mock_stdout
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        await asyncio.sleep(0.1)
        await fwd.stop()  # 不抛异常

    @pytest.mark.asyncio
    async def test_utf8_decode_errors_replace(self):
        """非法 UTF-8 字节用 replace 策略解码不抛异常。"""
        proc = MagicMock(spec=subprocess.Popen)
        mock_stdout = MagicMock()
        mock_stdout.readline.side_effect = [b"\xff\xfe bad utf8\n", b""]
        proc.stdout = mock_stdout
        proc.stderr = None
        fwd = LogForwarder(proc, "r1")
        await fwd.start()
        await asyncio.sleep(0.1)
        await fwd.stop()  # 不抛异常


class TestAnsiRegex:
    """_ANSI_RE 正则行为。"""

    def test_strips_color_codes(self):
        assert _ANSI_RE.sub("", "\x1b[32mgreen\x1b[0m") == "green"

    def test_strips_bold(self):
        assert _ANSI_RE.sub("", "\x1b[1mbold\x1b[0m") == "bold"

    def test_strips_multi_param(self):
        assert _ANSI_RE.sub("", "\x1b[1;32;40mtext\x1b[0m") == "text"

    def test_no_ansi_unchanged(self):
        assert _ANSI_RE.sub("", "plain text") == "plain text"

    def test_regex_compiled(self):
        """_ANSI_RE 是已编译正则对象。"""
        import re
        assert isinstance(_ANSI_RE, re.Pattern)