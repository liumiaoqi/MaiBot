/**
 * graph-transform —— 记忆图谱数据纯转换函数（R3 遗留 D6：P2-B 从 knowledge-graph.tsx 迁出）。
 *
 * 只放「后端 payload → 前端 GraphData / 详情合并」的纯函数，不依赖 React；
 * 页面状态与交互下沉到 hooks/use-graph-explorer.ts 与 hooks/use-graph-delete.ts。
 */
import type {
  MemoryEvidenceGraphPayload,
  MemoryEvidenceParagraphNodeMetadata,
  MemoryEvidenceRelationNodeMetadata,
  MemoryGraphEdgeDetailPayload,
  MemoryGraphNodeDetailPayload,
  MemoryGraphParagraphDetailPayload,
  MemoryGraphPayload,
  MemoryGraphRelationDetailPayload,
} from '@/lib/memory-api'

import type { GraphData, GraphNode } from './types/graph-types'

/** 实体关系图 payload → 前端 GraphData（实体节点 + 聚合边） */
export function toEntityGraphData(payload: MemoryGraphPayload): GraphData {
  const nodes: GraphNode[] = (payload.nodes ?? []).map((node) => ({
    id: node.id,
    type: 'entity',
    content: String(node.name ?? node.id),
    metadata: node.attributes ?? {},
  }))
  const edges = (payload.edges ?? []).map((edge) => ({
    source: edge.source,
    target: edge.target,
    weight: Number(edge.weight ?? 1),
    kind: 'relation' as const,
    label: String(edge.label ?? ''),
    relationHashes: edge.relation_hashes ?? [],
    predicates: edge.predicates ?? [],
    relationCount: Number(edge.relation_count ?? edge.relation_hashes?.length ?? 0),
    evidenceCount: Number(edge.evidence_count ?? 0),
  }))
  return { nodes, edges }
}

/** 证据图 payload → 前端 GraphData（paragraph → relation/entity 牵引） */
export function toEvidenceGraphData(payload: MemoryEvidenceGraphPayload | null | undefined): GraphData {
  return {
    nodes: (payload?.nodes ?? []).map((node) => ({
      id: node.id,
      type: node.type,
      content: node.content,
      metadata: node.metadata ?? {},
    })),
    edges: (payload?.edges ?? []).map((edge) => ({
      source: edge.source,
      target: edge.target,
      weight: Number(edge.weight ?? 1),
      kind: edge.kind,
      label: edge.label,
    })),
    focusEntities: payload?.focus_entities ?? [],
  }
}

/** 按关键词过滤图谱（节点内容/id/边 label/predicate 命中） */
export function filterGraphData(graph: GraphData, query: string): GraphData {
  const keyword = query.trim().toLowerCase()
  if (!keyword) {
    return graph
  }

  const matchedNodeIds = new Set(
    graph.nodes
      .filter((node) => node.content.toLowerCase().includes(keyword) || node.id.toLowerCase().includes(keyword))
      .map((node) => node.id),
  )

  const edges = graph.edges.filter((edge) => {
    const label = String(edge.label ?? '').toLowerCase()
    const predicateMatched = (edge.predicates ?? []).some((predicate) => predicate.toLowerCase().includes(keyword))
    const matched =
      matchedNodeIds.has(edge.source) ||
      matchedNodeIds.has(edge.target) ||
      label.includes(keyword) ||
      predicateMatched
    if (matched) {
      matchedNodeIds.add(edge.source)
      matchedNodeIds.add(edge.target)
    }
    return matched
  })

  return {
    nodes: graph.nodes.filter((node) => matchedNodeIds.has(node.id)),
    edges,
    focusEntities: graph.focusEntities,
  }
}

/** 合并节点详情与边详情里的关系列表（按 hash 去重） */
export function mergeUniqueRelations(
  nodeDetail: MemoryGraphNodeDetailPayload | null,
  edgeDetail: MemoryGraphEdgeDetailPayload | null,
): MemoryGraphRelationDetailPayload[] {
  const seen = new Set<string>()
  const items: MemoryGraphRelationDetailPayload[] = []
  for (const relation of [...(nodeDetail?.relations ?? []), ...(edgeDetail?.relations ?? [])]) {
    if (seen.has(relation.hash)) {
      continue
    }
    seen.add(relation.hash)
    items.push(relation)
  }
  return items
}

/** 合并节点详情与边详情里的段落列表（按 hash 去重） */
export function mergeUniqueParagraphs(
  nodeDetail: MemoryGraphNodeDetailPayload | null,
  edgeDetail: MemoryGraphEdgeDetailPayload | null,
): MemoryGraphParagraphDetailPayload[] {
  const seen = new Set<string>()
  const items: MemoryGraphParagraphDetailPayload[] = []
  for (const paragraph of [...(nodeDetail?.paragraphs ?? []), ...(edgeDetail?.paragraphs ?? [])]) {
    if (seen.has(paragraph.hash)) {
      continue
    }
    seen.add(paragraph.hash)
    items.push(paragraph)
  }
  return items
}

/** 证据图关系节点 metadata → 关系详情 payload（无 hash 返回 null） */
export function buildRelationFromMetadata(
  metadata: MemoryEvidenceRelationNodeMetadata | null | undefined,
): MemoryGraphRelationDetailPayload | null {
  const hash = String(metadata?.hash ?? '').trim()
  if (!hash) {
    return null
  }
  const subject = String(metadata?.subject ?? '').trim()
  const predicate = String(metadata?.predicate ?? '').trim()
  const object = String(metadata?.object ?? '').trim()
  const text = String(metadata?.text ?? `${subject} ${predicate} ${object}`).trim()
  return {
    hash,
    subject,
    predicate,
    object,
    text,
    confidence: Number(metadata?.confidence ?? 0),
    paragraph_count: Number(metadata?.paragraph_count ?? 0),
    paragraph_hashes: Array.isArray(metadata?.paragraph_hashes) ? metadata.paragraph_hashes.map(String) : [],
    source_paragraph: '',
  }
}

/** 证据图段落节点 metadata → 段落详情 payload（无 hash 返回 null） */
export function buildParagraphFromMetadata(
  metadata: MemoryEvidenceParagraphNodeMetadata | null | undefined,
): MemoryGraphParagraphDetailPayload | null {
  const hash = String(metadata?.hash ?? '').trim()
  if (!hash) {
    return null
  }
  const preview = String(metadata?.preview ?? '').trim()
  return {
    hash,
    content: preview,
    preview,
    source: String(metadata?.source ?? '').trim(),
    updated_at: typeof metadata?.updated_at === 'number' ? metadata.updated_at : null,
    entity_count: Number(metadata?.entity_count ?? 0),
    relation_count: Number(metadata?.relation_count ?? 0),
    entities: [],
    relations: [],
  }
}
