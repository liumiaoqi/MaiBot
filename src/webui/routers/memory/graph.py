"""graph 端点（节点/边 CRUD + 详情）+ query/aggregate + timeline。"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from src.services.memory_service import MemorySearchResult, memory_service
from src.webui.dependencies import require_auth
from src.webui.errors import AppError
from src.webui.errors.codes import ErrorCode
from src.webui.schemas.base import ApiResponse
from src.webui.schemas.memory import (
    EdgeCreateRequest,
    EdgeDeleteRequest,
    EdgeWeightRequest,
    MemoryTimelineResponse,
    NodeRenameRequest,
    NodeRequest,
)
from src.webui.routers.memory_helpers import (
    _format_graph_paragraph,
    _format_memory_relation,
    _memory_timeline,
    _query_memory_rows,
    _safe_float,
    _trim_memory_text,
)

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# graph 辅助函数
# ---------------------------------------------------------------------------

async def _graph_get(limit: int) -> dict:
    return await memory_service.graph_admin(action="get_graph", limit=limit)

async def _graph_search(query: str, limit: int) -> dict:
    return await memory_service.graph_admin(action="search", query=query, limit=limit)

async def _graph_get_node_detail(
    node_id: str,
    *,
    relation_limit: int,
    paragraph_limit: int,
    evidence_node_limit: int,
) -> dict:
    payload = await memory_service.graph_admin(
        action="node_detail",
        node_id=node_id,
        relation_limit=relation_limit,
        paragraph_limit=paragraph_limit,
        evidence_node_limit=evidence_node_limit,
    )
    if not bool(payload.get("success", False)):
        raise AppError(ErrorCode.BIZ_NOT_FOUND, str(payload.get("error", "未找到节点详情")), http_status=404)
    return payload

async def _graph_get_edge_detail(
    source: str,
    target: str,
    *,
    paragraph_limit: int,
    evidence_node_limit: int,
) -> dict:
    payload = await memory_service.graph_admin(
        action="edge_detail",
        source=source,
        target=target,
        paragraph_limit=paragraph_limit,
        evidence_node_limit=evidence_node_limit,
    )
    if not bool(payload.get("success", False)):
        raise AppError(ErrorCode.BIZ_NOT_FOUND, str(payload.get("error", "未找到边详情")), http_status=404)
    return payload

async def _graph_get_paragraph_detail(paragraph_hash: str, evidence_node_limit: int) -> dict:
    token = str(paragraph_hash or "").strip()
    if not token:
        raise AppError(ErrorCode.PARAM_INVALID, "paragraph_hash 不能为空")
    rows = await _query_memory_rows(
        """
        SELECT hash, content, source, created_at, updated_at, metadata, is_deleted, deleted_at
        FROM paragraphs
        WHERE hash = ?
        LIMIT 1
        """,
        (token,),
    )
    if not rows:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"未找到段落: {token}", http_status=404)

    paragraph_row = dict(rows[0])
    if bool(int(paragraph_row.get("is_deleted") or 0)) or paragraph_row.get("deleted_at") is not None:
        raise AppError(ErrorCode.BIZ_NOT_FOUND, f"段落已删除: {token}", http_status=404)

    entity_rows = [
        dict(row)
        for row in await _query_memory_rows(
            """
            SELECT e.hash, e.name, pe.mention_count
            FROM paragraph_entities pe
            LEFT JOIN entities e ON e.hash = pe.entity_hash
            WHERE pe.paragraph_hash = ?
            ORDER BY COALESCE(pe.mention_count, 1) DESC, e.name ASC
            """,
            (token,),
        )
    ]
    relation_rows = [
        dict(row)
        for row in await _query_memory_rows(
            """
            SELECT r.hash, r.subject, r.predicate, r.object, r.confidence
            FROM paragraph_relations pr
            JOIN relations r ON r.hash = pr.relation_hash
            WHERE pr.paragraph_hash = ?
              AND (r.is_inactive IS NULL OR r.is_inactive = 0)
            ORDER BY r.confidence DESC, r.created_at DESC
            """,
            (token,),
        )
    ]
    entities = [str(row.get("name") or row.get("hash") or "").strip() for row in entity_rows]
    entities = [name for name in entities if name]
    paragraph = _format_graph_paragraph(paragraph_row, entities, relation_rows)

    nodes: list[dict[str, Any]] = [
        {
            "id": f"paragraph:{token}",
            "type": "paragraph",
            "content": str(paragraph_row.get("content")),
            "metadata": {
                "hash": token,
                "source": paragraph.get("source"),
                "updated_at": paragraph.get("updated_at"),
                "entity_count": len(entities),
                "relation_count": len(relation_rows),
                "preview": paragraph.get("preview"),
            },
        }
    ]
    edges: list[dict[str, Any]] = []
    node_ids = {f"paragraph:{token}"}

    for row in entity_rows:
        entity_name = str(row.get("name") or row.get("hash") or "").strip()
        if not entity_name:
            continue
        node_id = f"entity:{entity_name}"
        if node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append({"id": node_id, "type": "entity", "content": entity_name, "metadata": {"entity_name": entity_name}})
        mention_count = int(row.get("mention_count") or 1)
        edges.append(
            {
                "source": f"paragraph:{token}",
                "target": node_id,
                "kind": "mentions",
                "label": f"提及 ×{mention_count}" if mention_count > 1 else "提及",
                "weight": float(max(1, mention_count)),
            }
        )

    for row in relation_rows:
        relation_hash = str(row.get("hash")).strip()
        if not relation_hash:
            continue
        relation_node_id = f"relation:{relation_hash}"
        relation_text = _format_memory_relation(row.get("subject"), row.get("predicate"), row.get("object"))
        if relation_node_id not in node_ids:
            node_ids.add(relation_node_id)
            nodes.append(
                {
                    "id": relation_node_id,
                    "type": "relation",
                    "content": relation_text,
                    "metadata": {
                        "hash": relation_hash,
                        "subject": str(row.get("subject")).strip(),
                        "predicate": str(row.get("predicate")).strip(),
                        "object": str(row.get("object")).strip(),
                        "confidence": float(row.get("confidence") or 0.0),
                        "paragraph_count": 1,
                        "paragraph_hashes": [token],
                        "text": relation_text,
                    },
                }
            )
        edges.append({"source": f"paragraph:{token}", "target": relation_node_id, "kind": "supports", "label": "支撑", "weight": 1.0})

    if len(nodes) > evidence_node_limit:
        kept_ids = {node["id"] for node in nodes[:evidence_node_limit]}
        nodes = [node for node in nodes if node["id"] in kept_ids]
        edges = [edge for edge in edges if edge["source"] in kept_ids and edge["target"] in kept_ids]

    return {
        "success": True,
        "paragraph": paragraph,
        "evidence_graph": {
            "nodes": nodes,
            "edges": edges,
            "focus_entities": entities,
        },
    }

async def _graph_create_node(payload: NodeRequest) -> dict:
    return await memory_service.graph_admin(action="create_node", name=payload.name)

async def _graph_delete_node(payload: NodeRequest) -> dict:
    return await memory_service.graph_admin(action="delete_node", name=payload.name)

async def _graph_rename_node(payload: NodeRenameRequest) -> dict:
    return await memory_service.graph_admin(action="rename_node", old_name=payload.old_name, new_name=payload.new_name)

async def _graph_create_edge(payload: EdgeCreateRequest) -> dict:
    return await memory_service.graph_admin(
        action="create_edge",
        subject=payload.subject,
        predicate=payload.predicate,
        object=payload.object,
        confidence=payload.confidence,
    )

async def _graph_delete_edge(payload: EdgeDeleteRequest) -> dict:
    return await memory_service.graph_admin(
        action="delete_edge",
        hash=payload.hash,
        subject=payload.subject,
        object=payload.object,
    )

async def _graph_update_edge_weight(payload: EdgeWeightRequest) -> dict:
    return await memory_service.graph_admin(
        action="update_edge_weight",
        hash=payload.hash,
        subject=payload.subject,
        object=payload.object,
        weight=payload.weight,
    )

async def _query_aggregate(
    query: str,
    *,
    limit: int,
    chat_id: str,
    person_id: str,
    time_start: float | None,
    time_end: float | None,
) -> dict:
    result: MemorySearchResult = await memory_service.search(
        query,
        limit=limit,
        mode="aggregate",
        chat_id=chat_id,
        person_id=person_id,
        time_start=time_start,
        time_end=time_end,
        respect_filter=False,
    )
    return {"success": True, **result.to_dict()}


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/graph")
async def get_memory_graph(limit: int = Query(200, ge=1, le=5000)):
    return await _graph_get(limit)

@router.get("/graph/search")
async def search_memory_graph(
    query: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
):
    return await _graph_search(query, limit)

@router.get("/graph/node-detail")
async def get_memory_graph_node_detail(
    node_id: str = Query(..., min_length=1),
    relation_limit: int = Query(20, ge=1, le=100),
    paragraph_limit: int = Query(20, ge=1, le=100),
    evidence_node_limit: int = Query(80, ge=12, le=200),
):
    return await _graph_get_node_detail(
        node_id,
        relation_limit=relation_limit,
        paragraph_limit=paragraph_limit,
        evidence_node_limit=evidence_node_limit,
    )

@router.get("/graph/edge-detail")
async def get_memory_graph_edge_detail(
    source: str = Query(..., min_length=1),
    target: str = Query(..., min_length=1),
    paragraph_limit: int = Query(20, ge=1, le=100),
    evidence_node_limit: int = Query(80, ge=12, le=200),
):
    return await _graph_get_edge_detail(
        source,
        target,
        paragraph_limit=paragraph_limit,
        evidence_node_limit=evidence_node_limit,
    )

@router.get("/graph/paragraph-detail")
async def get_memory_graph_paragraph_detail(
    paragraph_hash: str = Query(..., min_length=1),
    evidence_node_limit: int = Query(80, ge=12, le=200),
):
    return await _graph_get_paragraph_detail(paragraph_hash, evidence_node_limit)

@router.post("/graph/node")
async def create_memory_node(payload: NodeRequest):
    return await _graph_create_node(payload)

@router.delete("/graph/node")
async def delete_memory_node(payload: NodeRequest):
    return await _graph_delete_node(payload)

@router.post("/graph/node/rename")
async def rename_memory_node(payload: NodeRenameRequest):
    return await _graph_rename_node(payload)

@router.post("/graph/edge")
async def create_memory_edge(payload: EdgeCreateRequest):
    return await _graph_create_edge(payload)

@router.delete("/graph/edge")
async def delete_memory_edge(payload: EdgeDeleteRequest):
    return await _graph_delete_edge(payload)

@router.post("/graph/edge/weight")
async def update_memory_edge_weight(payload: EdgeWeightRequest):
    return await _graph_update_edge_weight(payload)

@router.get("/query/aggregate")
async def query_memory_aggregate(
    query: str = Query(""),
    limit: int = Query(20, ge=1, le=200),
    chat_id: str = Query(""),
    person_id: str = Query(""),
    time_start: float | None = Query(None),
    time_end: float | None = Query(None),
):
    return await _query_aggregate(
        query,
        limit=limit,
        chat_id=chat_id,
        person_id=person_id,
        time_start=time_start,
        time_end=time_end,
    )

@router.get("/timeline", response_model=ApiResponse[MemoryTimelineResponse])
async def get_memory_timeline(
    chat_id: str = Query(..., min_length=1),
    time_start: float | None = Query(None),
    time_end: float | None = Query(None),
    types: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
):
    return ApiResponse(data=await _memory_timeline(
        chat_id=chat_id,
        time_start=time_start,
        time_end=time_end,
        types=types,
        limit=limit,
    ))