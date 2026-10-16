"""`PluginPlatformDriver` 出站**载荷形状**的判据（"能听不能说"第三层）。

## 这一层坏在哪（真机现场）

路由与授权都修好之后，发送走的是插件驱动，但插件侧报：
`RuntimeError: 网关 Tool 调用失败: … tool=napcat.send_text error=EXECUTION_ERROR: KeyError: 'session_id'`
⇒ 形状对不上：我们发 `{message, route, metadata}`，而插件的 Tool 读的是**顶层**
`args["session_id"]` / `args["text"]`（`plugins/maibot-team.napcat-adapter/plugin.py:313-318`），
且 host 侧 `gateway_supervisor.invoke_message_gateway` 把我们给的 `args` **原样**透传。

## 判据（三条）

1. **正向**：文本回复的 args 里 `session_id` 与 `text` 都在**顶层**，且 `session_id`
   与消息携带的一致；`message`/`route` 仍在（别的网关插件按它们取值）。
2. **契约对拍（源级）**：把插件里 `napcat.send_text` 真正读的键（从源码 `args["…"]` 提取）
   与我们发的 args **对拍** —— 这样插件将来多读一个键，这里会红，而不是等真机 KeyError。
3. **反向（红线）**：`session_id` 缺失 ⇒ **拒发**（不调 supervisor、回执 FAILED 且原因可读）；
   无可发送文本分量 ⇒ 同样拒发（网关声明的工具是纯文本参数表，不许把 "[图片]" 当正文发）。
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.platform_io.drivers.plugin_driver import PluginPlatformDriver
from src.platform_io.types import DeliveryStatus, RouteKey

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_FILE = REPO_ROOT / "plugins" / "maibot-team.napcat-adapter" / "plugin.py"


class _RecordingSupervisor:
    """记录 `invoke_message_gateway` 收到的 args（驱动唯一依赖的口）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def invoke_message_gateway(
        self,
        plugin_id: str,
        component_name: str,
        args: dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> Any:
        self.calls.append(
            {
                "plugin_id": plugin_id,
                "component_name": component_name,
                "args": args or {},
                "timeout_ms": timeout_ms,
            }
        )
        return type(
            "_Response",
            (),
            {"payload": {"success": True, "result": {"success": True, "external_message_id": "ext-1"}}},
        )()


def _driver(supervisor: _RecordingSupervisor) -> PluginPlatformDriver:
    return PluginPlatformDriver(
        driver_id="plugin.maibot-team.napcat-adapter.gateway.qq_gateway",
        platform="qq",
        supervisor=supervisor,
        component_name="qq_gateway",
        supports_send=True,
        plugin_id="maibot-team.napcat-adapter",
        metadata={"tool_name": "napcat.send_text"},
    )


def _outbound_message(*, session_id: str, text: str = "在呢") -> Any:
    """按 `services/send_service.py:511-525` 的形态造一条出站消息。"""
    from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
    from src.common.data_models.session_message_data_model import SessionMessage

    message = SessionMessage(
        message_id="msg-1", timestamp=datetime(2026, 10, 16, 15, 0, 0), platform="qq"
    )
    message.message_info = MessageInfo(
        user_info=UserInfo(user_id="10001", user_nickname="麦麦")
    )
    message.raw_message = MessageSequence([TextComponent(text)])
    message.session_id = session_id
    return message


@pytest.mark.asyncio
async def test_args_carry_top_level_session_id_and_text() -> None:
    """正向：`session_id` 与 `text` 必须在**顶层**（插件 Tool 的参数表就是这个形状）。"""
    supervisor = _RecordingSupervisor()
    driver = _driver(supervisor)

    receipt = await driver.send_message(
        _outbound_message(session_id="d3ed272322bb363240cfaf0f1cc28319"),
        RouteKey(platform="qq", account_id="12345", scope=None),
    )

    assert receipt.status is DeliveryStatus.SENT
    args = supervisor.calls[0]["args"]
    assert args["session_id"] == "d3ed272322bb363240cfaf0f1cc28319", "顶层 session_id 缺失（真机 KeyError 的根因）"
    assert args["text"] == "在呢"
    # 兼容面：完整消息与路由照旧带上（别的网关插件按它们取值）
    assert args["message"]["session_id"] == "d3ed272322bb363240cfaf0f1cc28319"
    assert args["route"]["platform"] == "qq"
    assert args["route"]["account_id"] == "12345"


def test_plugin_tool_arg_keys_are_all_provided() -> None:
    """**契约对拍**：插件 `napcat.send_text` 从源码里读的键，我们必须全都提供。

    与"只断言我们发了什么"的区别：这条盯着**插件真正读什么**。插件将来多读一个键
    （比如再要 `group_id`），这里当场红——而不是等真机再吃一次 KeyError。
    """
    if not PLUGIN_FILE.exists():  # 裸 worktree 可能缺 gitlink 资源：跳过而不是假绿
        pytest.skip("插件目录缺失（worktree 未补 gitlink 资源）")

    source = PLUGIN_FILE.read_text(encoding="utf-8")
    match = re.search(
        r"async def tool_send_text\(self, args: Dict\[str, Any\]\) -> Dict\[str, Any\]:(?P<body>.*?)(?=\n    @|\n    async def |\Z)",
        source,
        re.DOTALL,
    )
    assert match is not None, "插件里找不到 tool_send_text（契约对拍失去对象，请更新本用例）"
    read_keys = set(re.findall(r'args\[\s*"([^"]+)"\s*\]', match.group("body")))
    assert read_keys, "插件 tool_send_text 不再按 args[...] 取值？契约对拍需要跟着改"

    supervisor = _RecordingSupervisor()
    driver = _driver(supervisor)
    import asyncio

    asyncio.run(
        driver.send_message(
            _outbound_message(session_id="sess-1"),
            RouteKey(platform="qq", account_id="12345", scope=None),
        )
    )
    provided = set(supervisor.calls[0]["args"].keys())
    missing = read_keys - provided
    assert not missing, f"插件读 {sorted(read_keys)}，我们只给了 {sorted(provided)}，缺 {sorted(missing)}"


@pytest.mark.asyncio
async def test_missing_session_id_refuses_without_calling_the_plugin() -> None:
    """**红线**：会话 ID 缺失 ⇒ 拒发 + 出声（不自行计算、不调插件、回执原因可读）。"""
    supervisor = _RecordingSupervisor()
    driver = _driver(supervisor)

    receipt = await driver.send_message(
        _outbound_message(session_id="   "),
        RouteKey(platform="qq", account_id=None, scope=None),
    )

    assert receipt.status is DeliveryStatus.FAILED
    assert "session_id" in (receipt.error or "")
    assert supervisor.calls == [], "缺 session_id 仍调了插件（应在本层拒发）"


@pytest.mark.asyncio
async def test_message_without_text_component_is_refused() -> None:
    """无可发送文本分量 ⇒ 拒发（网关声明的工具是纯文本参数表，不许把占位符当正文发）。"""
    from src.common.data_models.mai_message_data_model import MessageInfo, UserInfo
    from src.common.data_models.session_message_data_model import SessionMessage

    supervisor = _RecordingSupervisor()
    driver = _driver(supervisor)
    message = SessionMessage(
        message_id="msg-2", timestamp=datetime(2026, 10, 16, 15, 0, 0), platform="qq"
    )
    message.message_info = MessageInfo(
        user_info=UserInfo(user_id="10001", user_nickname="麦麦")
    )
    message.raw_message = MessageSequence([])
    message.session_id = "sess-2"

    receipt = await driver.send_message(message, RouteKey(platform="qq", account_id=None, scope=None))

    assert receipt.status is DeliveryStatus.FAILED
    assert "文本" in (receipt.error or "")
    assert supervisor.calls == []
