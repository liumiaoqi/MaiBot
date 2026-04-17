import pytest

from src.A_memorix.core.utils.summary_importer import SummaryImporter
from src.config.model_configs import TaskConfig
from src.services import llm_service as llm_api


def _fake_available_models() -> dict[str, TaskConfig]:
    return {
        "replyer": TaskConfig(
            model_list=["test-model"],
            max_tokens=128,
            temperature=0.7,
            selection_strategy="priority",
        )
    }


def test_resolve_summary_model_config_uses_auto_list_when_summarization_missing(monkeypatch):
    monkeypatch.setattr(llm_api, "get_available_models", _fake_available_models)

    importer = SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config={},
    )

    resolved = importer._resolve_summary_model_config()

    assert resolved is not None
    assert resolved.model_list == ["test-model"]


def test_resolve_summary_model_config_rejects_legacy_string_selector(monkeypatch):
    monkeypatch.setattr(llm_api, "get_available_models", _fake_available_models)

    importer = SummaryImporter(
        vector_store=None,
        graph_store=None,
        metadata_store=None,
        embedding_manager=None,
        plugin_config={"summarization": {"model_name": "auto"}},
    )

    with pytest.raises(ValueError, match="List\\[str\\]"):
        importer._resolve_summary_model_config()
