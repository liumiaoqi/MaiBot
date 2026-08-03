"""存量数据迁移到统一 id（MF-P1-004，R08 修正）。

读取 ConceptIndex（concepts.json）+ EntityStore（metadata.db entities 表）
+ TraceStore（traces.db），用 UnifiedIdGenerator 生成统一 id（同名同 id），
写入 ConceptGraphStore（concept_nodes / relation_edges / trace_edges）。

用法：
    python scripts/migrate_to_unified_id.py --data-dir /path/to/data
    python scripts/migrate_to_unified_id.py --data-dir /path/to/data --rollback

特性：
- --rollback：迁移前备份原数据文件，rollback 从备份恢复
- 断点续传：manifest 记录已迁移概念，中断后从断点继续
- 迁移完成后丢弃临时 manifest
"""

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.A_memorix.core.concept_graph.concept_graph_store import ConceptGraphStore  # noqa: E402
from src.A_memorix.core.concept_graph.models import (  # noqa: E402
    EdgeSource,
    NodeCategory,
    RelationEdge,
    TraceEdge,
)
from src.A_memorix.core.concept_graph.unified_id_generator import UnifiedIdGenerator  # noqa: E402

_MANIFEST = "unified_id_migration.json"
_BACKUP_DIR = "unified_id_backup"


def _load_concepts(data_dir: Path) -> dict[str, str]:
    """concepts.json → {概念名: 类型}。"""
    path = data_dir / "connectionist" / "concepts.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return dict(data.get("concept_types", {}) or {})


def _load_entities(metadata_db: Path) -> dict[str, str]:
    """metadata.db entities 表 → {实体名: hash}。"""
    if not metadata_db.exists():
        return {}
    conn = sqlite3.connect(metadata_db)
    try:
        rows = conn.execute(
            "SELECT name, hash FROM entities WHERE is_deleted = 0"
        ).fetchall()
        return {str(name): str(hash_value) for name, hash_value in rows if name}
    finally:
        conn.close()


def _load_relations(metadata_db: Path) -> list[tuple[str, str, str, float]]:
    """metadata.db relations 表 → [(subject, predicate, object, weight)]。"""
    if not metadata_db.exists():
        return []
    conn = sqlite3.connect(metadata_db)
    try:
        rows = conn.execute(
            "SELECT subject, predicate, object, confidence FROM relations "
            "WHERE is_inactive = 0"
        ).fetchall()
        return [(str(s), str(p), str(o), float(c or 1.0)) for s, p, o, c in rows]
    finally:
        conn.close()


def _load_traces(traces_db: Path) -> list[tuple[str, str, float, float, str]]:
    """traces.db → [(source, target, weight, valence, perspective)]。"""
    if not traces_db.exists():
        return []
    conn = sqlite3.connect(traces_db)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "traces" not in tables:
            return []
        rows = conn.execute("SELECT * FROM traces").fetchall()
        columns = [desc[0] for desc in conn.execute("SELECT * FROM traces LIMIT 1").description]
        col = {name: idx for idx, name in enumerate(columns)}

        def _get(row, name: str, default=None):
            idx = col.get(name)
            return row[idx] if idx is not None and row[idx] is not None else default

        traces = []
        for row in rows:
            source = str(_get(row, "source") or _get(row, "source_concept") or "")
            target = str(_get(row, "target") or _get(row, "target_concept") or "")
            if not source or not target:
                continue
            weight = float(_get(row, "weight", 0.5) or 0.5)
            valence = float(_get(row, "valence", 0.0) or 0.0)
            agent_id = str(_get(row, "agent_id", "") or "")
            traces.append((source, target, weight, valence, agent_id))
        return traces
    finally:
        conn.close()


def _load_manifest(data_dir: Path) -> set[str]:
    path = data_dir / _MANIFEST
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("migrated_concepts", []) or [])
    except Exception:
        return set()


def _save_manifest(data_dir: Path, migrated: set[str]) -> None:
    (data_dir / _MANIFEST).write_text(
        json.dumps({"migrated_concepts": sorted(migrated)}, ensure_ascii=False),
        encoding="utf-8",
    )


def _backup(data_dir: Path) -> Path:
    """备份原数据文件（concepts.json / metadata.db / traces.db / concept_graph.db）。"""
    backup_dir = data_dir / _BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    sources = [
        data_dir / "connectionist" / "concepts.json",
        data_dir / "metadata" / "metadata.db",
        data_dir / "connectionist" / "traces.db",
        data_dir / "concept_graph.db",
    ]
    for src in sources:
        if src.exists():
            shutil.copy2(src, backup_dir / src.name)
    return backup_dir


