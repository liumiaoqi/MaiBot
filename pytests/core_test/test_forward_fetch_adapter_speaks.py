"""`forward-fetch-speak`：`ForwardFetchAdapter` 的四条失败路径必须**具名出声**（2026-10-17）。

## 为什么有这条
该适配器的四条失败路径原先**一声不响**地返回 None ⇒ 调用方（`src/maisaka/context/messages.py`
的 prefetch）只看得见"没拉到"，**分不清**是"工具没注册/没暴露"、"工具调用失败"还是"返回结构不对"。

## 判据（lead 定）
- **(甲)** 合成"工具未注册 / 调用失败" ⇒ caplog 里能看到**具名 warning**（含工具名与原因）；
  ⛔ **不许只 assert 返回值是 None** —— 那证明不了"出声"；
- **(乙)** 反向自检：**正常路径一条 warning 都不许多**（成功时安静）；
- **(丙)** 返回值语义不变（仍 None / list）⇒ 既有调用方不受影响。

## 覆盖边界（如实）
"工具未注册"用**真** `ToolRegistry`（空注册表 ⇒ `未找到工具：…`）；
另外三条"返回结构不对"用**替身 registry** 精确构造 —— 真 registry 不会自然产出
"非法 JSON / payload `success=false` / result 结构不认识"这三种返回。
"""

import asyncio
import json

import pytest

from src.core.adapters.forward_fetch_adapter import ForwardFetchAdapter
from src.core.tooling import ToolExecutionResult, ToolInvocation, ToolRegistry

TOOL = ForwardFetchAdapter.TOOL_NAME


class _StubRegistry:
    """替身：`invoke` 直接返回造好的结果（用来精确构造三条"返回结构不对"）。"""

    def __init__(self, result: ToolExecutionResult) -> None:
        self._result = result
        self.seen: list[ToolInvocation] = []

    async def invoke(self, invocation: ToolInvocation, context=None) -> ToolExecutionResult:
        self.seen.append(invocation)
        return self._result


def _install(monkeypatch: pytest.MonkeyPatch, registry: object) -> None:
    """把适配器函数内 `from src.core.tooling import get_global_tool_registry` 换成替身。"""

    monkeypatch.setattr("src.core.tooling.get_global_tool_registry", lambda: registry)


def _fetch() -> object:
    return asyncio.run(ForwardFetchAdapter().fetch_forward_nodes("fwd-1"))


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


# ── (甲) 四条失败路径都必须出声（且具名）──────────────────────────────


def test_unregistered_tool_is_named(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """**(甲)** 工具**未注册**（真空注册表）⇒ 返回值仍 None，但必须有具名 warning。"""

    _install(monkeypatch, ToolRegistry())

    with caplog.at_level("WARNING"):
        assert _fetch() is None

    messages = _messages(caplog)
    assert any("未找到工具" in m and TOOL in m and "fwd-1" in m for m in messages), messages


def test_failed_invocation_is_named(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """**(甲)** 工具**调用失败** ⇒ 具名 warning 里必须带 `error_message` 的原因。"""

    _install(
        monkeypatch,
        _StubRegistry(
            ToolExecutionResult(
                tool_name=TOOL,
                success=False,
                error_message="工具 napcat.get_forward_msg 调用失败：RuntimeError: 连接已断开",
            )
        ),
    )

    with caplog.at_level("WARNING"):
        assert _fetch() is None

    messages = _messages(caplog)
    assert any("连接已断开" in m and TOOL in m and "fwd-1" in m for m in messages), messages


@pytest.mark.parametrize(
    ("content", "expect_in_message", "label"),
    [
        ("{不是合法 json", "不是合法 JSON", "非法 JSON"),
        (json.dumps({"success": False, "result": {"messages": []}}), "不是成功结构", "payload success=false"),
        (json.dumps({"success": True, "result": {"nodes": []}}), "结构不认识", "result 结构不认识"),
    ],
)
def test_structural_paths_are_named(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    content: str,
    expect_in_message: str,
    label: str,
) -> None:
    """**(甲)** 三条"返回结构不对"的路径 ⇒ 各自那条具名 warning（理由要**对得上**）。"""

    _install(monkeypatch, _StubRegistry(ToolExecutionResult(tool_name=TOOL, success=True, content=content)))

    with caplog.at_level("WARNING"):
        assert _fetch() is None

    messages = _messages(caplog)
    assert any(expect_in_message in m and TOOL in m for m in messages), (label, messages)


# ── (乙)(丙) 正常路径：安静 + 返回值语义不变 ─────────────────────────


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (json.dumps({"success": True, "result": [{"user_id": "u1"}]}), [{"user_id": "u1"}]),
        (json.dumps({"success": True, "result": {"messages": [{"user_id": "u2"}]}}), [{"user_id": "u2"}]),
    ],
)
def test_happy_path_is_silent_and_returns_nodes(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    content: str,
    expected: list[dict],
) -> None:
    """**(乙)** 成功时**一条 warning 都不许有**；**(丙)** 返回值仍是节点列表（语义不变）。"""

    _install(monkeypatch, _StubRegistry(ToolExecutionResult(tool_name=TOOL, success=True, content=content)))

    with caplog.at_level("WARNING"):
        nodes = _fetch()

    assert nodes == expected
    assert caplog.records == [], [record.getMessage() for record in caplog.records]
