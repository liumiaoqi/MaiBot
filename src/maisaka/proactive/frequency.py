"""主动对话频率控制器。

控制主动对话频率：
- 每智能体每小时最大频率由 AgentConfig.proactive_config.max_frequency_per_hour 决定
- 5分钟内已主动发言2次时抑制后续请求
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FrequencyRecord:
    """频率记录。"""

    timestamps: list[float] = field(default_factory=list)


class ProactiveFrequencyController:
    """主动对话频率控制器。"""

    SUPPRESS_WINDOW_SECONDS = 300
    SUPPRESS_THRESHOLD = 2

    def __init__(self) -> None:
        self._records: dict[str, FrequencyRecord] = defaultdict(FrequencyRecord)

    def can_trigger(
        self,
        agent_id: str,
        max_frequency_per_hour: int = 1,
        cooldown_seconds: int = 300,
    ) -> bool:
        """检查智能体是否可以触发主动对话。

        Args:
            agent_id: 智能体ID。
            max_frequency_per_hour: 每小时最大频率。
            cooldown_seconds: 冷却时间（秒）。

        Returns:
            是否可以触发。
        """
        now = time.time()
        record = self._records[agent_id]

        if record.timestamps:
            last = record.timestamps[-1]
            if now - last < cooldown_seconds:
                logger.debug(
                    "主动对话冷却中: agent=%s 剩余=%.0fs",
                    agent_id,
                    cooldown_seconds - (now - last),
                )
                return False

        recent = [t for t in record.timestamps if now - t < 3600]
        if len(recent) >= max_frequency_per_hour:
            logger.debug(
                "主动对话频率超限: agent=%s 本小时%d次(上限%d)",
                agent_id,
                len(recent),
                max_frequency_per_hour,
            )
            return False

        window_recent = [t for t in record.timestamps if now - t < self.SUPPRESS_WINDOW_SECONDS]
        if len(window_recent) >= self.SUPPRESS_THRESHOLD:
            logger.debug(
                "5分钟内主动发言%d次，抑制: agent=%s",
                len(window_recent),
                agent_id,
            )
            return False

        return True

    def record_trigger(self, agent_id: str) -> None:
        """记录一次主动对话触发。"""
        now = time.time()
        self._records[agent_id].timestamps.append(now)
        self._cleanup(agent_id)

    def _cleanup(self, agent_id: str) -> None:
        """清理过期记录。"""
        cutoff = time.time() - 7200
        record = self._records[agent_id]
        record.timestamps = [t for t in record.timestamps if t > cutoff]

    def reset(self, agent_id: str | None = None) -> None:
        """重置频率记录。"""
        if agent_id is None:
            self._records.clear()
        else:
            self._records.pop(agent_id, None)