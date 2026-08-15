"""ZG16-5: validate_manifest_scopes + CLI main() 测试。

覆盖 scope 合法性、Tier 1 缺失检测、CLI 退出码、JSON/human 输出、
manifest 不存在/损坏、manifest 不被修改、性能 < 100ms。
"""

import json
import time

import pytest

from src.plugin_runtime_v2.scope.validate_manifest_scopes import (
    ValidateResult,
    main,
    validate_manifest_scopes,
)


def _write_manifest(tmp_path, scopes=None, extra=None):
    """写入 manifest JSON 文件，返回路径字符串。"""
    data = {"id": "org.test.plugin", "version": "1.0.0", "name": "test"}
    if scopes is not None:
        data["scopes"] = scopes
    if extra:
        data.update(extra)
    path = tmp_path / "_manifest.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _write_code(tmp_path, content):
    """写入 plugin.py 代码文件，返回代码目录字符串。"""
    (tmp_path / "plugin.py").write_text(content, encoding="utf-8")
    return str(tmp_path)


class TestScopeValidity:
    """scope 合法性校验。"""

    def test_scope_validity_pass(self, tmp_path):
        """manifest 含合法 scope → ok=True。"""
        manifest = {"scopes": ["system:execute:cli"]}
        result = validate_manifest_scopes(manifest)
        assert result.ok is True
        assert result.invalid_scopes == []

    def test_invalid_scope(self, tmp_path):
        """manifest 含不合法 scope → ok=False。"""
        manifest = {"scopes": ["foo:bar:baz"]}
        result = validate_manifest_scopes(manifest)
        assert result.ok is False
        assert "foo:bar:baz" in result.invalid_scopes


class TestTier1Missing:
    """Tier 1 缺失检测。"""

    def test_tier1_missing_cli(self, tmp_path):
        """代码含 subprocess.run 但 manifest 无 system:execute:cli → 缺失。"""
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        manifest = {"scopes": ["message:send:text"]}
        result = validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        assert result.ok is False
        assert "system:execute:cli" in result.missing_scopes

    def test_screenshot_missing(self, tmp_path):
        """代码含 pyautogui.screenshot 但 manifest 无 system:read:screenshot → 缺失。"""
        code_dir = _write_code(tmp_path, "import pyautogui\npyautogui.screenshot()\n")
        manifest = {"scopes": ["message:send:text"]}
        result = validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        assert result.ok is False
        assert "system:read:screenshot" in result.missing_scopes

    def test_no_tier1_ops_no_missing(self, tmp_path):
        """代码无 Tier 1 调用 → 无 missing_scopes。"""
        code_dir = _write_code(tmp_path, "x = 1\n")
        manifest = {"scopes": ["message:send:text"]}
        result = validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        assert result.missing_scopes == []
        assert result.ok is True

    def test_tier1_declared_no_missing(self, tmp_path):
        """代码含 Tier 1 且 manifest 声明了 → ok=True。"""
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        manifest = {"scopes": ["system:execute:cli"]}
        result = validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        assert result.missing_scopes == []
        assert result.ok is True


class TestScopesFieldMissing:
    """scopes 字段缺失。"""

    def test_scopes_missing_no_tier1(self, tmp_path):
        """manifest 无 scopes 字段 + 无 Tier 1 代码 → ok=True。"""
        code_dir = _write_code(tmp_path, "x = 1\n")
        manifest = {"id": "org.test", "version": "1.0"}
        result = validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        assert result.ok is True

    def test_scopes_missing_with_tier1(self, tmp_path):
        """manifest 无 scopes 字段 + Tier 1 代码 → ok=False。"""
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        manifest = {"id": "org.test", "version": "1.0"}
        result = validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        assert result.ok is False
        assert "system:execute:cli" in result.missing_scopes


class TestCliExitCodes:
    """CLI 退出码。"""

    def test_pass_exit_0(self, tmp_path):
        """合法 manifest + 完整 scopes → exit 0。"""
        manifest_path = _write_manifest(tmp_path, scopes=["message:send:text"])
        code_dir = _write_code(tmp_path, "x = 1\n")
        exit_code = main([manifest_path, "--code", code_dir])
        assert exit_code == 0

    def test_fail_exit_1(self, tmp_path):
        """缺失 Tier 1 scope → exit 1。"""
        manifest_path = _write_manifest(tmp_path, scopes=["message:send:text"])
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        exit_code = main([manifest_path, "--code", code_dir])
        assert exit_code == 1

    def test_manifest_not_found_exit_2(self, tmp_path):
        """manifest 不存在 → exit 2。"""
        exit_code = main([str(tmp_path / "nonexistent.json")])
        assert exit_code == 2

    def test_manifest_corrupted_exit_2(self, tmp_path):
        """manifest JSON 损坏 → exit 2。"""
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        exit_code = main([str(path)])
        assert exit_code == 2

    def test_tier1_detector_failure_exit_2(self, tmp_path):
        """代码目录不存在 → exit 2。"""
        manifest_path = _write_manifest(tmp_path, scopes=["message:send:text"])
        exit_code = main([manifest_path, "--code", str(tmp_path / "no_such_dir")])
        assert exit_code == 2


class TestCliOutputFormat:
    """CLI 输出格式。"""

    def test_json_output(self, tmp_path, capsys):
        """--json → stdout 是合法 JSON。"""
        manifest_path = _write_manifest(tmp_path, scopes=["message:send:text"])
        main([manifest_path, "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "ok" in data
        assert "missing_scopes" in data
        assert "invalid_scopes" in data

    def test_human_output(self, tmp_path, capsys):
        """--human → 人可读中文文本。"""
        manifest_path = _write_manifest(tmp_path, scopes=["message:send:text"])
        main([manifest_path, "--human"])
        captured = capsys.readouterr()
        # 含中文说明
        assert "校验" in captured.out

    def test_human_output_missing(self, tmp_path, capsys):
        """--human + 缺失 → 含缺失信息。"""
        manifest_path = _write_manifest(tmp_path, scopes=["message:send:text"])
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        main([manifest_path, "--code", code_dir, "--human"])
        captured = capsys.readouterr()
        assert "缺失" in captured.out or "Tier 1" in captured.out


class TestManifestNotModified:
    """校验不修改 manifest 文件。"""

    def test_manifest_not_modified(self, tmp_path):
        manifest_path = _write_manifest(tmp_path, scopes=["system:execute:cli"])
        original = (tmp_path / "_manifest.json").read_text(encoding="utf-8")
        validate_manifest_scopes(manifest_path)
        after = (tmp_path / "_manifest.json").read_text(encoding="utf-8")
        assert original == after


class TestPerformance:
    """性能 < 100ms。"""

    def test_performance_under_100ms(self, tmp_path):
        """单次校验 < 100ms。"""
        manifest = {"scopes": ["system:execute:cli", "message:send:text"]}
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        start = time.perf_counter()
        validate_manifest_scopes(manifest, plugin_code_path=code_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"校验耗时 {elapsed_ms:.1f}ms 超过 100ms"


class TestValidateResultDataclass:
    """ValidateResult 数据类。"""

    def test_default_factory(self):
        result = ValidateResult(ok=True)
        assert result.missing_scopes == []
        assert result.invalid_scopes == []
        assert result.errors == []

    def test_frozen(self):
        result = ValidateResult(ok=True)
        with pytest.raises(AttributeError):
            result.ok = False  # type: ignore