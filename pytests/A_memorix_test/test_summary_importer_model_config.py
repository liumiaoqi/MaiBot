from types import SimpleNamespace

import pytest

from src.A_memorix.core.utils.summary_importer import (
    SummaryImporter,
    _message_timestamp,
    _normalize_entity_items,
    _normalize_relation_items,
)

from src.core.model_config_port_registry import (
    register_model_config_port,
    reset_model_config_port,
)
from src.llm_models.model_requirement import ResolvedModel


class _FakeModelConfigPort:
    """假 ModelConfigPort——resolve_by_capability 返回指定模型（ZG-12 主路径）。"""

    def __init__(self, model_name: str = "memory-model") -> None:
        self._model_name = model_name

    def resolve_by_capability(self, capabilities, *, agent_id="", options=None):
        return ResolvedModel(
            category="llm",
            name=self._model_name,
            model_identifier=self._model_name,
            api_provider="fake-provider",
            capabilities=frozenset(capabilities),
        )

    def get_model_config(self):
        return SimpleNamespace(models_dict={self._model_name: SimpleNamespace(name=self._model_name)})


@pytest.fixture(autouse=True)
def _reset_model_config_port_around_test():
    yield
    reset_model_config_port()


def _make_importer(plugin_config=None, llm_api=None):
    return SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config=plugin_config or {},
        llm_api=llm_api or SimpleNamespace(get_available_models=lambda: {}),
    )


def test_resolve_summary_model_config_uses_auto_list_when_summarization_missing():
    register_model_config_port(_FakeModelConfigPort("memory-model"))
    importer = _make_importer()

    resolved = importer._resolve_summary_model_config()

    assert resolved is not None
    assert resolved[1].model_list == ["memory-model"]


def test_resolve_summary_model_config_auto_falls_back_to_utils_then_planner():
    register_model_config_port(_FakeModelConfigPort("utils-model"))
    importer = _make_importer()
    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["utils-model"]

    register_model_config_port(_FakeModelConfigPort("planner-model"))
    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["planner-model"]


def test_resolve_summary_model_config_auto_falls_back_to_replyer():
    register_model_config_port(_FakeModelConfigPort("replyer-model"))
    importer = _make_importer()

    resolved = importer._resolve_summary_model_config()
    assert resolved is not None
    assert resolved[1].model_list == ["replyer-model"]


def test_resolve_summary_model_config_tolerates_legacy_string_selector():
    register_model_config_port(_FakeModelConfigPort("memory-model"))
    importer = _make_importer(plugin_config={"summarization": {"model_name": "auto"}})

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