def _rollback(data_dir: Path) -> None:
    backup_dir = data_dir / _BACKUP_DIR
    if not backup_dir.exists():
        print("无备份目录，无法回滚")
        sys.exit(1)
    targets = {
        "concepts.json": data_dir / "connectionist" / "concepts.json",
        "metadata.db": data_dir / "metadata" / "metadata.db",
        "traces.db": data_dir / "connectionist" / "traces.db",
        "concept_graph.db": data_dir / "concept_graph.db",
    }
    restored = 0
    for filename, target in targets.items():
        src = backup_dir / filename
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            restored += 1
        elif target.exists():
            # 备份缺失 = 迁移产物（迁移前不存在）→ 删除
            target.unlink()
    manifest = data_dir / _MANIFEST
    if manifest.exists():
        manifest.unlink()
    print(f"已从备份恢复 {restored} 个文件（迁移产物已删除）")


def main() -> int:
    parser = argparse.ArgumentParser(description="存量数据迁移到统一 id")
    parser.add_argument("--data-dir", required=True, help="MaiBot data 目录")
    parser.add_argument("--rollback", action="store_true", help="从备份回滚")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        print(f"数据目录不存在: {data_dir}")
        return 1

    if args.rollback:
        _rollback(data_dir)
        return 0

    backup_dir = _backup(data_dir)
    print(f"已备份原数据到: {backup_dir}")

    concepts = _load_concepts(data_dir)
    entities = _load_entities(data_dir / "metadata" / "metadata.db")
    relations = _load_relations(data_dir / "metadata" / "metadata.db")
    traces = _load_traces(data_dir / "connectionist" / "traces.db")
    print(
        f"读取: 概念={len(concepts)} 实体={len(entities)} "
        f"关系={len(relations)} trace={len(traces)}"
    )

    gen = UnifiedIdGenerator()
    migrated = _load_manifest(data_dir)
    print(f"断点续传: 已迁移 {len(migrated)} 个概念")

    if args.dry_run:
        total_names = len(set(concepts) | set(entities))
        print(f"[dry-run] 将写入 {total_names} 个节点 / {len(relations)} 条关系 / {len(traces)} 条 trace")
        return 0

    store = ConceptGraphStore(data_dir)
    store.init_schema()
    try:
        # 1. 节点（概念 + 实体，同名同 id）
        now = time.time()
        node_ids: dict[str, str] = {}
        for name in sorted(set(concepts) | set(entities)):
            if name in migrated:
                continue
            node_id = gen.generate(name)
            node_ids[name] = node_id
            category = NodeCategory.CONCEPT
            if name in concepts and name in entities:
                category = NodeCategory.BOTH
            elif name in entities:
                category = NodeCategory.ENTITY
            store.upsert_node(create_node(node_id, name, category, now))
            migrated.add(name)
        # 断点保存
        _save_manifest(data_dir, migrated)
        print(f"节点写入完成: {len(node_ids)} 新增（累计 {len(migrated)}）")

        # 2. 关系边迁移（subject/object 名 → id）
        relation_count = 0
        for subject, predicate, obj, weight in relations:
            source_id = node_ids.get(subject) or gen.generate(subject)
            target_id = node_ids.get(obj) or gen.generate(obj)
            if source_id not in migrated and subject not in node_ids:
                node_ids[subject] = source_id
                migrated.add(subject)
            if target_id not in migrated and obj not in node_ids:
                node_ids[obj] = target_id
                migrated.add(obj)
            store.upsert_relation_edge(RelationEdge(
                id=f"rel:{source_id}:{target_id}:{predicate}",
                source_id=source_id,
                target_id=target_id,
                relation_type=predicate,
                weight=weight,
                schema_source=EdgeSource.TAXONOMY_PROJECTION,
                created_at=now,
            ))
            relation_count += 1
        print(f"关系边迁移: {relation_count}")

        # 3. Trace 迁移（source/target 概念名 → id，perspective=agent_id）
        trace_count = 0
        for source, target, weight, valence, agent_id in traces:
            source_id = node_ids.get(source) or gen.generate(source)
            target_id = node_ids.get(target) or gen.generate(target)
            store.upsert_trace_edge(TraceEdge(
                id=f"trace:{source_id}:{target_id}:{agent_id}",
                source_concept_id=source_id,
                target_concept_id=target_id,
                weight=weight,
                valence=valence,
                perspective=f"agent:{agent_id}" if agent_id else "migrated",
                last_activated_at=now,
                created_at=now,
            ))
            trace_count += 1
        print(f"Trace 迁移: {trace_count}")

        # 4. 迁移完成：丢弃临时 manifest
        manifest = data_dir / _MANIFEST
        if manifest.exists():
            manifest.unlink()
        print("迁移完成，临时 manifest 已丢弃")
        return 0
    finally:
        store.close()


def create_node(node_id: str, name: str, category: NodeCategory, now: float):
    from src.A_memorix.core.concept_graph.models import ConceptNode

    return ConceptNode(id=node_id, name=name, type=category, created_at=now, updated_at=now)


if __name__ == "__main__":
    sys.exit(main())
