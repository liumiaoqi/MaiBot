"""ZG-25 升级适配层——桥接 ZG-25 临时列表 ↔ N5 持久 surface 语义。

对标 dsh region.ts:152-254 compactSurfaceRegion + tool-pairing.ts。
不复制 N5 算法——只提供转换 + 存储端口让 SurfaceReplacer / ToolPairingBalancer 调用。
"""

from dataclasses import dataclass, field
from typing import Any

from src.maisaka.context.messages import (
    AssistantMessage,
    LLMContextMessage,
    ToolResultMessage,
)


@dataclass(frozen=True)
class _N5EventMessage:
    """N5 事件 message 字段——含 content 列表（tool-call block）。"""

    content: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class _N5EventData:
    """N5 事件 data 字段——含 message。"""

    message: _N5EventMessage


@dataclass(frozen=True)
class N5Event:
    """N5 surface 事件——ToolPairingBalancer 平衡检查的输入。

    对标 dsh 事件序列：assistant/message / tool/result / user/message。
    """

    type: str
    seq: int
    data: _N5EventData | None = None


def to_n5_events(messages: list[LLMContextMessage]) -> list[N5Event]:
    """将 ZG-25 消息列表转换为 N5 surface 事件序列。

    映射规则（design 2.2.2 + 决策 2）：
    - AssistantMessage with tool_calls → event(type="assistant/message", content=[{type:"tool-call"}])
    - ToolResultMessage → event(type="tool/result")
    - 其他（UserMessage / AssistantMessage 无 tool_calls / CompactionSummaryMessage）→ event(type="user/message")

    纯转换，不抛异常。
    """
    events: list[N5Event] = []
    for seq, msg in enumerate(messages):
        if isinstance(msg, ToolResultMessage):
            events.append(N5Event(type="tool/result", seq=seq))
        elif isinstance(msg, AssistantMessage) and msg.tool_calls:
            tool_call_blocks = [{"type": "tool-call", "id": tc.call_id} for tc in msg.tool_calls]
            events.append(N5Event(
                type="assistant/message",
                seq=seq,
                data=_N5EventData(message=_N5EventMessage(content=tool_call_blocks)),
            ))
        else:
            events.append(N5Event(type="user/message", seq=seq))
    return events


_session_generations: dict[str, int] = {}


class TempListMemoryStore:
    """临时列表 MemoryStorePort——ZG-25 临时列表的 N5 存储端口。

    实现 MemoryStorePort 子集：read_surface_generation + replace_surface_range。
    纯内存操作——generation 按 session_id 追踪替换代数（跨多次压缩递增）。
    """

    def __init__(self, history: list[LLMContextMessage], session_id: str) -> None:
        self._session_id = session_id

    async def read_surface_generation(self, session_id: str) -> int:
        """读取当前 surface replace_generation。"""
        return _session_generations.get(session_id, 0)

    async def replace_surface_range(
        self,
        session_id: str,
        range: Any,
        summary_node_id: str,
        summary_text: str,
        tx_id: Any,
    ) -> int:
        """surface 替换——递增 generation，返回新代数（纯内存，不写库）。"""
        _session_generations[session_id] = _session_generations.get(session_id, 0) + 1
        return _session_generations[session_id]


_balancer_singleton: Any | None = None


def get_surface_replacer(
    history: list[LLMContextMessage],
    session_id: str,
) -> Any:
    """创建 N5 SurfaceReplacer，注入 TempListMemoryStore。

    每次压缩创建新实例——绑定当前 selected_history。
    测试 patch 接缝口（design 2.6.1 mock 点）。
    """
    from src.A_memorix.core.runtime.services.compaction.surface import SurfaceReplacer  # noqa: TID251 — ZG-25 升级复用 N5 成果

    store = TempListMemoryStore(history=history, session_id=session_id)
    return SurfaceReplacer(memory_store=store)


def get_tool_pairing_balancer() -> Any:
    """获取 N5 ToolPairingBalancer 模块级单例。

    首次构造后复用，无依赖。
    测试 patch 接缝口（design 2.6.1 mock 点）。
    """
    global _balancer_singleton
    if _balancer_singleton is None:
        from src.A_memorix.core.runtime.services.compaction.tool_pairing import ToolPairingBalancer  # noqa: TID251 — ZG-25 升级复用 N5 成果

        _balancer_singleton = ToolPairingBalancer()
    return _balancer_singleton
