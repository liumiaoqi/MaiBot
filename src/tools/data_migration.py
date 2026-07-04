"""MaiBot 多智能体架构数据迁移工具。

覆盖：
  1. ChatSession agent_id 字段回填（v34→v35 迁移后，为旧记录填充默认值）
  2. PersonInfo.know_counts → AgentRelationship 表数据转换
  3. 自动备份数据库

幂等设计：所有操作均可重复执行，不会产生重复数据。
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import select

from src.common.database.database import _DB_FILE, get_db_session
from src.common.database.database_model import AgentRelationship, ChatSession, PersonInfo
from src.common.logger import get_logger
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.relationship.level import RelationshipLevel

logger = get_logger("data_migration")


class DataMigrationTool:
    """多智能体架构数据迁移工具。"""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or _DB_FILE
        self._default_agent_id = "silver_wolf"

    def run_all(self, *, skip_backup: bool = False) -> dict[str, object]:
        """执行全部数据迁移步骤。

        Returns:
            迁移结果摘要，包含每个步骤的状态和计数。
        """
        results: dict[str, object] = {
            "started_at": datetime.now().isoformat(),
            "steps": {},
        }

        try:
            self._resolve_default_agent()
        except Exception as e:
            logger.warning("无法解析默认智能体，使用 silver_wolf: %s", e)

        if not skip_backup:
            backup_path = self.backup_database()
            results["backup_path"] = str(backup_path)

        step1 = self.migrate_chat_session_agent_id()
        results["steps"]["chat_session_agent_id"] = step1

        step2 = self.migrate_person_know_counts_to_relationships()
        results["steps"]["person_know_counts_to_relationships"] = step2

        results["completed_at"] = datetime.now().isoformat()
        results["success"] = True

        logger.info("数据迁移完成: %s", results)
        return results

    def _resolve_default_agent(self) -> None:
        """从 AgentConfigRegistry 获取默认智能体ID。"""
        try:
            registry = AgentConfigRegistry()
            default = registry.get_default_agent()
            self._default_agent_id = default.agent_id
        except Exception:
            pass

    def backup_database(self) -> Path:
        """备份数据库文件。

        Returns:
            备份文件路径。
        """
        if not self._db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {self._db_path}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self._db_path.parent / f"MaiBot_backup_{timestamp}.db"

        shutil.copy2(self._db_path, backup_path)
        logger.info("数据库已备份到: %s", backup_path)
        return backup_path

    def migrate_chat_session_agent_id(self) -> dict[str, object]:
        """为缺少 agent_id 的 ChatSession 记录填充默认智能体ID。

        幂等：已设置 agent_id 的记录不会被修改。
        """
        updated = 0
        total = 0

        try:
            with get_db_session() as session:
                statement = select(ChatSession).where(
                    ChatSession.agent_id.is_(None)  # type: ignore[union-attr]
                )
                rows = session.exec(statement).all()
                total = len(rows)

                for row in rows:
                    row.agent_id = self._default_agent_id
                    session.add(row)
                    updated += 1

                session.commit()

        except Exception as e:
            logger.error("ChatSession agent_id 迁移失败: %s", e)
            return {"success": False, "error": str(e), "updated": updated, "total": total}

        logger.info("ChatSession agent_id 迁移完成: 更新 %d/%d 条记录", updated, total)
        return {"success": True, "updated": updated, "total": total}

    def migrate_person_know_counts_to_relationships(self) -> dict[str, object]:
        """将 PersonInfo.know_counts 转换为 AgentRelationship 记录。

        转换规则：
          - 每个 PersonInfo 记录生成一条 AgentRelationship
          - agent_id 使用默认智能体
          - score = min(know_counts * 10, 1000)
          - level 由 score 自动计算
          - interaction_count = know_counts
          - 幂等：已存在的 (agent_id, user_id) 组合不会重复插入
        """
        created = 0
        skipped = 0
        total = 0

        try:
            with get_db_session() as session:
                persons = session.exec(
                    select(PersonInfo).where(PersonInfo.know_counts > 0)
                ).all()
                total = len(persons)

                for person in persons:
                    user_id = person.person_id
                    agent_id = self._default_agent_id

                    existing = session.query(AgentRelationship).filter(
                        AgentRelationship.agent_id == agent_id,
                        AgentRelationship.user_id == user_id,
                    ).first()

                    if existing is not None:
                        skipped += 1
                        continue

                    score = min(person.know_counts * 10.0, 1000.0)
                    level = RelationshipLevel.from_score(score)

                    rel = AgentRelationship(
                        agent_id=agent_id,
                        user_id=user_id,
                        score=score,
                        level=level.value,
                        interaction_count=person.know_counts,
                        last_interaction_at=person.last_known_time,
                        created_at=person.first_known_time or datetime.now(),
                    )
                    session.add(rel)
                    created += 1

                session.commit()

        except Exception as e:
            logger.error("PersonInfo → AgentRelationship 迁移失败: %s", e)
            return {
                "success": False,
                "error": str(e),
                "created": created,
                "skipped": skipped,
                "total": total,
            }

        logger.info(
            "PersonInfo → AgentRelationship 迁移完成: 创建 %d, 跳过 %d, 总计 %d",
            created, skipped, total,
        )
        return {
            "success": True,
            "created": created,
            "skipped": skipped,
            "total": total,
        }


def run_migration(*, skip_backup: bool = False) -> dict[str, object]:
    """便捷入口：执行全部数据迁移。"""
    tool = DataMigrationTool()
    return tool.run_all(skip_backup=skip_backup)


if __name__ == "__main__":
    import json

    result = run_migration()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))