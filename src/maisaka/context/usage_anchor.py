"""usage 锚定简化版——ZG16-2 design 模块 C。

简化版（baseline + 增量），不实现 envelope 匹配/signed delta 完整版
（dsh 拍板决策 4——MaiBot 无 event sourcing，过重）。

baseline 内存存储随进程生命周期，不持久化。失效条件：
system_prompt 变更 / tools 变更 / 模型切换（指纹不匹配自动失效）/ 进程重启。
"""


from typing import TYPE_CHECKING, List, Optional, Tuple

import json

from src.maisaka.context.token_estimator import estimate_messages

if TYPE_CHECKING:
    from src.maisaka.context.messages import LLMContextMessage

_Fingerprint = Tuple[str, str, str]


class UsageBaseline:
    """单次 baseline 记录。"""

    __slots__ = ("prompt_tokens",)

    def __init__(self, prompt_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens


class UsageAnchor:
    """usage 锚定器（简化版）。

    内部存储 _store: dict[Fingerprint, UsageBaseline]，
    键 = (model, hash(system_prompt), hash(tools)) 指纹维度。
    """

    def __init__(self) -> None:
        self._store: dict[_Fingerprint, UsageBaseline] = {}

    @staticmethod
    def _fingerprint(
        model: str,
        system_prompt: str,
        tools: list,
    ) -> _Fingerprint:
        tools_repr = json.dumps(tools, sort_keys=True, default=str) if tools else "[]"
        return (model, hash(system_prompt), hash(tools_repr))

    def get_baseline(
        self,
        model: str,
        system_prompt: str,
        tools: list,
    ) -> Optional[int]:
        """按指纹读内存 baseline，无则返回 None（首次请求）。"""
        baseline = self._store.get(self._fingerprint(model, system_prompt, tools))
        return baseline.prompt_tokens if baseline is not None else None

    def update_baseline(
        self,
        model: str,
        system_prompt: str,
        tools: list,
        prompt_tokens: int,
        estimated: int,
    ) -> None:
        """仅当 prompt_tokens >= estimated 时才更新（防 provider 少报导致低估爆窗）。

        provider 无 usage（prompt_tokens=0/None）→ 不更新。
        """
        if not prompt_tokens or prompt_tokens <= 0:
            return
        if prompt_tokens < estimated:
            return
        self._store[self._fingerprint(model, system_prompt, tools)] = UsageBaseline(prompt_tokens)

    def anchored_estimate(
        self,
        model: str,
        system_prompt: str,
        tools: list,
        incremental_messages: List["LLMContextMessage"],
        *,
        enable_visual_message: bool = True,
    ) -> int:
        """锚定估算：baseline 存在 + 指纹匹配 → baseline + 增量；否则纯启发式。"""
        baseline = self.get_baseline(model, system_prompt, tools)
        incremental = estimate_messages(
            incremental_messages,
            enable_visual_message=enable_visual_message,
        )
        if baseline is not None:
            return baseline + incremental
        return incremental

    def reset(self) -> None:
        """清空所有 baseline（测试用）。"""
        self._store.clear()


usage_anchor = UsageAnchor()