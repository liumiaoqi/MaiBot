"""PersonInfoPortAdapter — 将 Person 类包装为 PersonInfoPort Protocol。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.types import PersonInfoResult

from src.common.logger import get_logger

logger = get_logger("core.adapters.person_info_port")


class PersonInfoPortAdapter:
    """鸭子类型适配器，包裹 Person 类实现 PersonInfoPort Protocol。"""

    def get_person_info(self, platform: str, user_id: str) -> Optional[PersonInfoResult]:
        from src.core.types import PersonInfoResult
        from src.person_info.person_info import Person

        try:
            person = Person(platform=platform, user_id=user_id)
            return PersonInfoResult(
                is_known=person.is_known,
                person_id=person.person_id,
                person_name=person.person_name,
            )
        except Exception as exc:
            logger.debug(f"人物信息查询失败: platform={platform}, user_id={user_id}, error={exc}")
            return None
