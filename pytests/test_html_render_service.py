"""HTML 浏览器渲染服务测试。"""

from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.config.official_configs import PluginRuntimeRenderConfig
from src.services import html_render_service as html_render_service_module
from src.services.html_render_service import HTMLRenderService, ManagedBrowserRecord


class _FakeChromium:
    """用于模拟 Playwright Chromium 启动器的测试桩。"""

    def __init__(self, effects: List[Any]) -> None:
        """初始化 Chromium 启动测试桩。

        Args:
            effects: 每次调用 ``launch`` 时依次返回或抛出的结果。
        """

        self._effects: List[Any] = list(effects)
        self.calls: List[Dict[str, Any]] = []

    async def launch(self, **kwargs: Any) -> Any:
        """模拟 Playwright Chromium 的启动过程。

        Args:
            **kwargs: 浏览器启动参数。

        Returns:
            Any: 预设的浏览器对象。

        Raises:
            Exception: 当预设结果为异常对象时抛出。
        """

        self.calls.append(dict(kwargs))
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _FakePlaywright:
    """用于模拟 Playwright 根对象的测试桩。"""

    def __init__(self, chromium: _FakeChromium) -> None:
        """初始化 Playwright 测试桩。

        Args:
            chromium: Chromium 启动器测试桩。
        """

        self.chromium = chromium


def _build_render_config(**kwargs: Any) -> PluginRuntimeRenderConfig:
    """构造用于测试的浏览器渲染配置。

    Args:
        **kwargs: 需要覆盖的配置字段。

    Returns:
        PluginRuntimeRenderConfig: 测试使用的配置对象。
    """

    payload: Dict[str, Any] = {
        "auto_download_chromium": True,
        "browser_install_root": "data/test-playwright-browsers",
    }
    payload.update(kwargs)
    return PluginRuntimeRenderConfig(**payload)


@pytest.mark.asyncio
async def test_launch_browser_auto_downloads_chromium_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """未检测到可用浏览器时，应自动下载 Chromium 并记录状态。"""

    monkeypatch.setattr(html_render_service_module, "PROJECT_ROOT", tmp_path)
    service = HTMLRenderService()
    config = _build_render_config()
    fake_browser = object()
    fake_chromium = _FakeChromium(
        [
            RuntimeError("browserType.launch: Executable doesn't exist at /tmp/chromium"),
            fake_browser,
        ]
    )
    install_calls: List[str] = []

    monkeypatch.setattr(service, "_resolve_executable_path", lambda _config: "")

    async def fake_install(_config: PluginRuntimeRenderConfig) -> None:
        """模拟 Chromium 自动下载。

        Args:
            _config: 当前浏览器渲染配置。
        """

        install_calls.append(_config.browser_install_root)
        browsers_path = service._get_managed_browsers_path(_config)
        (browsers_path / "chromium-1234").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(service, "_install_chromium_browser", fake_install)

    browser = await service._launch_browser(_FakePlaywright(fake_chromium), config)

    assert browser is fake_browser
    assert install_calls == ["data/test-playwright-browsers"]
    assert len(fake_chromium.calls) == 2

    browser_record = service._load_managed_browser_record()
    assert browser_record is not None
    assert browser_record.install_source == "auto_download"
    assert browser_record.browser_name == "chromium"


@pytest.mark.asyncio
async def test_launch_browser_reuses_existing_managed_browser(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """已存在 Playwright 托管浏览器时，不应重复下载。"""

    monkeypatch.setattr(html_render_service_module, "PROJECT_ROOT", tmp_path)
    service = HTMLRenderService()
    config = _build_render_config()
    browsers_path = service._get_managed_browsers_path(config)
    (browsers_path / "chrome-headless-shell-1234").mkdir(parents=True, exist_ok=True)
    fake_browser = object()
    fake_chromium = _FakeChromium([fake_browser])

    monkeypatch.setattr(service, "_resolve_executable_path", lambda _config: "")

    async def fail_install(_config: PluginRuntimeRenderConfig) -> None:
        """若被错误调用则立即失败。

        Args:
            _config: 当前浏览器渲染配置。

        Raises:
            AssertionError: 表示本测试不期望进入下载逻辑。
        """

        raise AssertionError("不应触发自动下载")

    monkeypatch.setattr(service, "_install_chromium_browser", fail_install)

    browser = await service._launch_browser(_FakePlaywright(fake_chromium), config)

    assert browser is fake_browser
    assert len(fake_chromium.calls) == 1

    browser_record = service._load_managed_browser_record()
    assert browser_record is not None
    assert browser_record.install_source == "existing_cache"
    assert browser_record.browsers_path == str(browsers_path)


@pytest.mark.asyncio
async def test_launch_browser_prefers_local_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """探测到本机浏览器时，应优先使用可执行文件路径启动。"""

    monkeypatch.setattr(html_render_service_module, "PROJECT_ROOT", tmp_path)
    service = HTMLRenderService()
    config = _build_render_config()
    fake_browser = object()
    fake_chromium = _FakeChromium([fake_browser])
    executable_path = "/usr/bin/google-chrome"

    monkeypatch.setattr(service, "_resolve_executable_path", lambda _config: executable_path)

    browser = await service._launch_browser(_FakePlaywright(fake_chromium), config)

    assert browser is fake_browser
    assert len(fake_chromium.calls) == 1
    assert fake_chromium.calls[0]["executable_path"] == executable_path
    assert service._load_managed_browser_record() is None


def test_managed_browser_record_roundtrip() -> None:
    """托管浏览器记录应支持序列化与反序列化。"""

    record = ManagedBrowserRecord(
        browser_name="chromium",
        browsers_path="/tmp/playwright-browsers",
        install_source="auto_download",
        playwright_version="1.58.0",
        recorded_at="2026-04-03T10:00:00+00:00",
        last_verified_at="2026-04-03T10:00:01+00:00",
    )

    restored_record = ManagedBrowserRecord.from_dict(record.to_dict())

    assert restored_record == record
