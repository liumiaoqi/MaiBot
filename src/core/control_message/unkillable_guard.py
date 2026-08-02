"""ZG-8 控制消息优先级 — UNKILLABLE 保护引擎。

对标 Linux `SIGNAL_UNKILLABLE` + `sig_task_ignored`：
- UNKILLABLE 声明实体不被普通致命控制消息淘汰（软保护，ADR-05）
- force 通道可清除标志强制终止（对标 force_sig_info_to_task 清除 SIGNAL_UNKILLABLE）
- 非致命控制消息不受保护，正常投递
- 声明方限定 Orchestrator（约定受信；配置声明的实体 declared_by="config"）
"""

import time
from typing import Optional


from src.core.control_message.types import (

    ControlMessageKind,
    ProtectionAction,
    ProtectionResult,
    UnkillableDeclaration,
)


from src.common.logger import get_logger

logger = get_logger("unkillable_guard")

class UnkillableGuard:
    """UNKILLABLE 保护引擎 — 声明 / 保护判定 / force 清除。"""

    def __init__(self, app_config_port: object = None) -> None:
        """初始化保护引擎。

        Args:
            app_config_port: AppConfigPort（读取 unkillable_entities 配置清单，可选）。
                配置清单实体注册为 is_active=True 声明（declared_by="config"），
                运行时 declare_unkillable 可覆盖。
        """
        self._declarations: dict[str, UnkillableDeclaration] = {}
        if app_config_port is not None:
            try:
                entities = app_config_port.get_control_message_unkillable_entities()
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("UNKILLABLE 实体清单配置读取失败，使用空清单", exc_info=True)
                entities = []
            now = time.monotonic()
            for entity_id in entities or ():
                self._declarations[str(entity_id)] = UnkillableDeclaration(
                    entity_id=str(entity_id),
                    entity_type="agent",
                    declared_by="config",
                    is_active=True,
                    declared_time=now,
                )

    def declare_unkillable(self, entity_id: str, entity_type: str = "agent") -> None:
        """声明实体为 UNKILLABLE（spec §5.6.1 规则 1）。

        只允许 Orchestrator 调用（约定受信，spec §4.3 安全性 3）；重复声明覆盖。
        """
        self._declarations[entity_id] = UnkillableDeclaration(
            entity_id=entity_id,
            entity_type=entity_type,
            declared_by="orchestrator",
            is_active=True,
            declared_time=time.monotonic(),
        )

    def check_protection(
        self,
        entity_id: str,
        kind: ControlMessageKind,
        force: bool,
    ) -> ProtectionResult:
        """UNKILLABLE 保护判定（对标 sig_task_ignored）。

        - UNKILLABLE + 致命 + 非 force → REJECTED（拒绝淘汰，spec §5.6.1 规则 2）
        - UNKILLABLE + 致命 + force → CLEARED（清除标志允许淘汰，spec §5.6.1 规则 3）
        - 非致命或非 UNKILLABLE → PROCEED（spec §5.6.1 规则 4）

        Args:
            entity_id: 目标实体标识
            kind: 控制消息类别
            force: 是否 force 通道投递

        Returns:
            保护判定结果
        """
        decl = self._declarations.get(entity_id)
        if decl is None or not decl.is_active:
            return ProtectionResult(action=ProtectionAction.PROCEED)

        if kind == ControlMessageKind.SESSION_DESTROY:
            if force:
                decl.is_active = False
                return ProtectionResult(action=ProtectionAction.CLEARED)
            return ProtectionResult(
                action=ProtectionAction.REJECTED, reason="CONTROL_UNKILLABLE_PROTECTED"
            )

        return ProtectionResult(action=ProtectionAction.PROCEED)

    def clear_unkillable(self, entity_id: str) -> None:
        """清除 UNKILLABLE 标志（force 通道使用）。

        声明保留（is_active=False，审计记录不销毁，spec §6.5）。
        """
        decl = self._declarations.get(entity_id)
        if decl is not None:
            decl.is_active = False

    def list_unkillable_entities(self) -> list[UnkillableDeclaration]:
        """查询全部 UNKILLABLE 声明（含已清除的审计记录，spec §5.6.1 规则 5 内省）。"""
        return list(self._declarations.values())

    def is_protected(self, entity_id: str) -> bool:
        """查询实体是否处于保护中（is_active）。"""
        decl = self._declarations.get(entity_id)
        return decl is not None and decl.is_active

    def _get_declaration(self, entity_id: str) -> Optional[UnkillableDeclaration]:
        return self._declarations.get(entity_id)
