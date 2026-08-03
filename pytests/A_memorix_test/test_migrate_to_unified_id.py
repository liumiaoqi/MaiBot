"""MF-P1-004 验收：存量 id 迁移脚本。

对应 tasks.md 9.1：迁移后概念 id 与实体 id 一致（同名同 id）；
--rollback 恢复原始数据；断点续传。
"""

import json
import sqlite3

from pathlib import Path

from src.A_memorix.core.concept_graph.concept_graph_store import ConceptGraphStore
from src.A_memorix.core.concept_graph.unified_id_generator import UnifiedIdGenerator


def _setup_data_dir(tmp_path: Path) -> Path:
    """构造模拟数据：concepts.json + metadata.db + traces.db。"""
    data_dir = tmp_path / "data"
    (data_dir / "connectionist").mkdir(parents=True)
    (data_dir / "metadata").mkdir(parents=True)

    # concepts.json
    (data_dir / "connectionist" / "concepts.json").write_text(
        json.dumps({
            "concept_types": {"生日": "event", "契约": "abstract"},
            "synonyms": {},
            "frequencies": {},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # metadata.db（entities + relations）
    conn = sqlite3.connect(data_dir / "metadata" / "metadata.db")
    conn.execute("CREATE TABLE entities (name TEXT PRIMARY KEY, hash TEXT, is_deleted INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE relations (subject TEXT, predicate TEXT, object TEXT, confidence REAL, is_inactive INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO entities (name, hash, is_deleted) VALUES ('琪亚娜', 'hash-kiana', 0)")
    conn.execute(
        "INSERT INTO relations (subject, predicate, object, confidence, is_inactive) VALUES ('琪亚娜', '庆祝', '生日', 1.0, 0)"
    )
    conn.commit()
    conn.close()

    # traces.db
    conn = sqlite3.connect(data_dir / "connectionist" / "traces.db")
    conn.execute(
        "CREATE TABLE traces (source TEXT, target TEXT, weight REAL, valence REAL, agent_id TEXT)"
    )
    conn.execute("INSERT INTO traces VALUES ('琪亚娜', '生日', 0.8, 0.5, 'silver_wolf')")
    conn.commit()
    conn.close()
    return data_dir


def _load_script_main():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "migrate_to_unified_id",
        Path(__file__).resolve().parent.parent.parent / "scripts" / "migrate_to_unified_id.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.main


def _run_script(data_dir: Path, *extra: str) -> None:
    import sys

    main = _load_script_main()
    old_argv = sys.argv
    sys.argv = ["migrate_to_unified_id.py", "--data-dir", str(data_dir), *extra]
    try:
        assert main() == 0
    finally:
        sys.argv = old_argv


def test_migration_creates_unified_ids(tmp_path: Path) -> None:
    """迁移后概念与实体同名同 id（MF-P1-004）。"""
    data_dir = _setup_data_dir(tmp_path)
    _run_script(data_dir)

    store = ConceptGraphStore(data_dir)
    store.init_schema()
    try:
        gen = UnifiedIdGenerator()
        # 同名对象（琪亚娜 实体 + 生日 概念）id 与生成器一致
        kiana = store.get_node_by_name("琪亚娜")
        birthday = store.get_node_by_name("生日")
        assert kiana is not None and birthday is not None
        assert kiana.id == gen.generate("琪亚娜")
        assert birthday.id == gen.generate("生日")
        assert kiana.type.value == "entity"
        assert birthday.type.value == "concept"

        # 关系边迁移（琪亚娜 → 生日）
        edges = store.get_relation_edges(kiana.id)
        assert len(edges) == 1
        assert edges[0].relation_type == "庆祝"

        # Trace 迁移（perspective=agent:silver_wolf）
        traces = store.get_trace_edges(kiana.id)
        assert len(traces) == 1
        assert traces[0].perspective == "agent:silver_wolf"
    finally:
        store.close()


def test_rollback_restores_original_data(tmp_path: Path) -> None:
    """--rollback 恢复原始数据。"""
    data_dir = _setup_data_dir(tmp_path)
    original_concepts = (data_dir / "connectionist" / "concepts.json").read_text(encoding="utf-8")

    _run_script(data_dir)
    assert (data_dir / "concept_graph.db").exists()

    _run_script(data_dir, "--rollback")
    # concept_graph.db 被备份覆盖删除 → 不存在
    assert not (data_dir / "concept_graph.db").exists()
    # 原数据未动
    assert (data_dir / "connectionist" / "concepts.json").read_text(encoding="utf-8") == original_concepts


def test_resume_from_manifest(tmp_path: Path) -> None:
    """断点续传：manifest 记录已迁移概念，重跑跳过。"""
    data_dir = _setup_data_dir(tmp_path)
    _run_script(data_dir)

    # 手动制造 manifest（模拟中断后残留）
    (data_dir / "unified_id_migration.json").write_text(
        json.dumps({"migrated_concepts": ["生日"]}), encoding="utf-8",
    )
    # 重跑：生日跳过，琪亚娜补迁
    _run_script(data_dir)
    store = ConceptGraphStore(data_dir)
    store.init_schema()
    try:
        assert store.get_node_by_name("生日") is not None
        assert store.get_node_by_name("琪亚娜") is not None
    finally:
        store.close()
    assert not (data_dir / "unified_id_migration.json").exists()  # 完成后丢弃


def test_dry_run_no_write(tmp_path: Path) -> None:
    """--dry-run 只统计不写入。"""
    data_dir = _setup_data_dir(tmp_path)
    _run_script(data_dir, "--dry-run")
    assert not (data_dir / "concept_graph.db").exists()
