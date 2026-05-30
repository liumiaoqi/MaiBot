from pathlib import Path

from src.A_memorix.core.storage.metadata_store import MetadataStore


def test_get_all_sources_ignores_soft_deleted_paragraphs(tmp_path: Path) -> None:
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        live_hash = store.add_paragraph("Alice 喜欢地图", source="live-source")
        deleted_hash = store.add_paragraph("Bob 喜欢咖啡", source="deleted-source")

        assert live_hash
        store.mark_as_deleted([deleted_hash], "paragraph")

        sources = store.get_all_sources()
    finally:
        store.close()

    assert [item["source"] for item in sources] == ["live-source"]
    assert sources[0]["count"] == 1
