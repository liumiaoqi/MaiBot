"""ZG16-5: Tier1Detector 静态检测测试。

验证正则文本扫描能正确识别 Tier 1 高危操作调用模式，
含去重、不可读文件跳过、自定义规则、无副作用。
"""

import pytest

from src.plugin_runtime_v2.scope.validate_manifest_scopes import Tier1Detector


def _write_py(tmp_path, filename, content):
    """在 tmp_path 下写入 .py 文件，返回 tmp_path。"""
    (tmp_path / filename).write_text(content, encoding="utf-8")
    return tmp_path


class TestCliDetection:
    """system:execute:cli 检测。"""

    def test_subprocess_run(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import subprocess\nsubprocess.run(['ls'])\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:execute:cli" in detected

    def test_os_system(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import os\nos.system('ls')\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:execute:cli" in detected

    def test_os_popen(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import os\nos.popen('ls')\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:execute:cli" in detected

    def test_asyncio_create_subprocess_exec(self, tmp_path):
        _write_py(
            tmp_path, "plugin.py",
            "import asyncio\nasyncio.create_subprocess_exec('ls')\n",
        )
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:execute:cli" in detected


class TestScreenshotDetection:
    """system:read:screenshot 检测。"""

    def test_pyautogui_screenshot(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import pyautogui\npyautogui.screenshot()\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:read:screenshot" in detected

    def test_imagegrab_grab(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "from PIL import ImageGrab\nImageGrab.grab()\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:read:screenshot" in detected


class TestLocationDetection:
    """system:read:location 检测。"""

    def test_gps_exifread(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import exifread\nGPSInfo = tags['GPSInfo']\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:read:location" in detected

    def test_geopy_nominatim(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "from geopy import Nominatim\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:read:location" in detected


class TestAccountDetection:
    """account:execute:operation 检测。"""

    def test_qzone(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import qzone\nqzone.login()\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "account:execute:operation" in detected

    def test_qq_sign_in(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "# 每日签到\ndo_sign()\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "account:execute:operation" in detected


class TestFinanceDetection:
    """finance:read:qr_code 检测。"""

    def test_qr_code(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import qrcode\nqr = qrcode.make('test')\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "finance:read:qr_code" in detected

    def test_shou_kuan_ma(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "# 收款码识别\npass\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "finance:read:qr_code" in detected


class TestNetworkDetection:
    """network:fetch:url 检测。"""

    def test_requests_get(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import requests\nrequests.get('http://x')\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "network:fetch:url" in detected

    def test_httpx_get(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "import httpx\nhttpx.get('http://x')\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert "network:fetch:url" in detected

    def test_urllib_urlopen(self, tmp_path):
        _write_py(
            tmp_path, "plugin.py",
            "import urllib.request\nurllib.request.urlopen('http://x')\n",
        )
        detected = Tier1Detector.detect(str(tmp_path))
        assert "network:fetch:url" in detected


class TestNoTier1Ops:
    """无 Tier 1 操作 → 空列表。"""

    def test_no_tier1_ops(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "x = 1 + 2\nprint(x)\n")
        detected = Tier1Detector.detect(str(tmp_path))
        assert detected == []

    def test_empty_dir(self, tmp_path):
        detected = Tier1Detector.detect(str(tmp_path))
        assert detected == []


class TestDeduplication:
    """同一 scope 多次匹配 → 去重。"""

    def test_deduplication(self, tmp_path):
        _write_py(
            tmp_path, "plugin.py",
            "import subprocess\n"
            "subprocess.run(['ls'])\n"
            "subprocess.run(['pwd'])\n"
            "import os\nos.system('whoami')\n",
        )
        detected = Tier1Detector.detect(str(tmp_path))
        # system:execute:cli 只出现一次
        assert detected.count("system:execute:cli") == 1


class TestUnreadableFileSkipped:
    """不可读文件 → 跳过继续其他。"""

    def test_unreadable_file_skipped(self, tmp_path):
        # 可读文件含 Tier 1
        _write_py(tmp_path, "good.py", "import subprocess\nsubprocess.run(['ls'])\n")
        # 不可读文件（二进制乱码，UnicodeDecodeError）
        (tmp_path / "bad.py").write_bytes(b"\x80\x81\x82\xff\xfe")
        detected = Tier1Detector.detect(str(tmp_path))
        # 仍检测到 good.py 中的 cli
        assert "system:execute:cli" in detected


class TestCustomRules:
    """自定义规则。"""

    def test_custom_rules(self, tmp_path):
        _write_py(tmp_path, "plugin.py", "dangerous_call()\n")
        custom = {r"dangerous_call": "system:execute:cli"}
        detected = Tier1Detector.detect(str(tmp_path), rules=custom)
        assert "system:execute:cli" in detected

    def test_custom_rules_override(self, tmp_path):
        """自定义规则覆盖默认规则。"""
        _write_py(tmp_path, "plugin.py", "subprocess.run(['ls'])\n")
        # 空规则 → 不检测默认模式
        detected = Tier1Detector.detect(str(tmp_path), rules={})
        assert detected == []


class TestNoCodeExecution:
    """纯文本扫描，无副作用（不执行插件代码）。"""

    def test_no_code_execution(self, tmp_path):
        """含危险代码但不应被执行。"""
        _write_py(
            tmp_path, "plugin.py",
            "import os\n"
            "os.system('rm -rf /')  # 极其危险，但仅文本扫描\n"
            "raise SystemExit(99)   # 如果被执行会退出\n",
        )
        # detect 应正常返回，不执行代码
        detected = Tier1Detector.detect(str(tmp_path))
        assert "system:execute:cli" in detected


class TestPathNotFound:
    """代码目录不存在 → FileNotFoundError。"""

    def test_path_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Tier1Detector.detect(str(tmp_path / "nonexistent"))