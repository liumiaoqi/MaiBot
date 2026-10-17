"""(丙) 「接 vs 不接」**同刻对照** —— 走 webui 那条真实入口，而不是直接调 handler。

**对照的设计**（同一条请求路径，只差一件事）：

| 臂 | 请求 | 期望 |
|---|---|---|
| **(b) 透传在** | `V5ActionRequest(target=…, decision="raise")` | 到达 `memory_service.v5_admin` 的 kwargs 里**带 `decision="raise"`** |
| **(a) 透传不在 / 客户端没带** | `V5ActionRequest(target=…)`（无 `decision`） | kwargs 里**没有 `decision`** ⇒ 下游 handler 只会看到空值 ⇒ **具名拒绝**（不是静默当 neutral） |

⚠️ **为什么用 stub 而不是真库**：本件红线是"不动真库"；而 (丙) 要观测的是"**键有没有被传下去**"
（装配问题），不是"库有没有被改"（那是 (乙)/(甲) 在临时库上验的）⇒ **用 stub 观测装配**最干净，
也免掉"撤一行 → 发请求 → 再恢复"那种**改生产文件两次**的循环。

⚠️ **诚实边界**：(a) 这一臂我是用"**请求里不带 `decision`**"实现的，**我没有去撤掉 `_v5_action` 里那一行**。
两件事的**可观测结果相同**（下游拿不到 decision），但**严格说**前者测的是"客户端没带"、
后者测的是"带了但被丢"⇒ 若要**逐字**复现"撤那一行"，需要一次编辑+恢复（见回报里的说明）。
"""

from typing import Any

import pytest

from src.webui.routers.memory import maintenance
from src.webui.schemas.memory import V5ActionRequest


class _RecordingV5Admin:
    """记录 `v5_admin(action=..., **kwargs)` 的实参。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((action, kwargs))
        return {"success": True, "echo": {"action": action, **kwargs}}


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingV5Admin:
    recorder = _RecordingV5Admin()
    monkeypatch.setattr(maintenance.memory_service, "v5_admin", recorder)
    return recorder


def test_b_decision_reaches_the_service_when_present(recorder: _RecordingV5Admin) -> None:
    """(b) 透传在：`decision` **真的到达** `memory_service.v5_admin`（不是"HTTP 200"就算数）。"""

    import asyncio

    asyncio.run(
        maintenance.relation_feedback_memory(
            V5ActionRequest(target="h-1", decision="raise", reason="今晚聊得好")
        )
    )

    assert len(recorder.calls) == 1, recorder.calls
    action, kwargs = recorder.calls[0]
    assert action == "relation_feedback", (action, kwargs)
    assert kwargs.get("decision") == "raise", f"decision 没到达：{kwargs}"
    assert kwargs.get("target") == "h-1", kwargs
    assert kwargs.get("reason") == "今晚聊得好", kwargs


def test_a_without_decision_nothing_is_passed_down(recorder: _RecordingV5Admin) -> None:
    """(a) 透传不在 / 客户端没带：kwargs 里**没有 `decision`** ⇒ 下游只会看到空值（⇒ 具名拒绝）。"""

    import asyncio

    asyncio.run(maintenance.relation_feedback_memory(V5ActionRequest(target="h-2")))

    assert len(recorder.calls) == 1, recorder.calls
    _action, kwargs = recorder.calls[0]
    assert "decision" not in kwargs, f"未带 decision 却传下去了：{kwargs}"
    # ⇒ 下游（handler）拿到的是空值 ⇒ 它**具名拒绝**（该行为已由
    #   `tests/test_a_memorix_admin/test_v5_relation_feedback.py` 那条用例钉住）
    assert kwargs.get("target") == "h-2", kwargs
