from types import SimpleNamespace

import pytest

from src.A_memorix.core.utils.person_profile_service import PersonProfileService


class FakeMetadataStore:
    def __init__(self) -> None:
        self.snapshots: list[dict] = []

    @staticmethod
    def get_latest_person_profile_snapshot(person_id: str):
        del person_id
        return None

    @staticmethod
    def get_relations(**kwargs):
        del kwargs
        return []

    @staticmethod
    def get_paragraphs_by_source(source: str):
        if source == "person_fact:person-1":
            return [
                {
                    "hash": "person-fact-1",
                    "content": "测试用户喜欢猫。",
                    "source": source,
                    "metadata": {"source_type": "person_fact"},
                    "created_at": 2.0,
                    "updated_at": 2.0,
                }
            ]
        return []

    @staticmethod
    def get_paragraph(hash_value: str):
        if hash_value == "chat-summary-1":
            return {
                "hash": hash_value,
                "content": "机器人建议测试用户以后叫星灯。",
                "source": "chat_summary:session-1",
                "metadata": {"source_type": "chat_summary"},
                "word_count": 1,
            }
        if hash_value == "person-fact-1":
            return {
                "hash": hash_value,
                "content": "测试用户喜欢猫。",
                "source": "person_fact:person-1",
                "metadata": {"source_type": "person_fact"},
                "word_count": 1,
            }
        return None

    @staticmethod
    def get_paragraph_stale_relation_marks_batch(paragraph_hashes):
        del paragraph_hashes
        return {}

    @staticmethod
    def get_relation_status_batch(relation_hashes):
        del relation_hashes
        return {}

    @staticmethod
    def get_person_profile_override(person_id: str):
        del person_id
        return None

    def upsert_person_profile_snapshot(self, **kwargs):
        self.snapshots.append(kwargs)
        return {
            "person_id": kwargs["person_id"],
            "profile_text": kwargs["profile_text"],
            "aliases": kwargs["aliases"],
            "relation_edges": kwargs["relation_edges"],
            "vector_evidence": kwargs["vector_evidence"],
            "evidence_ids": kwargs["evidence_ids"],
            "updated_at": 1.0,
            "expires_at": kwargs["expires_at"],
            "source_note": kwargs["source_note"],
        }


class FakeRetriever:
    async def retrieve(self, query: str, top_k: int):
        del query, top_k
        return [
            SimpleNamespace(
                hash_value="chat-summary-1",
                result_type="paragraph",
                score=0.95,
                content="机器人建议测试用户以后叫星灯。",
                metadata={"source_type": "chat_summary"},
            )
        ]


@pytest.mark.asyncio
async def test_person_profile_keeps_chat_summary_as_recent_interaction_not_stable_profile():
    metadata_store = FakeMetadataStore()
    service = PersonProfileService(metadata_store=metadata_store, retriever=FakeRetriever())
    service.get_person_aliases = lambda person_id: (["测试用户"], "测试用户", [])

    payload = await service.query_person_profile(person_id="person-1", top_k=6, force_refresh=True)

    assert payload["success"] is True
    profile_text = payload["profile_text"]
    stable_section = profile_text.split("近期相关互动:", 1)[0]
    assert "测试用户喜欢猫" in stable_section
    assert "星灯" not in stable_section
    assert "近期相关互动:" in profile_text
    assert "星灯" in profile_text
