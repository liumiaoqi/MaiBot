"""智能体体验写入器 — 将关键思考结果写入连接主义记忆。

规则门控：仅在 REPLY 或 INTENTIONAL 动作、且文本长度满足阈值时写入。
fire-and-forget 模式，不阻塞思考循环。
"""


import asyncio
import time
from typing import Any

from src.common.logger import get_logger
from src.core.protocols import MemoryServicePort
from src.core.types import ObserveRequest, SilenceReason, ThinkAction, ThinkResult

logger = get_logger("experience_writer")

_REPLY_MIN_CHARS = 10
_INTENTIONAL_MIN_SUMMARY_CHARS = 20


class ExperienceWriter:
    def __init__(self, memory_port: MemoryServicePort, emotion_manager: Any = None) -> None:
        """体验写入器。

        Args:
            memory_port: 记忆服务端口（必选——agent 初始化时必须注入，禁止 None）
            emotion_manager: 情感管理器（可选，用于情感极性推导）
        """
        if memory_port is None:
            raise ValueError("ExperienceWriter: memory_port 注入失败——agent 初始化时必须注入已初始化的记忆端口")
        self._memory_port = memory_port
        self._emotion_manager = emotion_manager

    @staticmethod
    def should_write(result: ThinkResult) -> bool:
        if result.action == ThinkAction.REPLY and len(result.text or "") >= _REPLY_MIN_CHARS:
            return True
        if (
            result.action == ThinkAction.SILENT
            and result.silence_reason == SilenceReason.INTENTIONAL
        ):
            summary = (result.thought_summary or result.text or "")
            if len(summary) >= _INTENTIONAL_MIN_SUMMARY_CHARS:
                return True
        return False

    def write_experience(
        self,
        result: ThinkResult,
        session_id: str,
        agent_id: str,
        emotion_state: Any = None,
    ) -> None:
        summary = self._build_summary(result, emotion_state)
        valence = self._emotion_to_valence(result)
        asyncio.create_task(
            self._write_with_error_handling(
                summary=summary,
                valence=valence,
                agent_id=agent_id,
                session_id=session_id,
                action=result.action.value,
            )
        )

    async def _write_with_error_handling(
        self,
        *,
        summary: str,
        valence: str,
        agent_id: str,
        session_id: str,
        action: str,
    ) -> None:
        try:
            request = ObserveRequest(
                text=summary,
                valence=valence,
                source_id=f"experience:{agent_id}:{int(time.time())}",
                session_id=session_id,
                agent_id=agent_id,
                tags=("agent_experience", action),
            )
            await self._memory_port.observe_experience(request)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "体验写入失败", exception=exc)
            logger.warning(
                "体验写入失败: agent=%s action=%s", agent_id, action, exc_info=True,
            )

    @staticmethod
    def _build_summary(result: ThinkResult, emotion_state: Any = None) -> str:
        parts: list[str] = []
        if result.action == ThinkAction.REPLY and result.text:
            parts.append(f"回复: {result.text.strip()[:200]}")
        elif result.silence_reason == SilenceReason.INTENTIONAL:
            summary = (result.thought_summary or result.text or "").strip()
            if summary:
                parts.append(f"感知/意图: {summary[:200]}")
        emotion = getattr(emotion_state, "dominant_emotion", "") if emotion_state else ""
        if emotion:
            parts.append(f"情绪: {emotion}")
        return "；".join(parts) if parts else "体验记录"

    def _emotion_to_valence(self, result: ThinkResult) -> str:
        if self._emotion_manager is not None:
            try:
                state = self._emotion_manager.get_current_state()
                if state and hasattr(state, "dominant_emotion"):
                    emotion = state.dominant_emotion
                    positive = {"joy", "happy", "excited", "grateful", "love", "satisfied", "calm"}
                    negative = {"anger", "sad", "fear", "anxious", "frustrated", "jealous", "disgust"}
                    if emotion in positive:
                        return "positive"
                    if emotion in negative:
                        return "negative"
                    return "neutral"
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "操作异常 in experience_writer.py", exception=exc)
                logger.warning("操作异常 in experience_writer.py", exc_info=True)
        positive = {"joy", "happy", "excited", "grateful", "love", "satisfied", "calm"}
        negative = {"anger", "sad", "fear", "anxious", "frustrated", "jealous", "disgust"}
        if result.emotion_type in positive:
            return "positive"
        if result.emotion_type in negative:
            return "negative"
        return "neutral"
