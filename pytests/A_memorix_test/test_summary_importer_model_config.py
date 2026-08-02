from types import SimpleNamespace

from src.A_memorix.core.utils.summary_importer import (
    SummaryImporter,
    _message_timestamp,
    _normalize_entity_items,
    _normalize_relation_items,
)
from src.config.model_configs import TaskConfig


def _fake_llm_api(models: dict[str, TaskConfig]):
    return SimpleNamespace(get_available_models=lambda: models)


def test_resolve_summary_model_config_uses_auto_list_when_summarization_missing():
    importer = SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config={},
        llm_api=_fake_llm_api(
            {
                "memory": TaskConfig(
                    model_list=["memory-model"],
                    max_tokens=512,
                    temperature=0.4,
                    selection_strategy="random",
                ),
                "utils": TaskConfig(
                    model_list=["utils-model"],
                    max_tokens=256,
                    temperature=0.5,
                    selection_strategy="random",
                ),
                "replyer": TaskConfig(
                    model_list=["replyer-model"],
                    max_tokens=128,
                    temperature=0.7,
                    selection_strategy="random",
                ),
            }
        ),
    )

    resolved = importer._resolve_summary_model_config()

    assert resolved is not None
    assert resolved[1].model_list == ["memory-model"]


def test_resolve_summary_model_config_auto_falls_back_to_utils_then_planner():
    importer = SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config={},
        llm_api=_fake_llm_api(
            {
            "utils": TaskConfig(model_list=["utils-model"]),
            "planner": TaskConfig(model_list=["planner-model"]),
            "replyer": TaskConfig(model_list=["replyer-model"]),
            }
        ),
    )
    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["utils-model"]

    importer._llm_api = _fake_llm_api(
        {
            "planner": TaskConfig(model_list=["planner-model"]),
            "replyer": TaskConfig(model_list=["replyer-model"]),
        }
    )
    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["planner-model"]


def test_resolve_summary_model_config_auto_falls_back_to_replyer():
    importer = SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config={},
        llm_api=_fake_llm_api(
            {
            "replyer": TaskConfig(model_list=["replyer-model"]),
            "embedding": TaskConfig(model_list=["embedding-model"]),
            }
        ),
    )

    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["replyer-model"]


def test_resolve_summary_model_config_tolerates_legacy_string_selector():
    importer = SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config={"summarization": {"model_name": "auto"}},
        llm_api=_fake_llm_api(
            {
                "memory": TaskConfig(
                    model_list=["memory-model"],
                    max_tokens=512,
                    temperature=0.4,
                    selection_strategy="random",
                ),
            }
        ),
    )

    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["memory-model"]


def test_summary_importer_normalizes_llm_entities_and_relations():
    assert _normalize_entity_items(["Alice", {"name": "地图"}, ["bad"], "Alice"]) == ["Alice", "地图"]
    assert _normalize_entity_items("Alice") == []
    assert _normalize_relation_items(
        [
            {"subject": "Alice", "predicate": "持有", "object": "地图"},
            {"subject": "Alice", "predicate": "", "object": "地图"},
            ["bad"],
        ]
    ) == [{"subject": "Alice", "predicate": "持有", "object": "地图"}]


def test_summary_importer_message_timestamp_accepts_time_fallback():
    class Message:
        time = 123.5

    assert _message_timestamp(Message()) == 123.5
