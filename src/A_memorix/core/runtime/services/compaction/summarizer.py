"""ZG-N5 压缩升级——摘要生成器。

对标 dsh index.ts:236 summarize 子类化钩子 + summarizer.ts。
复用既有 LLM 调用通道生成摘要，新增收敛校验（framed_tokens < shadowed_tokens）。
不泄露私有推理——摘要内容仅来自模型可见会话内容。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from .config import ResolvedConfig
from .ports import LlmPort, TokenMeterPort
from .types import CompactionId, ModelRoute, SummaryNode, SummaryNotSmallerError


@dataclass(frozen=True)
class SummarizationInput:
    """摘要生成输入。"""

    session_id: str
    source_events: Sequence[Any]
    shadowed_token_count: int
    shadowed_seqs: tuple[int, ...]


@dataclass(frozen=True)
class SummaryResult:
    """摘要生成结果。"""

    summary: str
    framed_token_count: int
    summary_node: SummaryNode


class Summarizer:
    """摘要生成器——复用既有 LLM 通道 + 收敛校验。"""

    def __init__(
        self,
        llm_port: LlmPort,
        token_meter: TokenMeterPort,
        config: ResolvedConfig,
    ) -> None:
        self._llm_port = llm_port
        self._token_meter = token_meter
        self._config = config

    async def summarize(
        self,
        input: SummarizationInput,
        tx_id: CompactionId,
        model_route: ModelRoute,
        prompt_messages: Sequence[Any],
    ) -> SummaryResult:
        """生成摘要——复用既有 LLM 通道，校验摘要收敛。

        Args:
            input: 摘要输入（源事件 + shadowed token 计数）
            tx_id: 事务身份
            model_route: 模型路由
            prompt_messages: 构建好的 prompt 消息序列

        Returns:
            摘要结果

        Raises:
            SummaryNotSmallerError: framed_tokens >= shadowed_tokens（不收敛）
        """
        # 调用 LLM 生成摘要
        summary_text = await self._llm_port.summarize(
            prompt_messages=prompt_messages,
            model_route=model_route,
        )

        # 计量摘要 token
        framed_token_count = self._token_meter.count_tokens(summary_text)

        # 收敛校验：framed_tokens < shadowed_tokens
        if framed_token_count >= input.shadowed_token_count:
            raise SummaryNotSmallerError(
                f"摘要不收敛: framed_tokens ({framed_token_count}) >= "
                f"shadowed_tokens ({input.shadowed_token_count})"
            )

        # 构建摘要节点
        summary_node = SummaryNode(
            node_id=f"summary_{tx_id.value}",
            summary=summary_text,
            tx_id=tx_id,
            model_route=model_route,
            generated_at=datetime.now(),
        )

        return SummaryResult(
            summary=summary_text,
            framed_token_count=framed_token_count,
            summary_node=summary_node,
        )