"""插件运行时浏览器渲染能力测试。"""

from typing import Optional

import pytest

from src.plugin_runtime.integration import PluginRuntimeManager
from src.plugin_runtime.host.supervisor import PluginSupervisor
from src.services.html_render_service import HtmlRenderRequest, HtmlRenderResult


class _FakeRenderService:
    """用于替代真实浏览器渲染服务的测试桩。"""

    def __init__(self) -> None:
        """初始化测试桩。"""

        self.last_request: Optional[HtmlRenderRequest] = None

    async def render_html_to_png(self, request: HtmlRenderRequest) -> HtmlRenderResult:
        """记录请求并返回固定的渲染结果。

        Args:
            request: 当前渲染请求。

        Returns:
            HtmlRenderResult: 固定的测试渲染结果。
        """

        self.last_request = request
        return HtmlRenderResult(
            image_base64="ZmFrZS1pbWFnZQ==",
            mime_type="image/png",
            width=640,
            height=480,
            render_ms=12,
        )


def test_render_capability_is_registered() -> None:
    """Host 注册能力时应包含 render.html2png。"""

    manager = PluginRuntimeManager()
    supervisor = PluginSupervisor(plugin_dirs=[])

    manager._register_capability_impls(supervisor)

    assert "render.html2png" in supervisor.capability_service.list_capabilities()


@pytest.mark.asyncio
async def test_render_capability_forwards_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """render.html2png 应将请求透传给浏览器渲染服务。"""

    from src.plugin_runtime.capabilities import render as render_capability_module

    fake_service = _FakeRenderService()
    monkeypatch.setattr(render_capability_module, "get_html_render_service", lambda: fake_service)

    manager = PluginRuntimeManager()
    result = await manager._cap_render_html2png(
        "demo.plugin",
        "render.html2png",
        {
            "html": "<body><div id='card'>hello</div></body>",
            "selector": "#card",
            "viewport": {"width": 1024, "height": 768},
            "device_scale_factor": 1.5,
            "full_page": False,
            "omit_background": True,
            "wait_until": "networkidle",
            "wait_for_selector": "#card",
            "wait_for_timeout_ms": 150,
            "timeout_ms": 3000,
            "allow_network": True,
        },
    )

    assert result == {
        "success": True,
        "result": {
            "image_base64": "ZmFrZS1pbWFnZQ==",
            "mime_type": "image/png",
            "width": 640,
            "height": 480,
            "render_ms": 12,
        },
    }
    assert fake_service.last_request is not None
    assert fake_service.last_request.selector == "#card"
    assert fake_service.last_request.viewport_width == 1024
    assert fake_service.last_request.viewport_height == 768
    assert fake_service.last_request.device_scale_factor == 1.5
    assert fake_service.last_request.omit_background is True
    assert fake_service.last_request.wait_until == "networkidle"
    assert fake_service.last_request.allow_network is True
