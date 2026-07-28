"""PersonInfoPortAdapter — 将 Person 类包装为 PersonInfoPort Protocol。"""


from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.core.types import PersonDetailSnapshot, PersonInfoResult

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

    def get_person_id(self, platform: str, user_id: str) -> str:
        from src.person_info.person_info import get_person_id as _get_person_id
        return _get_person_id(platform, user_id)

    def get_person_id_by_name(self, person_name: str) -> str:
        from src.person_info.person_info import get_person_id_by_person_name
        return get_person_id_by_person_name(person_name)

    def get_person_attribute(self, person_id: str, field_name: str) -> Any:
        from src.person_info.person_info import Person
        person = Person(person_id=person_id)
        return getattr(person, field_name, None)

    def get_person_detail(self, person_id: str) -> Optional[PersonDetailSnapshot]:
        from src.core.types import PersonDetailSnapshot
        from src.person_info.person_info import Person
        person = Person(person_id=person_id)
        return PersonDetailSnapshot(
            is_known=bool(person.is_known),
            person_id=str(person.person_id or ""),
            person_name=str(person.person_name or ""),
            nickname=str(person.nickname or ""),
        )

    async def store_person_memory(
        self,
        person_name: str,
        fact: str,
        session_id: str,
        *,
        person_id: str = "",
        evidence_source: str = "user_supported",
        evidence_message_ids: list[str] | None = None,
    ) -> None:
        from src.person_info.person_info import store_person_memory_from_answer
        await store_person_memory_from_answer(
            person_name, fact, session_id,
            person_id=person_id,
            evidence_source=evidence_source,
            evidence_message_ids=evidence_message_ids or [],
        )
