"""子智能体类型注册表。

注册3类子智能体（dream/compaction/checkpoint_writer），
拒绝 explore/peer 等未授权类型。
"""

from __future__ import annotations

from typing import Any, Optional, Type

from .models import SubAgentType


_ALLOWED_TYPES: set[SubAgentType] = {
    SubAgentType.DREAM,
    SubAgentType.COMPACTION,
    SubAgentType.CHECKPOINT_WRITER,
}

_DENIED_TYPE_NAMES: set[str] = {"explore", "peer"}


class SubAgentRegistry:
    """子智能体类型注册表。

    提供 register / get / list_registered 方法。
    只允许 dream / compaction / checkpoint_writer 三类注册。
    """

    def __init__(self) -> None:
        self._registry: dict[SubAgentType, tuple[Type[Any], Type[Any]]] = {}

    def register(
        self,
        subagent_type: SubAgentType,
        agent_class: Type[Any],
        config_class: Type[Any],
    ) -> None:
        """注册子智能体类型。

        Args:
            subagent_type: 子智能体类型枚举。
            agent_class: 子智能体执行类。
            config_class: 子智能体配置类。

        Raises:
            ValueError: 尝试注册不允许的类型。
        """
        type_name = subagent_type.value if isinstance(subagent_type, SubAgentType) else str(subagent_type)
        if type_name in _DENIED_TYPE_NAMES:
            raise ValueError(
                f"不允许注册子智能体类型 '{type_name}'，"
                f"允许的类型: {[t.value for t in _ALLOWED_TYPES]}"
            )
        if subagent_type not in _ALLOWED_TYPES:
            raise ValueError(
                f"不允许注册子智能体类型 '{type_name}'，"
                f"允许的类型: {[t.value for t in _ALLOWED_TYPES]}"
            )
        self._registry[subagent_type] = (agent_class, config_class)

    def get(self, subagent_type: SubAgentType) -> Optional[tuple[Type[Any], Type[Any]]]:
        """获取已注册的子智能体类型。

        Args:
            subagent_type: 子智能体类型枚举。

        Returns:
            (agent_class, config_class) 元组，未注册则返回 None。
        """
        return self._registry.get(subagent_type)

    def list_registered(self) -> list[SubAgentType]:
        """列出所有已注册的子智能体类型。"""
        return list(self._registry.keys())

    def is_registered(self, subagent_type: SubAgentType) -> bool:
        """检查子智能体类型是否已注册。"""
        return subagent_type in self._registry

    def unregister(self, subagent_type: SubAgentType) -> None:
        """取消注册子智能体类型。"""
        self._registry.pop(subagent_type, None)